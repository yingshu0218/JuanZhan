"""Explicit ambiguity resolution over real readonly bytes, SQLite and HTTP."""
import sqlite3

import pytest

from test_sources import api
from test_source_incremental import seed,run,item,entries
from juanzhan.database import connect
from juanzhan.jobs import JobQueue
from juanzhan.source_matching import execute
from juanzhan.source_paths import SourceMounts
from juanzhan.worker import Worker


@pytest.fixture
def ambiguous(api):
    settings,client,headers,space=api
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:content=file.read()
    # Metadata observation fixtures do not claim sysfs extensionless files were scanned.
    source=seed(api,[item('old-a.txt',content),item('old-b.txt',content)])
    result=run(api,source,[item('core_id',content)]);assert result['needs_match']==3
    entry=next(e for e in entries(api,source) if e['document_id'] is None)
    url=f'/api/v1/sources/{source}/entries/{entry["id"]}'
    candidates=client.get(url+'/matches').json();assert candidates['total']==2
    return settings,client,headers,source,entry,url,candidates,content


def body(candidates,action='match'):
    result={'action':action,'expected_entry_updated_at':candidates['entry']['updated_at'],'request_id':'explicit-resolution'}
    if action=='match':
        chosen=candidates['items'][0]
        result.update(document_id=chosen['document_id'],expected_document_version=chosen['document_version'],expected_revision_id=chosen['revision_id'])
    return result


def test_match_keeps_identity_revision_manual_fields_and_actual_bytes(ambiguous):
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    selected=candidates['items'][0];root='/api/v1/documents/'+selected['document_id']
    assert client.patch(root,headers=headers,json={'expected_document_version':selected['document_version'],'title':'Manually confirmed title','is_favorite':True}).status_code==200
    space=client.get(root).json()['space_id']
    assert client.post('/api/v1/field-definitions',headers=headers,json={'space_id':space,'key':'note','label':'Note','type':'text'}).status_code==201
    doc=client.get(root).json()
    assert client.patch(root+'/metadata',headers=headers,json={'expected_document_version':doc['document_version'],'values':{'note':'retain confirmed metadata'},'confirm':True}).status_code==200
    candidates=client.get(url+'/matches').json();payload=body(candidates)
    assert client.post(url+'/resolve',json=payload).status_code==403
    response=client.post(url+'/resolve',headers=headers,json=payload);assert response.status_code==202,response.text
    id=response.json()['job_id']
    assert client.post(url+'/resolve',headers=headers,json=payload).json()['job_id']==id
    assert Worker(settings).run_once()=={'job_id':id,'status':'completed'}
    after=client.get(root).json();assert after['title']=='Manually confirmed title' and after['is_favorite']
    assert after['current_revision_id']==selected['revision_id']
    assert client.get(root+'/metadata').json()[0]['value']=='retain confirmed metadata'
    assert client.get(root+'/download').content==content
    current=entries((settings,client,headers,space),source)
    assert len(current)==2 and next(e for e in current if e['relative_path']=='core_id')['document_id']==selected['document_id']
    assert client.post(url+'/resolve',headers=headers,json=payload).json()=={'job_id':id,'status':'completed'}
    assert client.post(url+'/resolve',headers=headers,json={**payload,'action':'new_document','document_id':None,'expected_document_version':None,'expected_revision_id':None}).status_code==409
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:assert file.read()==content
    with connect(settings.database) as db:
        import json
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        audit=db.execute("SELECT before_json,after_json FROM document_events WHERE event_type='source_entry_matched'").fetchone()
        assert json.loads(audit[0])['source_entry']['relative_path_norm']=='old-a.txt'
        assert json.loads(audit[1])['source_entry']['relative_path_norm']=='core_id'


def test_explicit_new_document_does_not_merge_equal_hashes(ambiguous):
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    old_ids={c['document_id'] for c in candidates['items']}
    payload=body(candidates,'new_document')
    response=client.post(url+'/resolve',headers=headers,json=payload);assert response.status_code==202,response.text
    id=response.json()['job_id'];assert Worker(settings).run_once()['status']=='completed'
    result=JobQueue(settings).get(id)['result'];assert result['document_id'] not in old_ids and result['matched'] is False
    doc=client.get('/api/v1/documents/'+result['document_id']).json();assert doc['triage_status']=='needs_review'
    assert client.get('/api/v1/documents/'+doc['id']+'/download').content==content
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==3
        assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
    assert client.post(url+'/resolve',headers=headers,json=payload).json()['job_id']==id


def test_stale_document_version_and_entry_observation_are_rejected(ambiguous):
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    payload=body(candidates)
    assert client.post(url+'/resolve',headers=headers,json={**payload,'expected_entry_updated_at':'stale'}).status_code==409
    queued=client.post(url+'/resolve',headers=headers,json=payload);assert queued.status_code==202
    assert client.patch('/api/v1/documents/'+payload['document_id'],headers=headers,json={'expected_document_version':payload['expected_document_version'],'description':'concurrent update'}).status_code==200
    result=Worker(settings).run_once();assert result['status']=='failed'
    assert JobQueue(settings).get(result['job_id'])['error']['code']=='VERSION_CONFLICT'
    assert client.get(url+'/matches').json()['total']==2
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0


