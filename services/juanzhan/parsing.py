"""Archive-owned parse history and fenced publication. Never mutates business fields."""
from contextlib import contextmanager
from io import BytesIO
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import uuid

from .conversion_models import Options
from .converter_client import ConverterClient, ConverterClientError
from .database import connect
from .document_events import utc_now
from .jobs import JobQueue, LostLease
from .source_paths import SourceMounts, SourcePathError
from .storage import ManagedStore, IntegrityError, parse_key

MAX_RESULT=16*1024*1024

class ParseFailure(Exception):
    def __init__(self,code,retryable=False):
        self.code,self.retryable=code,retryable
        super().__init__(code)


def dumps(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def requested(db,job):
    if job['kind'] not in ('parse','ocr') or job['target_type']!='document':return
    payload=json.loads(job['payload_json'])
    revision=payload.get('revision_id')
    if db.execute('SELECT 1 FROM file_revisions WHERE id=? AND document_id=?',(revision,job['target_id'])).fetchone():
        db.execute('INSERT OR IGNORE INTO parse_requests(job_id,document_id,revision_id) VALUES (?,?,?)',
                   (job['id'],job['target_id'],revision))


def failed(db,job,code):
    if job['kind'] not in ('parse','ocr') or job['target_type']!='document':return
    db.execute("UPDATE parse_runs SET status='failed',completed_at=?,error_json=? WHERE status='running' AND id IN "
               '(SELECT a.parse_run_id FROM parse_attempts a JOIN parse_requests q ON q.sequence=a.request_sequence '
               'WHERE q.job_id=? AND a.attempt=?)',
               (utc_now(),dumps({'code':code,'message':'Parse attempt did not complete'}),job['id'],job['attempts']))


def begin(settings,job):
    payload=json.loads(job['payload_json'])
    if set(payload)-{'revision_id','ocr_enabled','ocr_languages','generate_preview'} or 'revision_id' not in payload:
        raise ParseFailure('INVALID_JOB_PAYLOAD')
    try:
        options=Options(file_revision_id=payload['revision_id'],parse_run_id=uuid.uuid4().hex,
            ocr_enabled=payload.get('ocr_enabled',job['kind']=='ocr'),
            ocr_languages=payload.get('ocr_languages',''),generate_preview=payload.get('generate_preview',True))
    except ValueError:raise ParseFailure('INVALID_JOB_PAYLOAD') from None
    queue=JobQueue(settings)
    with queue.write() as db:
        db.row_factory=sqlite3.Row
        owned=queue._owned(db,job['id'],job['lease_token'])
        requested(db,owned)
        request=db.execute('SELECT * FROM parse_requests WHERE job_id=?',(job['id'],)).fetchone()
        if request is None:raise ParseFailure('PARSE_REVISION_UNAVAILABLE')
        doc=db.execute('SELECT * FROM documents WHERE id=?',(request['document_id'],)).fetchone()
        if doc['deleted_at'] is not None or doc['current_revision_id']!=request['revision_id']:
            raise ParseFailure('PARSE_SUPERSEDED')
        # Only the automatic first parse is a fallback. Explicit reparse/OCR stays available.
        if job['kind']=='parse' and owned['idempotency_key']=='parse:'+request['revision_id'] and db.execute(
            'SELECT 1 FROM agent_analyses a JOIN agent_imports i ON i.id=a.import_id '
            'WHERE i.document_id=? AND i.revision_id=? LIMIT 1',
            (doc['id'],request['revision_id'])).fetchone():
            return None, None
        previous=db.execute('SELECT parse_run_id FROM parse_attempts WHERE request_sequence=? AND attempt=?',
                            (request['sequence'],job['attempts'])).fetchone()
        if previous:raise ParseFailure('PARSE_ATTEMPT_ALREADY_STARTED')
        timestamp=utc_now()
        db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,started_at,created_at) "
                   "VALUES (?,?,?,'pending','pending','1.0','running',?,?)",
                   (options.parse_run_id,doc['id'],request['revision_id'],timestamp,timestamp))
        db.execute('INSERT INTO parse_attempts(parse_run_id,request_sequence,attempt) VALUES (?,?,?)',
                   (options.parse_run_id,request['sequence'],job['attempts']))
        from .derived import schedule_gc
        schedule_gc(db,settings,'parse-gc:'+job['id']+':'+str(job['attempts']),time.time()+86400)
        revision=dict(db.execute('SELECT * FROM file_revisions WHERE id=?',(request['revision_id'],)).fetchone())
        options=options.model_copy(update={'declared_mime':revision['mime_type']})
        return options,revision


