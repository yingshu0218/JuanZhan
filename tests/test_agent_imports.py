"""External-agent imports use real original bytes, SQLite and local Converter fallback."""
import copy
import json
import pytest
from test_parsing import pipeline
from juanzhan.worker import Worker
from juanzhan.database import connect
from format_samples import samples

ROOT='/api/v1/agent'
def token(pipeline,enabled=True,spaces=None):
    _,client,csrf,space=pipeline
    r=client.post('/api/v1/agent-tokens',headers=csrf,json={'name':'external-test-agent','space_ids':spaces or [space],'import_enabled':enabled})
    assert r.status_code==201,r.text
    return r.json(),{'Authorization':'Bearer '+r.json()['token']}
def imported(pipeline,h,name='meeting.txt',data=b'Confirmed delivery on Friday.',key='import-1'):
    _,client,_,space=pipeline
    return client.post(ROOT+'/imports/'+key,params={'space_id':space,'filename':name},headers={**h,'Content-Type':'application/octet-stream'},content=data)
def payload(saved,template='generic',text='Confirmed delivery on Friday.'):
    from juanzhan.agent_imports import TEMPLATES
    point={'text':'Delivery is confirmed for Friday.','basis':'explicit','sources':[{'start':0,'end':len(text),'quote':text}]}
    return {'submission_id':'analysis-1','revision_id':saved['revision_id'],'original_sha256':saved['original_sha256'],'template_id':template,'template_version':1,'agent_name':'External fixture agent','markdown':text,'summary':[point],'fields':{k:None for k in TEMPLATES[template]['fields']},'additional_points':[]}

@pytest.mark.parametrize('template',['generic','contract','invoice','meeting','report'])
def test_templates_import_submit_read_original_and_local_fallback(pipeline,template):
    settings,client,_,space=pipeline;_,h=token(pipeline)
    templates=client.get(ROOT+'/analysis-templates',headers=h)
    assert templates.status_code==200 and len(templates.json()['templates'])==5
    result=imported(pipeline,h);assert result.status_code==201,result.text;saved=result.json()
    replay=imported(pipeline,h);assert replay.json()==saved
    assert imported(pipeline,h,data=b'different').status_code==409
    body=payload(saved,template)
    r=client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=body);assert r.status_code==201,r.text
    assert client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=body).json()==r.json()
    different=copy.deepcopy(body);different['summary'][0]['text']='Different conclusion'
    assert client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=different).status_code==409
    read=client.get(ROOT+'/documents/'+saved['document_id']+'/analyses',params={'space_id':space},headers=h)
    assert read.status_code==200 and read.json()['items'][0]['analysis']==body
    assert Worker(settings).run_once()['status']=='completed'
    assert client.get('/api/v1/documents/'+saved['document_id']+'/download').content==b'Confirmed delivery on Friday.'
    with connect(settings.database) as db:
        assert db.execute('select count(*) from parse_runs').fetchone()[0]==0
        result=json.loads(db.execute("select result_json from jobs where kind='parse'").fetchone()[0])
        assert result['reason']=='AGENT_ANALYSIS_AVAILABLE'
    with connect(settings.database) as db:
        assert db.execute('select count(*) from documents').fetchone()[0]==1
        assert db.execute('select count(*) from metadata_values').fetchone()[0]==0


def test_readonly_scope_revoke_other_agent_and_invalid_evidence(pipeline):
    _,client,csrf,space=pipeline
    _,readonly=token(pipeline,False);assert imported(pipeline,readonly).status_code==403
    issued,h=token(pipeline);saved=imported(pipeline,h).json()
    _,other=token(pipeline);body=payload(saved)
    endpoint=ROOT+'/imports/'+saved['id']+'/analyses'
    assert client.post(endpoint,headers=other,json=body).status_code==404
    bad=copy.deepcopy(body);bad['summary'][0]['sources'][0]['quote']='invented'
    assert client.post(endpoint,headers=h,json=bad).status_code==422
    bad=copy.deepcopy(body);bad['original_sha256']='0'*64
    assert client.post(endpoint,headers=h,json=bad).status_code==409
    bad=copy.deepcopy(body);bad['fields']['invented']=None
    assert client.post(endpoint,headers=h,json=bad).status_code==422
    private=client.post('/api/v1/spaces',headers=csrf,json={'name':'private'}).json()['id']
    _,restricted=token(pipeline,spaces=[private]);assert imported(pipeline,restricted).status_code==404
    assert client.get('/api/v1/documents',headers=h).status_code==403
    assert client.delete('/api/v1/agent-tokens/'+issued['id'],headers=csrf).status_code==204
    assert imported(pipeline,h,key='next').status_code==401

