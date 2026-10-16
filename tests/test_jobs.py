import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from pathlib import Path
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect, migrate
from juanzhan.document_events import record_event
from juanzhan.documents import Registration
from juanzhan.jobs import JobQueue, JobSpec, LostLease
from juanzhan.storage import ManagedStore
from juanzhan.worker import Worker


class Clock:
    value = 1000.0
    def __call__(self):
        return self.value
    def advance(self,seconds):
        self.value += seconds


@pytest.fixture
def queue(tmp_path):
    settings = Settings(tmp_path/'archive','converter-token')
    settings.prepare_archive()
    migrate(settings.database)
    store = ManagedStore(settings.data_dir/'managed')
    store.initialize()
    clock = Clock()
    return JobQueue(settings,clock), clock, settings, store


def spec(key='job',**overrides):
    return JobSpec(kind='gc',target_type='managed_staging',idempotency_key=key,**overrides)


def test_enqueue_idempotency_and_transaction_rollback(queue):
    jobs, clock, settings, store = queue
    first = jobs.enqueue(spec(payload={'a':1,'b':2}))
    assert jobs.enqueue(spec(payload={'b':2,'a':1}))['id']==first['id']
    with pytest.raises(HTTPException) as caught:
        jobs.enqueue(spec(payload={'a':3}))
    assert caught.value.detail['code']=='IDEMPOTENCY_CONFLICT'
    with connect(settings.database) as db:
        db.execute('BEGIN IMMEDIATE')
        rolled_back = jobs.enqueue(spec('rollback'),db=db)
        db.rollback()
    with pytest.raises(HTTPException):
        jobs.get(rolled_back['id'])
    with pytest.raises(ValueError):
        jobs.enqueue(spec(payload={'nan':float('nan')}))
    with pytest.raises(ValueError):
        jobs.enqueue(spec(payload={'large':'x'*65537}))


def test_concurrent_enqueue_and_claim_are_unique(queue):
    jobs, clock, settings, store = queue
    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda _:jobs.enqueue(spec())['id'],range(8)))
    assert len(set(ids))==1
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda i:jobs.claim('worker-'+str(i)),range(8)))
    assert sum(claim is not None for claim in claims)==1
    assert jobs.get(ids[0])['attempts']==1


def test_expired_lease_fences_old_worker_and_enforces_budget(queue):
    jobs, clock, settings, store = queue
    job = jobs.enqueue(spec(max_attempts=2))
    old = jobs.claim('old',lease_seconds=5)
    clock.advance(5)
    assert jobs.claim('new',lease_seconds=5) is None  # Bounded retry backoff.
    with pytest.raises(LostLease):
        jobs.heartbeat(job['id'],old['lease_token'])
    clock.advance(1)
    new = jobs.claim('new',lease_seconds=5)
    assert new['attempts']==2 and new['lease_token']!=old['lease_token']
    with pytest.raises(LostLease):
        jobs.complete(job['id'],old['lease_token'],{'stale':True})
    clock.advance(5)
    assert jobs.claim('third') is None
    terminal = jobs.get(job['id'])
    assert terminal['status']=='failed' and terminal['attempts']==2
    with pytest.raises(HTTPException):
        jobs.retry(job['id'])
    assert jobs.claim('fourth') is None


def test_database_effect_and_completion_commit_once(queue):
    jobs, clock, settings, store = queue
    with connect(settings.database) as db:
        db.execute("CREATE TABLE effects(id TEXT PRIMARY KEY, count INTEGER NOT NULL)")
        db.commit()
    job = jobs.enqueue(spec())
    claim = jobs.claim('worker')
    def apply(db,current):
        db.execute('INSERT INTO effects VALUES (?,1)',(current['id'],))
    assert jobs.complete(job['id'],claim['lease_token'],{'done':True},effect=apply)
    assert not jobs.complete(job['id'],claim['lease_token'],{'done':'duplicate'},effect=apply)
    with connect(settings.database) as db:
        assert db.execute('SELECT count FROM effects').fetchone()==(1,)
    assert jobs.get(job['id'])['result']=={'done':True}


def test_effect_failure_or_expired_commit_rolls_back(queue):
    jobs, clock, settings, store = queue
    with connect(settings.database) as db:
        db.execute('CREATE TABLE effects(id INTEGER PRIMARY KEY)')
        db.commit()
    job = jobs.enqueue(spec())
    claim = jobs.claim('worker',lease_seconds=5)
    def fails(db,current):
        db.execute('INSERT INTO effects VALUES (1)')
        raise RuntimeError('simulated effect failure')
    with pytest.raises(RuntimeError):
        jobs.complete(job['id'],claim['lease_token'],{},effect=fails)
    def expires(db,current):
        db.execute('INSERT INTO effects VALUES (1)')
        clock.advance(5)
    with pytest.raises(LostLease):
        jobs.complete(job['id'],claim['lease_token'],{},effect=expires)
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM effects').fetchone()==(0,)
    assert jobs.get(job['id'])['status']=='running'


