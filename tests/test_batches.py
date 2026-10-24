import json
import sqlite3

import pytest

from test_document_api import api, upload, detail, patch, folder
from juanzhan.batches import execute
from juanzhan.database import connect
from juanzhan.jobs import JobQueue, LostLease
from juanzhan.worker import Worker


def submit(client,headers,space,ids,operation='set_favorite',payload=None,versions=None,mode='explicit'):
    return client.post('/api/v1/documents/batch',headers=headers,json={
        'space_id':space,'document_ids':ids,'selection_mode':mode,
        'expected_versions':versions if versions is not None else {id:1 for id in ids},
        'operation':operation,'payload':{'is_favorite':True} if payload is None else payload})


def finish(settings,id):
    queue=JobQueue(settings)
    while True:
        job=queue.claim('test')
        assert job is not None
        if job['kind']=='batch':queue.complete(job['id'],job['lease_token'],lambda db,owned: execute(db,owned,settings))
        else:queue.failure(job['id'],job['lease_token'],'HANDLER_NOT_AVAILABLE','Not implemented',retryable=False)
        if job['id']==id:return queue.get(id)['result']


def test_snapshot_partial_results_restart_and_guarded_undo(api):
    app,settings,client,headers,space=api
    a=upload(client,headers,space,b'a')['document_id']
    b=upload(client,headers,space,b'b')['document_id']
    missing='not-present'
    job=submit(client,headers,space,[a,b,missing],mode='snapshot').json()['job_id']
    # A later import cannot expand the frozen selection. A concurrent edit fails only b.
    later=upload(client,headers,space,b'later')['document_id']
    assert patch(client,headers,b,1,title='Edited').status_code==200
    result=finish(settings,job)
    assert result['succeeded']==1 and result['failed']==2
    assert {i.get('error_code') for i in result['items']}=={None,'VERSION_CONFLICT','NOT_FOUND'}
    assert detail(client,a)['is_favorite'] and not detail(client,later)['is_favorite']
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM document_events WHERE batch_job_id=?',(job,)).fetchone()[0]==1
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers)
    assert undo.status_code==202
    undo_id=undo.json()['job_id']
    assert client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']==undo_id
    assert finish(settings,undo_id)['succeeded']==1
    assert detail(client,a)['document_version']==3 and not detail(client,a)['is_favorite']
    assert client.post('/api/v1/jobs/'+undo_id+'/undo',headers=headers).status_code==409
    # Restarted queue does not reapply a completed effect.
    assert JobQueue(settings).get(job)['result']==result


def test_noop_tag_deltas_and_undo_does_not_overwrite_later_edit(api):
    app,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    initial=set(detail(client,id)['tag_ids'])
    tags=[client.post('/api/v1/tags',headers=headers,json={'space_id':space,'name':name}).json()['id'] for name in ('A','B')]
    assert patch(client,headers,id,1,tags_add=[tags[0]]).status_code==200
    job=submit(client,headers,space,[id],'add_tags',{'tag_ids':[tags[0]]},{id:2}).json()['job_id']
    assert finish(settings,job)['skipped']==1 and detail(client,id)['document_version']==2
    assert client.post('/api/v1/jobs/'+job+'/undo',headers=headers).status_code==409
    job=submit(client,headers,space,[id],'add_tags',{'tag_ids':[tags[1]]},{id:2}).json()['job_id']
    assert finish(settings,job)['succeeded']==1
    assert set(detail(client,id)['tag_ids'])==set(tags)|initial
    patch(client,headers,id,3,title='Later edit')
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    result=finish(settings,undo)
    assert result['items'][0]['error_code']=='VERSION_CONFLICT'
    assert detail(client,id)['title']=='Later edit' and set(detail(client,id)['tag_ids'])==set(tags)|initial


@pytest.mark.parametrize('operation,payload',[
    ('set_favorite',{'is_favorite':'true'}),('set_favorite',{'is_favorite':True,'title':'extra'}),
    ('add_tags',{'tag_ids':None}),('move_folder',{}),('set_triage',{'triage_status':'invented'})])
