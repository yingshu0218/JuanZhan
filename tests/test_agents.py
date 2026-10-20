"""Real SQLite/files/Converter HTTP and agent protocol, never model mocks."""
import json
import time
import pytest
from test_parsing import pipeline,upload,append
from test_indexing import drain
from juanzhan.worker import Worker
from juanzhan.auth import digest,set_password
from juanzhan.database import connect
from juanzhan.overviews import summarize

ROOT='/api/v1/agent'

def credential(pipeline,spaces=None):
    settings,client,csrf,space=pipeline
    response=client.post('/api/v1/agent-tokens',headers=csrf,json={'name':'read-only-test','space_ids':spaces or [space]})
    assert response.status_code==201,response.text
    token=response.json();return token,{'Authorization':'Bearer '+token['token']}

def parsed(pipeline,text='# 合同资料\n\n## 验收\n\n合同金额：30000元。\n\n## 风险\n\n注意：延期应书面通知。'):
    settings,_,_,_=pipeline;doc=upload(pipeline,text.encode(),'合同.md');assert Worker(settings).run_once()['status']=='completed';drain(settings);return doc['document_id']

def rpc(client,headers,method,params=None,version='2025-11-25',id=1):
    params=params or {}
    h={**headers,'Accept':'application/json, text/event-stream','MCP-Protocol-Version':version}
    if version=='2026-07-28':
        params={**params,'_meta':{'io.modelcontextprotocol/protocolVersion':version,'io.modelcontextprotocol/clientInfo':{'name':'test-agent','version':'1'},'io.modelcontextprotocol/clientCapabilities':{}}}
        h['Mcp-Method']=method
        if method=='tools/call':h['Mcp-Name']=params.get('name','')
    return client.post(ROOT+'/mcp',headers=h,json={'jsonrpc':'2.0','id':id,'method':method,'params':params})


def test_scope_credential_lifecycle_csrf_and_business_write_denial(pipeline):
    settings,client,csrf,space=pipeline
    assert client.post('/api/v1/agent-tokens',json={'name':'x','space_ids':[space]}).status_code==403
    assert client.post('/api/v1/agent-tokens',headers=csrf,json={'name':'x','space_ids':[space,space]}).status_code==422
    assert client.post('/api/v1/agent-tokens',headers=csrf,json={'name':'x','space_ids':['unknown']}).status_code==422
    token,h=credential(pipeline)
    assert client.get(ROOT+'/spaces',headers=h).json()['items'][0]['id']==space
    assert token['token'].startswith('jza_')
    with connect(settings.database) as db:
        stored=db.execute('SELECT token_hash FROM agent_tokens WHERE id=?',(token['id'],)).fetchone()[0]
        assert stored==digest(token['token']) and token['token'] not in stored
    assert 'token' not in client.get('/api/v1/agent-tokens').json()[0]
    for method,path in [('GET','/api/v1/documents'),('POST','/api/v1/documents/search'),('POST','/api/v1/spaces'),('GET','/api/v1/auth/tokens'),('POST','/api/v1/agent-tokens')]:
        assert client.request(method,path,headers=h,json={}).status_code==403,(method,path)
    assert client.get(ROOT+'/catalog',headers=h,params={'space_id':space}).status_code==200
    assert client.delete('/api/v1/agent-tokens/'+token['id'],headers=csrf).status_code==204
    assert client.get(ROOT+'/spaces',headers=h).status_code==401


def test_spaces_and_document_scope_404_trash_and_cross_run_rejected(pipeline):
    settings,client,csrf,space=pipeline;id=parsed(pipeline)
    other=client.post('/api/v1/spaces',headers=csrf,json={'name':'Private'}).json()['id']
    token,h=credential(pipeline,[other])
    assert len(client.get(ROOT+'/spaces',headers=h).json()['items'])==1
    for path in ('/catalog','/documents/'+id+'/overview','/documents/'+id+'/content'):
        assert client.get(ROOT+path,headers=h,params={'space_id':space}).status_code==404
    assert client.get(ROOT+'/documents/'+id+'/overview',headers=h,params={'space_id':other}).status_code==404
    _,h=credential(pipeline)
    second=parsed(pipeline,'Different source')
    run=client.get('/api/v1/documents/'+second).json()['current_parse_run_id']
    assert client.get(ROOT+'/documents/'+id+'/content',headers=h,params={'space_id':space,'parse_run_id':run}).status_code==404
    version=client.get('/api/v1/documents/'+id).json()['document_version']
    response=client.post('/api/v1/documents/'+id+'/trash',headers=csrf,json={'expected_document_version':version})
    assert response.status_code==200,response.text
    assert client.get(ROOT+'/documents/'+id+'/overview',headers=h,params={'space_id':space}).status_code==404