def test_retry_classification_manual_and_progress(queue):
    jobs, clock, settings, store = queue
    job = jobs.enqueue(spec(auto_retry=False,max_attempts=2))
    claim = jobs.claim('worker',lease_seconds=5)
    jobs.progress(job['id'],claim['lease_token'],2,3)
    assert jobs.get(job['id'])['progress_done']==2
    jobs.failure(job['id'],claim['lease_token'],'TEMPORARY','Temporary problem',retryable=True)
    assert jobs.get(job['id'])['status']=='failed'
    assert jobs.retry(job['id'])=={'job_id':job['id'],'status':'queued'}
    second = jobs.claim('worker')
    assert second['attempts']==2
    jobs.failure(job['id'],second['lease_token'],'PERMANENT','Cannot process',retryable=False)
    with pytest.raises(HTTPException):
        jobs.retry(job['id'])
    with pytest.raises(LostLease):
        jobs.progress(job['id'],second['lease_token'],3,3)
    with pytest.raises(ValueError):
        jobs.progress(job['id'],second['lease_token'],4,3)


def test_automatic_backoff_and_manual_expedite_do_not_reset_attempts(queue):
    jobs, clock, settings, store = queue
    job = jobs.enqueue(spec())
    first = jobs.claim('worker')
    jobs.failure(job['id'],first['lease_token'],'TEMP','Temporary',retryable=True)
    assert jobs.get(job['id'])['status']=='queued'
    assert jobs.claim('worker') is None
    jobs.retry(job['id'])
    second = jobs.claim('worker')
    assert second['attempts']==2


def test_worker_real_maintenance_and_unsupported_handler(queue):
    jobs, clock, settings, store = queue
    jobs = JobQueue(settings)
    staged = store.root/'.staging'/('a'*32+'.part')
    staged.write_bytes(b'interrupted')
    os.utime(staged,(0,0))
    job = jobs.enqueue(spec())
    outcome = Worker(settings).run_once()
    assert outcome=={'job_id':job['id'],'status':'completed'}
    assert jobs.get(job['id'])['result']=={'removed_staging_files':1}
    assert not staged.exists()
    unsupported = jobs.enqueue(JobSpec(kind='parse',target_type='document',target_id='not-a-real-parser',idempotency_key='parse'))
    Worker(settings).run_once()
    result = jobs.get(unsupported['id'])
    assert result['status']=='failed' and result['attempts']==1
    assert result['error']['code']=='HANDLER_NOT_AVAILABLE'


def slow_handler(job,data_dir,connection):
    time.sleep(3)


def crashing_handler(job,data_dir,connection):
    os._exit(91)


def test_worker_enforces_timeout_and_child_crash_budget(queue):
    jobs, clock, settings, store = queue
    jobs = JobQueue(settings)
    job = jobs.enqueue(spec(timeout_seconds=0.2,max_attempts=1))
    started = time.monotonic()
    Worker(settings,handler=slow_handler,lease_seconds=0.5).run_once()
    assert time.monotonic()-started<3
    assert jobs.get(job['id'])['error']['code']=='JOB_TIMEOUT'
    assert jobs.get(job['id'])['status']=='failed'
    another = jobs.enqueue(spec('crash',max_attempts=1))
    Worker(settings,handler=crashing_handler).run_once()
    assert jobs.get(another['id'])['error']['code']=='WORKER_CHILD_EXITED'
    assert jobs.get(another['id'])['attempts']==1


