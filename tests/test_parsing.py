"""Actual Archive upload/SQLite/store -> real HTTP Converter -> durable fenced parse."""
from io import BytesIO
from dataclasses import replace
import hashlib
import json
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.conversion_store import ConverterConfig
from juanzhan.database import connect
from juanzhan.documents import DocumentService,RevisionChange
from juanzhan.jobs import JobQueue,JobSpec,LostLease
from juanzhan.parsing import begin,execute,publish,ParseFailure
from juanzhan.storage import ManagedStore
from juanzhan.worker import Worker
from test_converter import real_server
from format_samples import samples,raster_sample

@pytest.fixture
def pipeline(tmp_path,monkeypatch):
    settings=Settings(tmp_path/'archive','pipeline-token',cookie_secure=False)
    converter=create_app('converter',Settings(tmp_path/'unused','pipeline-token'),
                         converter_config=ConverterConfig(root=tmp_path/'spool'))
    app=create_app('archive',settings)
    with real_server(converter) as base,TestClient(app) as client:
        monkeypatch.setenv('CONVERTER_URL',base)
        set_password(settings,'pipeline-password')
        csrf=client.get('/api/v1/auth/session').json()['csrf_token']
        csrf=client.post('/api/v1/auth/login',json={'username':'admin','password':'pipeline-password'},headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        headers={'X-CSRF-Token':csrf}
        space=client.post('/api/v1/spaces',json={'name':'Parse'},headers=headers).json()['id']
        yield settings,client,headers,space


def upload(pipeline,content=b'Actual persisted text',name='file.txt'):
    settings,client,headers,space=pipeline
    response=client.post('/api/v1/documents/upload',headers=headers,data={'space_id':space},files={'file':(name,content)})
    assert response.status_code==201,response.text
    return response.json()


def rows(settings,sql,*params):
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute(sql,params)]


def queue_parse(settings,document,revision,**extra):
    return JobQueue(settings).enqueue(JobSpec(kind='parse',target_type='document',target_id=document,
        payload={'revision_id':revision,**extra},idempotency_key=uuid.uuid4().hex))


def append(settings,document,content):
    store=ManagedStore(settings.data_dir/'managed')
    obj=store.put(BytesIO(content),max_bytes=1024*1024)
    service=DocumentService(settings)
    current=service.get_record(document)
    return service.append_managed_revision(document,obj,RevisionChange(original_filename='next.txt',mime_type='text/plain',expected_document_version=current['document_version']))['current_revision_id']

@pytest.mark.parametrize('kind',list(samples()))
def test_six_real_formats_automatically_persist(pipeline,kind):
    settings,client,headers,_=pipeline
    mime,content=samples()[kind];uploaded=upload(pipeline,content,'sample.'+kind)
    before=client.get('/api/v1/documents/'+uploaded['document_id']).json()
    assert Worker(settings).run_once()['status']=='completed'
    job=JobQueue(settings).get(uploaded['job_id'])
    run=job['result']['parse_run_id']
    assert rows(settings,'SELECT status FROM parse_runs WHERE id=?',run)[0]['status']=='completed'
    assert rows(settings,'SELECT * FROM content_blocks WHERE parse_run_id=?',run)
    assets=rows(settings,'SELECT * FROM derived_assets WHERE parse_run_id=?',run)
    assert {a['asset_kind'] for a in assets}>={'json','plain_text','markdown'}
    store=ManagedStore(settings.data_dir/'derived')
    for asset in assets:
        with store.open(asset['storage_key']) as file:
            data=file.read();assert hashlib.sha256(data).hexdigest()==asset['sha256']
            if asset['asset_kind']=='json':assert json.loads(data)['parse_run_id']==run
    after=client.get('/api/v1/documents/'+uploaded['document_id']).json()
    assert after['current_parse_run_id']==run and after['processing_status']=='completed' and not after['content_stale']
    assert all(after[k]==before[k] for k in ('title','document_version','folder_id','tag_ids','triage_status'))
    assert not rows(settings,'PRAGMA foreign_key_check')