@contextmanager
def original(settings,revision,max_bytes,*,allow_snapshot=True):
    if revision['size_bytes']>max_bytes:raise ParseFailure('CONVERTER_INPUT_LIMIT')
    if allow_snapshot and revision['storage_kind']=='external':
        from .source_snapshots import stored
        with connect(settings.database) as db:
            obj=stored(db,revision['id'])
        if obj:
            if (obj[1],obj[2])!=(revision['sha256'],revision['size_bytes']):raise ParseFailure('ORIGINAL_INTEGRITY')
            try:
                with ManagedStore(settings.data_dir/'managed').open(obj[0]) as file:yield file
            except IntegrityError:raise ParseFailure('ORIGINAL_INTEGRITY') from None
            return
    if revision['storage_kind']=='managed':
        with connect(settings.database) as db:
            obj=db.execute('SELECT storage_key FROM managed_objects WHERE id=?',(revision['managed_object_id'],)).fetchone()
        if not obj or parse_key(obj[0])!=(revision['sha256'],revision['size_bytes']):raise ParseFailure('ORIGINAL_INTEGRITY')
        try:
            with ManagedStore(settings.data_dir/'managed').open(obj[0]) as file:yield file
        except IntegrityError:raise ParseFailure('ORIGINAL_INTEGRITY') from None
    else:
        with connect(settings.database) as db:
            source=db.execute('SELECT s.root_ref,s.status,e.relative_path_norm FROM source_entries e JOIN sources s ON s.id=e.source_id '
                              'WHERE e.id=?',(revision['source_entry_id'],)).fetchone()
        if not source or source[1]=='disabled':raise ParseFailure('SOURCE_OFFLINE',True)
        # Pin current bytes in Archive-private temporary storage. Size/mtime are not proof.
        with SourceMounts(settings.source_mounts).open(source[0],source[2]) as file, tempfile.TemporaryFile(dir=settings.data_dir) as copy:
            before=os.fstat(file.fileno());digest=hashlib.sha256();size=0
            while chunk:=file.read(min(65536,max_bytes-size+1)):
                size+=len(chunk)
                if size>max_bytes:raise ParseFailure('CONVERTER_INPUT_LIMIT')
                digest.update(chunk);copy.write(chunk)
            after=os.fstat(file.fileno())
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise ParseFailure('SOURCE_CHANGED',True)
            if size!=revision['size_bytes'] or digest.hexdigest()!=revision['sha256']:raise ParseFailure('SOURCE_REVISION_CHANGED')
            copy.seek(0);yield copy


def publish(db,job,options,result,assets):
    db.row_factory=sqlite3.Row
    request=db.execute('SELECT * FROM parse_requests WHERE job_id=?',(job['id'],)).fetchone()
    run=db.execute('SELECT status FROM parse_runs WHERE id=?',(options.parse_run_id,)).fetchone()
    if request is None or run is None or run['status']!='running':raise LostLease('Parse attempt is no longer active')
    doc=db.execute('SELECT * FROM documents WHERE id=?',(request['document_id'],)).fetchone()
    newest=db.execute('SELECT max(sequence) FROM parse_requests WHERE document_id=? AND revision_id=?',
                      (request['document_id'],request['revision_id'])).fetchone()[0]
    if doc['deleted_at'] is not None or doc['current_revision_id']!=request['revision_id'] or newest!=request['sequence']:
        failed(db,job,'PARSE_SUPERSEDED')
        return {'parse_run_id':options.parse_run_id,'status':'discarded','reason':'PARSE_SUPERSEDED'}
    extraction=result['extraction'];status=result['status'];timestamp=utc_now()
    db.execute('UPDATE parse_runs SET parser_name=?,parser_version=?,schema_version=?,status=?,text_available=?,ocr_used=?,'
               'language=?,page_count=?,completed_at=?,warnings_json=? WHERE id=?',
               (result['parser']['name'],result['parser']['version'],result['schema_version'],status,int(extraction['text_available']),
                int(extraction['ocr_used']),result.get('language'),result.get('page_count'),timestamp,dumps(result['warnings']),options.parse_run_id))
    if status=='completed':
        for block in result['blocks']:
            structure={key:value for key,value in block.items() if key in ('level','table')}
            db.execute('INSERT INTO content_blocks VALUES (?,?,?,?,?,?,?,?,?)',
                (uuid.uuid4().hex,options.parse_run_id,block['id'],block['index'],block['type'],block['text'],
                 dumps(structure),dumps(block['locator']),block.get('confidence')))
        for candidate in result['metadata_candidates']:
            provenance={key:value for key,value in candidate.items() if key in ('source','locator')}
            db.execute('INSERT INTO extracted_metadata VALUES (?,?,?,?,?,?)',
                (uuid.uuid4().hex,options.parse_run_id,candidate['key'],dumps(candidate['value']),dumps(provenance),candidate.get('confidence')))
        for index,(kind,media,obj,source_ref) in enumerate(assets):
            existing=db.execute('SELECT id FROM derived_assets WHERE parse_run_id=? AND asset_kind=? AND storage_key=?',
                                (options.parse_run_id,kind,obj.storage_key)).fetchone()
            asset_id=existing[0] if existing else uuid.uuid4().hex
            if not existing:
                db.execute('INSERT INTO derived_assets VALUES (?,?,?,?,?,?,?,?)',
                           (asset_id,options.parse_run_id,kind,obj.storage_key,obj.sha256,obj.size_bytes,media,timestamp))
            db.execute('INSERT INTO parse_asset_order VALUES (?,?,?,?)',(options.parse_run_id,index,asset_id,source_ref))
            db.execute('DELETE FROM derived_gc_candidates WHERE storage_key=?',(obj.storage_key,))
        db.execute('UPDATE documents SET current_parse_run_id=? WHERE id=?',(options.parse_run_id,request['document_id']))
        from .tagging import apply
        apply(db,request['document_id'],request['revision_id'],text='\n'.join(block['text'] for block in result['blocks'])[:50000])
    return {'parse_run_id':options.parse_run_id,'revision_id':request['revision_id'],'status':status,
            'text_available':extraction['text_available'],'ocr_used':extraction['ocr_used']}


