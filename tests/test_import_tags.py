"""Real SQLite, managed bytes and HTTP pipeline tag precedence and filtering."""
from test_parsing import pipeline, upload, append, queue_parse
from test_agent_imports import token, imported, payload, ROOT
from juanzhan.worker import Worker
from juanzhan.database import connect

def names(client, space, document):
    tags={tag['id']:tag['name'] for tag in client.get('/api/v1/tags',params={'space_id':space}).json()}
    return {tags[id] for id in client.get('/api/v1/documents/'+document).json()['tag_ids']}

def test_fallback_agent_override_and_explicit_empty(pipeline):
    settings,client,_,space=pipeline;_,h=token(pipeline)
    saved=imported(pipeline,h,name='contract.txt',data=b'Contract payment after acceptance.').json()
    assert names(client,space,saved['document_id'])=={'TXT','合同'}
    body=payload(saved,text='Contract payment after acceptance.');body['tags']=['采购','  验收  ','采购']
    path=ROOT+'/imports/'+saved['id']+'/analyses'
    assert client.post(path,headers=h,json=body).status_code==201
    assert names(client,space,saved['document_id'])=={'采购','验收'}
    assert Worker(settings).run_once()['status']=='completed'
    assert names(client,space,saved['document_id'])=={'采购','验收'}
    body['submission_id']='empty';body['tags']=[]
    assert client.post(path,headers=h,json=body).status_code==201
    assert names(client,space,saved['document_id'])==set()
    # Explicit reparse also respects Agent's empty selection.
    queue_parse(settings,saved['document_id'],saved['revision_id'])
    assert Worker(settings).run_once()['status']=='completed'
    assert names(client,space,saved['document_id'])==set()

def test_manual_selection_wins_and_any_all_search(pipeline):
    settings,client,csrf,space=pipeline;_,h=token(pipeline)
    saved=imported(pipeline,h).json();doc=saved['document_id']
    a=client.post('/api/v1/tags',headers=csrf,json={'space_id':space,'name':'项目A'}).json()['id']
    b=client.post('/api/v1/tags',headers=csrf,json={'space_id':space,'name':'待跟进'}).json()['id']
    current=client.get('/api/v1/documents/'+doc).json()
    edited=client.patch('/api/v1/documents/'+doc,headers=csrf,json={'expected_document_version':current['document_version'],'tags_add':[a,b],'tags_remove':current['tag_ids']})
    assert edited.status_code==200,edited.text
    body=payload(saved);body['tags']=['不应覆盖人工']
    assert client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=body).status_code==201
    assert names(client,space,doc)=={'项目A','待跟进'}
    second=upload(pipeline,b'Second file','other.txt')['document_id']
    current=client.get('/api/v1/documents/'+second).json()
    assert client.patch('/api/v1/documents/'+second,headers=csrf,json={'expected_document_version':current['document_version'],'tags_add':[a]}).status_code==200
    for mode,count in [('all',1),('any',2)]:
        r=client.post('/api/v1/documents/search',headers=csrf,json={'space_id':space,'tags':{'ids':[a,b],'match':mode}})
        assert r.status_code==200,r.text
        assert r.json()['total']==count
    bad=client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json={**body,'submission_id':'bad','tags':['\n']})
    assert bad.status_code==422

def test_content_fallback_new_revision_and_old_original_preserved(pipeline):
    settings,client,_,space=pipeline
    saved=upload(pipeline,b'Meeting minutes with an action plan.','notes.txt');doc=saved['document_id']
    assert names(client,space,doc)=={'TXT'}
    assert Worker(settings).run_once()['status']=='completed'
    assert names(client,space,doc)=={'TXT','会议'}
    revision=append(settings,doc,b'Invoice billing summary.')
    queue_parse(settings,doc,revision)
    assert Worker(settings).run_once()['status']=='completed'
    assert names(client,space,doc)=={'TXT','账单'}
    with connect(settings.database) as db:
        assert db.execute('select count(*) from file_revisions where document_id=?',(doc,)).fetchone()[0]==2

def test_saved_filter_persistence_space_scope_and_csrf(pipeline):
    settings,client,csrf,space=pipeline
    body={'space_id':space,'name':'采购待办','criteria':{'text':'采购','tag_ids':[],'match':'all'}}
    assert client.post('/api/v1/saved-filters',json=body).status_code==403
    r=client.post('/api/v1/saved-filters',headers=csrf,json=body);assert r.status_code==200,r.text
    saved=r.json()
    assert client.get('/api/v1/saved-filters',params={'space_id':space}).json()==[saved]
    replaced=client.post('/api/v1/saved-filters',headers=csrf,json={**body,'criteria':{'text':'修订'}}).json()
    assert replaced['id']==saved['id']
    other=client.post('/api/v1/spaces',headers=csrf,json={'name':'another'}).json()['id']
    assert client.get('/api/v1/saved-filters',params={'space_id':other}).json()==[]
    assert client.delete('/api/v1/saved-filters/'+saved['id'],headers=csrf).status_code==204
    assert client.get('/api/v1/saved-filters',params={'space_id':space}).json()==[]

def test_tag_policies_and_saved_filters_survive_backup_restore(pipeline,tmp_path):
    from juanzhan.backup import create,restore
    settings,client,csrf,space=pipeline
    saved=upload(pipeline,b'Invoice sample.','invoice.txt')
    response=client.post('/api/v1/saved-filters',headers=csrf,json={'space_id':space,'name':'账单','criteria':{'tag_ids':client.get('/api/v1/documents/'+saved['document_id']).json()['tag_ids']}})
    assert response.status_code==200
    bundle=tmp_path/'tag-backup';create(settings,bundle);restore(bundle,tmp_path/'tag-restored')
    with connect(tmp_path/'tag-restored/database/archive.sqlite3') as db:
        assert db.execute('select count(*) from saved_filters').fetchone()[0]==1
        assert db.execute('select source from document_tag_policy').fetchone()[0]=='platform'
        assert db.execute('select count(*) from automatic_document_tags').fetchone()[0]==2
        assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert not db.execute('pragma foreign_key_check').fetchall()