def test_reject_bad_operation_payloads(api,operation,payload):
    _,_,client,headers,space=api
    assert submit(client,headers,space,['id'],operation,payload).status_code==422


def test_selection_limits_auth_and_metadata_payload(api):
    _,_,client,headers,space=api
    assert submit(client,{},space,['id']).status_code==403
    assert submit(client,headers,space,[]).status_code==422
    assert submit(client,headers,space,['id','id']).status_code==422
    assert submit(client,headers,space,['id'],versions={}).status_code==422
    assert submit(client,headers,space,[str(i) for i in range(101)]).status_code==422
    assert submit(client,headers,space,['id'],'set_metadata',{}).status_code==422


def test_batch_metadata_seven_types_clear_noop_and_guarded_undo(api):
    from test_metadata import field,write
    _,settings,client,headers,space=api
    ids=[upload(client,headers,space,str(n).encode())['document_id'] for n in range(2)]
    kinds={'text':'text','notes':'long_text','count':'integer','amount':'decimal',
           'date':'date','flag':'boolean','choice':'single_select','keep':'text'}
    for key,kind in kinds.items():
        field(client,headers,space,key,kind,**({'options':[{'id':'a','label':'A'}]} if kind=='single_select' else {}))
    for id in ids:assert write(client,headers,id,1,{'keep':'unchanged'}).status_code==200
    values={'text':'Title','notes':'Long\ntext','count':9223372036854775807,
            'amount':'2.0001','date':'2026-10-19','flag':False,'choice':'a'}
    job=submit(client,headers,space,ids,'set_metadata',{'values':values,'confirm':True},{id:2 for id in ids}).json()['job_id']
    assert finish(settings,job)['succeeded']==2
    for id in ids:
        saved=client.get('/api/v1/documents/'+id+'/metadata').json()
        assert {v['key']:v['value'] for v in saved}=={**values,'keep':'unchanged'}
        assert detail(client,id)['document_version']==3
    noop=submit(client,headers,space,ids,'set_metadata',{'values':values,'confirm':True},{id:3 for id in ids}).json()['job_id']
    assert finish(settings,noop)['skipped']==2
    assert patch(client,headers,ids[1],3,title='Later edit').status_code==200
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    result=finish(settings,undo)
    assert result['succeeded']==1
    assert {r['document_id']:r for r in result['items']}[ids[1]]['error_code']=='VERSION_CONFLICT'
    assert {v['key']:v['value'] for v in client.get('/api/v1/documents/'+ids[0]+'/metadata').json()}=={'keep':'unchanged'}
    assert detail(client,ids[1])['title']=='Later edit'


def test_metadata_clear_preserves_false_provenance_and_filing_failure_is_per_item(api):
    from test_metadata import field,write
    _,settings,client,headers,space=api
    flag=field(client,headers,space,'flag','boolean')
    ids=[upload(client,headers,space,str(n).encode())['document_id'] for n in range(2)]
    for id in ids:assert write(client,headers,id,1,{'flag':False},confirm=False).status_code==200
    with connect(settings.database) as db:
        db.execute("UPDATE metadata_values SET origin='imported',updated_by='importer' WHERE document_id=?",(ids[0],));db.commit()
    type_id=client.post('/api/v1/document-types',headers=headers,json={'space_id':space,'key':'required',
        'label':'Required','fields':[{'field_definition_id':flag,'required_for_filing':True}]}).json()['id']
    patch(client,headers,ids[1],2,document_type_id=type_id)
    client.post('/api/v1/documents/'+ids[1]+'/triage',headers=headers,json={'expected_document_version':3,'triage_status':'filed'})
    job=submit(client,headers,space,ids,'set_metadata',{'values':{'flag':None},'confirm':True},{ids[0]:2,ids[1]:4}).json()['job_id']
    result=finish(settings,job)
    assert result['succeeded']==1 and result['items'][1]['error_code']=='MISSING_REQUIRED_FIELDS'
    assert client.get('/api/v1/documents/'+ids[0]+'/metadata').json()==[]
    assert client.get('/api/v1/documents/'+ids[1]+'/metadata').json()[0]['value'] is False
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    assert finish(settings,undo)['succeeded']==1
    with connect(settings.database) as db:
        assert tuple(db.execute('SELECT value_bool,origin,is_confirmed,updated_by FROM metadata_values WHERE document_id=?',(ids[0],)).fetchone())==(0,'imported',0,'importer')


