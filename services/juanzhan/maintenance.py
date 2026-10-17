"""Fenced metadata purge and reference-aware managed GC. No external unlink API."""
import argparse
import json
import os
import re
import sqlite3
import stat
import time
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .auth import fail
from .catalog import ID, required, transaction
from .config import Settings
from .database import connect
from .document_events import record_event, utc_now
from .document_records import expected, snapshot
from .documents import Version
from .exclusions import add, bump
from .jobs import JobQueue, JobSpec, encoded
from .storage import ManagedStore, directory, parse_key

RETENTION_SECONDS=86400


class PurgeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm_document_id: ID
    expected_document_version: Version


class ExcludeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_entry_id: ID
    expected_document_version: Version | None=None
    reason: str=Field(default='',max_length=1000)


def gc_job(db,settings,key,due):
    job=JobQueue(settings).enqueue(JobSpec(kind='gc',target_type='managed_objects',payload={},idempotency_key=key,timeout_seconds=120),db=db)
    db.execute("UPDATE jobs SET available_at=? WHERE id=? AND status='queued'",(due,job['id']))
    return job


def exclude(db,job):
    db.row_factory=sqlite3.Row
    payload=json.loads(job['payload_json'])
    entry=required(db,'source_entries',job['target_id'])
    if entry['relative_path_norm']!=payload['path']:fail(409,'SOURCE_CHANGED','Source entry changed')
    timestamp=utc_now()
    if entry['document_id']:
        before=expected(db,entry['document_id'],payload['version'])
        if before['deleted_at'] is None:
            db.execute('UPDATE documents SET deleted_at=?,updated_at=?,document_version=document_version+1 WHERE id=?',
                (timestamp,timestamp,entry['document_id']))
            record_event(db,entry['document_id'],'document_unindexed',before,snapshot(db,entry['document_id']),timestamp=timestamp)
    rule=add(db,entry,payload['reason'],timestamp)
    db.execute('DELETE FROM source_missing_observations WHERE source_entry_id=?',(entry['id'],))
    db.execute('DELETE FROM source_exclusion_intents WHERE job_id=?',(job['id'],))
    bump(db,entry['source_id'])
    return {'source_entry_id':entry['id'],'exclusion_id':rule,'document_id':entry['document_id'],'external_file_deleted':False}


def purge(db,job,settings):
    db.row_factory=sqlite3.Row
    payload=json.loads(job['payload_json'])
    before=expected(db,job['target_id'],payload['version'])
    if before['deleted_at'] is None:fail(409,'DOCUMENT_NOT_TRASHED','Move the document to trash first')
    id=before['id'];timestamp=utc_now();now=time.time()
    object_keys=[r[0] for r in db.execute('SELECT DISTINCT o.storage_key FROM managed_objects o JOIN file_revisions r '
                                         'ON r.managed_object_id=o.id WHERE r.document_id=?',(id,))]
    for entry in db.execute('SELECT * FROM source_entries WHERE document_id=?',(id,)).fetchall():
        add(db,entry,'document_purged',timestamp)
        bump(db,entry['source_id'])
    # Fence active document handlers; future completions cannot restore purged data.
    db.execute("UPDATE jobs SET status='cancelled',retryable=0,error_json=?,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? "
               "WHERE target_type='document' AND target_id=? AND status IN ('queued','running')",
               (encoded({'code':'DOCUMENT_PURGED','message':'Document was purged','retryable':False}),timestamp,id))
    db.execute('DELETE FROM document_search WHERE document_id=?',(id,))
    db.execute('UPDATE documents SET current_revision_id=NULL,current_parse_run_id=NULL WHERE id=?',(id,))
    db.execute('DELETE FROM file_revisions WHERE document_id=?',(id,))
    db.execute('DELETE FROM source_entries WHERE document_id=?',(id,))
    db.execute('DELETE FROM documents WHERE id=?',(id,))
    db.execute('INSERT INTO document_purge_receipts VALUES (?,?,?,?)',(id,payload['version'],job['id'],timestamp))
    for key in object_keys:
        if not db.execute('SELECT 1 FROM file_revisions r JOIN managed_objects o ON o.id=r.managed_object_id WHERE o.storage_key=? LIMIT 1',(key,)).fetchone():
            db.execute('INSERT INTO managed_gc_candidates VALUES (?,?) ON CONFLICT(storage_key) DO UPDATE SET eligible_after=max(eligible_after,excluded.eligible_after)',
                       (key,now+RETENTION_SECONDS))
    from .derived import schedule_gc
    schedule_gc(db,settings,'derived-after-purge:'+job['id'],now+RETENTION_SECONDS)
    gc=gc_job(db,settings,'gc-after-purge:'+job['id'],now+RETENTION_SECONDS) if object_keys else None
    return {'document_id':id,'purged':True,'external_file_deleted':False,'gc_job_id':gc['id'] if gc else None}


