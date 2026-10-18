"""Backup/restore drill with actual SQLite WAL, files, HTTP and conversion output."""
import hashlib
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_parsing import pipeline,upload
from format_samples import raster_sample
from juanzhan.apps import create_app
from juanzhan.backup import create,restore
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.jobs import JobQueue,JobSpec
from juanzhan.indexing import schedule
from juanzhan.storage import ManagedStore,StorageBusy
from juanzhan.worker import Worker


def login(client):
    csrf=client.get('/api/v1/auth/session').json()['csrf_token']
    return client.post('/api/v1/auth/login',json={'username':'admin','password':'pipeline-password'},headers={'X-CSRF-Token':csrf})


def test_consistent_backup_restore_drill_and_no_overwrite(pipeline,tmp_path):
    settings,client,_,space=pipeline
    original=raster_sample('PDF')
    receipt=upload(pipeline,original,'备份预览.pdf');Worker(settings).run_once()
    text=upload(pipeline,'恢复演练中文检索'.encode(),'演练.txt');Worker(settings).run_once()
    schedule(settings);Worker(settings).run_once(prefer_index=True);Worker(settings).run_once(prefer_index=True)
    # A real claimed job models a worker interrupted by backup/restore. Budget is retained.
    queue=JobQueue(settings)
    job=queue.enqueue(JobSpec(kind='gc',target_type='managed_staging',idempotency_key='restore-active'))
    active=queue.claim('interrupted-worker');assert active['id']==job['id']
    bundle=tmp_path/'backup';result=create(settings,bundle);assert result['files']>2
    with pytest.raises(FileExistsError):create(settings,bundle)
    target=tmp_path/'restored';assert restore(bundle,target)['credentials_revoked']
    with pytest.raises(FileExistsError):restore(bundle,target)
    restored=Settings(target,'pipeline-token',cookie_secure=False)
    with TestClient(create_app('archive',restored)) as after:
        assert after.get('/api/v1/documents/'+receipt['document_id']+'/download').status_code==401
        assert login(after).status_code==200
        root='/api/v1/documents/'+receipt['document_id']
        assert after.get(root+'/download').content==original
        preview=after.get(root+'/preview').json();assert preview['items']
        assert after.get(root+'/preview/'+preview['items'][0]['id']+'?expected_revision_id='+preview['revision_id']).status_code==200
        assert after.get('/api/v1/documents/'+text['document_id']+'/content?format=text').json()['body']
        search=after.get('/api/v1/documents',params={'space_id':space,'q':'中文检索'}).json()
        assert search['total']==1
        job=after.get('/api/v1/jobs/'+active['id']).json()
        assert job['status']=='queued' and job['attempts']==1 and job['max_attempts']==3
    with connect(restored.database) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT count(*) FROM auth_api_tokens').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM migration_checksums').fetchone()[0]==8
    # Live source retains its worker lease; recovery mutations are confined to new DB.
    assert queue.get(active['id'])['status']=='running'


def test_backup_rejects_busy_stores_and_missing_original(pipeline,tmp_path):
    settings,client,_,_=pipeline;upload(pipeline,b'backup original')
    with ManagedStore(settings.data_dir/'managed').locked():
        with pytest.raises(StorageBusy):create(settings,tmp_path/'busy')
    assert not (tmp_path/'busy').exists()
    with connect(settings.database) as db:key=db.execute('SELECT storage_key FROM managed_objects').fetchone()[0]
    (settings.data_dir/'managed'/key).unlink()
    with pytest.raises(FileNotFoundError):create(settings,tmp_path/'missing')
    assert not (tmp_path/'missing').exists()


@pytest.mark.parametrize('fault',['checksum','symlink','traversal','incomplete','missing'])
def test_restore_rejects_damaged_or_unsafe_bundles(pipeline,tmp_path,fault):
    settings,_,_,_=pipeline;upload(pipeline,b'restore original')
    bundle=tmp_path/'backup';create(settings,bundle)
    path=bundle/'manifest.json';manifest=json.loads(path.read_text())
    member=bundle/manifest['files'][1]['name']
    if fault=='checksum':member.chmod(0o600);member.write_bytes(b'bad')
    elif fault=='symlink':member.unlink();member.symlink_to('/etc/passwd')
    elif fault=='missing':member.unlink()
    elif fault=='incomplete':(bundle/'COMPLETE').unlink()
    else:
        manifest['files'][1]['name']='../escape';raw=json.dumps(manifest).encode();path.write_bytes(raw)
        (bundle/'COMPLETE').write_text(hashlib.sha256(raw).hexdigest())
    target=tmp_path/'new'
    with pytest.raises((ValueError,FileNotFoundError)):restore(bundle,target)
    assert not target.exists() and not (tmp_path/'escape').exists()


def test_cli_create_and_restore_private_new_directories(pipeline,tmp_path):
    import os,subprocess,sys
    settings,_,_,_=pipeline;upload(pipeline,b'command line restore original')
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'services'),
         'JUANZHAN_DATA_DIR':str(settings.data_dir)}
    bundle=tmp_path/'cli-backup';target=tmp_path/'cli-restored'
    for args in (['create','--output',str(bundle)],['restore','--input',str(bundle),'--output',str(target)]):
        result=subprocess.run([sys.executable,'-m','juanzhan.backup',*args],env=env,text=True,capture_output=True)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)['external_sources_included'] is False
    assert target.stat().st_mode & 0o777==0o700
    assert (target/'database/archive.sqlite3').stat().st_mode & 0o777==0o600
    result=subprocess.run([sys.executable,'-m','juanzhan.backup','restore','--input',str(bundle),'--output',str(target)],env=env,text=True,capture_output=True)
    assert result.returncode!=0 and 'existing data was not replaced' in result.stderr


def test_partial_restore_cannot_start_archive(tmp_path):
    target=tmp_path/'interrupted';target.mkdir()
    (target/'RESTORE_IN_PROGRESS').write_text('incomplete')
    with pytest.raises(RuntimeError,match='Incomplete restore'):
        with TestClient(create_app('archive',Settings(target,''))):pass
    assert not (target/'database').exists()
