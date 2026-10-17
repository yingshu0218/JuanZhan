import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.jobs import JobQueue, LostLease
from juanzhan.source_scans import preview
from juanzhan.worker import Worker

ROOT = '/sys/devices/system/cpu/cpu0/topology'


@pytest.fixture
def api(tmp_path):
    settings = Settings(tmp_path/'data', '', source_mounts=(('docs', ROOT), ('same', ROOT),
        ('parent', '/sys'), ('writable', str(tmp_path)), ('other', '/sys/kernel')))
    with TestClient(create_app('archive', settings), base_url='https://archive.test') as client:
        set_password(settings, 'source-test-password')
        csrf = client.get('/api/v1/auth/session').json()['csrf_token']
        csrf = client.post('/api/v1/auth/login', json={'username':'admin','password':'source-test-password'},
                          headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        headers = {'X-CSRF-Token':csrf}
        space = client.post('/api/v1/spaces', json={'name':'Sources'}, headers=headers).json()['id']
        yield settings, client, headers, space


def create(client, headers, space, **values):
    return client.post('/api/v1/sources', headers=headers, json={
        'space_id':space, 'name':'Read only', 'kind':'external', 'root_alias':'docs',
        'initial_import_policy':'flat', **values})


def submit(client, headers, source):
    return client.post('/api/v1/sources/'+source+'/preview-scan', headers=headers)


def state(settings, run_id):
    with connect(settings.database) as db:
        return db.execute('SELECT status,result_json,error_json,finished_at FROM scan_runs WHERE id=?', (run_id,)).fetchone()


def test_registration_queries_csrf_overlap_and_boundaries(api):
    settings, client, headers, space = api
    assert create(client, {}, space).status_code == 403
    source = create(client, headers, space, initial_import_policy='tree', initial_triage_status='needs_review').json()
    assert source['root_alias']=='docs' and source['status']=='ready'
    assert ROOT not in json.dumps(source) and 'root_ref' not in source
    assert source['initial_import_completed_at'] is None and source['last_successful_scan_at'] is None
    assert client.get('/api/v1/sources?space_id='+space).json()==[source]
    assert client.get('/api/v1/sources/'+source['id']).json()==source
    for alias in ('docs','same','parent'):
        response=create(client, headers, space, root_alias=alias)
        assert response.status_code==409 and response.json()['error']['code']=='SOURCE_OVERLAP'
    for values in ({'root_alias':'/etc'}, {'root_alias':'unknown'}, {'root_alias':'writable'},
                   {'scan_interval_minutes':True}, {'kind':'managed'}, {'root_path':'/etc'},
                   {'initial_target_folder_id':'missing'}):
        assert create(client,headers,space,**values).status_code in (404,422)
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    folder=client.post('/api/v1/folders',headers=headers,json={'space_id':other,'name':'Wrong space'}).json()['id']
    assert create(client,headers,space,initial_target_folder_id=folder).status_code==422
    assert client.get('/api/v1/sources?space_id=absent').status_code==404
    assert client.get('/api/v1/sources/absent').status_code==404
    # Distinct, non-overlapping physical root is allowed, regardless of space.
    assert create(client,headers,other,root_alias='other').status_code==201


def test_real_worker_preview_is_durable_coalesced_and_not_import(api):
    settings,client,headers,space=api
    source=create(client,headers,space).json()['id']
    assert submit(client,{},source).status_code==403
    first=submit(client,headers,source)
    assert first.status_code==202
    job_id=first.json()['job_id']
    assert submit(client,headers,source).json()['job_id']==job_id
    assert client.get('/api/v1/sources/'+source).json()['status']=='scanning'
    assert Worker(settings).run_once()=={'job_id':job_id,'status':'completed'}
    job=JobQueue(settings).get(job_id)
    assert job['result']['source_id']==source and job['result']['estimated_files']==0
    assert job['result']['ignored_files']>0
    assert job['result']['warnings']==['METADATA_ESTIMATE_NOT_SNAPSHOT','IGNORED_UNSUPPORTED_UNSAFE_OR_INVALID_ENTRIES']
    with connect(settings.database) as db:
        run_id=db.execute('SELECT target_id FROM jobs WHERE id=?',(job_id,)).fetchone()[0]
        for table in ('documents','source_entries','file_revisions'):
            assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
    run=state(settings,run_id)
    assert run[0]=='completed' and json.loads(run[1])==job['result'] and run[3]
    with TestClient(create_app('archive',settings),base_url='https://archive.test') as restarted:
        restarted.cookies.update(client.cookies)
        assert restarted.get('/api/v1/jobs/'+job_id).json()['result']==job['result']
        fresh=restarted.get('/api/v1/sources/'+source).json()
        assert fresh['status']=='ready' and fresh['last_successful_scan_at'] is None
        assert fresh['initial_import_completed_at'] is None
    assert submit(client,headers,source).json()['job_id']!=job_id


def test_entries_literal_segment_prefix_pagination_and_offline_preservation(api,tmp_path):
    settings,client,headers,space=api
    source=create(client,headers,space).json()['id']
    with connect(settings.database) as db:
        for index,path in enumerate(('a/doc.txt','ab/doc.txt','a%/doc.txt','a_/doc.txt','a/next.txt')):
            db.execute('INSERT INTO source_entries(id,source_id,space_id,relative_path_norm,relative_path_display,size_bytes,status,created_at,updated_at) '
                "VALUES (?,?,?,?,?,7,'available','2026-10-17','2026-10-17')",(str(index),source,space,path,path))
        db.commit()
    path='/api/v1/sources/'+source+'/entries'
    page=client.get(path,params={'relative_prefix':'a','page_size':1}).json()
    assert page['total']==2 and page['items'][0]['relative_path']=='a/doc.txt'
    assert client.get(path,params={'relative_prefix':'a','page':2,'page_size':1}).json()['items'][0]['relative_path']=='a/next.txt'
    assert client.get(path,params={'relative_prefix':'a%'}).json()['total']==1
    assert client.get(path,params={'relative_prefix':'a_'}).json()['total']==1
    for prefix in ('../a','/a','a/','a//b'):
        assert client.get(path,params={'relative_prefix':prefix}).status_code==422
    assert client.get(path,params={'page_size':101}).status_code==422
    assert client.get(path,params={'page':0}).status_code==422
    offline=replace(settings,source_mounts=(('docs',str(tmp_path/'missing')),))
    with TestClient(create_app('archive',offline),base_url='https://archive.test') as second:
        second.cookies.update(client.cookies)
        assert second.get('/api/v1/sources/'+source).json()['status']=='offline'
        assert second.get(path).json()['total']==5
        assert all(x['status']=='available' for x in second.get(path).json()['items'])
        assert submit(second,headers,source).status_code==422


def test_offline_retry_and_recovery_do_not_mark_missing(api,tmp_path):
    settings,client,headers,space=api
    source=create(client,headers,space).json()['id']
    job_id=submit(client,headers,source).json()['job_id']
    offline=replace(settings,source_mounts=(('docs',str(tmp_path/'gone')),))
    assert Worker(offline).run_once()['status']=='queued'
    job=JobQueue(settings).get(job_id)
    assert job['error']['code']=='SOURCE_OFFLINE' and job['attempts']==1
    with connect(settings.database) as db:
        run_id=db.execute('SELECT target_id FROM jobs WHERE id=?',(job_id,)).fetchone()[0]
        assert db.execute('SELECT status FROM sources WHERE id=?',(source,)).fetchone()[0]=='offline'
    assert state(settings,run_id)[0]=='queued'
    JobQueue(settings).retry(job_id)
    assert Worker(settings).run_once()['status']=='completed'
    assert state(settings,run_id)[0]=='completed'
    assert client.get('/api/v1/sources/'+source).json()['status']=='ready'


def test_preview_failure_limits_and_lease_fence(api):
    settings,client,headers,space=api
    source=create(client,headers,space).json()['id']
    job_id=submit(client,headers,source).json()['job_id']
    clock=[2000000000.0]
    queue=JobQueue(settings,clock=lambda:clock[0])
    job=queue.claim('first',lease_seconds=1)
    assert job['id']==job_id
    from juanzhan.source_paths import SourcePathError
    with pytest.raises(SourcePathError,match='SOURCE_PREVIEW_LIMIT'):
        preview(settings,job,max_entries=0)
    result=preview(settings,job)
    clock[0]+=2
    with pytest.raises(LostLease):
        queue.complete(job_id,job['lease_token'],result)
    assert state(settings,job['target_id'])[0]=='running'
    assert queue.claim('replacement') is None  # Recovery queues a bounded retry delay.
    assert state(settings,job['target_id'])[0]=='queued'
    clock[0]+=2
    retry=queue.claim('replacement')
    assert retry['attempts']==2
    assert queue.complete(job_id,retry['lease_token'],result)
    assert not queue.complete(job_id,job['lease_token'],{'wrong':True})
    assert json.loads(state(settings,job['target_id'])[1])==result


def test_terminal_failure_updates_run_and_keeps_import_markers_empty(api):
    settings,client,headers,space=api
    source=create(client,headers,space).json()['id']
    id=submit(client,headers,source).json()['job_id']
    queue=JobQueue(settings)
    job=queue.claim('preview')
    queue.failure(id,job['lease_token'],'JOB_TIMEOUT','Job execution deadline exceeded',retryable=False)
    run=state(settings,job['target_id'])
    assert run[0]=='failed' and run[1] is None and run[3]
    assert json.loads(run[2])['code']=='JOB_TIMEOUT'
    response=client.get('/api/v1/sources/'+source).json()
    assert response['status']=='error' and response['health']['mount_status']=='ready'
    assert response['last_successful_scan_at'] is None and response['initial_import_completed_at'] is None
    with connect(settings.database) as db:
        db.execute("UPDATE sources SET status='disabled' WHERE id=?",(source,))
        db.commit()
    assert submit(client,headers,source).status_code==409
    assert client.get('/api/v1/sources/'+source).json()['status']=='disabled'


def test_removed_preview_target_does_not_block_the_queue(api):
    settings,_,_,_=api
    from juanzhan.jobs import JobSpec
    queue=JobQueue(settings)
    missing=queue.enqueue(JobSpec(kind='scan_preview',target_type='source_preview',target_id='removed',idempotency_key='removed-run'))
    assert Worker(settings).run_once()=={'job_id':missing['id'],'status':'failed'}
    assert queue.get(missing['id'])['error']['code']=='INVALID_SOURCE_PREVIEW'
    assert Worker(settings).run_once() is None
