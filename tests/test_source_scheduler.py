"""Durable scan deadlines, concurrent ticks and real readonly worker execution."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from test_sources import api,create
from test_source_initial import scan
from juanzhan.database import connect
from juanzhan.jobs import JobQueue
from juanzhan.source_scheduler import schedule
from juanzhan.worker import Worker


def configure(client,headers,id,minutes,version=1):
    return client.patch('/api/v1/sources/'+id+'/schedule',headers=headers,
        json={'scan_interval_minutes':minutes,'expected_schedule_version':version})


def due(settings,source):
    with connect(settings.database) as db:
        return db.execute('SELECT next_due_at FROM source_scan_schedules WHERE source_id=?',(source,)).fetchone()[0]


def test_schedule_config_versions_csrf_validation_and_pause(api):
    settings,client,headers,space=api
    source=create(client,headers,space).json();id=source['id']
    assert source['scan_schedule']=={'version':1,'last_job_id':None,'next_run_at':None}
    assert configure(client,{},id,60).status_code==403
    for value in (True,-1,525601,'60'):
        assert configure(client,headers,id,value).status_code==422
    enabled=configure(client,headers,id,60);assert enabled.status_code==200,enabled.text
    assert enabled.json()['scan_schedule']['version']==2 and enabled.json()['scan_schedule']['next_run_at']
    assert configure(client,headers,id,5).status_code==409
    paused=configure(client,headers,id,0,2);assert paused.status_code==200
    assert paused.json()['scan_schedule']['version']==3 and due(settings,id) is None
    assert configure(client,headers,id,None,3).status_code==200
    assert client.get('/api/v1/sources/'+id).json()['scan_interval_minutes'] is None


def test_deadline_restart_concurrent_ticks_and_actual_incremental_worker(api):
    settings,client,headers,space=api
    source=create(client,headers,space,scan_interval_minutes=5).json()['id']
    deadline=due(settings,source)
    # Never automatically confirms the initial import.
    assert schedule(settings,clock=lambda:deadline+100)==[]
    initial=scan(client,headers,source);assert initial.status_code==202
    assert Worker(settings).run_once()['status']=='completed'
    assert schedule(settings,clock=lambda:deadline-1)==[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:schedule(settings,clock=lambda:deadline),range(4)))
    ids=[id for group in results for id in group];assert len(ids)==1
    assert due(settings,source)==deadline+300
    # A fresh scheduler instance uses the persisted deadline, with no duplicate catch-up.
    assert schedule(settings,clock=lambda:deadline)==[]
    assert Worker(settings).run_once()=={'job_id':ids[0],'status':'completed'}
    info=client.get('/api/v1/sources/'+source).json()
    assert info['scan_schedule']['last_job_id']==ids[0]
    assert JobQueue(settings).get(ids[0])['result']['mode']=='incremental'
    assert info['scan_schedule']['version']==1


def test_active_manual_scan_is_not_duplicated_and_disabled_sources_do_not_run(api):
    settings,client,headers,space=api
    source=create(client,headers,space,scan_interval_minutes=1).json()['id']
    assert scan(client,headers,source).status_code==202
    assert Worker(settings).run_once()['status']=='completed'
    manual=scan(client,headers,source,'incremental');assert manual.status_code==202
    deadline=due(settings,source)
    assert schedule(settings,clock=lambda:deadline+600)==[]
    assert due(settings,source)==deadline+660
    with connect(settings.database) as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE target_type='source_incremental'").fetchone()[0]==1
        db.execute("UPDATE sources SET status='disabled' WHERE id=?",(source,));db.commit()
    assert schedule(settings,clock=lambda:deadline+10000)==[]


def test_failed_enqueue_rolls_back_deadline_and_scan_run(api):
    settings,client,headers,space=api
    source=create(client,headers,space,scan_interval_minutes=1).json()['id']
    assert scan(client,headers,source).status_code==202
    assert Worker(settings).run_once()['status']=='completed'
    deadline=due(settings,source)
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER reject_scheduled BEFORE INSERT ON jobs WHEN NEW.idempotency_key LIKE 'source-scheduled:%' BEGIN SELECT RAISE(ABORT,'test enqueue failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):schedule(settings,clock=lambda:deadline)
    assert due(settings,source)==deadline
    with connect(settings.database) as db:
        assert db.execute("SELECT count(*) FROM scan_runs WHERE mode='incremental'").fetchone()[0]==0


def test_schedule_survives_consistent_backup_and_new_directory_restore(api,tmp_path):
    from dataclasses import replace
    from juanzhan.backup import create as backup,restore
    settings,client,headers,space=api
    source=create(client,headers,space,scan_interval_minutes=2).json()['id']
    assert scan(client,headers,source).status_code==202
    assert Worker(settings).run_once()['status']=='completed'
    deadline=due(settings,source)
    backup(settings,tmp_path/'bundle');restore(tmp_path/'bundle',tmp_path/'restored')
    restored=replace(settings,data_dir=tmp_path/'restored')
    assert due(restored,source)==deadline
    jobs=schedule(restored,clock=lambda:deadline+1000);assert len(jobs)==1
    assert Worker(restored).run_once()=={'job_id':jobs[0],'status':'completed'}
    assert due(settings,source)==deadline
    with connect(restored.database) as db:assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_upgrade_eight_migrations_preserves_existing_source_config(tmp_path):
    import shutil
    from juanzhan.config import Settings
    from juanzhan.database import MIGRATIONS,migrate
    settings=Settings(tmp_path/'legacy','');settings.prepare_archive()
    legacy=tmp_path/'migrations';legacy.mkdir()
    for path in sorted(MIGRATIONS.glob('*.sql'))[:8]:shutil.copyfile(path,legacy/path.name)
    migrate(settings.database,legacy)
    with connect(settings.database) as db:
        db.execute("INSERT INTO spaces VALUES ('s','Existing','now','now')")
        db.execute("INSERT INTO sources(id,space_id,name,kind,root_ref,scan_interval_minutes,created_at,updated_at) VALUES ('source','s','Existing','external','docs',60,'now','now')")
        original=dict(db.execute('SELECT name,sha256 FROM migration_checksums'));db.commit()
    migrate(settings.database);migrate(settings.database)
    assert due(settings,'source')>0
    with connect(settings.database) as db:
        assert db.execute("SELECT scan_interval_minutes FROM sources WHERE id='source'").fetchone()[0]==60
        checksums=dict(db.execute('SELECT name,sha256 FROM migration_checksums'))
        assert set(checksums)=={path.name for path in MIGRATIONS.glob('*.sql')}
        assert all(checksums[k]==v for k,v in original.items())