def test_external_natural_language_workflow_search_overview_read_analysis(pipeline):
    settings,client,csrf,space=pipeline;id=parsed(pipeline);_,h=credential(pipeline)
    before=client.get('/api/v1/documents/'+id).json()
    # The external agent turns the user's question into lexical keywords and chosen document IDs.
    query=client.post(ROOT+'/search',headers=h,json={'space_id':space,'text':'合同 金额'})
    assert query.status_code==200,query.text
    assert [item['id'] for item in query.json()['items']]==[id]
    assert query.json()['search_index']['incomplete'] is False
    from test_fields import create as create_field
    from test_metadata import write
    created=create_field(client,csrf,space,key='amount',type='decimal',filterable=True)
    assert created.status_code==201
    version=client.get('/api/v1/documents/'+id).json()['document_version']
    assert write(client,csrf,id,version,{'amount':'30000.0001'}).status_code==200
    drain(settings)
    before=client.get('/api/v1/documents/'+id).json()
    catalog=client.get(ROOT+'/catalog',headers=h,params={'space_id':space}).json()
    assert catalog['fields'][0]['key']=='amount' and catalog['fields'][0]['constraints']=={}
    exact=client.post(ROOT+'/search',headers=h,json={'space_id':space,'metadata':[{'key':'amount','operator':'gte','value':'30000.0001'}]})
    assert exact.status_code==200 and exact.json()['total']==1
    assert client.post(ROOT+'/search',headers=h,json={'space_id':space,'metadata':[{'key':'amount','operator':'gt','value':'30000.0001'}]}).status_code==422
    overview=client.get(ROOT+'/documents/'+id+'/overview',headers=h,params={'space_id':space})
    assert overview.status_code==200,overview.text
    summary=overview.json();assert summary['method']=='extractive-v2' and summary['points']
    web=client.get('/api/v1/documents/'+id+'/overview').json();assert web==summary
    source=summary['points'][0]['sources'][0]
    read=client.get(ROOT+'/documents/'+id+'/content',headers=h,params={'space_id':space,'parse_run_id':summary['parse_run_id']}).json()
    assert any(block['id']==source['block_id'] for block in read['blocks'])
    analysis=client.post(ROOT+'/analysis-context',headers=h,json={'space_id':space,'question':'这份合同有哪些金额和延期风险？','document_ids':[id]})
    assert analysis.status_code==200,analysis.text
    result=analysis.json();assert not result['answer_generated'] and 'untrusted' in result['instructions']
    assert '30000' in str(result) and '延期' in str(result)
    assert result['documents'][0]['evidence']['parse_run_id']==summary['parse_run_id']
    fields=result['documents'][0]['evidence']['business_fields']
    assert fields['items'][0]['value']=='30000.0001' and fields['items'][0]['is_confirmed']
    assert fields['scope']=='current_document' and not fields['partial']
    assert result['documents'][0]['evidence']['document_version']==summary['document_version']
    assert str(settings.data_dir) not in analysis.text
    after=client.get('/api/v1/documents/'+id).json();assert before==after
    assert overview.headers['cache-control']=='no-store'
    assert client.post(ROOT+'/search',headers=h,json={'space_id':space,'trash':'include'}).status_code==422
    assert client.post(ROOT+'/analysis-context',headers=h,json={'space_id':space,'question':'x','document_ids':[id,id]}).status_code==422


@pytest.mark.parametrize('version',['2025-06-18','2025-11-25','2026-07-28'])
def test_mcp_discovery_and_tools_are_readonly_and_interoperate(pipeline,version):
    settings,client,_,space=pipeline;id=parsed(pipeline);_,h=credential(pipeline)
    if version=='2026-07-28':
        result=rpc(client,h,'server/discover',version=version).json()['result']
        assert result['supportedVersions'][0]==version and result['resultType']=='complete'
    else:
        init=rpc(client,h,'initialize',{'protocolVersion':version,'clientInfo':{'name':'test','version':'1'},'capabilities':{}},version=version)
        assert init.json()['result']['protocolVersion']==version
    response=rpc(client,h,'tools/list',version=version)
    assert response.status_code==200,response.text
    names={tool['name'] for tool in response.json()['result']['tools']}
    assert names=={'list_spaces','get_catalog','search_documents','get_document_overview','read_document','prepare_analysis','get_formats'}
    for tool in response.json()['result']['tools']:assert tool['annotations']['readOnlyHint']
    result=rpc(client,h,'tools/call',{'name':'get_document_overview','arguments':{'space_id':space,'document_id':id}},version).json()['result']
    assert not result['isError'] and result['structuredContent']['document_id']==id
    denied=rpc(client,h,'tools/call',{'name':'read_document','arguments':{'space_id':space,'document_id':'unknown'}},version).json()['result']
    assert denied['isError'] and 'NOT_FOUND' in denied['content'][0]['text']


