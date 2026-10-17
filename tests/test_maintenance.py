import io
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from test_document_api import api,upload,detail
from juanzhan.database import connect
from juanzhan.jobs import JobQueue,JobSpec
from juanzhan.maintenance import collect,exclude,purge,run_gc,RETENTION_SECONDS
from juanzhan.storage import StorageBusy
from juanzhan.worker import Worker
from juanzhan.documents import Registration


def claim(settings,id):
    queue=JobQueue(settings)
    while job:=queue.claim('test'):
        if job['id']==id:return job
        queue.failure(job['id'],job['lease_token'],'HANDLER_NOT_AVAILABLE','Unsupported',retryable=False)
    raise AssertionError('Job not ready')


def trash(client,headers,id):
    version=detail(client,id)['document_version']
    response=client.post('/api/v1/documents/'+id+'/trash',headers=headers,json={'expected_document_version':version})
    assert response.status_code==200
    return detail(client,id)['document_version']


def submit(client,headers,id,version):
    return client.post('/api/v1/documents/'+id+'/purge',headers=headers,json={'confirm_document_id':id,'expected_document_version':version})


def finish(settings,id):
    owned=claim(settings,id)
    JobQueue(settings).complete(id,owned['lease_token'],lambda db,job:purge(db,job,settings))
    return JobQueue(settings).get(id)['result']


def gc(settings,now=None):
    queue=JobQueue(settings)
    job=queue.enqueue(JobSpec(kind='gc',target_type='managed_objects',idempotency_key='gc-test:'+str(time.time_ns())))
    owned=claim(settings,job['id'])
    if now is None:run_gc(settings,owned)
    else:
        from juanzhan.storage import ManagedStore
        store=ManagedStore(settings.data_dir/'managed')
        with store.locked(exclusive=True) as root:
            queue.complete(owned['id'],owned['lease_token'],lambda db,j:collect(db,j,root,settings,clock=lambda:now))
    return queue.get(job['id'])['result']


def test_purge_requires_trash_confirmation_version_and_replays_receipt(api):
    app,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    assert submit(client,{},id,1).status_code==403
    assert submit(client,headers,id,1).json()['error']['code']=='DOCUMENT_NOT_TRASHED'
    assert client.post('/api/v1/documents/'+id+'/purge',headers=headers,json={'confirm_document_id':'wrong','expected_document_version':1}).status_code==422
    version=trash(client,headers,id)
    response=submit(client,headers,id,version);assert response.status_code==202
    job=response.json()['job_id']
    assert submit(client,headers,id,version).json()['job_id']==job
    result=finish(settings,job);assert result['purged'] and result['external_file_deleted'] is False
    assert client.get('/api/v1/documents/'+id).status_code==404
    assert submit(client,headers,id,version).json()=={'job_id':job,'status':'completed'}
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM document_purge_receipts').fetchone()[0]==1
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_restore_after_queued_purge_prevents_deletion(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id'];version=trash(client,headers,id)
    job=submit(client,headers,id,version).json()['job_id']
    client.post('/api/v1/documents/'+id+'/restore',headers=headers,json={'expected_document_version':version})
    owned=claim(settings,job)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        JobQueue(settings).complete(job,owned['lease_token'],lambda db,j:purge(db,j,settings))
    assert error.value.detail['code']=='VERSION_CONFLICT'
    assert detail(client,id)['deleted_at'] is None


def test_gc_preserves_all_revision_refs_and_waits_after_last_purge(api):
    app,settings,client,headers,space=api
    a=upload(client,headers,space,b'shared')['document_id']
    b=client.post('/api/v1/documents/upload',headers=headers,data={'space_id':space,'duplicate_policy':'keep_separate'},files={'file':('copy.txt',b'shared')}).json()['document_id']
    with connect(settings.database) as db:key=db.execute('SELECT storage_key FROM managed_objects').fetchone()[0]
    version=trash(client,headers,a);finish(settings,submit(client,headers,a,version).json()['job_id'])
    assert gc(settings,now=time.time()+RETENTION_SECONDS*2)['deleted_objects']==0
    with app.state.storage.open(key) as stream:assert stream.read()==b'shared'
    version=trash(client,headers,b);finish(settings,submit(client,headers,b,version).json()['job_id'])
    assert gc(settings)['deleted_objects']==0
    assert gc(settings,now=time.time()+RETENTION_SECONDS*2)['deleted_objects']==1
    assert app.state.storage.probe(key)=='missing'
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0


def test_orphan_gc_two_pass_grace_symlinks_and_active_registration_lock(api,tmp_path):
    app,settings,_,_,space=api
    obj=app.state.storage.put(io.BytesIO(b'orphan'),max_bytes=10)
    assert gc(settings)['discovered']==1
    assert app.state.storage.probe(obj.storage_key)=='available'
    assert gc(settings,now=time.time()+RETENTION_SECONDS*2)['deleted_objects']==1
    obj=app.state.storage.put(io.BytesIO(b'pending'),max_bytes=10)
    called=threading.Event();release=threading.Event()
    original=app.state.documents.verify_object
    def pause(item):original(item);called.set();assert release.wait(5)
    app.state.documents.verify_object=pause
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            registration=executor.submit(app.state.documents.register_managed,obj,Registration(space_id=space,title='Pinned',original_filename='p.txt',mime_type='text/plain'))
            assert called.wait(5)
            with pytest.raises(StorageBusy):
                with app.state.storage.locked(exclusive=True):pass
            release.set();registration.result()
    finally:release.set();app.state.documents.verify_object=original
    external=tmp_path/'outside';external.write_bytes(b'do not delete')
    fake=app.state.storage.root/'sha256'/'aa';fake.mkdir(exist_ok=True)
    (fake/('a'*64+'-13')).symlink_to(external)
    assert gc(settings,now=time.time()+RETENTION_SECONDS*2)['deleted_objects']==0
    assert external.read_bytes()==b'do not delete'


def test_gc_keeps_trashed_documents_historical_revisions_until_purge(api):
    app,settings,client,headers,space=api
    saved=upload(client,headers,space,b'old history');id=saved['document_id']
    obj=app.state.storage.put(io.BytesIO(b'new bytes'),max_bytes=20)
    from juanzhan.documents import RevisionChange
    app.state.documents.append_managed_revision(id,obj,RevisionChange(expected_document_version=1,original_filename='new.txt',mime_type='text/plain'))
    version=trash(client,headers,id)
    assert gc(settings,now=time.time()+RETENTION_SECONDS*2)['deleted_objects']==0
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM file_revisions WHERE document_id=?',(id,)).fetchone()[0]==2
    finish(settings,submit(client,headers,id,version).json()['job_id'])
    assert gc(settings,now=time.time()+RETENTION_SECONDS*2)['deleted_objects']==2


def test_invalid_due_candidate_does_not_block_followup_for_new_orphans(api):
    app,settings,_,_,_=api
    app.state.storage.put(io.BytesIO(b'future orphan'),max_bytes=20)
    with connect(settings.database) as db:
        db.execute('INSERT INTO managed_gc_candidates VALUES (?,?)',('invalid-key',time.time()-1));db.commit()
    assert gc(settings)['discovered']==1
    with connect(settings.database) as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE target_type='managed_objects' AND available_at>?",(time.time(),)).fetchone()[0]>=1
