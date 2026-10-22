"""Registered storage accounting and explicit, fenced, reference-safe cleanup jobs."""
import json
import sqlite3
import time
from typing import Literal
from fastapi import APIRouter,Request
from pydantic import Field,field_validator
from .auth import fail
from .catalog import Input,required,transaction
from .database import connect
from .document_records import expected,snapshot
from .document_events import record_event,utc_now
from .source_files import SourceRequest,revision,requested
from .jobs import JobQueue,JobSpec
from .maintenance import gc_job,RETENTION_SECONDS
from .derived import schedule_gc

class Cleanup(Input):
    kind: Literal['reading_previews','unused_objects']
    confirm: Literal[True]
    request_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    limit: int=Field(default=1000,ge=1,le=10000,strict=True)

    @field_validator('confirm',mode='before')
    @classmethod
    def confirmed(cls,value):
        if value is not True:raise ValueError('Explicit confirmation required')
        return value

class DeleteRevision(SourceRequest):
    confirm_revision_id: str=Field(min_length=1,max_length=255)

def protected(db,id,rev,job_id=None):
    doc=required(db,'documents',id)
    if rev['id']==doc['current_revision_id']:fail(409,'CURRENT_REVISION_PROTECTED','Current original cannot be removed')
    run=db.execute('SELECT revision_id FROM parse_runs WHERE id=?',(doc['current_parse_run_id'],)).fetchone()
    if run and run[0]==rev['id']:fail(409,'SUCCESSFUL_CONTENT_PROTECTED','The visible successful overview requires this original version')
    if db.execute('SELECT 1 FROM metadata_values v JOIN parse_runs p ON p.id=v.source_parse_run_id WHERE p.revision_id=? LIMIT 1',(rev['id'],)).fetchone():
        fail(409,'BUSINESS_PROVENANCE_PROTECTED','Business field provenance requires this original version')
    if db.execute("SELECT 1 FROM jobs WHERE target_id=? AND id<>COALESCE(?,'') AND status IN ('queued','running') "
                  "AND json_extract(payload_json,'$.revision_id')=? LIMIT 1",(id,job_id,rev['id'])).fetchone():
        fail(409,'REVISION_BUSY','A background task still requires this version')