def test_failed_new_revision_retains_successful_content_and_business_fields(pipeline):
    settings,client,headers,_=pipeline;uploaded=upload(pipeline)
    Worker(settings).run_once()
    old=client.get('/api/v1/documents/'+uploaded['document_id']).json()['current_parse_run_id']
    revision=append(settings,uploaded['document_id'],b'%PDF-1.4\nmalformed')
    job=queue_parse(settings,uploaded['document_id'],revision)
    Worker(settings).run_once()
    assert JobQueue(settings).get(job['id'])['status']=='failed'
    after=client.get('/api/v1/documents/'+uploaded['document_id']).json()
    assert after['current_parse_run_id']==old and after['content_stale'] and after['processing_status']=='failed'
    assert rows(settings,'SELECT * FROM content_blocks WHERE parse_run_id=?',old)
    assert len(rows(settings,'SELECT * FROM parse_runs'))==2


def test_unsupported_does_not_promote(pipeline):
    settings,client,_,_=pipeline;uploaded=upload(pipeline,b'\x00unknown','sample.bin')
    assert Worker(settings).run_once()['status']=='completed'
    job=JobQueue(settings).get(uploaded['job_id']);assert job['result']['status']=='unsupported'
    assert rows(settings,'SELECT status FROM parse_runs')[0]['status']=='unsupported'
    assert not client.get('/api/v1/documents/'+uploaded['document_id']).json()['current_parse_run_id']
    assert not rows(settings,'SELECT * FROM derived_assets')


def test_real_ocr_and_duplicate_frame_assets_preserve_order(pipeline):
    settings,client,_,_=pipeline;uploaded=upload(pipeline,raster_sample('TIFF',pages=2),'scan.tiff')
    # Replace pending parse options through a new request; superseded job must not publish.
    queue=JobQueue(settings)
    first=queue.claim('fixture');queue.failure(first['id'],first['lease_token'],'SUPERSEDED','Test setup',retryable=False)
    job=queue_parse(settings,uploaded['document_id'],uploaded['revision_id'],ocr_enabled=True,ocr_languages='eng')
    assert Worker(settings).run_once()['status']=='completed'
    run=queue.get(job['id'])['result']['parse_run_id']
    assert rows(settings,'SELECT ocr_used FROM parse_runs WHERE id=?',run)[0]['ocr_used']==1
    assert {json.loads(b['locator_json'])['page'] for b in rows(settings,'SELECT * FROM content_blocks WHERE parse_run_id=?',run)}=={1,2}
    links=rows(settings,'SELECT * FROM parse_asset_order WHERE parse_run_id=? ORDER BY asset_index',run)
    assert len(links)==5 and links[2]['derived_asset_id']==links[3]['derived_asset_id']


def test_lost_lease_fails_attempt_then_retry_has_new_run(pipeline):
    settings,_,_,_=pipeline;uploaded=upload(pipeline)
    queue=JobQueue(settings);job=queue.claim('old',lease_seconds=.01)
    options,_=begin(settings,job)
    time.sleep(.02)
    queue.claim('recovery')  # Expired lease is persisted, backoff prevents immediate reclaim.
    assert rows(settings,'SELECT status FROM parse_runs WHERE id=?',options.parse_run_id)[0]['status']=='failed'
    with pytest.raises(LostLease):queue.complete(job['id'],job['lease_token'],{})
    queue.retry(job['id'])
    assert Worker(settings).run_once()['status']=='completed'
    assert len(rows(settings,'SELECT * FROM parse_runs'))==2
    assert queue.get(job['id'])['result']['parse_run_id']!=options.parse_run_id
    assert len(rows(settings,"SELECT * FROM jobs WHERE target_type='derived_objects'"))==2  # Each retry needs its own delayed recovery, even after an earlier GC completed.


@pytest.mark.parametrize('change',['request','revision','trash'])
def test_newer_request_and_revision_and_trash_fence_publication(pipeline,change):
    settings,_,_,_=pipeline;uploaded=upload(pipeline)
    queue=JobQueue(settings);job=queue.claim('old');options,revision=begin(settings,job)
    # Real converter result, before Archive commit, remains untrusted for promotion after a new request.
    from juanzhan.converter_client import ConverterClient
    import os
    converter=ConverterClient(os.environ['CONVERTER_URL'],settings.converter_token)
    with ManagedStore(settings.data_dir/'managed').open(rows(settings,'SELECT storage_key FROM managed_objects')[0]['storage_key']) as file:remote=converter.submit(file,options)['job_id']
    converter.wait(remote);result=converter.result(remote,file_revision_id=revision['id'],parse_run_id=options.parse_run_id)
    if change=='request':queue_parse(settings,uploaded['document_id'],revision['id'])
    elif change=='revision':append(settings,uploaded['document_id'],b'new revision')
    else:
        from juanzhan.documents import VersionChange
        DocumentService(settings).trash(uploaded['document_id'],VersionChange(expected_document_version=1))
    queue.complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,options,result,[]))
    assert queue.get(job['id'])['result']['status']=='discarded'
    assert not rows(settings,'SELECT current_parse_run_id FROM documents')[0]['current_parse_run_id']
    converter.delete(remote)


