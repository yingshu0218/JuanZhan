"""Persistent administrator backup workflows with real SQLite, files and HTTP."""
import json
from dataclasses import replace
import time
import uuid

from fastapi.testclient import TestClient
import pytest

from test_document_api import api
from test_parsing import pipeline, upload
from test_backup import login
from juanzhan.apps import create_app
from juanzhan.backup_management import Repository, schedule
from juanzhan.backup_api import schedule_public
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.jobs import JobQueue
from juanzhan.worker import Worker

ROOT='/api/v1/system'

def start(client,headers,request_id=None):
    response=client.post(ROOT+'/backups',headers=headers,json={'request_id':request_id or uuid.uuid4().hex})
    assert response.status_code==202,response.text
    return response.json()


def finish(settings,id):
    queue=JobQueue(settings)
    for _ in range(20):
        if queue.get(id)['status'] in ('completed','failed','cancelled'):
            return queue.get(id)
        Worker(settings).run_once()
    raise AssertionError('Operation did not terminate')


def test_create_download_restore_import_real_original_and_plan_reset(pipeline,tmp_path):
    settings,client,_,space=pipeline
    csrf=client.get('/api/v1/auth/session').json()['csrf_token'];headers={'X-CSRF-Token':csrf}
    receipt=upload(pipeline,b'real backup management original','original.txt')
    assert finish(settings,receipt['job_id'])['status']=='completed'
    plan=client.patch(ROOT+'/backup-schedule',headers=headers,json={'expected_version':1,'interval_minutes':60,'keep_count':2,'max_age_days':30})
    assert plan.status_code==200,plan.text
    first=start(client,headers,'create-unique-001')
    assert start(client,headers,'create-unique-001')==first
    assert finish(settings,first['job_id'])['status']=='completed'
    item=client.get(ROOT+'/backups/'+first['backup_id']).json()
    assert item['available'] and item['status']=='ready' and item['bytes']>0
    assert 'artifact_token' not in item and 'source_token' not in item
    assert str(settings.data_dir) not in json.dumps(item)
    response=client.get(ROOT+'/backups/'+first['backup_id']+'/download')
    assert response.status_code==200 and response.content.startswith(b'PK')
    assert response.headers['cache-control']=='no-store'
    imported=client.post(ROOT+'/backups/import?request_id=import-unique-001',headers={**headers,'Content-Type':'application/zip'},content=response.content)
    assert imported.status_code==202,imported.text
    imported=imported.json();assert finish(settings,imported['job_id'])['status']=='completed'
    again=client.post(ROOT+'/backups/import?request_id=import-unique-001',headers={**headers,'Content-Type':'application/zip'},content=response.content)
    assert again.json()==imported
    recovery=client.post(ROOT+'/backups/'+imported['backup_id']+'/restore',headers=headers,json={'request_id':'restore-unique-001'})
    assert recovery.status_code==202,recovery.text
    recovery=recovery.json()
    assert finish(settings,recovery['job_id'])['status']=='completed'
    assert client.get(ROOT+'/recoveries').json()['items'][0]['status']=='ready'
    with connect(settings.database) as db:
        id,token=db.execute('SELECT id,artifact_token FROM recovery_records WHERE id=?',(recovery['recovery_id'],)).fetchone()
    target=Repository(settings).path('recoveries',id,token)
    restored=Settings(target,'pipeline-token',cookie_secure=False,backup_dir=tmp_path/'recovered-backup-storage')
    with TestClient(create_app('archive',restored)) as after:
        assert after.get('/api/v1/documents/'+receipt['document_id']+'/download').status_code==401
        assert login(after).status_code==200
        assert after.get('/api/v1/documents/'+receipt['document_id']+'/download').content==b'real backup management original'
        plan=after.get(ROOT+'/backup-schedule').json()
        assert plan['interval_minutes']==0 and plan['next_run_at'] is None
        with connect(restored.database) as db:
            assert db.execute("SELECT COUNT(*) FROM jobs WHERE target_type IN ('system_backup','system_recovery') AND status IN ('queued','running')").fetchone()[0]==0
    assert client.get('/api/v1/documents/'+receipt['document_id']+'/download').content==b'real backup management original'
    assert client.get(ROOT+'/backup-schedule').json()['interval_minutes']==60


