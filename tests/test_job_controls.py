import pytest
from test_parsing import pipeline,upload
from juanzhan.database import connect
from juanzhan.jobs import JobQueue,JobSpec,LostLease
from juanzhan.worker import Worker

def act(client,csrf,action,ids):
 r=client.post('/api/v1/jobs/control',headers=csrf,json={'action':action,'job_ids':ids});assert r.status_code==200,r.text;return r.json()

def test_pause_resume_cancel_delete_and_lease_fencing(pipeline):
 settings,client,csrf,_=pipeline;saved=upload(pipeline);queue=JobQueue(settings)
 claimed=queue.claim('test-owner');assert claimed['id']==saved['job_id']
 assert act(client,csrf,'pause',[claimed['id']])['succeeded']==1
 assert queue.get(claimed['id'])['status']=='paused'
 with pytest.raises(LostLease):queue.complete(claimed['id'],claimed['lease_token'],{'status':'bad'})
 assert queue.claim('other') is None
 assert client.get('/api/v1/jobs',params={'status':'paused'}).json()['total']==1
 assert client.get('/api/v1/jobs',params={'status':'queued'}).json()['total']==0
 assert act(client,csrf,'resume',[claimed['id']])['succeeded']==1
 assert queue.get(claimed['id'])['attempts']==1
 assert queue.get(claimed['id'])['max_attempts']==4
 assert Worker(settings).run_once()['status']=='completed'
 assert act(client,csrf,'cancel',[claimed['id']])['failed']==1
 assert act(client,csrf,'delete',[claimed['id']])['succeeded']==1
 assert queue.get(claimed['id'])['deleted']
 assert claimed['id'] not in {item['id'] for item in client.get('/api/v1/jobs').json()['items']}
 assert client.get('/api/v1/documents/'+saved['document_id']+'/download').content
 with connect(settings.database) as db:
  assert db.execute('select count(*) from jobs where id=?',(claimed['id'],)).fetchone()[0]==1
  assert db.execute('select count(*) from job_control_events').fetchone()[0]==3

def test_bulk_partial_failure_csrf_and_cancelled_parse_stays_pending(pipeline):
 settings,client,csrf,_=pipeline
 saved=upload(pipeline)
 assert client.post('/api/v1/jobs/control',json={'action':'pause','job_ids':[saved['job_id']]}).status_code==403
 result=act(client,csrf,'cancel',[saved['job_id'],'missing'])
 assert result['succeeded']==1 and result['failed']==1
 assert Worker(settings).run_once() is None
 assert act(client,csrf,'delete',[saved['job_id']])['succeeded']==1
 pending=client.get('/api/v1/pending-documents').json()
 assert pending['total']==1 and 'analysis' in pending['items'][0]['pending_reasons']
 assert client.get('/api/v1/documents/'+saved['document_id']+'/download').status_code==200

def test_pending_disappears_only_after_current_content_markdown_and_index(pipeline):
 from test_indexing import drain
 from juanzhan.markdown_copies import schedule
 settings,client,csrf,_=pipeline;saved=upload(pipeline)
 assert Worker(settings).run_once()['status']=='completed'
 pending=client.get('/api/v1/pending-documents').json();assert pending['total']==1
 assert 'analysis' not in pending['items'][0]['pending_reasons']
 schedule(settings)
 while Worker(settings).run_once():pass
 drain(settings)
 assert client.get('/api/v1/pending-documents').json()['total']==0
 # Completed task deletion does not change file completion.
 assert act(client,csrf,'delete',[saved['job_id']])['succeeded']==1
 assert client.get('/api/v1/pending-documents').json()['total']==0
 from test_parsing import append
 append(settings,saved['document_id'],b'new revision not processed')
 assert client.get('/api/v1/pending-documents').json()['total']==1

def test_pending_process_respects_policy_and_restores_cancelled_work(pipeline):
 from test_indexing import drain
 from juanzhan.markdown_copies import schedule
 settings,client,csrf,_=pipeline;saved=upload(pipeline)
 act(client,csrf,'cancel',[saved['job_id']])
 body={'request_id':'pending-test','documents':[{'id':saved['document_id'],'revision_id':saved['revision_id']}]}
 r=client.post('/api/v1/pending-documents/process',headers=csrf,json=body);assert r.status_code==200,r.text
 assert r.json()['succeeded']==1 and r.json()['items'][0]['job_ids']
 assert Worker(settings).run_once()['status']=='completed'
 schedule(settings)
 while Worker(settings).run_once():pass
 drain(settings)
 assert client.get('/api/v1/pending-documents').json()['total']==0


def slow_control_handler(job,data_dir,connection):
 import time
 time.sleep(20)
 connection.send(('success',{'should_not_publish':True}))