def router(settings):
    routes=APIRouter(prefix='/api/v1')
    @routes.get('/system/storage')
    def usage():
        with connect(settings.database) as db:
            def scalar(sql):return db.execute(sql).fetchone()[0] or 0
            return {'accounting':'registered_objects','physical_original_bytes':scalar('SELECT sum(size_bytes) FROM managed_objects WHERE id IN (SELECT managed_object_id FROM original_object_references)'),
                'physical_derived_bytes':scalar('SELECT sum(size_bytes) FROM (SELECT storage_key,max(size_bytes) AS size_bytes FROM (SELECT storage_key,size_bytes FROM derived_assets UNION ALL SELECT storage_key,size_bytes FROM reading_previews UNION ALL SELECT storage_key,size_bytes FROM revision_markdown) GROUP BY storage_key)'),
                'current_original_bytes':scalar('SELECT sum(r.size_bytes) FROM file_revisions r JOIN documents d ON d.current_revision_id=r.id WHERE r.storage_kind=\'managed\' OR EXISTS(SELECT 1 FROM revision_snapshots s WHERE s.revision_id=r.id)'),
                'historical_original_bytes':scalar('SELECT sum(r.size_bytes) FROM file_revisions r JOIN documents d ON d.id=r.document_id WHERE r.id<>d.current_revision_id AND (r.storage_kind=\'managed\' OR EXISTS(SELECT 1 FROM revision_snapshots s WHERE s.revision_id=r.id))'),
                'external_snapshot_bytes':scalar('SELECT sum(size_bytes) FROM managed_objects WHERE id IN (SELECT managed_object_id FROM revision_snapshots)'),
                'reading_preview_bytes':scalar('SELECT sum(size_bytes) FROM (SELECT storage_key,max(size_bytes) AS size_bytes FROM reading_previews GROUP BY storage_key)'),
                'original_revisions':scalar('SELECT count(*) FROM file_revisions'),
                'external_revisions_without_snapshot':scalar("SELECT count(*) FROM file_revisions r WHERE r.storage_kind='external' AND NOT EXISTS(SELECT 1 FROM revision_snapshots s WHERE s.revision_id=r.id)"),
                'reading_preview_count':scalar('SELECT count(*) FROM reading_previews'),
                'trash_documents':scalar('SELECT count(*) FROM documents WHERE deleted_at IS NOT NULL'),
                'gc_retention_seconds':RETENTION_SECONDS,
                'note':'Physical categories deduplicate object keys; current/historical/snapshot figures are overlapping classifications, not an additive disk total. Unregistered files and filesystem overhead are not counted.'}
    @routes.post('/system/storage/cleanup',status_code=202)
    def cleanup(body:Cleanup,request:Request):
        payload=body.model_dump();key='storage-cleanup:'+body.request_id
        with transaction(settings,request) as db:
            old=requested(db,key,payload)
            if old:return old
            job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='storage_cleanup',payload=payload,idempotency_key=key,timeout_seconds=120),db=db)
            return {'job_id':job['id'],'status':job['status']}
    @routes.delete('/documents/{id}/revisions/{revision_id}',status_code=202)
    def remove_revision(id:str,revision_id:str,body:DeleteRevision,request:Request):
        if body.revision_id!=revision_id or body.confirm_revision_id!=revision_id:fail(422,'REVISION_CONFIRMATION_REQUIRED','Confirm the exact historical revision')
        payload=body.model_dump();key='revision-cleanup:'+id+':'+body.request_id
        with transaction(settings,request) as db:
            old=requested(db,key,payload)
            if old:return old
            expected(db,id,body.expected_document_version);rev=revision(db,id,revision_id);protected(db,id,rev)
            job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='document_revision_cleanup',target_id=id,payload=payload,idempotency_key=key,timeout_seconds=120),db=db)
            return {'job_id':job['id'],'status':job['status']}
    return routes

def execute(settings,job):
    payload=json.loads(job['payload_json'])
    def publish(db,owned):
        db.row_factory=sqlite3.Row
        now=time.time()
        if job['target_type']=='document_revision_cleanup':
            before=expected(db,job['target_id'],payload['expected_document_version']);rev=revision(db,before['id'],payload['revision_id'])
            protected(db,before['id'],rev,job['id'])
            db.execute('DELETE FROM file_revisions WHERE id=?',(rev['id'],))
            timestamp=utc_now()
            db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(timestamp,before['id']))
            record_event(db,before['id'],'historical_revision_removed',before,snapshot(db,before['id']),timestamp=timestamp)
            result={'document_id':before['id'],'revision_id':rev['id'],'removed':True,'external_file_modified':False}
        else:
            removed=0;more=False
            if payload['kind']=='reading_previews':
                ids=[r[0] for r in db.execute('SELECT revision_id FROM reading_previews ORDER BY revision_id LIMIT ?',(payload['limit'],))]
                db.executemany('DELETE FROM reading_previews WHERE revision_id=?',[(id,) for id in ids]);removed=len(ids)
                more=db.execute('SELECT 1 FROM reading_previews LIMIT 1').fetchone() is not None
            result={'removed_reading_previews':removed,'more_remaining':more,'originals_modified':False}
        managed=gc_job(db,settings,'managed-after-cleanup:'+job['id'],now+RETENTION_SECONDS)
        derived=schedule_gc(db,settings,'derived-after-cleanup:'+job['id'],now+RETENTION_SECONDS)
        return {**result,'gc_job_ids':[managed['id'],derived['id']],'physical_cleanup_after_seconds':RETENTION_SECONDS}
    JobQueue(settings).complete(job['id'],job['lease_token'],publish)
