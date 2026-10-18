"""Readonly physical source bytes, SQLite and HTTP adoption boundaries."""
import hashlib
import os
import sqlite3

import pytest

from test_sources import api
from test_sources import create as create_source
from test_source_initial import scan, source_row
from juanzhan.adoptions import execute
from juanzhan.database import connect
from juanzhan.document_events import utc_now
from juanzhan.jobs import JobQueue
from juanzhan.source_initial import register_external
from juanzhan.source_paths import SourceMounts
from juanzhan.worker import Worker


@pytest.fixture
def external(api):
    settings,client,headers,space=api
    source=create_source(client,headers,space).json()['id']
    queued=scan(client,headers,source).json()['job_id']
    queue=JobQueue(settings);job=queue.claim('fixture')
    assert job['id']==queued
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:
        content=file.read();info=os.fstat(file.fileno())
    item={'path':'core_id','size_bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),
        'mtime_ns':info.st_mtime_ns,'identity_hint':f'{info.st_dev}:{info.st_ino}',
        'mime_type':'text/plain','file_modified_at':None}
    # Sysfs has no supported file extensions; this registers actual readonly bytes,
    # rather than claiming an extensionless file was discovered by the scanner.
    with queue.write() as db:
        db.row_factory=sqlite3.Row
        document,entry=register_external(db,job,source_row(settings,source),item,None,'needs_review',settings,utc_now())
    queue.complete(job['id'],job['lease_token'],{})
    parse=queue.claim('fixture');assert parse['kind']=='parse'
    queue.failure(parse['id'],parse['lease_token'],'FIXTURE_NO_CONVERTER','Converter is not part of this fixture',retryable=False)
    doc=client.get('/api/v1/documents/'+document).json()
    payload={'expected_document_version':doc['document_version'],'expected_revision_id':doc['current_revision_id'],'request_id':'verified-copy'}
    return settings,client,headers,source,document,entry,content,payload


def test_verified_copy_new_revision_idempotency_and_source_protection(external):
    settings,client,headers,source,document,entry,content,payload=external
    url='/api/v1/documents/'+document
    assert client.post(url+'/adopt',json=payload).status_code==403
    response=client.post(url+'/adopt',headers=headers,json=payload);assert response.status_code==202,response.text
    id=response.json()['job_id']
    assert client.post(url+'/adopt',headers=headers,json=payload).json()['job_id']==id
    busy=client.post('/api/v1/sources/'+source+'/exclude-entry',headers=headers,
        json={'source_entry_id':entry,'expected_document_version':payload['expected_document_version']})
    assert busy.status_code==409 and busy.json()['error']['code']=='SOURCE_ENTRY_BUSY'
    result=Worker(settings).run_once();assert result=={'job_id':id,'status':'completed'}
    job=JobQueue(settings).get(id);new=job['result']['revision_id']
    assert new!=payload['expected_revision_id'] and job['result']['external_file_modified'] is False
    doc=client.get(url).json();assert doc['document_version']==payload['expected_document_version']+1
    revisions=client.get(url+'/revisions').json();assert len(revisions)==2
    assert revisions[0]['storage_kind']=='managed' and revisions[1]['storage_kind']=='external'
    assert client.get(url+'/download').content==content
    assert client.get(url+'/download?revision_id='+payload['expected_revision_id']).content==content
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:assert file.read()==content
    assert client.post(url+'/adopt',headers=headers,json=payload).json()=={'job_id':id,'status':'completed'}
    assert client.post(url+'/adopt',headers=headers,json={**payload,'expected_document_version':999}).status_code==409
    rules=client.get('/api/v1/sources/'+source+'/exclusions').json();assert len(rules)==1 and rules[0]['protected'] is True
    assert client.delete('/api/v1/sources/'+source+'/exclusions/'+rules[0]['id'],headers=headers).status_code==409
    assert client.post('/api/v1/sources/'+source+'/exclude-entry',headers=headers,
        json={'source_entry_id':entry,'expected_document_version':doc['document_version']}).status_code==409
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM jobs WHERE id=? AND kind='parse'",(job['result']['parse_job_id'],)).fetchone()[0]==1
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_concurrent_edit_fails_without_switch_and_releases_barrier(external):
    settings,client,headers,source,document,entry,content,payload=external
    root='/api/v1/documents/'+document
    queued=client.post(root+'/adopt',headers=headers,json=payload).json()['job_id']
    assert client.patch(root,headers=headers,json={'expected_document_version':payload['expected_document_version'],'title':'Concurrent title'}).status_code==200
    assert Worker(settings).run_once()=={'job_id':queued,'status':'failed'}
    assert JobQueue(settings).get(queued)['error']['code']=='VERSION_CONFLICT'
    doc=client.get(root).json();assert doc['title']=='Concurrent title' and doc['current_revision_id']==payload['expected_revision_id']
    assert client.get(root+'/download').content==content
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0