def execute(settings,job,client=None):
    queue=JobQueue(settings)
    options,revision=begin(settings,job)
    if options is None:
        queue.complete(job['id'],job['lease_token'],{'status':'skipped','reason':'AGENT_ANALYSIS_AVAILABLE'})
        return
    from .source_snapshots import ensure
    remote=None
    try:client=client or ConverterClient(os.getenv('CONVERTER_URL','http://converter:8000'),settings.converter_token)
    except ValueError:raise ParseFailure('CONVERTER_NOT_CONFIGURED') from None
    store=ManagedStore(settings.data_dir/'derived');store.initialize()
    try:
        ensure(settings,revision,job)
        with original(settings,revision,client.max_file_bytes) as file:
            queue.step(job['id'],job['lease_token'],'submit')
            remote=client.submit(file,options)['job_id']
        with JobQueue(settings).write() as db:
            JobQueue(settings)._owned(db,job['id'],job['lease_token'])
            db.execute('UPDATE parse_attempts SET remote_job_id=? WHERE parse_run_id=?',(remote,options.parse_run_id))
        queue.step(job['id'],job['lease_token'],'extract')
        terminal=client.wait(remote,deadline_seconds=min(45,job['timeout_seconds']))
        if terminal['status']!='completed':
            code=(terminal.get('error') or {}).get('error',{}).get('code')
            raise ParseFailure(code if code in ('CONVERTER_RESTARTED','CONVERSION_TIMEOUT','PDF_PASSWORD_REQUIRED','INVALID_DOCUMENT','RESULT_LIMIT','IMAGE_PIXEL_LIMIT','OCR_PAGE_LIMIT') else 'CONVERSION_FAILED',code in ('CONVERTER_RESTARTED','CONVERTER_PUBLISH_FAILED'))
        result=client.result(remote,file_revision_id=revision['id'],parse_run_id=options.parse_run_id)
        if result['status']=='failed':raise ParseFailure('CONVERSION_FAILED')
        assets=[]
        queue.step(job['id'],job['lease_token'],'assets',0,len(result['artifacts'])+1 if result['status']=='completed' else 0)
        if result['status']=='completed':
            total=sum(a['size_bytes'] for a in result['artifacts'])
            raw=dumps(result).encode()
            if total>MAX_RESULT or len(raw)>MAX_RESULT:raise ParseFailure('CONVERTER_RESULT_LIMIT')
            # Shared store lock spans publication and DB registration; GC takes exclusive first.
            with store.locked():
                for asset in result['artifacts']:
                    with client.artifact(asset) as file:
                        obj=store.put(file,max_bytes=MAX_RESULT,expected_sha256=asset['sha256'],expected_size=asset['size_bytes'])
                    assets.append((asset['kind'],asset['media_type'],obj,asset['artifact_ref']))
                    queue.step(job['id'],job['lease_token'],'assets',len(assets),len(result['artifacts'])+1)
                # Keep the complete normalized result, including provenance and OCR languages.
                obj=store.put(BytesIO(raw),max_bytes=MAX_RESULT)
                assets.append(('json','application/json',obj,None))
                queue.step(job['id'],job['lease_token'],'assets',len(assets),len(result['artifacts'])+1)
                queue.step(job['id'],job['lease_token'],'publish')
                JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,options,result,assets))
        else:
            queue.step(job['id'],job['lease_token'],'publish')
            JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,options,result,[]))
    except ConverterClientError as exc:
        raise ParseFailure(exc.code,exc.code in ('CONVERTER_UNAVAILABLE','CONVERTER_WAIT_TIMEOUT') or exc.status in (404,408,409,429,500,502,503,504)) from None
    except SourcePathError as exc:
        raise ParseFailure(exc.code,exc.code in ('SOURCE_OFFLINE','SOURCE_CHANGED','SOURCE_FILE_MISSING')) from None
    except IntegrityError:
        raise ParseFailure('DERIVED_INTEGRITY') from None
    finally:
        if remote:
            try:client.delete(remote)
            except ConverterClientError:pass  # Active/crashed requests remain bounded by Converter wall limit + TTL.
