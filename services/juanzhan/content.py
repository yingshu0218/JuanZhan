"""Authenticated cached content, parse provenance and explicit reprocessing."""
import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import Field, field_validator

from .auth import fail
from .catalog import transaction
from .document_api import project
from .document_records import expected, snapshot
from .documents import VersionChange
from .jobs import JobQueue, JobSpec, row
from .source_paths import SourceMounts
from .storage import IntegrityError, ManagedStore, StorageError, parse_key

MAX_BYTES=16*1024*1024
Page=Annotated[int,Query(ge=1,le=1000000)]
PageSize=Annotated[int,Query(ge=1,le=100)]

class Reprocess(VersionChange):
    expected_revision_id: Annotated[str,Field(min_length=1,max_length=255)]
    request_id: Annotated[str,Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')]
    ocr: bool = Field(default=False,strict=True)
    force: bool = Field(default=False,strict=True)
    ocr_languages: str = Field(default='',max_length=255)
    generate_preview: bool = Field(default=True,strict=True)

    @field_validator('ocr_languages')
    @classmethod
    def languages(cls,value):
        values=value.split(',') if value else []
        if len(values)!=len(set(values)) or set(values)-{'eng','chi_sim'}:raise ValueError('Invalid OCR languages')
        return ','.join(sorted(values))


def bounded(value):
    if len(json.dumps(value,ensure_ascii=False,allow_nan=False).encode())>MAX_BYTES:
        fail(413,'CONTENT_RESPONSE_LIMIT','Response exceeds the content budget; use a smaller page')
    return value


def read_rows(db,sql,params,columns):
    # Budget in SQLite before fetching large cached JSON values into application memory.
    expression='+'.join('COALESCE(length(CAST('+column+' AS BLOB)),0)' for column in columns)
    size=db.execute('SELECT COALESCE(sum('+expression+'),0) FROM ('+sql+')',params).fetchone()[0]
    if size>MAX_BYTES:fail(413,'CONTENT_RESPONSE_LIMIT','Cached page exceeds the response budget')
    return db.execute(sql,params).fetchall()


def selected(db,document,run_id=None):
    id=run_id or document['current_parse_run_id']
    if id is None:fail(404,'CONTENT_NOT_AVAILABLE','No successful cached content is available')
    run=db.execute('SELECT * FROM parse_runs WHERE id=? AND document_id=?',(id,document['id'])).fetchone()
    if run is None:fail(404,'NOT_FOUND','Parse run not found')
    return run


def headers(response):
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'


def router(settings):
    routes=APIRouter(prefix='/api/v1/documents')
    derived=ManagedStore(settings.data_dir/'derived')
    originals=ManagedStore(settings.data_dir/'managed')
    mounts=SourceMounts(settings.source_mounts)

    @routes.get('/{id}/parse-runs')
    def history(id: str,response: Response,page: Page=1,page_size: PageSize=20):
        headers(response)
        with transaction(settings) as db:
            doc=snapshot(db,id)
            total=db.execute('SELECT count(*) FROM parse_runs WHERE document_id=?',(id,)).fetchone()[0]
            # Never materialize an unbounded history or embed every candidate value.
            runs=read_rows(db,'SELECT p.*,q.job_id,a.attempt FROM parse_runs p LEFT JOIN parse_attempts a ON a.parse_run_id=p.id '
                'LEFT JOIN parse_requests q ON q.sequence=a.request_sequence WHERE p.document_id=? '
                'ORDER BY COALESCE(q.sequence,0) DESC,COALESCE(a.attempt,0) DESC,p.created_at DESC,p.id DESC LIMIT ? OFFSET ?',
                (id,page_size,(page-1)*page_size),('warnings_json','error_json','parser_name','parser_version','language'))
            items=[]
            for run in runs:
                item={k:run[k] for k in ('id','revision_id','status','schema_version','parser_name','parser_version','language','page_count','created_at','started_at','completed_at','job_id','attempt')}
                item.update(ocr_used=bool(run['ocr_used']),text_available=bool(run['text_available']),
                    warnings=json.loads(run['warnings_json']),error=json.loads(run['error_json']) if run['error_json'] else None,
                    is_current=run['id']==doc['current_parse_run_id'],
                    candidate_count=db.execute('SELECT count(*) FROM extracted_metadata WHERE parse_run_id=?',(run['id'],)).fetchone()[0])
                items.append(item)
            return bounded({'items':items,'page':page,'page_size':page_size,'total':total})

    @routes.get('/{id}/candidates')
    def candidates(id: str,response: Response,parse_run_id: Annotated[str | None,Query(min_length=1,max_length=255)]=None,page: Page=1,page_size: PageSize=20):
        headers(response)
        with transaction(settings) as db:
            doc=snapshot(db,id)
            if not parse_run_id and not doc['current_parse_run_id']:
                return {'items':[],'page':page,'page_size':page_size,'total':0,'parse_run_id':None}
            run=selected(db,doc,parse_run_id)
            total=db.execute('SELECT count(*) FROM extracted_metadata WHERE parse_run_id=?',(run['id'],)).fetchone()[0]
            values=read_rows(db,'SELECT * FROM extracted_metadata WHERE parse_run_id=? ORDER BY id LIMIT ? OFFSET ?',
                             (run['id'],page_size,(page-1)*page_size),('candidate_key','candidate_value_json','provenance_json'))
            adoptable=bool(run['status']=='completed' and run['revision_id']==doc['current_revision_id'] and
                           run['id']==doc['current_parse_run_id'] and doc['deleted_at'] is None)
            items=[{'id':r['id'],'key':r['candidate_key'],'value':json.loads(r['candidate_value_json']),
                    'confidence':r['confidence'],'provenance':json.loads(r['provenance_json']),
                    'parse_run_id':run['id'],'revision_id':run['revision_id'],'adoptable':adoptable} for r in values]
            return bounded({'items':items,'page':page,'page_size':page_size,'total':total,'parse_run_id':run['id']})

    @routes.get('/{id}/content')
    def content(id: str,response: Response,format: Literal['blocks','text','markdown']='blocks',
                parse_run_id: Annotated[str | None,Query(min_length=1,max_length=255)]=None,page: Page=1,page_size: PageSize=100):
        headers(response)
        with transaction(settings) as db:
            view=project(db,id,originals,mounts)
            run=selected(db,view,parse_run_id)
            if run['status']!='completed':fail(409,'CONTENT_NOT_COMPLETED','This parse run has no successful content')
            result={'document_id':id,'content_revision_id':run['revision_id'],'parse_run_id':run['id'],'format':format,
                    'stale_for_current_revision':bool(view['content_stale'] or run['id']!=view['current_parse_run_id'] or
                        run['revision_id']!=view['current_revision_id'] or view['availability_status'] in
                        ('source_offline','missing','suspected_missing','needs_match')),
                    'warnings':json.loads(run['warnings_json']),'current_revision_id':view['current_revision_id'],
                    'processing_status':view['processing_status'],'availability_status':view['availability_status'],
                    'text_available':bool(run['text_available']),'ocr_used':bool(run['ocr_used'])}
            if format=='blocks':
                total=db.execute('SELECT count(*) FROM content_blocks WHERE parse_run_id=?',(run['id'],)).fetchone()[0]
                blocks=read_rows(db,'SELECT * FROM content_blocks WHERE parse_run_id=? ORDER BY block_index LIMIT ? OFFSET ?',
                                  (run['id'],page_size,(page-1)*page_size),('text_content','structural_json','locator_json'))
                result.update(body=[{'id':b['block_id'],'index':b['block_index'],'type':b['block_type'],'text':b['text_content'],
                    'structure':json.loads(b['structural_json']),'locator':json.loads(b['locator_json']),
                    'confidence':b['confidence']} for b in blocks],page=page,page_size=page_size,total=total)
            else:
                if page!=1:fail(422,'INVALID_CONTENT_PAGE','Text and Markdown are not paginated')
                kind='plain_text' if format=='text' else 'markdown'
                asset=db.execute('SELECT * FROM derived_assets WHERE parse_run_id=? AND asset_kind=? ORDER BY id LIMIT 1',(run['id'],kind)).fetchone()
                if asset is None:fail(503,'DERIVED_CONTENT_UNAVAILABLE','Cached content asset is unavailable')
                try:
                    if asset['size_bytes']>MAX_BYTES or parse_key(asset['storage_key'])!=(asset['sha256'],asset['size_bytes']):
                        raise IntegrityError('Invalid descriptor')
                    with derived.open(asset['storage_key']) as file:result['body']=file.read(MAX_BYTES+1).decode('utf-8')
                except (OSError,StorageError,ValueError,UnicodeError):
                    fail(503,'DERIVED_CONTENT_UNAVAILABLE','Cached content asset could not be verified')
            return bounded(result)

    @routes.post('/{id}/reprocess',status_code=202)
    def reprocess(id: str,body: Reprocess,request: Request,response: Response):
        headers(response)
        if body.ocr_languages and not body.ocr:fail(422,'OCR_DISABLED','Languages require OCR')
        with transaction(settings,request) as db:
            doc=expected(db,id,body.expected_document_version)
            if doc['deleted_at'] is not None:fail(409,'DOCUMENT_TRASHED','Restore before reprocessing')
            if not doc['current_revision_id'] or doc['current_revision_id']!=body.expected_revision_id:
                fail(409,'REVISION_CONFLICT','Original revision changed; reload before reprocessing')
            payload={'revision_id':doc['current_revision_id'],'ocr_enabled':body.ocr,
                     'ocr_languages':body.ocr_languages,'generate_preview':body.generate_preview}
            key='reprocess:'+hashlib.sha256((id+':'+body.request_id).encode()).hexdigest()
            existing=db.execute('SELECT id FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
            if existing:
                job=row(db,existing[0])
                if json.loads(job['payload_json'])!=payload:fail(409,'IDEMPOTENCY_CONFLICT','Request ID was used for different options')
                return {'job_id':job['id'],'status':job['status']}
            active=db.execute("SELECT 1 FROM jobs WHERE target_type='document' AND target_id=? AND kind IN('parse','ocr') "
                "AND status IN('queued','running') AND json_extract(payload_json,'$.revision_id')=? LIMIT 1",(id,doc['current_revision_id'])).fetchone()
            if active:fail(409,'PARSE_ALREADY_RUNNING','This revision already has an active parse request')
            view=project(db,id,originals,mounts)
            if not body.force and view['processing_status']=='completed' and not view['content_stale']:
                fail(409,'ALREADY_PARSED','Set force=true to explicitly reprocess successful content')
            job=JobQueue(settings).enqueue(JobSpec(kind='ocr' if body.ocr else 'parse',target_type='document',target_id=id,
                payload=payload,idempotency_key=key),db=db)
            return {'job_id':job['id'],'status':job['status']}
    return routes
