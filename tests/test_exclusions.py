import json
import pytest
from test_sources import api,create
from test_source_incremental import seed,item,run,entries,doc,claim,manifest
from test_source_initial import scan,source_row
from juanzhan.database import connect
from juanzhan.jobs import JobQueue
from juanzhan.maintenance import exclude,purge
from juanzhan.source_incremental import publish
from juanzhan.source_paths import SourcePathError
from juanzhan.exclusions import epoch


def cancel(api,source,entry,headers=None):
    _,client,default,_=api
    return client.post('/api/v1/sources/'+source+'/exclude-entry',headers=default if headers is None else headers,
        json={'source_entry_id':entry['id'],'expected_document_version':doc(api,entry['document_id'])['document_version'] if entry['document_id'] else None,'reason':'User choice'})


def complete(api,id):
    owned=claim(api[0],id)
    JobQueue(api[0]).complete(id,owned['lease_token'],exclude)
    return JobQueue(api[0]).get(id)['result']


def test_exclusion_csrf_barrier_commit_remove_and_no_automatic_restore(api):
    settings,client,headers,space=api
    source=seed(api,[item('a.txt')]);entry=entries(api,source)[0]
    assert cancel(api,source,entry,{}).status_code==403
    queued=cancel(api,source,entry);assert queued.status_code==202
    assert cancel(api,source,entry).json()['job_id']==queued.json()['job_id']
    result=complete(api,queued.json()['job_id'])
    assert result['external_file_deleted'] is False and doc(api,entry['document_id'])['deleted_at']
    rule=client.get('/api/v1/sources/'+source+'/exclusions').json()[0]
    version=doc(api,entry['document_id'])['document_version']
    assert run(api,source,[item('a.txt',b'changed')])['updated_files']==0
    assert run(api,source,[])['suspected_missing']==0
    assert doc(api,entry['document_id'])['document_version']==version
    other=create(client,headers,space,root_alias='other').json()['id']
    assert client.delete('/api/v1/sources/'+other+'/exclusions/'+rule['id'],headers=headers).status_code==422
    assert client.delete('/api/v1/sources/'+source+'/exclusions/'+rule['id'],headers={}).status_code==403
    assert client.delete('/api/v1/sources/'+source+'/exclusions/'+rule['id'],headers=headers).status_code==204
    run(api,source,[item('a.txt')])
    assert doc(api,entry['document_id'])['deleted_at'] is not None


def test_pending_exclusion_and_epoch_changes_fence_prepared_scan(api):
    settings,client,headers,_=api
    source=seed(api,[item('a.txt')]);entry=entries(api,source)[0]
    with connect(settings.database) as db:old_epoch=epoch(db,source)
    queued=cancel(api,source,entry).json()['job_id'];owned=claim(settings,queued)
    scan_id=scan(client,headers,source,'incremental').json()['job_id'];scan_job=claim(settings,scan_id)
    observed=source_row(settings,source);observed['_exclusion_epoch']=old_epoch
    counts={'imported_files':0,'updated_files':0,'reassociated_files':0,'recovered_files':0,'unchanged_files':0}
    with pytest.raises(SourcePathError,match='SOURCE_CHANGED'):
        JobQueue(settings).complete(scan_id,scan_job['lease_token'],lambda db,j:publish(db,j,observed,manifest([item('a.txt')]),counts,settings))
    assert doc(api,entry['document_id'])['deleted_at'] is None
    JobQueue(settings).complete(queued,owned['lease_token'],exclude)
    JobQueue(settings).failure(scan_id,scan_job['lease_token'],'SOURCE_CHANGED','Changed',retryable=False)
    assert run(api,source,[item('a.txt')])['updated_files']==0


def test_failed_cancel_removes_barrier_and_never_commits_rule(api):
    settings,client,headers,_=api
    source=seed(api,[item('a.txt')]);entry=entries(api,source)[0]
    id=cancel(api,source,entry).json()['job_id'];owned=claim(settings,id)
    client.patch('/api/v1/documents/'+entry['document_id'],headers=headers,json={'expected_document_version':1,'title':'Changed'})
    from fastapi import HTTPException
    with pytest.raises(HTTPException):JobQueue(settings).complete(id,owned['lease_token'],exclude)
    JobQueue(settings).failure(id,owned['lease_token'],'VERSION_CONFLICT','Changed',retryable=False)
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
    assert client.get('/api/v1/sources/'+source+'/exclusions').json()==[]
    assert doc(api,entry['document_id'])['deleted_at'] is None


def test_external_purge_keeps_rule_prevents_reimport_and_removal_allows_new_document(api):
    settings,client,headers,_=api
    source=seed(api,[item('a.txt')]);entry=entries(api,source)[0];id=entry['document_id']
    client.post('/api/v1/documents/'+id+'/trash',headers=headers,json={'expected_document_version':1})
    job=client.post('/api/v1/documents/'+id+'/purge',headers=headers,json={'confirm_document_id':id,'expected_document_version':2}).json()['job_id']
    owned=claim(settings,job)
    JobQueue(settings).complete(job,owned['lease_token'],lambda db,j:purge(db,j,settings))
    assert entries(api,source)==[] and client.get('/api/v1/documents/'+id).status_code==404
    assert run(api,source,[item('a.txt')])['imported_files']==0
    rule=client.get('/api/v1/sources/'+source+'/exclusions').json()[0]
    client.delete('/api/v1/sources/'+source+'/exclusions/'+rule['id'],headers=headers)
    assert run(api,source,[item('a.txt')])['imported_files']==1
    assert entries(api,source)[0]['document_id']!=id