def test_protocol_budgets_origin_unknown_version_and_invalid_input(pipeline):
    _,client,_,space=pipeline;_,h=credential(pipeline)
    assert rpc(client,{**h,'Origin':'https://evil.invalid'},'tools/list').status_code==403
    assert client.post(ROOT+'/mcp',headers=h,json={}).status_code==406
    assert client.get(ROOT+'/mcp',headers=h).status_code==405
    assert client.delete(ROOT+'/mcp',headers=h).status_code==405
    assert rpc(client,h,'tools/list',version='1900-01-01').json()['error']['code']==-32022
    assert rpc(client,h,'unknown',version='2026-07-28').status_code==404
    headers={**h,'Accept':'application/json,text/event-stream','MCP-Protocol-Version':'2026-07-28','Mcp-Method':'wrong'}
    assert client.post(ROOT+'/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{'_meta':{'io.modelcontextprotocol/protocolVersion':'2026-07-28'}}}).json()['error']['code']==-32020
    assert client.post(ROOT+'/mcp',headers={**h,'Accept':'application/json,text/event-stream'},json=[]).status_code==400
    assert client.post(ROOT+'/search',headers={**h,'Content-Type':'application/json'},content='x'*65537).status_code==413
    assert client.post(ROOT+'/search',headers=h,json={'space_id':space,'page_size':21}).status_code==422
    assert client.post(ROOT+'/search',headers=h,json={'space_id':space,'url':'https://evil.invalid'}).status_code==422


def test_expiry_rate_and_password_reset_revoke_scoped_credentials(pipeline):
    settings,client,_,_=pipeline;token,h=credential(pipeline)
    with connect(settings.database) as db:
        db.execute('UPDATE agent_tokens SET rate_window=?,rate_count=60 WHERE id=?',(int(time.time())//60,token['id']));db.commit()
    assert client.get(ROOT+'/spaces',headers=h).status_code==429
    with connect(settings.database) as db:
        db.execute('UPDATE agent_tokens SET expires_at=0 WHERE id=?',(token['id'],));db.commit()
    assert client.get(ROOT+'/spaces',headers=h).status_code==401
    _,h=credential(pipeline);set_password(settings,'new-password-for-tests')
    assert client.get(ROOT+'/spaces',headers=h).status_code==401
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM agent_token_spaces').fetchone()[0]==0


def test_backend_overview_keeps_irregular_chapters_and_source_indices():
    data={'total':4,'body':[{'id':'a','index':0,'type':'heading','text':'第一章','structure':{'level':1}},
        {'id':'b','index':1,'type':'paragraph','text':'书籍第一段。'},
        {'id':'c','index':2,'type':'heading','text':'第二章','structure':{'level':2}},
        {'id':'d','index':3,'type':'paragraph','text':'书籍第二段。'}]}
    result=summarize(data)
    assert [point['label'] for point in result['points']]==['第一章','第二章']
    assert result['points'][0]['sources'][0]['block_id']=='a'


def test_analysis_retains_confirmed_fields_when_no_body_and_large_integer_precision(pipeline):
    settings,client,csrf,space=pipeline
    from test_fields import create as create_field
    from test_metadata import write
    id=upload(pipeline,b'\x00unknown','unsupported.bin')['document_id'];Worker(settings).run_once()
    assert create_field(client,csrf,space,key='code',type='integer').status_code==201
    version=client.get('/api/v1/documents/'+id).json()['document_version']
    assert write(client,csrf,id,version,{'code':9223372036854775807}).status_code==200
    _,h=credential(pipeline)
    result=client.post(ROOT+'/analysis-context',headers=h,json={'space_id':space,'question':'读取人工确认编号','document_ids':[id]})
    assert result.status_code==200,result.text
    data=result.json()['documents'][0]
    assert data['evidence'] is None and not data['overview']['text_available']
    field=data['business_fields']['items'][0]
    assert field['is_confirmed'] and field['value']=='9223372036854775807' and field['value_encoding']=='integer-string'


def test_restore_does_not_revive_agent_credentials(pipeline,tmp_path):
    from fastapi.testclient import TestClient
    from juanzhan.apps import create_app
    from juanzhan.backup import create,restore
    from juanzhan.config import Settings
    settings,client,_,_=pipeline;_,h=credential(pipeline)
    bundle=tmp_path/'agent-backup';create(settings,bundle)
    destination=tmp_path/'agent-restore';assert restore(bundle,destination)['credentials_revoked']
    recovered=Settings(destination,'pipeline-token',cookie_secure=False)
    with TestClient(create_app('archive',recovered)) as after:
        assert after.get(ROOT+'/spaces',headers=h).status_code==401
    assert client.get(ROOT+'/spaces',headers=h).status_code==200
    with connect(recovered.database) as db:
        assert db.execute('SELECT count(*) FROM agent_tokens').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM agent_token_spaces').fetchone()[0]==0