@pytest.mark.parametrize('payload',[{}, {'values':{} ,'confirm':True},{'values':{'x':1},'confirm':'true'},
    {'values':{'x':1}}, {'values':{'x':1},'confirm':True,'extra':1}])
def test_batch_metadata_rejects_ambiguous_payload(api,payload):
    _,_,client,headers,space=api
    assert submit(client,headers,space,['missing'],'set_metadata',payload).status_code==422


def test_batch_metadata_undo_revalidates_changed_field_rules(api):
    from test_metadata import field,write
    _,settings,client,headers,space=api
    definition=field(client,headers,space,'code','text')
    id=upload(client,headers,space)['document_id']
    write(client,headers,id,1,{'code':'old'})
    job=submit(client,headers,space,[id],'set_metadata',{'values':{'code':'new'},'confirm':True},{id:2}).json()['job_id']
    finish(settings,job)
    assert client.patch('/api/v1/field-definitions/'+definition,headers=headers,json={'constraints':{'regex':'new'}}).status_code==200
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    assert finish(settings,undo)['items'][0]['error_code']=='INVALID_METADATA_VALUE'
    assert client.get('/api/v1/documents/'+id+'/metadata').json()[0]['value']=='new'
    assert detail(client,id)['document_version']==3


def test_batch_metadata_audit_and_lease_failures_rollback_actual_values(api):
    from test_metadata import field
    _,settings,client,headers,space=api
    field(client,headers,space,'code','text')
    ids=[upload(client,headers,space,str(n).encode())['document_id'] for n in range(2)]
    with connect(settings.database) as db:
        db.execute("CREATE TRIGGER reject_metadata_batch BEFORE INSERT ON document_events WHEN NEW.batch_job_id IS NOT NULL AND NEW.document_id='"+ids[1]+"' BEGIN SELECT RAISE(ABORT,'fixture audit failure'); END")
        db.commit()
    job=submit(client,headers,space,ids,'set_metadata',{'values':{'code':'saved'},'confirm':True}).json()['job_id']
    result=finish(settings,job)
    assert result['succeeded']==1 and result['items'][1]['error_code']=='INTEGRITY_CONFLICT'
    assert client.get('/api/v1/documents/'+ids[1]+'/metadata').json()==[]
    next_job=submit(client,headers,space,[ids[0]],'set_metadata',{'values':{'code':None},'confirm':True},{ids[0]:2}).json()['job_id']
    queue=JobQueue(settings);claim=queue.claim('lease-fixture')
    assert claim['id']==next_job
    def expired(db,owned):
        result=execute(db,owned,settings)
        db.execute('UPDATE jobs SET lease_expires_at=0 WHERE id=?',(owned['id'],))
        return result
    with pytest.raises(LostLease):queue.complete(next_job,claim['lease_token'],expired)
    assert client.get('/api/v1/documents/'+ids[0]+'/metadata').json()[0]['value']=='saved'
    assert detail(client,ids[0])['document_version']==2