def collect(db,job,root,settings,*,clock=time.time):
    """Caller holds exclusive managed-store lock and fenced SQLite write transaction.

    Crashes after unlink may leave only an unreferenced DB row, safely retryable.
    We never unlink while any historical/trash revision references the key.
    """
    now=clock();counts={'discovered':0,'deleted_objects':0,'retained_objects':0,'ignored_files':0}
    with directory(root,'sha256') as objects:
        for prefix in os.listdir(objects):
            if not re.fullmatch('[0-9a-f]{2}',prefix):continue
            try:
                bucket_context=directory(objects,prefix)
                with bucket_context as bucket:
                    for name in os.listdir(bucket):
                        key='sha256/'+prefix+'/'+name
                        try:_,size=parse_key(key)
                        except ValueError:counts['ignored_files']+=1;continue
                        info=os.stat(name,dir_fd=bucket,follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode) or info.st_size!=size:
                            counts['ignored_files']+=1;continue
                        referenced=db.execute('SELECT 1 FROM file_revisions r JOIN managed_objects o ON o.id=r.managed_object_id WHERE o.storage_key=? LIMIT 1',(key,)).fetchone()
                        if referenced:
                            db.execute('DELETE FROM managed_gc_candidates WHERE storage_key=?',(key,))
                            counts['retained_objects']+=1;continue
                        candidate=db.execute('SELECT eligible_after FROM managed_gc_candidates WHERE storage_key=?',(key,)).fetchone()
                        if candidate is None:
                            db.execute('INSERT INTO managed_gc_candidates VALUES (?,?)',(key,now+RETENTION_SECONDS))
                            counts['discovered']+=1;continue
                        if candidate[0]>now:counts['retained_objects']+=1;continue
                        os.unlink(name,dir_fd=bucket);os.fsync(bucket)
                        db.execute('DELETE FROM managed_objects WHERE storage_key=?',(key,))
                        db.execute('DELETE FROM managed_gc_candidates WHERE storage_key=?',(key,))
                        counts['deleted_objects']+=1
            except (NotADirectoryError,FileNotFoundError):continue
            except OSError as exc:
                # Directory symlinks are ignored; real IO failures must fail the job.
                if exc.errno==40:counts['ignored_files']+=1
                else:raise
    # Recover a crash after unlink, or an unreferenced missing object row.
    for key, in db.execute('SELECT storage_key FROM managed_gc_candidates WHERE eligible_after<=?',(now,)).fetchall():
        try:parse_key(key)
        except ValueError:continue
        if db.execute('SELECT 1 FROM file_revisions r JOIN managed_objects o ON o.id=r.managed_object_id WHERE o.storage_key=?',(key,)).fetchone():continue
        if ManagedStore(settings.data_dir/'managed').probe(key)=='missing':
            db.execute('DELETE FROM managed_objects WHERE storage_key=?',(key,))
            db.execute('DELETE FROM managed_gc_candidates WHERE storage_key=?',(key,))
    future=db.execute('SELECT min(eligible_after) FROM managed_gc_candidates WHERE eligible_after>?',(now,)).fetchone()[0]
    if future is not None and future>now:gc_job(db,settings,'gc-followup:'+job['id'],future)
    return counts


def run_gc(settings,job):
    store=ManagedStore(settings.data_dir/'managed')
    with store.locked(exclusive=True) as root:
        JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:collect(db,owned,root,settings))


