"""Verified readonly external copy, followed by a fenced managed revision switch."""
import json
import sqlite3
import time

from fastapi import APIRouter, Request
from pydantic import Field

from .auth import fail
from .catalog import ID, required, transaction
from .database import connect
from .document_events import record_event, utc_now
from .document_records import expected, snapshot
from .documents import DocumentService, RevisionInput, VersionChange
from .exclusions import add, blocked, bump
from .jobs import JobQueue, JobSpec
from .maintenance import gc_job
from .parsing import original
from .storage import ManagedStore


class Adopt(VersionChange):
    expected_revision_id: ID
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')


def checked(db, id, payload):
    doc=expected(db,id,payload['expected_document_version'])
    if doc['deleted_at'] is not None:fail(409,'DOCUMENT_TRASHED','Restore before taking into managed storage')
    if doc['current_revision_id']!=payload['expected_revision_id']:
        fail(409,'REVISION_CONFLICT','Current original changed; reload')
    revision=db.execute('SELECT * FROM file_revisions WHERE id=? AND document_id=?',
                        (doc['current_revision_id'],id)).fetchone()
    if revision is None or revision['storage_kind']!='external':
        fail(409,'EXTERNAL_REVISION_REQUIRED','Choose a current external original')
    entry=required(db,'source_entries',revision['source_entry_id'])
    if entry['document_id']!=id:fail(409,'SOURCE_CHANGED','Source entry no longer belongs to this document')
    return doc,dict(revision),dict(entry)


def router(settings):
    routes=APIRouter(prefix='/api/v1/documents');queue=JobQueue(settings)

    @routes.post('/{id}/adopt',status_code=202)
    def adopt(id:str,body:Adopt,request:Request):
        payload=body.model_dump();key='adopt:'+id+':'+body.request_id
        with transaction(settings,request) as db:
            existing=db.execute('SELECT id,status,payload_json FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
            if existing:
                previous=json.loads(existing['payload_json'])
                if any(previous.get(k)!=v for k,v in payload.items()):
                    fail(409,'IDEMPOTENCY_CONFLICT','Request ID was used for different adoption parameters')
                return {'job_id':existing['id'],'status':existing['status']}
            doc,revision,entry=checked(db,id,payload)
            if revision['size_bytes']>settings.upload_max_bytes:
                fail(413,'ADOPTION_LIMIT','External original exceeds the managed input limit')
            if blocked(db,entry['source_id'],entry['relative_path_norm']):
                fail(409,'SOURCE_ENTRY_BUSY','Source entry has a pending operation or exclusion')
            payload.update(source_entry_id=entry['id'],path=entry['relative_path_norm'],max_bytes=settings.upload_max_bytes)
            job=queue.enqueue(JobSpec(kind='batch',target_type='document_adoption',target_id=id,
                payload=payload,idempotency_key=key,timeout_seconds=120),db=db)
            db.execute('INSERT INTO source_exclusion_intents VALUES (?,?,?,?)',
                       (job['id'],entry['id'],entry['source_id'],entry['relative_path_norm']))
            bump(db,entry['source_id'])
            # A complete filesystem object can outlive a failed SQL publication.
            gc_job(db,settings,'gc-after-adoption:'+job['id'],time.time()+86400)
            return {'job_id':job['id'],'status':job['status']}
    return routes


def execute(settings,job):
    payload=json.loads(job['payload_json']);queue=JobQueue(settings)
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        _,revision,_=checked(db,job['target_id'],payload)
    store=ManagedStore(settings.data_dir/'managed')
    # Store lock precedes the DB transaction, matching upload and GC lock order.
    with store.locked(),original(settings,revision,payload['max_bytes']) as file:
        obj=store.put(file,max_bytes=payload['max_bytes'],expected_size=revision['size_bytes'],expected_sha256=revision['sha256'])
        def publish(db,owned):
            db.row_factory=sqlite3.Row
            before,current,entry=checked(db,job['target_id'],payload)
            intent=db.execute('SELECT * FROM source_exclusion_intents WHERE job_id=?',(job['id'],)).fetchone()
            if current!=revision or entry['id']!=payload['source_entry_id'] or entry['relative_path_norm']!=payload['path'] or not intent:
                fail(409,'SOURCE_CHANGED','Source registration changed during adoption')
            object_id=DocumentService.managed_object(db,obj)
            number=db.execute('SELECT COALESCE(max(revision_no),0)+1 FROM file_revisions WHERE document_id=?',(before['id'],)).fetchone()[0]
            new_id=DocumentService.insert_revision(db,before['id'],number,object_id,obj,
                RevisionInput(original_filename=revision['original_filename'],mime_type=revision['mime_type']))
            timestamp=utc_now()
            db.execute('UPDATE documents SET current_revision_id=?,document_version=document_version+1,updated_at=? WHERE id=?',
                       (new_id,timestamp,before['id']))
            add(db,entry,'adopted_managed',timestamp)
            db.execute('DELETE FROM source_exclusion_intents WHERE job_id=?',(job['id'],))
            bump(db,entry['source_id'])
            # Preserve OCR settings of the successful body while it remains visible as stale.
            previous=db.execute('SELECT j.payload_json FROM parse_attempts a JOIN parse_requests q ON q.sequence=a.request_sequence '
                'JOIN jobs j ON j.id=q.job_id WHERE a.parse_run_id=?',(before['current_parse_run_id'],)).fetchone()
            options=json.loads(previous[0]) if previous else {}
            options={k:v for k,v in options.items() if k in ('ocr_enabled','ocr_languages','generate_preview')}
            parse=queue.enqueue(JobSpec(kind='ocr' if options.get('ocr_enabled') else 'parse',target_type='document',target_id=before['id'],
                payload={'revision_id':new_id,**options},idempotency_key='parse:'+new_id),db=db)
            record_event(db,before['id'],'document_adopted',before,snapshot(db,before['id']),timestamp=timestamp)
            return {'document_id':before['id'],'revision_id':new_id,'parse_job_id':parse['id'],'external_file_modified':False}
        return queue.complete(job['id'],job['lease_token'],publish)