def test_auth_csrf_inputs_busy_and_safe_deletion(api):
    _,settings,client,headers,_=api
    with TestClient(client.app,base_url='https://archive.test') as anonymous:
        assert anonymous.get(ROOT+'/backups').status_code==401
        assert anonymous.get(ROOT+'/backup-schedule').status_code==401
        assert anonymous.get(ROOT+'/recoveries').status_code==401
    assert client.post(ROOT+'/backups',json={'request_id':'valid-request'}).status_code==403
    assert client.post(ROOT+'/backups',headers=headers,json={'request_id':'../escape'}).status_code==422
    assert client.post(ROOT+'/backups',headers=headers,json={'request_id':'valid-request','path':'/etc/passwd'}).status_code==422
    first=start(client,headers)
    assert client.post(ROOT+'/backups',headers=headers,json={'request_id':uuid.uuid4().hex}).status_code==409
    assert client.delete(ROOT+'/backups/'+first['backup_id'],headers=headers).status_code==409
    assert finish(settings,first['job_id'])['status']=='completed'
    assert client.delete(ROOT+'/backups/'+first['backup_id']).status_code==403
    assert client.delete(ROOT+'/backups/'+first['backup_id'],headers=headers).status_code==200
    assert client.delete(ROOT+'/backups/'+first['backup_id'],headers=headers).status_code==200
    item=client.get(ROOT+'/backups/'+first['backup_id']).json()
    assert item['status']=='deleted' and not item['available']
    assert client.get(ROOT+'/backups/'+first['backup_id']+'/download').status_code==409
    assert client.post(ROOT+'/backups/'+first['backup_id']+'/restore',headers=headers,json={'request_id':'recovery-deleted'}).status_code==409


def test_schedule_version_persistence_no_catchup_and_retention(api):
    _,settings,client,headers,_=api
    body={'expected_version':1,'interval_minutes':1,'keep_count':1,'max_age_days':1}
    assert client.patch(ROOT+'/backup-schedule',headers=headers,json=body).status_code==200
    assert client.patch(ROOT+'/backup-schedule',headers=headers,json=body).status_code==409
    with connect(settings.database) as db:due=db.execute('SELECT next_due_at FROM backup_schedule').fetchone()[0]
    assert schedule(settings,clock=lambda:due-1)==[]
    jobs=schedule(settings,clock=lambda:due+10000);assert len(jobs)==1
    assert schedule(settings,clock=lambda:due+10000)==[]
    assert finish(settings,jobs[0])['status']=='completed'
    second=schedule(settings,clock=lambda:due+10061);assert len(second)==1
    assert finish(settings,second[0])['status']=='completed'
    rows=client.get(ROOT+'/backups').json()['items'];assert len(rows)==2
    assert sum(row['available'] for row in rows)==1
    assert sum(row['status']=='deleted' for row in rows)==1
    cookie='; '.join(k+'='+v for k,v in client.cookies.items())
    with TestClient(create_app('archive',settings),base_url='https://archive.test') as restarted:
        assert restarted.get(ROOT+'/backup-schedule',headers={'Cookie':cookie}).json()['keep_count']==1
    version=client.get(ROOT+'/backup-schedule').json()['version']
    assert client.patch(ROOT+'/backup-schedule',headers=headers,json={**body,'expected_version':version,'interval_minutes':0}).status_code==200
    assert schedule(settings,clock=lambda:due+100000)==[]


def test_bad_import_and_corrupt_download_are_not_usable(api):
    _,settings,client,headers,_=api
    assert client.post(ROOT+'/backups/import?request_id=wrong-content',headers=headers,content=b'bad').status_code==415
    imported=client.post(ROOT+'/backups/import?request_id=invalid-archive',headers={**headers,'Content-Type':'application/zip'},content=b'not a zip')
    assert imported.status_code==202,imported.text
    job=finish(settings,imported.json()['job_id']);assert job['status']=='failed' and job['error']['code']=='BACKUP_INVALID'
    first=start(client,headers);assert finish(settings,first['job_id'])['status']=='completed'
    repo=Repository(settings)
    with connect(settings.database) as db:
        token=db.execute('SELECT artifact_token FROM backup_records WHERE id=?',(first['backup_id'],)).fetchone()[0]
    path=repo.path('artifacts',first['backup_id'],token)
    content=path.read_bytes();path.write_bytes(b'x'+content[1:])
    response=client.get(ROOT+'/backups/'+first['backup_id']+'/download')
    assert response.status_code==409 and str(path) not in response.text


def test_repository_cannot_overlap_live_or_external_data(api,tmp_path):
    _,settings,_,_,_=api
    for path in (settings.data_dir,settings.data_dir/'nested',settings.data_dir.parent):
        with pytest.raises(ValueError):Repository(replace(settings,backup_dir=path))
    external=tmp_path/'external';external.mkdir()
    with pytest.raises(ValueError):Repository(replace(settings,backup_dir=external/'backup',source_mounts=(('readonly',str(external)),)))
    target=tmp_path/'linked';target.symlink_to(tmp_path/'outside')
    with pytest.raises((ValueError,FileExistsError)):Repository(replace(settings,backup_dir=target))