def test_batch_metadata_snapshot_budget_fails_only_oversized_item(api,monkeypatch):
    from test_metadata import field,write
    import juanzhan.batches as batches
    _,settings,client,headers,space=api
    field(client,headers,space,'notes','long_text')
    ids=[upload(client,headers,space,str(n).encode())['document_id'] for n in range(2)]
    assert write(client,headers,ids[0],1,{'notes':'x'*8192}).status_code==200
    monkeypatch.setattr(batches,'MAX_METADATA_SNAPSHOT_BYTES',4096)
    job=submit(client,headers,space,ids,'set_metadata',{'values':{'notes':'new'},'confirm':True},{ids[0]:2,ids[1]:1}).json()['job_id']
    result=finish(settings,job)
    assert result['succeeded']==1 and result['items'][0]['error_code']=='BATCH_METADATA_SNAPSHOT_LIMIT'
    assert client.get('/api/v1/documents/'+ids[0]+'/metadata').json()[0]['value']=='x'*8192
    assert detail(client,ids[0])['document_version']==2


def test_item_scope_failure_and_audit_failure_roll_back_only_that_item(api):
    app,settings,client,headers,space=api
    ids=[upload(client,headers,space,str(i).encode())['document_id'] for i in range(3)]
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    foreign=upload(client,headers,other,b'foreign')['document_id']
    with connect(settings.database) as db:
        db.execute("CREATE TRIGGER reject_batch BEFORE INSERT ON document_events WHEN NEW.batch_job_id IS NOT NULL AND NEW.document_id='"+ids[1]+"' BEGIN SELECT RAISE(ABORT,'injected'); END")
        db.commit()
    job=submit(client,headers,space,ids+[foreign]).json()['job_id']
    result=finish(settings,job)
    assert result['succeeded']==2 and result['failed']==2
    assert detail(client,ids[1])['document_version']==1 and not detail(client,ids[1])['is_favorite']
    assert not detail(client,foreign)['is_favorite']
    assert {i.get('error_code') for i in result['items']}=={None,'INTEGRITY_CONFLICT','CROSS_SPACE_REFERENCE'}


