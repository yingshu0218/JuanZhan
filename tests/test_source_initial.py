import hashlib
import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from test_sources import api, create, submit, state
from juanzhan.apps import create_app
from juanzhan.database import connect
from juanzhan.jobs import JobQueue, LostLease
from juanzhan.source_initial import initial, publish
from juanzhan.source_paths import SourcePathError
from juanzhan.worker import Worker


def scan(client, headers, source, mode='initial'):
    return client.post('/api/v1/sources/'+source+'/scan', headers=headers, json={'mode':mode})


def manifest(items):
    records=[]
    for kind,path in items:
        item={'kind':kind,'path':path}
        if kind=='file':
            item.update(sha256=hashlib.sha256(b'same bytes').hexdigest(),size_bytes=10,
                mime_type='text/plain',mtime_ns=1000000000,file_modified_at='1970-01-01T00:00:01Z',identity_hint='1:2')
        records.append(json.dumps(item)+'\n')
    return io.StringIO(''.join(records))


def source_row(settings,id):
    with connect(settings.database) as db:
        db.row_factory=__import__('sqlite3').Row
        return dict(db.execute('SELECT * FROM sources WHERE id=?',(id,)).fetchone())


def counts(source,files=2):
    return {'source_id':source,'mode':'initial','imported_files':files,'created_folders':0,'ignored_files':0,'imported_bytes':files*10}


def table_counts(settings):
    with connect(settings.database) as db:
        return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in
                ('documents','file_revisions','source_entries','folders','document_events','managed_objects')}


def test_real_empty_initial_coalescing_csrf_and_replay_after_restart(api):
    settings,client,headers,space=api
    source=create(client,headers,space).json()['id']
    assert scan(client,{},source).status_code==403
    assert scan(client,headers,source,'incremental').status_code==409
    preview=submit(client,headers,source).json()['job_id']
    assert scan(client,headers,source).json()['error']['code']=='SOURCE_SCAN_BUSY'
    assert Worker(settings).run_once()['status']=='completed'
    job_id=scan(client,headers,source).json()['job_id']
    assert scan(client,headers,source).json()['job_id']==job_id
    assert submit(client,headers,source).json()['error']['code']=='SOURCE_SCAN_BUSY'
    assert Worker(settings).run_once()=={'job_id':job_id,'status':'completed'}
    assert JobQueue(settings).get(job_id)['result']['imported_files']==0
    record=source_row(settings,source)
    assert record['initial_import_completed_at'] and record['last_successful_scan_at']
    assert record['initial_import_completed_at']==record['last_successful_scan_at']
    before=table_counts(settings)
    with TestClient(create_app('archive',settings),base_url='https://archive.test') as restarted:
        restarted.cookies.update(client.cookies)
        assert scan(restarted,headers,source).json()=={'job_id':job_id,'status':'completed'}
    assert table_counts(settings)==before


@pytest.mark.parametrize('policy,triage',[('tree','needs_review'),('flat','filed')])
def test_atomic_metadata_registration_and_independent_same_hash_documents(api,policy,triage):
    settings,client,headers,space=api
    target=client.post('/api/v1/folders',headers=headers,json={'space_id':space,'name':'Target'}).json()['id']
    source=create(client,headers,space,initial_import_policy=policy,initial_triage_status=triage,initial_target_folder_id=target).json()['id']
    job_id=scan(client,headers,source).json()['job_id']
    queue=JobQueue(settings)
    owned=queue.claim('initial')
    items=[('directory','资料'),('directory','资料/空目录'),('file','资料/a.txt'),('file','b.txt')] if policy=='tree' else [('file','资料/a.txt'),('file','b.txt')]
    assert queue.complete(job_id,owned['lease_token'],lambda db,job:publish(db,job,source_row(settings,source),manifest(items),counts(source),settings))
    result=queue.get(job_id)['result']
    assert result['created_folders']==(2 if policy=='tree' else 0)
    with connect(settings.database) as db:
        rows=db.execute('SELECT d.id,d.folder_id,d.triage_status,d.document_version,r.storage_kind,r.sha256,r.managed_object_id '
            'FROM documents d JOIN file_revisions r ON r.id=d.current_revision_id ORDER BY d.title').fetchall()
        assert len(rows)==2 and rows[0][0]!=rows[1][0] and rows[0][5]==rows[1][5]
        assert all(r[2:5]==(triage,1,'external') and r[6] is None for r in rows)
        if policy=='flat':assert all(r[1]==target for r in rows)
        else:
            nested=db.execute("SELECT id FROM folders WHERE name='资料'").fetchone()[0]
            assert {r[1] for r in rows}=={target,nested}
        assert db.execute("SELECT count(*) FROM jobs WHERE kind='parse'").fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM document_events WHERE actor='source_scan'").fetchone()[0]==2
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    run=state(settings,owned['target_id'])
    assert run[0]=='completed' and json.loads(run[1])==result
    # Later logical edits survive every initial replay and never bump the version again.
    id=rows[0][0]
    assert client.patch('/api/v1/documents/'+id,headers=headers,json={'expected_document_version':1,'title':'Human title','folder_id':None}).status_code==200
    before=table_counts(settings)
    assert scan(client,headers,source).json()['job_id']==job_id
    assert client.get('/api/v1/documents/'+id).json()['title']=='Human title'
    assert client.get('/api/v1/documents/'+id).json()['document_version']==2
    assert table_counts(settings)==before