def test_snapshot_copy_keeps_business_writes_and_lease_heartbeats_available(pipeline,tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    from juanzhan import backup
    settings,client,_,_=pipeline
    receipt=upload(pipeline,b'concurrent snapshot original','snapshot.txt')
    assert finish(settings,receipt['job_id'])['status']=='completed'
    queue=JobQueue(settings)
    from juanzhan.jobs import JobSpec
    queue.enqueue(JobSpec(kind='gc',target_type='managed_staging',idempotency_key='snapshot-heartbeat'))
    owned=queue.claim('snapshot-heartbeat-test')
    copying=threading.Event();release=threading.Event();original=backup.copy_object
    def paused(*args,**kwargs):
        copying.set()
        assert release.wait(10)
        return original(*args,**kwargs)
    monkeypatch.setattr(backup,'copy_object',paused)
    target=tmp_path/'concurrent-backup'
    with ThreadPoolExecutor(max_workers=2) as executor:
        future=executor.submit(backup.create,settings,target)
        try:
            assert copying.wait(5)
            # This write completes while immutable object copying is still held.
            queue.heartbeat(owned['id'],owned['lease_token'])
            queue.worker_heartbeat('snapshot-heartbeat-test')
            csrf=client.get('/api/v1/auth/session').json()['csrf_token']
            result=client.patch('/api/v1/documents/'+receipt['document_id'],headers={'X-CSRF-Token':csrf},json={'expected_document_version':1,'title':'changed after snapshot'})
            assert result.status_code==200,result.text
        finally:release.set()
        assert future.result(timeout=5)['files']>1
    with connect(target/'database/archive.sqlite3') as db:
        assert db.execute('SELECT title FROM documents WHERE id=?',(receipt['document_id'],)).fetchone()[0]=='snapshot.txt'
    assert client.get('/api/v1/documents/'+receipt['document_id']).json()['title']=='changed after snapshot'


def test_real_worker_daemon_runs_due_backup_then_restart_preserves_disabled_plan(api,tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    _,settings,client,headers,_=api
    body={'expected_version':1,'interval_minutes':1,'keep_count':2,'max_age_days':30}
    assert client.patch(ROOT+'/backup-schedule',headers=headers,json=body).status_code==200
    with connect(settings.database) as db:
        db.execute('UPDATE backup_schedule SET next_due_at=?',(time.time()-1,));db.commit()
    env={**os.environ,'JUANZHAN_DATA_DIR':str(settings.data_dir),'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'services')}
    def run_until(predicate):
        with connect(settings.database) as db:
            db.execute('DELETE FROM worker_heartbeats');db.commit()
        process=subprocess.Popen([sys.executable,'-m','juanzhan.worker','--poll-seconds','0.05'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                with connect(settings.database) as db:started=db.execute('SELECT COUNT(*) FROM worker_heartbeats').fetchone()[0]>0
                if started and predicate():return
                assert process.poll() is None
                time.sleep(0.05)
            raise AssertionError('Daemon did not reach expected state')
        finally:
            process.terminate();process.wait(timeout=10)
    run_until(lambda:any(item['status']=='ready' for item in client.get(ROOT+'/backups').json()['items']))
    plan=client.get(ROOT+'/backup-schedule').json();assert plan['last_job_id'] and plan['next_run_at']
    assert client.patch(ROOT+'/backup-schedule',headers=headers,json={**body,'expected_version':plan['version'],'interval_minutes':0}).status_code==200
    before=client.get(ROOT+'/backups').json()['total']
    run_until(lambda:client.get(ROOT+'/backup-schedule').json()['interval_minutes']==0)
    assert client.get(ROOT+'/backups').json()['total']==before


def test_lost_lease_never_publishes_and_interrupted_work_is_reclaimed(api):
    from juanzhan.backup_management import execute,cleanup
    from juanzhan.jobs import LostLease
    _,settings,client,headers,_=api
    receipt=start(client,headers)
    queue=JobQueue(settings);owned=queue.claim('old-backup-worker')
    with connect(settings.database) as db:
        db.execute('UPDATE jobs SET lease_expires_at=? WHERE id=?',(time.time()-1,owned['id']));db.commit()
    with pytest.raises(LostLease):execute(settings,owned)
    repo=Repository(settings)
    assert not list((repo.root/'artifacts').iterdir())
    assert not list((repo.root/'work').iterdir())
    orphan=repo.path('work','a'*32,'b'*32);orphan.mkdir();(orphan/'partial').write_bytes(b'partial snapshot')
    unknown=repo.root/'work'/'administrator-notes';unknown.mkdir()
    with repo.locked():assert cleanup(settings,repo)==1
    assert unknown.exists() and not orphan.exists()
    with connect(settings.database) as db:
        item=db.execute('SELECT artifact_token FROM backup_records WHERE id=?',(receipt['backup_id'],)).fetchone()
    assert item[0] is None


def test_busy_repository_retries_with_finite_budget_and_recovery_blocks_delete(api):
    _,settings,client,headers,_=api
    first=start(client,headers);repo=Repository(settings)
    with repo.locked():
        result=Worker(settings).run_once();assert result['status']=='queued'
    job=JobQueue(settings).get(first['job_id']);assert job['attempts']==1 and job['error']['code']=='STORAGE_BUSY'
    with connect(settings.database) as db:
        db.execute('UPDATE jobs SET available_at=? WHERE id=?',(time.time(),first['job_id']));db.commit()
    assert finish(settings,first['job_id'])['status']=='completed'
    recovery=client.post(ROOT+'/backups/'+first['backup_id']+'/restore',headers=headers,json={'request_id':'protected-recovery'}).json()
    assert client.delete(ROOT+'/backups/'+first['backup_id'],headers=headers).status_code==409
    assert finish(settings,recovery['job_id'])['status']=='completed'
    assert client.delete(ROOT+'/backups/'+first['backup_id'],headers=headers).status_code==200
    assert client.get(ROOT+'/recoveries').json()['items'][0]['status']=='ready'


def test_operator_stages_to_new_data_and_explicit_cleanup_keeps_live_instance(api,tmp_path):
    from juanzhan.backup_admin import stage,remove
    _,settings,client,headers,_=api
    first=start(client,headers);assert finish(settings,first['job_id'])['status']=='completed'
    restored=client.post(ROOT+'/backups/'+first['backup_id']+'/restore',headers=headers,json={'request_id':'operator-recovery'}).json()
    assert finish(settings,restored['job_id'])['status']=='completed'
    target=tmp_path/'operator-new-data'
    result=stage(settings,restored['recovery_id'],target)
    assert result['activation_required'] and (target/'database/archive.sqlite3').is_file()
    with pytest.raises(FileExistsError):stage(settings,restored['recovery_id'],target)
    assert (target/'database/archive.sqlite3').is_file()
    assert remove(settings,restored['recovery_id'])['removed']
    assert client.get(ROOT+'/recoveries').json()['items'][0]['status']=='unavailable'
    assert client.get('/healthz').status_code==200
    with connect(target/'database/archive.sqlite3') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_failed_automatic_backup_never_retires_latest_success(api,monkeypatch):
    from juanzhan import backup_management as management
    _,settings,client,headers,_=api
    body={'expected_version':1,'interval_minutes':1,'keep_count':1,'max_age_days':1}
    assert client.patch(ROOT+'/backup-schedule',headers=headers,json=body).status_code==200
    with connect(settings.database) as db:due=db.execute('SELECT next_due_at FROM backup_schedule').fetchone()[0]
    first=schedule(settings,clock=lambda:due)[0]
    assert finish(settings,first)['status']=='completed'
    old=client.get(ROOT+'/backups').json()['items'][0]
    second=schedule(settings,clock=lambda:due+61)[0]
    queue=JobQueue(settings);owned=queue.claim('full-disk-test');assert owned['id']==second
    actual=management.shutil.disk_usage(Repository(settings).root)
    monkeypatch.setattr(management.shutil,'disk_usage',lambda _:type(actual)(actual.total,actual.used,128*1024**2))
    with pytest.raises(ValueError,match='budget'):management.execute(settings,owned)
    queue.failure(second,owned['lease_token'],'BACKUP_INVALID','Backup storage budget failed',retryable=False)
    item=client.get(ROOT+'/backups/'+old['id']).json()
    assert item['available'] and item['deleted_at'] is None
    assert client.get(ROOT+'/backups/'+old['id']+'/download').status_code==200


def test_upgrade_from_nine_migrations_preserves_old_rows_and_starts_plan_disabled(tmp_path):
    import shutil
    from juanzhan.database import MIGRATIONS,migrate
    settings=Settings(tmp_path/'archive','')
    settings.prepare_archive()
    legacy=tmp_path/'old-migrations';legacy.mkdir()
    for file in MIGRATIONS.glob('*.sql'):
        if file.name<'0010':shutil.copyfile(file,legacy/file.name)
    migrate(settings.database,legacy)
    with connect(settings.database) as db:
        db.execute("INSERT INTO spaces VALUES ('old-space','Legacy preserved','2026-10-19T00:00:00Z','2026-10-19T00:00:00Z')")
        checksums=dict(db.execute('SELECT name,sha256 FROM migration_checksums'));db.commit()
    migrate(settings.database)
    with connect(settings.database) as db:
        assert db.execute('SELECT name FROM spaces').fetchone()[0]=='Legacy preserved'
        assert db.execute('SELECT COUNT(*) FROM backup_records').fetchone()[0]==0
        assert schedule_public(db)['interval_minutes']==0
        current=dict(db.execute('SELECT name,sha256 FROM migration_checksums'))
        assert all(current[name]==checksum for name,checksum in checksums.items())
        assert len(current)==len(list(MIGRATIONS.glob('*.sql')))
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
