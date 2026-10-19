"""Explicit, byte-verified resolution of unlinked ambiguous source entries."""
import json
import sqlite3

from fastapi import APIRouter,Query,Request
from pydantic import Field,model_validator

from .auth import fail
from .catalog import Input,ID,required,same_space,transaction
from .database import connect
from .document_events import record_event,utc_now
from .document_records import expected,snapshot
from .documents import Version
from .exclusions import blocked,bump
from .jobs import JobQueue,JobSpec
from .parsing import original
from .source_initial import register_external
from .source_paths import SourceMounts,SourcePathError
from .uploads import sniff

MAX_BYTES=1024*1024*1024


class Resolve(Input):
    action: str=Field(pattern=r'^(match|new_document)$')
    expected_entry_updated_at: str=Field(min_length=1,max_length=64)
    request_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    document_id: ID | None=None
    expected_document_version: Version | None=None
    expected_revision_id: ID | None=None

    @model_validator(mode='after')
    def target(self):
        values=(self.document_id,self.expected_document_version,self.expected_revision_id)
        if self.action=='match' and any(v is None for v in values):raise ValueError('Choose an exact document version')
        if self.action=='new_document' and any(v is not None for v in values):raise ValueError('New registration cannot replace a document')
        return self


def incoming(db,source_id,entry_id,updated_at=None):
    source=required(db,'sources',source_id);entry=required(db,'source_entries',entry_id)
    if entry['source_id']!=source_id:fail(422,'CROSS_SOURCE_REFERENCE','Entry belongs to another source')
    if source['kind']!='external' or source['status']=='disabled' or not source['initial_import_completed_at']:
        fail(409,'SOURCE_DISABLED','Complete the initial import before resolving entries')
    if entry['document_id'] is not None or entry['status']!='needs_match':
        fail(409,'SOURCE_ENTRY_RESOLVED','Choose an unlinked ambiguous entry')
    if updated_at is not None and entry['updated_at']!=updated_at:
        fail(409,'SOURCE_CHANGED','Entry changed; reload the candidates')
    if not entry['sha256'] or not entry['last_seen_scan_id']:
        fail(409,'SOURCE_ENTRY_UNVERIFIED','A successful source observation is required')
    return dict(source),dict(entry)


def chosen(db,source,entry,payload):
    doc=expected(db,payload['document_id'],payload['expected_document_version'])
    if doc['space_id']!=source['space_id']:fail(422,'CROSS_SPACE_REFERENCE','Document belongs to another space')
    if doc['deleted_at'] is not None:fail(409,'DOCUMENT_TRASHED','Restore the document first')
    if doc['current_revision_id']!=payload['expected_revision_id']:fail(409,'REVISION_CONFLICT','Original changed; reload')
    rev=required(db,'file_revisions',doc['current_revision_id'])
    if rev['storage_kind']!='external':fail(409,'EXTERNAL_REVISION_REQUIRED','Choose an external original')
    old=required(db,'source_entries',rev['source_entry_id'])
    if old['source_id']!=source['id'] or old['id']==entry['id'] or old['document_id']!=doc['id']:
        fail(422,'CROSS_SOURCE_REFERENCE','Choose a linked entry from this source')
    if old['status'] not in ('needs_match','suspected_missing','missing'):
        fail(409,'SOURCE_MATCH_INVALID','Previous entry is no longer awaiting a match')
    if (rev['sha256'],rev['size_bytes'])!=(entry['sha256'],entry['size_bytes']):
        fail(409,'SOURCE_MATCH_INVALID','Only the same verified original bytes may be reassociated')
    if blocked(db,source['id'],old['relative_path_norm']):
        fail(409,'SOURCE_ENTRY_BUSY','Previous entry has an exclusion or pending operation')
    return doc,dict(old)