def router(settings):
    routes=APIRouter(prefix='/api/v1');queue=JobQueue(settings)

    @routes.get('/sources/{id}/exclusions')
    def rules(id:str):
        with transaction(settings) as db:
            required(db,'sources',id)
            return [{'id':r['id'],'source_id':r['source_id'],'relative_path':r['relative_path_norm'],'reason':r['reason'],'created_at':r['created_at']}
                    for r in db.execute('SELECT * FROM source_exclusions WHERE source_id=? ORDER BY created_at,id',(id,))]

    @routes.post('/sources/{id}/exclude-entry',status_code=202)
    def cancel(id:str,body:ExcludeRequest,request:Request):
        with transaction(settings,request) as db:
            required(db,'sources',id);entry=required(db,'source_entries',body.source_entry_id)
            if entry['source_id']!=id:fail(422,'CROSS_SOURCE_REFERENCE','Entry belongs to another source')
            pending=db.execute('SELECT j.id,j.status FROM source_exclusion_intents x JOIN jobs j ON j.id=x.job_id WHERE x.source_entry_id=?',(entry['id'],)).fetchone()
            if pending:return {'job_id':pending['id'],'status':pending['status']}
            if entry['document_id']:
                if body.expected_document_version is None:fail(422,'VERSION_REQUIRED','Expected document version required')
                expected(db,entry['document_id'],body.expected_document_version)
            job=queue.enqueue(JobSpec(kind='batch',target_type='source_exclude',target_id=entry['id'],
                payload={'path':entry['relative_path_norm'],'version':body.expected_document_version,'reason':body.reason},
                idempotency_key='exclude:'+uuid.uuid4().hex),db=db)
            db.execute('INSERT INTO source_exclusion_intents VALUES (?,?,?,?)',(job['id'],entry['id'],id,entry['relative_path_norm']))
            bump(db,id)
            return {'job_id':job['id'],'status':job['status']}

    @routes.delete('/sources/{id}/exclusions/{exclusion_id}',status_code=204)
    def remove(id:str,exclusion_id:str,request:Request):
        with transaction(settings,request) as db:
            required(db,'sources',id);rule=required(db,'source_exclusions',exclusion_id)
            if rule['source_id']!=id:fail(422,'CROSS_SOURCE_REFERENCE','Rule belongs to another source')
            db.execute('DELETE FROM source_exclusions WHERE id=?',(exclusion_id,));bump(db,id)

    @routes.post('/documents/{id}/purge',status_code=202)
    def submit_purge(id:str,body:PurgeRequest,request:Request):
        if body.confirm_document_id!=id:fail(422,'CONFIRMATION_MISMATCH','Confirm the exact document ID')
        with transaction(settings,request) as db:
            receipt=db.execute('SELECT * FROM document_purge_receipts WHERE document_id=?',(id,)).fetchone()
            if receipt:
                if receipt['document_version']!=body.expected_document_version:fail(409,'DOCUMENT_PURGED','Document was already purged')
                return {'job_id':receipt['job_id'],'status':'completed'}
            document=expected(db,id,body.expected_document_version)
            if document['deleted_at'] is None:fail(409,'DOCUMENT_NOT_TRASHED','Move the document to trash first')
            job=queue.enqueue(JobSpec(kind='purge',target_type='document_purge',target_id=id,
                payload={'version':body.expected_document_version},idempotency_key='purge:'+id+':'+str(body.expected_document_version)),db=db)
            return {'job_id':job['id'],'status':job['status']}
    return routes


def main():
    parser=argparse.ArgumentParser(description='Queue reference-aware managed object GC (minimum 24h grace)')
    parser.add_argument('operation',choices=['gc'])
    parser.add_argument('--store',choices=['managed','derived'],default='managed')
    args=parser.parse_args()
    settings=Settings.from_env()
    job=JobQueue(settings).enqueue(JobSpec(kind='gc',target_type='derived_objects' if args.store=='derived' else 'managed_objects',idempotency_key='manual-gc:'+uuid.uuid4().hex))
    print(json.dumps({'job_id':job['id'],'status':job['status']}))


if __name__=='__main__':main()