def test_integrity_failure_keeps_original_and_no_partial_rows(pipeline):
    settings,_,_,_=pipeline;uploaded=upload(pipeline)
    key=rows(settings,'SELECT storage_key FROM managed_objects')[0]['storage_key']
    path=settings.data_dir/'managed'/key;path.chmod(0o600);path.write_bytes(b'x'*len(path.read_bytes()))
    assert Worker(settings).run_once()['status']=='failed'
    assert JobQueue(settings).get(uploaded['job_id'])['error']['code']=='ORIGINAL_INTEGRITY'
    assert not rows(settings,'SELECT * FROM derived_assets') and not rows(settings,'SELECT * FROM content_blocks')
    assert path.exists() and rows(settings,'SELECT status FROM parse_runs')[0]['status']=='failed'


def test_failed_same_revision_keeps_current_and_marks_stale(pipeline):
    settings,client,_,_=pipeline;uploaded=upload(pipeline)
    Worker(settings).run_once()
    old=client.get('/api/v1/documents/'+uploaded['document_id']).json()['current_parse_run_id']
    job=queue_parse(settings,uploaded['document_id'],uploaded['revision_id'])
    owned=JobQueue(settings).claim('failure');begin(settings,owned)
    JobQueue(settings).failure(owned['id'],owned['lease_token'],'CONVERSION_FAILED','Test injected failure',retryable=False)
    shown=client.get('/api/v1/documents/'+uploaded['document_id']).json()
    assert shown['current_parse_run_id']==old and shown['content_stale']


def test_publish_transaction_failure_orphans_are_safe_and_retry_reuses_files(pipeline,monkeypatch):
    import juanzhan.parsing as parsing
    settings,_,_,_=pipeline;uploaded=upload(pipeline)
    queue=JobQueue(settings);job=queue.claim('fixture');real_publish=parsing.publish
    def interrupted(db,owned,options,result,assets):
        real_publish(db,owned,options,result,assets)
        raise OSError('Injected crash before commit')
    monkeypatch.setattr(parsing,'publish',interrupted)
    with pytest.raises(OSError):execute(settings,job)
    assert not rows(settings,'SELECT * FROM content_blocks') and not rows(settings,'SELECT * FROM derived_assets')
    assert rows(settings,'SELECT current_parse_run_id FROM documents')[0]['current_parse_run_id'] is None
    orphans=list((settings.data_dir/'derived'/'sha256').glob('*/*'));assert orphans
    queue.failure(job['id'],job['lease_token'],'STORAGE_IO_ERROR','Injected',retryable=True)
    monkeypatch.setattr(parsing,'publish',real_publish)
    queue.retry(job['id']);assert Worker(settings).run_once()['status']=='completed'
    assert all(path.exists() for path in orphans)
    assert rows(settings,'SELECT * FROM derived_assets') and len(rows(settings,'SELECT * FROM parse_runs'))==2


def test_derived_gc_preserves_history_and_rechecks_references(pipeline):
    from juanzhan.derived import collect
    settings,_,_,_=pipeline;uploaded=upload(pipeline)
    Worker(settings).run_once()
    store=ManagedStore(settings.data_dir/'derived')
    orphan=store.put(BytesIO(b'orphan bytes'),max_bytes=100)
    queue=JobQueue(settings)
    gc=queue.enqueue(JobSpec(kind='gc',target_type='derived_objects',idempotency_key='test-gc'))
    job=queue.claim('gc');assert job['id']==gc['id']
    base=time.time()
    with store.locked(exclusive=True) as root:
        queue.complete(job['id'],job['lease_token'],lambda db,owned:collect(db,owned,root,settings,clock=lambda:base))
    assert rows(settings,'SELECT eligible_after FROM derived_gc_candidates WHERE storage_key=?',orphan.storage_key)[0]['eligible_after']==base+86400
    nextjob=queue.enqueue(JobSpec(kind='gc',target_type='derived_objects',idempotency_key='test-gc-later'))
    job=queue.claim('later');assert job['id']==nextjob['id']
    with store.locked(exclusive=True) as root:
        queue.complete(job['id'],job['lease_token'],lambda db,owned:collect(db,owned,root,settings,clock=lambda:base+86401))
    assert store.probe(orphan.storage_key)=='missing'
    for asset in rows(settings,'SELECT * FROM derived_assets'):
        with store.open(asset['storage_key']):pass