def test_folder_conflict_rolls_back_every_record_and_can_retry(api):
    settings,client,headers,space=api
    conflict=client.post('/api/v1/folders',headers=headers,json={'space_id':space,'name':'Taken'}).json()['id']
    source=create(client,headers,space,initial_import_policy='tree').json()['id']
    job_id=scan(client,headers,source).json()['job_id']
    queue=JobQueue(settings)
    owned=queue.claim('initial')
    baseline=table_counts(settings)
    items=[('directory','Good'),('file','Good/a.txt'),('directory','Taken')]
    with pytest.raises(SourcePathError,match='SOURCE_FOLDER_CONFLICT'):
        queue.complete(job_id,owned['lease_token'],lambda db,job:publish(db,job,source_row(settings,source),manifest(items),counts(source,1),settings))
    assert table_counts(settings)==baseline
    assert source_row(settings,source)['initial_import_completed_at'] is None
    with connect(settings.database) as db:assert db.execute("SELECT count(*) FROM jobs WHERE kind='parse'").fetchone()[0]==0
    queue.failure(job_id,owned['lease_token'],'SOURCE_FOLDER_CONFLICT','Logical folder name conflicts',retryable=False)
    assert client.patch('/api/v1/folders/'+conflict,headers=headers,json={'name':'Renamed'}).status_code==200
    next_id=scan(client,headers,source).json()['job_id']
    retry=queue.claim('retry')
    assert retry['id']==next_id
    queue.complete(next_id,retry['lease_token'],lambda db,job:publish(db,job,source_row(settings,source),manifest(items),counts(source,1),settings))
    assert queue.get(next_id)['result']['imported_files']==1


def test_expired_lease_after_metadata_writes_rolls_back_import_and_parse_jobs(api):
    settings,client,headers,space=api
    source=create(client,headers,space,initial_import_policy='tree').json()['id']
    id=scan(client,headers,source).json()['job_id']
    clock=[2000000000.0]
    queue=JobQueue(settings,clock=lambda:clock[0])
    job=queue.claim('first',lease_seconds=1)
    before=table_counts(settings)
    def slow_commit(db,owned):
        result=publish(db,owned,source_row(settings,source),manifest([('directory','A'),('file','A/a.txt')]),counts(source,1),settings)
        clock[0]+=2
        return result
    with pytest.raises(LostLease):queue.complete(id,job['lease_token'],slow_commit)
    assert table_counts(settings)==before
    assert source_row(settings,source)['initial_import_completed_at'] is None
    assert state(settings,job['target_id'])[0]=='running'
    with connect(settings.database) as db:assert db.execute("SELECT count(*) FROM jobs WHERE kind='parse'").fetchone()[0]==0


def test_normalized_directory_collision_is_not_silently_merged(api):
    settings,client,headers,space=api
    source=create(client,headers,space,initial_import_policy='tree').json()['id']
    id=scan(client,headers,source).json()['job_id']
    queue=JobQueue(settings)
    job=queue.claim('initial')
    before=table_counts(settings)
    with pytest.raises(SourcePathError,match='SOURCE_FOLDER_CONFLICT'):
        queue.complete(id,job['lease_token'],lambda db,owned:publish(db,owned,source_row(settings,source),
            manifest([('directory','Case'),('file','Case/a.txt'),('directory','case')]),counts(source,1),settings))
    assert table_counts(settings)==before


def test_anonymous_manifest_limit_failure_leaves_no_metadata_or_temp_files(api,monkeypatch):
    settings,client,headers,space=api
    source=create(client,headers,space,initial_import_policy='tree').json()['id']
    id=scan(client,headers,source).json()['job_id']
    job=JobQueue(settings).claim('initial')
    settings=replace(settings,source_mounts=(('docs','/sys/devices/system/cpu/cpu0'),))
    import juanzhan.source_initial as module
    monkeypatch.setattr(module,'MAX_MANIFEST_BYTES',0)
    before=table_counts(settings)
    files=set(settings.data_dir.iterdir())
    with pytest.raises(SourcePathError,match='SOURCE_MANIFEST_LIMIT'):initial(settings,job)
    assert table_counts(settings)==before and set(settings.data_dir.iterdir())==files
    assert source_row(settings,source)['initial_import_completed_at'] is None