def test_move_trash_restore_and_deleted_reference_blocks_undo(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    f=folder(client,headers,space,'Target')
    job=submit(client,headers,space,[id],'move_folder',{'folder_id':f}).json()['job_id']
    finish(settings,job)
    assert detail(client,id)['folder_id']==f and detail(client,id)['triage_status']=='needs_review'
    trash=submit(client,headers,space,[id],'trash',{}, {id:2}).json()['job_id']
    assert finish(settings,trash)['succeeded']==1
    undo=client.post('/api/v1/jobs/'+trash+'/undo',headers=headers).json()['job_id']
    assert finish(settings,undo)['succeeded']==1
    assert detail(client,id)['folder_id']==f and detail(client,id)['deleted_at'] is None
    remove=submit(client,headers,space,[id],'move_folder',{'folder_id':None},{id:4}).json()['job_id']
    finish(settings,remove)
    assert client.post('/api/v1/folders/'+f+'/delete',headers=headers,json={'mode':'only_if_empty'}).status_code==204
    undo=client.post('/api/v1/jobs/'+remove+'/undo',headers=headers).json()['job_id']
    assert finish(settings,undo)['items'][0]['error_code']=='NOT_FOUND'
    assert detail(client,id)['folder_id'] is None


def test_real_worker_atomic_completion_and_expired_lease(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    job=submit(client,headers,space,[id]).json()['job_id']
    worker=Worker(settings)
    for _ in range(2):worker.run_once()
    assert JobQueue(settings).get(job)['status']=='completed'
    assert detail(client,id)['is_favorite']
    # A stale owner cannot execute any batch effects, even with a valid snapshot.
    next_job=submit(client,headers,space,[id],'set_favorite',{'is_favorite':False},{id:2}).json()['job_id']
    clock=[100.0]
    queue=JobQueue(settings,clock=lambda:clock[0])
    # Use real epoch for availability, then expire the claimed lease.
    import time
    clock[0]=time.time()
    claimed=queue.claim('stale',lease_seconds=1)
    assert claimed['id']==next_job
    clock[0]+=2
    with pytest.raises(LostLease):queue.complete(next_job,claimed['lease_token'],execute)
    assert detail(client,id)['is_favorite'] and detail(client,id)['document_version']==2


def test_tag_remove_successful_undo_and_no_duplicate_effect(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    initial=set(detail(client,id)['tag_ids'])
    tag=client.post('/api/v1/tags',headers=headers,json={'space_id':space,'name':'Keep'}).json()['id']
    patch(client,headers,id,1,tags_add=[tag])
    job=submit(client,headers,space,[id],'remove_tags',{'tag_ids':[tag]},{id:2}).json()['job_id']
    finish(settings,job)
    assert set(detail(client,id)['tag_ids'])==initial
    assert not JobQueue(settings).complete(job,'obsolete-token',execute)
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    finish(settings,undo)
    assert set(detail(client,id)['tag_ids'])==initial|{tag} and detail(client,id)['document_version']==4


def test_type_and_triage_use_filing_rules_and_cross_space_references(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Second'}).json()['id']
    foreign=folder(client,headers,other,'Foreign')
    job=submit(client,headers,space,[id],'move_folder',{'folder_id':foreign}).json()['job_id']
    assert finish(settings,job)['items'][0]['error_code']=='CROSS_SPACE_REFERENCE'
    type_id=client.post('/api/v1/document-types',headers=headers,json={'space_id':space,'key':'memo','label':'Memo'}).json()['id']
    job=submit(client,headers,space,[id],'set_type',{'document_type_id':type_id}).json()['job_id']
    assert finish(settings,job)['succeeded']==1
    job=submit(client,headers,space,[id],'set_triage',{'triage_status':'filed'},{id:2}).json()['job_id']
    assert finish(settings,job)['succeeded']==1 and detail(client,id)['triage_status']=='filed'
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    assert finish(settings,undo)['succeeded']==1 and detail(client,id)['triage_status']=='needs_review'


def test_lease_expiry_after_effect_rolls_back_documents_events_and_result(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    job=submit(client,headers,space,[id]).json()['job_id']
    queue=JobQueue(settings)
    claim=queue.claim('test')
    queue.failure(claim['id'],claim['lease_token'],'HANDLER_NOT_AVAILABLE','Not implemented',retryable=False)
    claim=queue.claim('test')
    assert claim['id']==job
    def expires(db,owned):
        result=execute(db,owned)
        db.execute('UPDATE jobs SET lease_expires_at=0 WHERE id=?',(job,))
        return result
    with pytest.raises(LostLease):queue.complete(job,claim['lease_token'],expires)
    assert detail(client,id)['document_version']==1 and not detail(client,id)['is_favorite']
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM document_events WHERE batch_job_id=?',(job,)).fetchone()[0]==0
    assert queue.get(job)['result'] is None
    assert queue.complete(job,claim['lease_token'],execute)
    assert detail(client,id)['document_version']==2


def test_restore_batch_is_scoped_versioned_and_undoable(api):
    _,settings,client,headers,space=api
    a=upload(client,headers,space,b'restore-a')['document_id']
    b=upload(client,headers,space,b'restore-b')['document_id']
    f=folder(client,headers,space,'Restore folder')
    patch(client,headers,a,1,folder_id=f)
    assert client.post('/api/v1/documents/'+a+'/trash',headers=headers,json={'expected_document_version':2}).status_code==200
    job=submit(client,headers,space,[a,b],'restore',{}, {a:3,b:1}).json()['job_id']
    result=finish(settings,job)
    assert result['succeeded']==1 and result['skipped']==1
    assert detail(client,a)['folder_id']==f and detail(client,a)['deleted_at'] is None
    undo=client.post('/api/v1/jobs/'+job+'/undo',headers=headers).json()['job_id']
    assert finish(settings,undo)['succeeded']==1
    assert detail(client,a)['deleted_at'] is not None and detail(client,a)['document_version']==5
    assert detail(client,b)['document_version']==1


def test_restore_batch_conflict_does_not_restore_other_versions(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    client.post('/api/v1/documents/'+id+'/trash',headers=headers,json={'expected_document_version':1})
    job=submit(client,headers,space,[id],'restore',{}, {id:1}).json()['job_id']
    assert finish(settings,job)['items'][0]['error_code']=='VERSION_CONFLICT'
    assert detail(client,id)['deleted_at'] is not None


@pytest.mark.parametrize('payload',[
    {'ocr':'true'},{'ocr_languages':'eng'},{'ocr':True,'ocr_languages':'fra'},
    {'request_id':'injected'},{'expected_document_version':1},{'force':1},
])
def test_reprocess_rejects_invalid_options(api,payload):
    _,_,client,headers,space=api
    assert submit(client,headers,space,['id'],'reprocess',payload).status_code==422


def test_batch_reprocess_partial_results_no_undo_and_fenced_enqueue(api):
    _,settings,client,headers,space=api
    a=upload(client,headers,space,b'reparse-a')['document_id']
    b=upload(client,headers,space,b'reparse-b')['document_id']
    # Finish initial uploads with explicit failure so a fresh parse can be queued.
    queue=JobQueue(settings)
    for _ in range(2):
        claim=queue.claim('initial')
        queue.failure(claim['id'],claim['lease_token'],'TEST_INITIAL_FAILURE','fixture',retryable=False)
    job=submit(client,headers,space,[a,b,'missing'],'reprocess',{}).json()['job_id']
    patch(client,headers,b,1,title='Concurrent edit')
    claim=queue.claim('batch')
    def expires(db,owned):
        result=execute(db,owned,settings)
        db.execute('UPDATE jobs SET lease_expires_at=0 WHERE id=?',(job,))
        return result
    with pytest.raises(LostLease):queue.complete(job,claim['lease_token'],expires)
    with connect(settings.database) as db:
        assert db.execute("SELECT count(*) FROM jobs WHERE kind='parse'").fetchone()[0]==2
    queue.complete(job,claim['lease_token'],lambda db,owned: execute(db,owned,settings))
    result=queue.get(job)['result']
    assert result['succeeded']==1 and result['failed']==2
    child=result['items'][0]['parse_job_id']
    assert queue.get(child)['status']=='queued'
    assert detail(client,a)['document_version']==1
    assert {i.get('error_code') for i in result['items']}=={None,'VERSION_CONFLICT','NOT_FOUND'}
    assert client.post('/api/v1/jobs/'+job+'/undo',headers=headers).status_code==409
    another=submit(client,headers,space,[a],'reprocess',{}).json()['job_id']
    running=queue.claim('parse')
    assert running['id']==child
    claimed=queue.claim('batch')
    queue.complete(another,claimed['lease_token'],lambda db,owned: execute(db,owned,settings))
    assert queue.get(another)['result']['items'][0]['error_code']=='PARSE_ALREADY_RUNNING'


def test_batch_ocr_options_and_trashed_cross_space_guards(api):
    _,settings,client,headers,space=api
    a=upload(client,headers,space,b'ocr-options')['document_id']
    b=upload(client,headers,space,b'trashed-options')['document_id']
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Batch other'}).json()['id']
    c=upload(client,headers,other,b'other-options')['document_id']
    client.post('/api/v1/documents/'+b+'/trash',headers=headers,json={'expected_document_version':1})
    queued=submit(client,headers,space,[a,b,c],'reprocess',
        {'ocr':True,'ocr_languages':'eng,chi_sim','generate_preview':False},{a:1,b:2,c:1}).json()['job_id']
    result=finish(settings,queued)
    assert result['succeeded']==1 and result['failed']==2
    assert {i.get('error_code') for i in result['items']}=={None,'DOCUMENT_TRASHED','CROSS_SPACE_REFERENCE'}
    with connect(settings.database) as db:
        child=db.execute('SELECT kind,payload_json FROM jobs WHERE id=?',(result['items'][0]['parse_job_id'],)).fetchone()
        assert child[0]=='ocr'
        assert json.loads(child[1])['ocr_languages']=='chi_sim,eng'
        assert json.loads(child[1])['generate_preview'] is False
