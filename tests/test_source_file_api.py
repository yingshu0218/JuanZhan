import json
import sqlite3
import uuid
from io import BytesIO
from test_parsing import pipeline,upload,append
from test_sources import api,ROOT
from test_source_incremental import seed,item,entries
from juanzhan.worker import Worker
from juanzhan.database import connect
from juanzhan.storage import ManagedStore

def test_explicit_external_snapshot_task_and_version_inventory(api):
    from pathlib import Path
    settings,client,headers,space=api
    body=Path(ROOT,'core_id').read_bytes();source=seed(api,[item('core_id',body)])
    document=entries(api,source)[0]['document_id'];doc=client.get('/api/v1/documents/'+document).json()
    path='/api/v1/documents/'+document
    before=client.get(path+'/source-files').json()
    assert before['items'][0]['server_copy'] is False
    payload={'expected_document_version':doc['document_version'],'revision_id':doc['current_revision_id'],'request_id':'explicit-snapshot'}
    assert client.post(path+'/source-snapshot',json=payload).status_code==403
    accepted=client.post(path+'/source-snapshot',headers=headers,json=payload)
    assert accepted.status_code==202,accepted.text
    assert client.post(path+'/source-snapshot',headers=headers,json=payload).json()==accepted.json()
    for _ in range(4):
        Worker(settings).run_once()
        if client.get('/api/v1/jobs/'+accepted.json()['job_id']).json()['status']=='completed':break
    final=client.get('/api/v1/jobs/'+accepted.json()['job_id']).json()
    assert final['status']=='completed',final
    inventory=client.get(path+'/source-files').json()
    assert inventory['items'][0]['server_copy'] and inventory['items'][0]['storage_kind']=='external'
    assert inventory['items'][0]['source']['id']==source
    assert ROOT not in json.dumps(inventory)
    assert client.get(path+'/download').content==body

def test_current_revision_protected_and_explicit_historical_cleanup(pipeline):
    settings,client,headers,space=pipeline
    saved=upload(pipeline,b'old original');document=saved['document_id']
    old=client.get('/api/v1/documents/'+document).json()['current_revision_id']
    # Queue cancellation is an explicit fixture step; active tasks are separately tested below.
    with connect(settings.database) as db:
        db.execute("UPDATE jobs SET status='cancelled' WHERE id=?",(saved['job_id'],));db.commit()
    current=append(settings,document,b'new original')
    doc=client.get('/api/v1/documents/'+document).json();version=doc['document_version']
    def body(id):return {'expected_document_version':version,'revision_id':id,'confirm_revision_id':id,'request_id':uuid.uuid4().hex}
    assert client.request('DELETE',f'/api/v1/documents/{document}/revisions/{current}',headers=headers,json=body(current)).status_code==409
    accepted=client.request('DELETE',f'/api/v1/documents/{document}/revisions/{old}',headers=headers,json=body(old))
    assert accepted.status_code==202,accepted.text
    for _ in range(4):
        Worker(settings).run_once()
        if client.get('/api/v1/jobs/'+accepted.json()['job_id']).json()['status']=='completed':break
    job=client.get('/api/v1/jobs/'+accepted.json()['job_id']).json()
    assert job['status']=='completed',job
    assert client.get('/api/v1/documents/'+document+'/download').content==b'new original'
    assert client.get('/api/v1/documents/'+document+'/download',params={'revision_id':old}).status_code==404

def test_storage_registered_accounting_and_preview_cache_cleanup(pipeline):
    settings,client,headers,space=pipeline
    saved=upload(pipeline,b'accounting original');document=saved['document_id']
    revision=client.get('/api/v1/documents/'+document).json()['current_revision_id']
    store=ManagedStore(settings.data_dir/'derived');store.initialize();obj=store.put(BytesIO(b'%PDF-cache-test'),max_bytes=1024)
    with connect(settings.database) as db:
        db.execute('INSERT INTO reading_previews VALUES (?,?,?,?,?,?)',(revision,obj.storage_key,obj.sha256,obj.size_bytes,'fixture','2026-10-21T00:00:00Z'));db.commit()
    usage=client.get('/api/v1/system/storage').json()
    assert usage['physical_original_bytes']==len(b'accounting original')
    assert usage['reading_preview_bytes']==len(b'%PDF-cache-test') and usage['reading_preview_count']==1
    payload={'kind':'reading_previews','confirm':True,'request_id':'clear-reading-cache'}
    assert client.post('/api/v1/system/storage/cleanup',headers=headers,json={**payload,'confirm':1}).status_code==422
    assert client.post('/api/v1/system/storage/cleanup',json=payload).status_code==403
    accepted=client.post('/api/v1/system/storage/cleanup',headers=headers,json=payload)
    assert accepted.status_code==202,accepted.text
    for _ in range(4):
        Worker(settings).run_once()
        if client.get('/api/v1/jobs/'+accepted.json()['job_id']).json()['status']=='completed':break
    assert client.get('/api/v1/system/storage').json()['reading_preview_count']==0
    assert client.get('/api/v1/documents/'+document+'/download').content==b'accounting original'
    # Physical cleanup is deferred and existing bytes remain until reference-safe GC.
    with store.open(obj.storage_key) as file:assert file.read()==b'%PDF-cache-test'