def test_upgrade_backfills_requests_without_replaying_old_jobs(tmp_path):
    import shutil
    from juanzhan.database import MIGRATIONS,migrate
    from juanzhan.documents import Registration
    settings=Settings(tmp_path/'legacy','token');settings.prepare_archive()
    legacy=tmp_path/'migrations';legacy.mkdir()
    for path in sorted(MIGRATIONS.glob('*.sql'))[:5]:shutil.copyfile(path,legacy/path.name)
    migrate(settings.database,migrations=legacy)
    store=ManagedStore(settings.data_dir/'managed');store.initialize()
    with connect(settings.database) as db:
        db.execute("INSERT INTO spaces VALUES ('space','Legacy','now','now')");db.commit()
        checksums=dict(db.execute('SELECT name,sha256 FROM migration_checksums'))
    doc=DocumentService(settings).register_managed(store.put(BytesIO(b'legacy'),max_bytes=100),Registration(space_id='space',title='Legacy',original_filename='legacy.txt',mime_type='text/plain'))
    with connect(settings.database) as db:
        for id,status in [('queued','queued'),('old-failed','failed')]:
            db.execute("INSERT INTO jobs(id,kind,target_type,target_id,status,payload_json,created_at,updated_at) VALUES (?,'parse','document',?,?,?,'before','before')",
                       (id,doc['id'],status,json.dumps({'revision_id':doc['current_revision_id']})))
        db.commit()
    migrate(settings.database);migrate(settings.database)
    assert {r['job_id'] for r in rows(settings,'SELECT * FROM parse_requests')}=={'queued','old-failed'}
    assert {r['id']:r['status'] for r in rows(settings,'SELECT * FROM jobs')}=={'queued':'queued','old-failed':'failed'}
    assert not rows(settings,'SELECT * FROM parse_runs')
    current={r['name']:r['sha256'] for r in rows(settings,'SELECT * FROM migration_checksums')}
    assert len(current)==len(list(MIGRATIONS.glob('*.sql'))) and all(current[k]==v for k,v in checksums.items())


def test_late_obsolete_attempt_does_not_shadow_newer_status(pipeline):
    settings,client,_,_=pipeline;uploaded=upload(pipeline)
    queue=JobQueue(settings);old=queue.claim('old')
    newer=queue_parse(settings,uploaded['document_id'],uploaded['revision_id'])
    new=queue.claim('new');execute(settings,new)
    successful=client.get('/api/v1/documents/'+uploaded['document_id']).json()['current_parse_run_id']
    execute(settings,old)  # It starts later but belongs to the older request sequence.
    shown=client.get('/api/v1/documents/'+uploaded['document_id']).json()
    assert shown['processing_status']=='completed' and not shown['content_stale']
    assert shown['current_parse_run_id']==successful
    assert queue.get(old['id'])['result']['status']=='discarded'


def test_database_rejects_cross_document_parse_and_asset_links(pipeline):
    settings,_,_,_=pipeline
    first=upload(pipeline,b'first');Worker(settings).run_once()
    second=upload(pipeline,b'second');Worker(settings).run_once()
    attempts=rows(settings,'SELECT * FROM parse_attempts')
    assets=rows(settings,'SELECT * FROM derived_assets WHERE parse_run_id=?',attempts[1]['parse_run_id'])
    with connect(settings.database) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('INSERT INTO parse_asset_order VALUES (?,?,?,NULL)',(attempts[0]['parse_run_id'],100,assets[0]['id']))
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE parse_asset_order SET derived_asset_id=? WHERE parse_run_id=?',(assets[0]['id'],attempts[0]['parse_run_id']))
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE parse_attempts SET request_sequence=? WHERE parse_run_id=?',(attempts[1]['request_sequence'],attempts[0]['parse_run_id']))
        db.rollback()