def test_old_path_still_present_and_hash_mismatch_never_reassociate(ambiguous):
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    payload=body(candidates)
    with connect(settings.database) as db:
        old=db.execute('SELECT source_entry_id FROM file_revisions WHERE id=?',(payload['expected_revision_id'],)).fetchone()[0]
        db.execute("UPDATE source_entries SET relative_path_norm='core_siblings_list' WHERE id=?",(old,));db.commit()
    queued=client.post(url+'/resolve',headers=headers,json=payload);assert queued.status_code==202
    result=Worker(settings).run_once();assert result['status']=='failed'
    assert JobQueue(settings).get(result['job_id'])['error']['code']=='SOURCE_MATCH_OLD_PRESENT'
    with connect(settings.database) as db:
        db.execute('UPDATE source_entries SET sha256=? WHERE id=?',('0'*64,entry['id']));db.commit()
    changed=client.get(url+'/matches').json();assert changed['total']==0
    queued=client.post(url+'/resolve',headers=headers,json={**body(changed,'new_document'),'request_id':'changed-bytes'})
    assert queued.status_code==202
    result=Worker(settings).run_once();assert result['status']=='failed'
    assert JobQueue(settings).get(result['job_id'])['error']['code']=='SOURCE_REVISION_CHANGED'
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==2


def test_audit_failure_restores_both_source_entries(ambiguous):
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    queued=client.post(url+'/resolve',headers=headers,json=body(candidates));assert queued.status_code==202
    job=JobQueue(settings).claim('audit-failure')
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER reject_match BEFORE INSERT ON document_events WHEN NEW.event_type='source_entry_matched' BEGIN SELECT RAISE(ABORT,'test audit failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):execute(settings,job)
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM source_entries').fetchone()[0]==3
        assert db.execute('SELECT document_id FROM source_entries WHERE id=?',(entry['id'],)).fetchone()[0] is None
        assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==1


def test_candidate_pagination_and_strict_resolution_payload(ambiguous):
    from fastapi.testclient import TestClient
    from juanzhan.apps import create_app
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    first=client.get(url+'/matches?page_size=1').json();second=client.get(url+'/matches?page_size=1&page=2').json()
    assert first['total']==second['total']==2 and len(first['items'])==len(second['items'])==1
    assert first['items'][0]['document_id']!=second['items'][0]['document_id']
    assert client.get(url+'/matches?page_size=101').status_code==422
    for payload in ({**body(candidates),'action':'guess'},
                    {**body(candidates),'expected_document_version':True},
                    {**body(candidates),'action':'new_document'},
                    {**body(candidates,'new_document'),'extra':'ignored'}):
        assert client.post(url+'/resolve',headers=headers,json=payload).status_code==422
    with TestClient(create_app('archive',settings)) as stranger:
        assert stranger.get(url+'/matches').status_code==401
        assert stranger.post(url+'/resolve',json=body(candidates)).status_code==401


def test_purge_cancels_pending_match_and_releases_unlinked_entry_barrier(ambiguous):
    from juanzhan.maintenance import purge
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    payload=body(candidates);root='/api/v1/documents/'+payload['document_id']
    queued=client.post(url+'/resolve',headers=headers,json=payload);assert queued.status_code==202
    queue=JobQueue(settings);owned=queue.claim('paused-matcher');assert owned['id']==queued.json()['job_id']
    trashed=client.post(root+'/trash',headers=headers,json={'expected_document_version':payload['expected_document_version']})
    assert trashed.status_code==200
    response=client.post(root+'/purge',headers=headers,json={'confirm_document_id':payload['document_id'],'expected_document_version':trashed.json()['document_version']})
    assert response.status_code==202
    cleanup=queue.claim('purger');assert cleanup['id']==response.json()['job_id']
    queue.complete(cleanup['id'],cleanup['lease_token'],lambda db,job:purge(db,job,settings))
    assert queue.get(owned['id'])['status']=='cancelled'
    assert client.get(url+'/matches').json()['total']==1
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
        assert db.execute('SELECT document_id FROM source_entries WHERE id=?',(entry['id'],)).fetchone()[0] is None


def test_lost_lease_does_not_publish_resolution(ambiguous,monkeypatch):
    from juanzhan.jobs import LostLease
    settings,client,headers,source,entry,url,candidates,content=ambiguous
    assert client.post(url+'/resolve',headers=headers,json=body(candidates)).status_code==202
    queue=JobQueue(settings);job=queue.claim('expiry-test');real_complete=JobQueue.complete
    def expired(self,id,token,result,**kwargs):
        with connect(settings.database) as db:
            db.execute('UPDATE jobs SET lease_expires_at=0 WHERE id=?',(id,));db.commit()
        return real_complete(self,id,token,result,**kwargs)
    monkeypatch.setattr(JobQueue,'complete',expired)
    with pytest.raises(LostLease):execute(settings,job)
    assert client.get(url+'/matches').json()['total']==2
    with connect(settings.database) as db:
        assert db.execute('SELECT document_id FROM source_entries WHERE id=?',(entry['id'],)).fetchone()[0] is None
        assert db.execute("SELECT count(*) FROM document_events WHERE event_type='source_entry_matched'").fetchone()[0]==0