def missing_previous(mounts,source,old):
    try:
        with mounts.open(source['root_ref'],old['relative_path_norm']):
            fail(409,'SOURCE_MATCH_OLD_PRESENT','Previous path still exists; do not replace its association')
    except SourcePathError as exc:
        if exc.code!='SOURCE_FILE_MISSING':raise


def router(settings):
    routes=APIRouter(prefix='/api/v1/sources');queue=JobQueue(settings)

    @routes.get('/{id}/entries/{entry_id}/matches')
    def candidates(id:str,entry_id:str,page:int=Query(default=1,ge=1,le=1000000),page_size:int=Query(default=20,ge=1,le=100)):
        with transaction(settings) as db:
            source,entry=incoming(db,id,entry_id)
            sql=(' FROM source_entries e JOIN documents d ON d.id=e.document_id JOIN file_revisions r ON r.id=d.current_revision_id '
                "WHERE e.source_id=? AND e.id!=? AND e.status IN ('needs_match','suspected_missing','missing') "
                "AND d.deleted_at IS NULL AND r.storage_kind='external' AND r.source_entry_id=e.id AND r.sha256=? AND r.size_bytes=? "
                'AND NOT EXISTS(SELECT 1 FROM source_exclusions x WHERE x.source_id=e.source_id AND x.relative_path_norm=e.relative_path_norm) '
                'AND NOT EXISTS(SELECT 1 FROM source_exclusion_intents x WHERE x.source_id=e.source_id AND x.relative_path_norm=e.relative_path_norm)')
            params=(id,entry_id,entry['sha256'],entry['size_bytes'])
            total=db.execute('SELECT count(*)'+sql,params).fetchone()[0]
            rows=db.execute('SELECT d.id AS document_id,d.title,d.document_version,r.id AS revision_id,e.relative_path_display AS previous_path'+sql+
                ' ORDER BY e.relative_path_norm,e.id LIMIT ? OFFSET ?',(*params,page_size,(page-1)*page_size)).fetchall()
            return {'entry':{k:entry[k] for k in ('id','relative_path_display','sha256','size_bytes','updated_at')},
                'items':[dict(r) for r in rows],'page':page,'page_size':page_size,'total':total}

    @routes.post('/{id}/entries/{entry_id}/resolve',status_code=202)
    def submit(id:str,entry_id:str,body:Resolve,request:Request):
        payload=body.model_dump();key='resolve:'+entry_id+':'+body.request_id
        with transaction(settings,request) as db:
            previous=db.execute('SELECT id,status,payload_json FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
            if previous:
                old=json.loads(previous['payload_json'])
                if old.get('source_id')!=id or any(old.get(k)!=v for k,v in payload.items()):
                    fail(409,'IDEMPOTENCY_CONFLICT','Request ID was used with different resolution parameters')
                return {'job_id':previous['id'],'status':previous['status']}
            source,entry=incoming(db,id,entry_id,body.expected_entry_updated_at)
            if blocked(db,id,entry['relative_path_norm']):fail(409,'SOURCE_ENTRY_BUSY','Entry has a pending operation or exclusion')
            if entry['size_bytes']>MAX_BYTES:fail(413,'SOURCE_MATCH_LIMIT','Original exceeds the verification limit')
            if body.action=='match':chosen(db,source,entry,payload)
            payload.update(source_id=id,entry_id=entry_id,path=entry['relative_path_norm'],sha256=entry['sha256'],size_bytes=entry['size_bytes'])
            job=queue.enqueue(JobSpec(kind='batch',target_type='document_match' if body.action=='match' else 'source_entry_register',
                target_id=body.document_id if body.action=='match' else entry_id,payload=payload,idempotency_key=key,timeout_seconds=300),db=db)
            db.execute('INSERT INTO source_exclusion_intents VALUES (?,?,?,?)',(job['id'],entry_id,id,entry['relative_path_norm']))
            bump(db,id)
            return {'job_id':job['id'],'status':job['status']}
    return routes


def execute(settings,job):
    payload=json.loads(job['payload_json']);queue=JobQueue(settings)
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        source,entry=incoming(db,payload['source_id'],payload['entry_id'],payload['expected_entry_updated_at'])
        old=chosen(db,source,entry,payload)[1] if payload['action']=='match' else None
        baseline=db.execute('SELECT root_digest FROM source_root_baselines WHERE source_id=?',(source['id'],)).fetchone()
    mounts=SourceMounts(settings.source_mounts)
    if not baseline or mounts.digest(source['root_ref'])!=baseline[0]:raise SourcePathError('SOURCE_ROOT_CHANGED')
    if old:missing_previous(mounts,source,old)
    revision={'storage_kind':'external','source_entry_id':entry['id'],'sha256':payload['sha256'],'size_bytes':payload['size_bytes']}
    with original(settings,revision,MAX_BYTES) as file:
        mime=sniff(file,entry['relative_path_norm'].rsplit('/',1)[-1])
        def publish(db,owned):
            db.row_factory=sqlite3.Row
            current,observed=incoming(db,source['id'],entry['id'],payload['expected_entry_updated_at'])
            if current['root_ref']!=source['root_ref'] or observed!=entry or mounts.digest(current['root_ref'])!=baseline[0]:
                fail(409,'SOURCE_CHANGED','Source registration changed during verification')
            intent=db.execute('SELECT 1 FROM source_exclusion_intents WHERE job_id=? AND source_entry_id=?',(job['id'],entry['id'])).fetchone()
            if not intent:fail(409,'SOURCE_CHANGED','Resolution barrier no longer exists')
            timestamp=utc_now()
            if payload['action']=='match':
                before,linked=chosen(db,current,observed,payload)
                if linked!=old:fail(409,'SOURCE_CHANGED','Previous entry changed during verification')
                missing_previous(mounts,current,linked)
                before['source_entry']={k:linked[k] for k in ('id','relative_path_norm','status','sha256')}
                db.execute('DELETE FROM source_entries WHERE id=?',(entry['id'],))
                db.execute("UPDATE source_entries SET relative_path_norm=?,relative_path_display=?,file_identity_hint=?,size_bytes=?,mtime_ns=?,sha256=?,status='available',last_seen_scan_id=?,updated_at=? WHERE id=?",
                    (entry['relative_path_norm'],entry['relative_path_display'],entry['file_identity_hint'],entry['size_bytes'],entry['mtime_ns'],entry['sha256'],entry['last_seen_scan_id'],timestamp,old['id']))
                db.execute('DELETE FROM source_missing_observations WHERE source_entry_id=?',(old['id'],))
                db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(timestamp,before['id']))
                after=snapshot(db,before['id'])
                updated=db.execute('SELECT * FROM source_entries WHERE id=?',(old['id'],)).fetchone()
                after['source_entry']={k:updated[k] for k in ('id','relative_path_norm','status','sha256')}
                record_event(db,before['id'],'source_entry_matched',before,after,timestamp=timestamp)
                result={'document_id':before['id'],'source_entry_id':old['id'],'matched':True}
            else:
                folder=current['new_file_target_folder_id']
                if folder is not None:same_space(db,'folders',folder,current['space_id'])
                db.execute('DELETE FROM source_entries WHERE id=?',(entry['id'],))
                item={'path':entry['relative_path_norm'],'sha256':entry['sha256'],'size_bytes':entry['size_bytes'],
                    'identity_hint':entry['file_identity_hint'],'mtime_ns':entry['mtime_ns'],'mime_type':mime,'file_modified_at':None}
                document,new_entry=register_external(db,{'target_id':entry['last_seen_scan_id']},current,item,folder,'needs_review',settings,timestamp)
                record_event(db,document,'ambiguous_entry_registered',None,snapshot(db,document),timestamp=timestamp)
                result={'document_id':document,'source_entry_id':new_entry,'matched':False}
            bump(db,current['id'])
            return {**result,'external_file_modified':False}
        return queue.complete(job['id'],job['lease_token'],publish)