def test_audit_failure_rolls_back_all_publication(external):
    settings,client,headers,source,document,entry,content,payload=external
    response=client.post('/api/v1/documents/'+document+'/adopt',headers=headers,json=payload);assert response.status_code==202
    queue=JobQueue(settings);job=queue.claim('audit-test')
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER fail_adoption BEFORE INSERT ON document_events WHEN NEW.event_type='document_adopted' BEGIN SELECT RAISE(ABORT,'audit failed'); END;")
    with pytest.raises(sqlite3.IntegrityError):execute(settings,job)
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM file_revisions WHERE document_id=?',(document,)).fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM source_exclusions').fetchone()[0]==0
        assert db.execute('SELECT current_revision_id FROM documents WHERE id=?',(document,)).fetchone()[0]==payload['expected_revision_id']
    # Physical orphan remains for delayed reference-aware GC, not unsafe eager unlink.
    assert list((settings.data_dir/'managed'/'sha256').glob('*/*'))
    queue.failure(job['id'],job['lease_token'],'AUDIT_FAILURE','Test injection',retryable=False)
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0


def test_successful_body_and_confirmed_metadata_survive_then_real_reparse(external,monkeypatch,tmp_path):
    from dataclasses import replace
    from juanzhan.apps import create_app
    from juanzhan.config import Settings
    from juanzhan.conversion_store import ConverterConfig
    from test_converter import real_server
    settings,client,headers,source,document,entry,content,payload=external
    token='adoption-real-converter-token'
    converter=create_app('converter',Settings(tmp_path/'unused',token),converter_config=ConverterConfig(root=tmp_path/'converter'))
    root='/api/v1/documents/'+document
    with real_server(converter) as base:
        monkeypatch.setenv('CONVERTER_URL',base)
        worker=Worker(replace(settings,converter_token=token))
        response=client.post(root+'/reprocess',headers=headers,json={**payload,'request_id':'initial-success'})
        assert response.status_code==202,response.text
        assert worker.run_once()['status']=='completed'
        doc=client.get(root).json();old_run=doc['current_parse_run_id'];assert old_run
        assert client.post('/api/v1/field-definitions',headers=headers,json={'space_id':doc['space_id'],'key':'note','label':'Note','type':'text'}).status_code==201
        response=client.patch(root+'/metadata',headers=headers,json={'expected_document_version':doc['document_version'],'values':{'note':'confirmed manual'},'confirm':True})
        assert response.status_code==200,response.text
        doc=client.get(root).json()
        response=client.post(root+'/adopt',headers=headers,json={**payload,'expected_document_version':doc['document_version']})
        assert response.status_code==202,response.text
        assert worker.run_once()['status']=='completed'
        assert client.get(root).json()['current_parse_run_id']==old_run
        assert worker.run_once()['status']=='completed'
        assert client.get(root).json()['current_parse_run_id']!=old_run
        assert client.get(root+'/parse-runs').json()['total']==2
        assert client.get(root+'/metadata').json()[0]['value']=='confirmed manual'
        assert client.get(root+'/download').content==content


def test_hash_mismatch_never_switches_or_changes_external_bytes(external):
    settings,client,headers,source,document,entry,content,payload=external
    with connect(settings.database) as db:
        db.execute('UPDATE file_revisions SET sha256=? WHERE id=?',('0'*64,payload['expected_revision_id']));db.commit()
    response=client.post('/api/v1/documents/'+document+'/adopt',headers=headers,json=payload)
    assert response.status_code==202
    result=Worker(settings).run_once();assert result['status']=='failed'
    assert JobQueue(settings).get(result['job_id'])['error']['code']=='SOURCE_REVISION_CHANGED'
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:assert file.read()==content


def test_intent_fences_prepared_scans_and_lost_lease_cannot_publish(external,monkeypatch):
    from juanzhan.exclusions import epoch,verify
    from juanzhan.jobs import LostLease
    from juanzhan.source_paths import SourcePathError
    settings,client,headers,source,document,entry,content,payload=external
    with connect(settings.database) as db:observed={'id':source,'_exclusion_epoch':epoch(db,source)}
    assert client.post('/api/v1/documents/'+document+'/adopt',headers=headers,json=payload).status_code==202
    with connect(settings.database) as db:
        with pytest.raises(SourcePathError):verify(db,observed)
    queue=JobQueue(settings);job=queue.claim('expired-adoption')
    real_complete=JobQueue.complete
    def expired(self,id,token,result,**kwargs):
        with connect(settings.database) as db:
            db.execute('UPDATE jobs SET lease_expires_at=0 WHERE id=?',(id,));db.commit()
        return real_complete(self,id,token,result,**kwargs)
    monkeypatch.setattr(JobQueue,'complete',expired)
    with pytest.raises(LostLease):execute(settings,job)
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM file_revisions WHERE document_id=?',(document,)).fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM source_exclusions').fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM document_events WHERE event_type='document_adopted'").fetchone()[0]==0


def test_offline_source_has_finite_retries_then_releases_scan_barrier(external):
    from dataclasses import replace
    settings,client,headers,source,document,entry,content,payload=external
    response=client.post('/api/v1/documents/'+document+'/adopt',headers=headers,json=payload)
    assert response.status_code==202
    id=response.json()['job_id'];worker=Worker(replace(settings,source_mounts=(('docs','/absent-adoption-source'),)))
    for attempt in range(1,4):
        result=worker.run_once();assert result['job_id']==id
        job=JobQueue(settings).get(id);assert job['attempts']==attempt
        assert job['error']['code']=='SOURCE_OFFLINE'
        assert result['status']==('failed' if attempt==3 else 'queued')
        with connect(settings.database) as db:
            assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==(0 if attempt==3 else 1)
            db.execute('UPDATE jobs SET available_at=0 WHERE id=?',(id,));db.commit()
    assert client.get('/api/v1/documents/'+document).json()['current_revision_id']==payload['expected_revision_id']