@pytest.mark.parametrize('kind',['txt','md','html','docx','pdf'])
def test_several_real_file_formats_import_without_analysis(pipeline,kind):
    settings,client,_,_=pipeline;_,h=token(pipeline)
    _,data=samples()[kind]
    response=imported(pipeline,h,name='source.'+kind,data=data)
    assert response.status_code==201,response.text
    assert Worker(settings).run_once()['status']=='completed'
    assert client.get('/api/v1/documents/'+response.json()['document_id']+'/download').content==data


def test_template_unknowns_inference_history_stale_and_backups(pipeline,tmp_path):
    from test_parsing import append
    from juanzhan.backup import create,restore
    settings,client,_,space=pipeline;_,h=token(pipeline)
    saved=imported(pipeline,h).json();body=payload(saved,'contract')
    body['summary'][0]['basis']='inference'
    endpoint=ROOT+'/imports/'+saved['id']+'/analyses'
    assert client.post(endpoint,headers=h,json=body).status_code==201
    second=copy.deepcopy(body);second['submission_id']='second';second['template_id']='generic'
    second['fields']={k:None for k in ['topic','main_points','conclusions','open_questions']}
    assert client.post(endpoint,headers=h,json=second).status_code==201
    path=ROOT+'/documents/'+saved['document_id']+'/analyses'
    result=client.get(path,headers=h,params={'space_id':space}).json()
    assert result['total']==2 and len(result['items'])==1
    assert client.get(path,headers=h,params={'space_id':space,'page':2}).json()['items'][0]['analysis']['summary'][0]['basis']=='inference'
    append(settings,saved['document_id'],b'Next original revision')
    assert client.post(endpoint,headers=h,json=body).status_code==409
    assert client.get(path,headers=h,params={'space_id':space}).json()['items'][0]['stale']
    bundle=tmp_path/'bundle';create(settings,bundle);restore(bundle,tmp_path/'restored')
    with connect(tmp_path/'restored/database/archive.sqlite3') as db:
        assert db.execute('select count(*) from agent_analyses').fetchone()[0]==2
        assert db.execute('select count(*) from agent_tokens').fetchone()[0]==0


def test_raw_import_boundaries_and_json_budget(pipeline):
    _,client,_,_=pipeline;_,h=token(pipeline)
    for name in ['../secret.txt','.DS_Store','a/b.txt']:
        assert imported(pipeline,h,name=name).status_code==422
    saved=imported(pipeline,h).json()
    endpoint=ROOT+'/imports/'+saved['id']+'/analyses'
    assert client.post(endpoint,headers={**h,'Content-Type':'application/json'},content=b' '*(2*1024*1024+1)).status_code==413
    assert imported(pipeline,h,name='renamed.txt').status_code==409


def test_external_markdown_is_searchable_without_local_text_and_mcp_pages(pipeline):
    from test_indexing import drain
    from test_agents import rpc
    settings,client,_,space=pipeline;_,h=token(pipeline)
    saved=imported(pipeline,h,name='binary.dat',data=b'\x00binary file').json()
    body=payload(saved,text='External OCR evidence with unique needleword.')
    endpoint=ROOT+'/imports/'+saved['id']+'/analyses'
    assert client.post(endpoint,headers=h,json=body).status_code==201
    Worker(settings).run_once();drain(settings)
    found=client.post(ROOT+'/search',headers=h,json={'space_id':space,'text':'needleword'})
    assert found.status_code==200 and found.json()['total']==1
    result=rpc(client,h,'tools/call',{'name':'read_document_analysis','arguments':{'space_id':space,'document_id':saved['document_id'],'length':10}}).json()['result']
    assert not result.get('isError'),result
    from juanzhan.agent_imports import ReadAnalysis
    assert ReadAnalysis.model_fields['offset'].default==0


def test_agent_priority_preserves_explicit_reparse_and_revision_fallback(pipeline):
    from test_parsing import append, queue_parse
    settings,client,_,_=pipeline
    _,h=token(pipeline); saved=imported(pipeline,h).json()
    assert client.post(ROOT+'/imports/'+saved['id']+'/analyses',headers=h,json=payload(saved)).status_code==201
    assert Worker(settings).run_once()['status']=='completed'
    doc=client.get('/api/v1/documents/'+saved['document_id']).json()
    assert doc['processing_status']=='completed' and not doc['content_stale']
    # An explicit request is independent of the automatic import job.
    from juanzhan.jobs import JobSpec
    client.app.state.jobs.enqueue(JobSpec(kind='parse',target_type='document',target_id=saved['document_id'],payload={'revision_id':saved['revision_id']},idempotency_key='explicit-agent-reparse'))
    assert Worker(settings).run_once()['status']=='completed'
    with connect(settings.database) as db:
        assert db.execute('select count(*) from parse_runs').fetchone()[0]==1
    revision=append(settings,saved['document_id'],b'New version needs local extraction.')
    queue_parse(settings,saved['document_id'],revision)
    assert Worker(settings).run_once()['status']=='completed'
    with connect(settings.database) as db:
        assert db.execute('select count(*) from parse_runs').fetchone()[0]==2
