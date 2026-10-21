"""Version-pinned source inventory and explicit durable snapshot requests."""
import json
import sqlite3
from fastapi import APIRouter,Request,Query
from pydantic import Field
from .auth import fail
from .catalog import ID,Input,required,transaction
from .database import connect
from .documents import VersionChange
from .document_records import expected
from .jobs import JobQueue,JobSpec
from .source_snapshots import stored,ensure,MAX_BYTES
from .storage import ManagedStore
from .document_api import availability

class SourceRequest(VersionChange):
    revision_id: ID
    request_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')

class SourceMigration(Input):
    request_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    page_size: int=Field(default=100,ge=1,le=500,strict=True)

def revision(db,document_id,revision_id):
    db.row_factory=sqlite3.Row
    required(db,'documents',document_id)
    row=db.execute('SELECT * FROM file_revisions WHERE id=? AND document_id=?',(revision_id,document_id)).fetchone()
    if row is None:fail(404,'NOT_FOUND','Document revision not found')
    return dict(row)

def requested(db,key,payload,*,subset=False):
    old=db.execute('SELECT * FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
    if old:
        previous=json.loads(old['payload_json'])
        if (any(previous.get(k)!=v for k,v in payload.items()) if subset else previous!=payload):fail(409,'IDEMPOTENCY_CONFLICT','Request ID was used for another operation')
        return {'job_id':old['id'],'status':old['status']}

def router(settings):
    routes=APIRouter(prefix='/api/v1')
    @routes.get('/documents/{id}/source-files')
    def inventory(id:str,page:int=Query(default=1,ge=1,le=1000000),page_size:int=Query(default=20,ge=1,le=50)):
        with connect(settings.database) as db:
            db.row_factory=sqlite3.Row
            document=required(db,'documents',id)
            rows=db.execute('SELECT * FROM file_revisions WHERE document_id=? ORDER BY revision_no DESC LIMIT ? OFFSET ?',
                (id,page_size,(page-1)*page_size)).fetchall()
            items=[];store=ManagedStore(settings.data_dir/'managed')
            for row in rows:
                rev=dict(row);copy=stored(db,rev['id']);source=None
                if rev['storage_kind']=='external':
                    linked=db.execute('SELECT s.id,s.name,s.status,e.status AS entry_status,e.relative_path_display '
                        'FROM sources s JOIN source_entries e ON e.source_id=s.id WHERE e.id=?',(rev['source_entry_id'],)).fetchone()
                    if linked:source={'id':linked['id'],'name':linked['name'],'status':linked['status'],'entry_status':linked['entry_status'],'relative_path':linked['relative_path_display']}
                state,_=availability(db,row,store)
                items.append({key:rev[key] for key in ('id','revision_no','original_filename','mime_type','size_bytes','sha256','created_at','storage_kind')}
                    | {'is_current':rev['id']==document['current_revision_id'],'server_copy':rev['storage_kind']=='managed' or copy is not None,
                       'availability_status':state,'source':source})
            total=db.execute('SELECT count(*) FROM file_revisions WHERE document_id=?',(id,)).fetchone()[0]
            return {'document_id':id,'document_version':document['document_version'],'current_revision_id':document['current_revision_id'],
                    'items':items,'page':page,'page_size':page_size,'total':total}
    @routes.post('/documents/{id}/source-snapshot',status_code=202)
    def snapshot_request(id:str,body:SourceRequest,request:Request):
        payload=body.model_dump();key='snapshot:'+id+':'+body.request_id
        with transaction(settings,request) as db:
            old=requested(db,key,payload)
            if old:return old
            doc=expected(db,id,body.expected_document_version);rev=revision(db,id,body.revision_id)
            if doc['deleted_at']:fail(409,'DOCUMENT_TRASHED','Restore before creating a server copy')
            if rev['storage_kind']!='external':fail(409,'EXTERNAL_REVISION_REQUIRED','A managed original already has a server copy')
            if rev['size_bytes']>MAX_BYTES:fail(413,'SNAPSHOT_INPUT_LIMIT','Original exceeds the snapshot input budget')
            job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='document_snapshot',target_id=id,
                payload=payload,idempotency_key=key,timeout_seconds=180),db=db)
            return {'job_id':job['id'],'status':job['status']}
    @routes.post('/sources/{id}/source-snapshots',status_code=202)
    def migrate(id:str,body:SourceMigration,request:Request):
        payload=body.model_dump();key='source-snapshot-migration:'+id+':'+body.request_id
        with transaction(settings,request) as db:
            old=requested(db,key,payload,subset=True)
            if old:return old
            source=required(db,'sources',id)
            if source['status']=='disabled' or not source['initial_import_completed_at']:fail(409,'SOURCE_DISABLED','Finish initial import and enable the source first')
            end=db.execute("SELECT max(r.id) FROM file_revisions r JOIN documents d ON d.current_revision_id=r.id "
                "JOIN source_entries e ON e.id=r.source_entry_id WHERE e.source_id=? AND d.deleted_at IS NULL AND r.storage_kind='external'",(id,)).fetchone()[0] or ''
            payload.update(after='',until=end,root=key)
            job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='source_snapshot_batch',target_id=id,
                payload=payload,idempotency_key=key,timeout_seconds=120),db=db)
            return {'job_id':job['id'],'status':job['status']}
    return routes