def test_job_restart_http_auth_and_retry_boundary(queue):
    jobs, clock, settings, store = queue
    jobs = JobQueue(settings)
    job = jobs.enqueue(spec(auto_retry=False))
    claim = jobs.claim('worker')
    jobs.failure(job['id'],claim['lease_token'],'TEMP','Temporary failure',retryable=True)
    app = create_app('archive',settings)
    with TestClient(app,base_url='https://archive.test') as client:
        assert client.get('/api/v1/jobs/'+job['id']).status_code==401
        set_password(settings,'job-test-password')
        csrf = client.get('/api/v1/auth/session').json()['csrf_token']
        csrf = client.post('/api/v1/auth/login',json={'username':'admin','password':'job-test-password'},headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        public = client.get('/api/v1/jobs/'+job['id'])
        assert public.status_code==200
        for key in ('lease_token','lease_owner','payload_json','idempotency_key','request_hash'):
            assert key not in public.json()
        assert client.post('/api/v1/jobs/'+job['id']+'/retry').status_code==403
        assert client.post('/api/v1/jobs/'+job['id']+'/retry',headers={'X-CSRF-Token':csrf}).status_code==202
        assert client.get('/api/v1/jobs/missing').status_code==404
    with TestClient(create_app('archive',settings),base_url='https://archive.test'):
        assert JobQueue(settings).get(job['id'])['attempts']==1


def test_queue_commit_can_atomically_update_real_document_and_audit(queue):
    jobs, clock, settings, store = queue
    app = create_app('archive',settings)
    with TestClient(app):
        with connect(settings.database) as db:
            db.execute("INSERT INTO spaces VALUES ('s','Space','now','now')")
            db.commit()
        obj = store.put(io.BytesIO(b'original'),max_bytes=100)
        document = app.state.documents.register_managed(obj,Registration(space_id='s',title='Test',original_filename='test.txt',mime_type='text/plain'))
        job = jobs.enqueue(spec(target_id=document['id']))
        claimed = jobs.claim('worker')
        def apply(db,current):
            db.execute('UPDATE documents SET document_version=document_version+1 WHERE id=?',(document['id'],))
            record_event(db,document['id'],'job_effect',None,{'job_id':current['id']})
        jobs.complete(job['id'],claimed['lease_token'],{'document_id':document['id']},effect=apply)
        jobs.complete(job['id'],claimed['lease_token'],{},effect=apply)
        assert app.state.documents.get_record(document['id'])['document_version']==2
        with connect(settings.database) as db:
            assert db.execute("SELECT count(*) FROM document_events WHERE event_type='job_effect'").fetchone()==(1,)
        with store.open(obj.storage_key) as file:
            assert file.read()==b'original'


def test_worker_heartbeat_health_is_bounded(queue):
    jobs, clock, settings, store = queue
    assert not jobs.worker_healthy('worker')
    jobs.worker_heartbeat('worker')
    assert jobs.worker_healthy('worker')
    clock.advance(10)
    assert not jobs.worker_healthy('worker')


def test_actual_process_crash_leaves_claim_for_restart_recovery(queue):
    jobs, clock, settings, store = queue
    job = jobs.enqueue(spec())
    code = """
import os,sys
from pathlib import Path
from juanzhan.config import Settings
from juanzhan.jobs import JobQueue
q=JobQueue(Settings(Path(sys.argv[1]),''),clock=lambda:1000.0)
assert q.claim('crashing-worker',lease_seconds=5)
os._exit(92)
"""
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1]/'services'))
    child=subprocess.run([sys.executable,'-c',code,str(settings.data_dir)],env=env)
    assert child.returncode==92
    assert jobs.get(job['id'])['status']=='running'
    restarted=JobQueue(settings,clock)
    clock.advance(5)
    assert restarted.claim('replacement') is None
    clock.advance(1)
    claim=restarted.claim('replacement')
    assert claim['id']==job['id'] and claim['attempts']==2
    restarted.complete(job['id'],claim['lease_token'],{'recovered':True})
    assert restarted.get(job['id'])['status']=='completed'


def test_worker_invalid_payload_never_echoes_private_values(queue):
    jobs, clock, settings, store = queue
    jobs=JobQueue(settings)
    job=jobs.enqueue(spec(payload={'private-path-and-secret':'do-not-echo'}))
    Worker(settings).run_once()
    result=jobs.get(job['id'])
    assert result['status']=='failed' and result['error']['code']=='INVALID_JOB_PAYLOAD'
    assert 'do-not-echo' not in json.dumps(result)
    assert 'private-path' not in json.dumps(result)


def test_job_migration_preserves_prior_work_and_documents(tmp_path):
    from juanzhan.database import MIGRATIONS
    old=tmp_path/'old-migrations'
    old.mkdir()
    for file in sorted(MIGRATIONS.glob('*.sql'))[:2]:
        (old/file.name).write_bytes(file.read_bytes())
    database=tmp_path/'archive.sqlite3'
    migrate(database,old)
    with connect(database) as db:
        db.execute("INSERT INTO spaces VALUES ('s','Space','now','now')")
        db.execute("INSERT INTO jobs(id,kind,target_type,status,created_at,updated_at) VALUES ('legacy','parse','document','queued','now','now')")
        db.commit()
    migrate(database)
    with connect(database) as db:
        assert db.execute("SELECT name FROM spaces WHERE id='s'").fetchone()==('Space',)
        assert db.execute("SELECT status,attempts,timeout_seconds,auto_retry FROM jobs WHERE id='legacy'").fetchone()==('queued',0,60,1)