def test_reading_preview_guard_and_version_ownership(pipeline):
    settings,client,headers,space=pipeline
    one=upload(pipeline,b'one')['document_id'];two=upload(pipeline,b'two')['document_id']
    a=client.get('/api/v1/documents/'+one).json();b=client.get('/api/v1/documents/'+two).json()
    assert client.get('/api/v1/documents/'+one+'/reading-preview',params={'revision_id':b['current_revision_id']}).status_code==404
    status=client.get('/api/v1/documents/'+one+'/reading-preview').json()
    assert status['supported'] is False and status['state']=='not_generated'
    request={'expected_document_version':a['document_version'],'revision_id':a['current_revision_id'],'request_id':'unsupported-file'}
    assert client.post('/api/v1/documents/'+one+'/reading-preview',headers=headers,json=request).status_code==422
    assert client.get('/api/v1/documents/'+one+'/reading-preview/file',params={'revision_id':a['current_revision_id']}).status_code==404


def test_bulk_snapshot_pagination_and_replay_preserves_source(api):
    from pathlib import Path
    settings,client,headers,space=api
    names=['core_id','physical_package_id']
    originals={name:Path(ROOT,name).read_bytes() for name in names}
    source=seed(api,[item(name,body,hint='1:'+str(i)) for i,(name,body) in enumerate(originals.items())])
    # Isolate explicit migration from independently scheduled parsing.
    with connect(settings.database) as db:
        db.execute("UPDATE jobs SET status='cancelled' WHERE kind='parse' AND status='queued'");db.commit()
    path=f'/api/v1/sources/{source}/source-snapshots'
    payload={'request_id':'bulk-two-pages','page_size':1}
    receipt=client.post(path,headers=headers,json=payload)
    assert receipt.status_code==202,receipt.text
    assert client.post(path,headers=headers,json=payload).json()==receipt.json()
    assert client.post(path,headers=headers,json={**payload,'page_size':2}).status_code==409
    for _ in range(10):Worker(settings).run_once()
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM revision_snapshots').fetchone()[0]==2
        parents=db.execute("SELECT status,result_json FROM jobs WHERE target_type='source_snapshot_batch'").fetchall()
        assert len(parents)==2 and all(row[0]=='completed' for row in parents),parents
        assert sum(json.loads(row[1])['scheduled_count'] for row in parents)==2
    for entry in entries(api,source):
        path='/api/v1/documents/'+entry['document_id']
        inventory=client.get(path+'/source-files').json()['items'][0]
        assert inventory['server_copy'] and inventory['source']['id']==source
        assert client.get(path+'/download').content==originals[inventory['original_filename']]


def test_historical_cleanup_protects_successful_overview_and_active_tasks(pipeline):
    settings,client,headers,space=pipeline
    first=upload(pipeline,b'original overview source');document=first['document_id']
    path='/api/v1/documents/'+document
    old=client.get(path).json()['current_revision_id']
    for _ in range(4):
        Worker(settings).run_once()
        if client.get('/api/v1/jobs/'+first['job_id']).json()['status']=='completed':break
    assert client.get('/api/v1/jobs/'+first['job_id']).json()['status']=='completed'
    append(settings,document,b'updated original, previous overview remains')
    before=client.get(path).json()
    body={'expected_document_version':before['document_version'],'revision_id':old,'confirm_revision_id':old,'request_id':'protected-overview'}
    rejected=client.request('DELETE',path+'/revisions/'+old,headers=headers,json=body)
    assert rejected.status_code==409 and rejected.json()['error']['code']=='SUCCESSFUL_CONTENT_PROTECTED'
    assert client.get(path+'/download',params={'revision_id':old}).content==b'original overview source'
    second=upload(pipeline,b'active parse original');other=second['document_id'];other_path='/api/v1/documents/'+other
    busy_revision=client.get(other_path).json()['current_revision_id']
    append(settings,other,b'next revision')
    other_doc=client.get(other_path).json()
    body={'expected_document_version':other_doc['document_version'],'revision_id':busy_revision,'confirm_revision_id':busy_revision,'request_id':'protected-active-job'}
    rejected=client.request('DELETE',other_path+'/revisions/'+busy_revision,headers=headers,json=body)
    assert rejected.status_code==409 and rejected.json()['error']['code']=='REVISION_BUSY'