def test_running_worker_is_interrupted_and_cannot_publish_after_cancel(pipeline):
 import time
 from concurrent.futures import ThreadPoolExecutor
 settings,client,csrf,_=pipeline
 queue=JobQueue(settings)
 saved=queue.enqueue(JobSpec(kind='gc',target_type='controlled-test',idempotency_key='slow-controlled'))
 with ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(Worker(settings,handler=slow_control_handler,lease_seconds=3).run_once)
  deadline=time.monotonic()+10
  while queue.get(saved['id'])['status']!='running' and time.monotonic()<deadline:time.sleep(.02)
  assert queue.get(saved['id'])['status']=='running'
  assert act(client,csrf,'cancel',[saved['id']])['succeeded']==1
  assert future.result(timeout=8)['status']=='cancelled'
 assert queue.get(saved['id'])['result'] is None


def test_agent_current_analysis_satisfies_markdown_but_old_revision_does_not(pipeline):
 from test_agent_imports import token,imported,payload,ROOT
 from test_indexing import drain
 from test_parsing import append
 settings,client,csrf,_=pipeline;_,h=token(pipeline);saved=imported(pipeline,h).json()
 assert client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=payload(saved)).status_code==201
 assert Worker(settings).run_once()['status']=='completed';drain(settings)
 assert client.get('/api/v1/pending-documents').json()['total']==0
 append(settings,saved['document_id'],b'new original')
 assert client.get('/api/v1/pending-documents').json()['total']==1


def test_paused_parse_and_pending_process_respect_current_format_policy(pipeline):
 settings,client,csrf,_=pipeline;saved=upload(pipeline)
 act(client,csrf,'pause',[saved['job_id']])
 policy=client.get('/api/v1/system/upload-policy').json()
 assert client.put('/api/v1/system/upload-policy',headers=csrf,json={'expected_version':policy['version'],'excluded_groups':policy['excluded_groups'],'custom_extensions':['txt']}).status_code==200
 assert act(client,csrf,'resume',[saved['job_id']])['items'][0]['error_code']=='UPLOAD_FORMAT_EXCLUDED'
 pending=client.get('/api/v1/pending-documents').json()
 assert pending['total']==1 and pending['items'][0]['format_excluded']
 r=client.post('/api/v1/pending-documents/process',headers=csrf,json={'request_id':'blocked','documents':[{'id':saved['document_id'],'revision_id':saved['revision_id']}]})
 assert r.json()['failed']==1
 assert JobQueue(settings).get(saved['job_id'])['status']=='paused'


def test_backup_restore_keeps_paused_work_but_does_not_reenable_backup_operations(pipeline,tmp_path):
 from juanzhan.backup import create,restore
 from juanzhan.config import Settings
 settings,client,csrf,_=pipeline;saved=upload(pipeline)
 backup=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='system_backup',idempotency_key='restored-backup-paused'))
 act(client,csrf,'pause',[saved['job_id'],backup['id']])
 bundle=tmp_path/'bundle';create(settings,bundle);restore(bundle,tmp_path/'restored')
 restored=JobQueue(Settings(tmp_path/'restored',''))
 assert restored.get(saved['job_id'])['status']=='paused'
 assert restored.get(backup['id'])['status']=='cancelled'
 assert restored.claim('restored-owner') is None


def test_resume_started_parse_uses_new_attempt_number_and_preserves_history(pipeline):
 from juanzhan.parsing import begin
 settings,client,csrf,_=pipeline;saved=upload(pipeline);queue=JobQueue(settings)
 claimed=queue.claim('parse-owner');options,_=begin(settings,claimed)
 act(client,csrf,'pause',[claimed['id']]);act(client,csrf,'resume',[claimed['id']])
 assert Worker(settings).run_once()['status']=='completed'
 with connect(settings.database) as db:
  assert db.execute('select status from parse_runs where id=?',(options.parse_run_id,)).fetchone()[0]=='failed'
  assert db.execute('select attempt from parse_attempts order by attempt').fetchall()==[(1,),(2,)]
  assert db.execute('select max_attempts-attempts from jobs where id=?',(claimed['id'],)).fetchone()[0]==2


def test_agent_arriving_after_pending_requeue_skips_local_fallback(pipeline):
 from test_agent_imports import token,imported,payload,ROOT
 settings,client,csrf,_=pipeline;_,h=token(pipeline);saved=imported(pipeline,h).json()
 with connect(settings.database) as db:initial=db.execute("select id from jobs where kind='parse'").fetchone()[0]
 act(client,csrf,'cancel',[initial])
 body={'request_id':'agent-race','documents':[{'id':saved['document_id'],'revision_id':saved['revision_id']}]}
 assert client.post('/api/v1/pending-documents/process',headers=csrf,json=body).json()['succeeded']==1
 assert client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=payload(saved)).status_code==201
 assert Worker(settings).run_once()['status']=='completed'
 with connect(settings.database) as db:assert db.execute('select count(*) from parse_runs').fetchone()[0]==0
