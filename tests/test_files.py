"""Real HTTP originals/passive previews and integrity/ownership failures."""
import json
from fastapi.testclient import TestClient
from test_parsing import pipeline,upload,append,rows
from format_samples import raster_sample
from juanzhan.apps import create_app
from juanzhan.database import connect
from juanzhan.worker import Worker


def test_download_is_pinned_attachment_and_never_active_html(pipeline):
    settings,client,_,_=pipeline
    payload=b'<script>window.evil=true</script>'
    receipt=upload(pipeline,payload,'untrusted.html');root='/api/v1/documents/'+receipt['document_id']
    response=client.get(root+'/download');assert response.status_code==200
    assert response.content==payload
    assert response.headers['content-type']=='application/octet-stream'
    assert response.headers['content-disposition'].startswith('attachment;')
    assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'
    assert 'sandbox' in response.headers['content-security-policy']
    revision=client.get(root).json()['current_revision_id']
    assert client.get(root+'/download?expected_revision_id=wrong').status_code==409
    assert client.get(root+'/preview').json()['items']==[]
    append(settings,receipt['document_id'],b'next original')
    assert client.get(root+'/download?expected_revision_id='+revision).status_code==409
    assert client.get(root+'/download').content==b'next original'
    with TestClient(create_app('archive',settings)) as stranger:
        for path in ('/download','/preview','/preview/missing?expected_revision_id='+revision):
            assert stranger.get(root+path).status_code==401
    assert client.get('/api/v1/documents/missing/download').status_code==404


def test_real_pdf_passive_preview_ownership_stale_and_corruption(pipeline):
    settings,client,_,_=pipeline
    receipt=upload(pipeline,raster_sample('PDF'),'真实预览.pdf');Worker(settings).run_once()
    root='/api/v1/documents/'+receipt['document_id']
    manifest=client.get(root+'/preview').json();assert manifest['items']
    item=manifest['items'][0];url=root+'/preview/'+item['id']+'?expected_revision_id='+manifest['revision_id']
    response=client.get(url);assert response.status_code==200 and response.content.startswith(b'\x89PNG\r\n\x1a\n')
    assert response.headers['content-type']=='image/png' and response.headers['cache-control']=='no-store'
    other=upload(pipeline,b'other','other.txt')
    assert client.get('/api/v1/documents/'+other['document_id']+'/preview/'+item['id']+'?expected_revision_id='+other['revision_id']).status_code==404
    asset=rows(settings,'SELECT storage_key FROM derived_assets WHERE id=?',item['id'])[0]
    path=settings.data_dir/'derived'/asset['storage_key'];path.chmod(0o600);path.write_bytes(b'broken')
    assert client.get(url).status_code==409
    append(settings,receipt['document_id'],b'new current original')
    assert client.get(root+'/preview').status_code==409
    assert client.get(url).status_code==409


def test_corrupt_managed_original_never_returns_recorded_bytes(pipeline):
    settings,client,_,_=pipeline;receipt=upload(pipeline,b'good bytes')
    obj=rows(settings,'SELECT storage_key FROM managed_objects')[0]
    path=settings.data_dir/'managed'/obj['storage_key'];path.chmod(0o600);path.write_bytes(b'bad bytes!')
    response=client.get('/api/v1/documents/'+receipt['document_id']+'/download')
    assert response.status_code==409 and str(settings.data_dir) not in response.text


from test_sources import api as source_api, create as create_source
from test_source_initial import scan
from dataclasses import replace


def test_readonly_external_download_offline_changed_and_boundary(source_api):
    settings,client,headers,space=source_api
    source=create_source(client,headers,space).json()['id']
    response=scan(client,headers,source);assert response.status_code==202
    # Register actual read-only sysfs bytes through the shared registration service;
    # sysfs names have no supported import extension, so this is not scan acceptance.
    from juanzhan.jobs import JobQueue
    from juanzhan.source_initial import register_external
    from juanzhan.source_paths import SourceMounts
    from juanzhan.document_events import utc_now
    from test_source_initial import source_row
    import hashlib,os
    observed=source_row(settings,source);job=JobQueue(settings).get(response.json()['job_id'])
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:
        content=file.read();info=os.fstat(file.fileno())
    item={'path':'core_id','size_bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),
          'mtime_ns':info.st_mtime_ns,'identity_hint':f'{info.st_dev}:{info.st_ino}',
          'mime_type':'text/plain','file_modified_at':None}
    with JobQueue(settings).write() as db:
        import sqlite3
        db.row_factory=sqlite3.Row
        register_external(db,job,observed,item,None,'filed',settings,utc_now())
    record=rows(settings,"SELECT d.id,r.id AS revision,e.relative_path_norm,s.root_ref FROM documents d JOIN file_revisions r ON r.id=d.current_revision_id JOIN source_entries e ON e.id=r.source_entry_id JOIN sources s ON s.id=e.source_id LIMIT 1")[0]
    root='/api/v1/documents/'+record['id']
    from juanzhan.source_paths import SourceMounts
    with SourceMounts(settings.source_mounts).open(record['root_ref'],record['relative_path_norm']) as file:expected=file.read()
    assert client.get(root+'/download').content==expected
    # Real unavailable and writable mount configurations must fail, without path disclosure.
    for mounts in ((('docs','/absent-readonly-source'),),(('docs',str(settings.data_dir)),)):
        with TestClient(create_app('archive',replace(settings,source_mounts=mounts)),base_url='https://archive.test') as other:
            csrf=other.get('/api/v1/auth/session').json()['csrf_token']
            assert other.post('/api/v1/auth/login',headers={'X-CSRF-Token':csrf},json={'username':'admin','password':'source-test-password'}).status_code==200
            response=other.get(root+'/download');assert response.status_code==409
            assert mounts[0][1] not in response.text
    with connect(settings.database) as db:
        db.execute("UPDATE file_revisions SET sha256=? WHERE id=?",('0'*64,record['revision']));db.commit()
    assert client.get(root+'/download').status_code==409
    with connect(settings.database) as db:
        db.execute("UPDATE source_entries SET relative_path_norm='../escape' WHERE document_id=?",(record['id'],));db.commit()
    assert client.get(root+'/download').status_code==409