def execute_snapshot(settings,job):
    if job['target_type']=='source_snapshot_batch':
        payload=json.loads(job['payload_json'])
        def page(db,owned):
            db.row_factory=sqlite3.Row;source=required(db,'sources',job['target_id'])
            if source['status']=='disabled':fail(409,'SOURCE_DISABLED','Source was disabled')
            rows=db.execute("SELECT r.id,r.document_id,d.document_version FROM file_revisions r JOIN documents d ON d.current_revision_id=r.id "
                "JOIN source_entries e ON e.id=r.source_entry_id WHERE e.source_id=? AND r.storage_kind='external' AND d.deleted_at IS NULL "
                "AND r.id>? AND r.id<=? AND NOT EXISTS(SELECT 1 FROM revision_snapshots s WHERE s.revision_id=r.id) ORDER BY r.id LIMIT ?",
                (source['id'],payload['after'],payload['until'],payload['page_size']+1)).fetchall()
            ids=[]
            for row in rows[:payload['page_size']]:
                child={'revision_id':row['id'],'expected_document_version':row['document_version'],'request_id':payload['request_id']}
                pending=db.execute("SELECT id FROM jobs WHERE target_type='document_snapshot' AND target_id=? AND status IN ('queued','running') "
                    "AND json_extract(payload_json,'$.revision_id')=? LIMIT 1",(row['document_id'],row['id'])).fetchone()
                if pending:ids.append(pending['id'])
                else:
                    queued=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='document_snapshot',target_id=row['document_id'],payload=child,
                        idempotency_key=payload['root']+':revision:'+row['id'],timeout_seconds=180),db=db)
                    ids.append(queued['id'])
            following=None
            if len(rows)>payload['page_size']:
                continuation={**payload,'after':rows[payload['page_size']-1]['id']}
                following=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='source_snapshot_batch',target_id=source['id'],payload=continuation,
                    idempotency_key=payload['root']+':page:'+continuation['after'],timeout_seconds=120),db=db)['id']
            return {'source_id':source['id'],'snapshot_job_ids':ids,'scheduled_count':len(ids),'continuation_job_id':following,'external_files_modified':False}
        JobQueue(settings).complete(job['id'],job['lease_token'],page);return
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        rev=revision(db,job['target_id'],json.loads(job['payload_json'])['revision_id'])
    queue=JobQueue(settings)
    queue.step(job['id'],job['lease_token'],'copy')
    ensure(settings,rev,job)
    queue.step(job['id'],job['lease_token'],'publish')
    JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:{'document_id':job['target_id'],
        'revision_id':rev['id'],'server_copy':True,'external_file_modified':False})
