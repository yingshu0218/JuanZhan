import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from test_document_api import api, upload, detail, patch
from juanzhan.apps import create_app
from juanzhan.database import connect


def create(client,headers,space,key='amount',type='decimal',**values):
    return client.post('/api/v1/field-definitions',headers=headers,json={
        'space_id':space,'key':key,'type':type,'label':'Amount',**values})


def update(client,headers,id,**values):
    return client.patch('/api/v1/field-definitions/'+id,headers=headers,json=values)


def test_seven_types_scoped_list_patch_flags_and_persistence(api):
    _,settings,client,headers,space=api
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Second'}).json()['id']
    types=['text','long_text','integer','decimal','date','boolean','single_select']
    saved=[]
    for type in types:
        response=create(client,headers,space,key=type,type=type)
        assert response.status_code==201,response.text
        field=response.json();saved.append(field)
        assert field['constraints']=={} and not field['searchable'] and field['is_active']
    foreign=create(client,headers,other,key='decimal').json()
    assert len(client.get('/api/v1/field-definitions').json())==8
    listed=client.get('/api/v1/field-definitions',params={'space_id':space}).json()
    assert [f['key'] for f in listed]==sorted(types)
    assert foreign['id'] not in [f['id'] for f in listed]
    changed=update(client,headers,saved[3]['id'],label='  金额  ',constraints={'min':'2.00','max':'10.00'},searchable=True,filterable=True,is_active=False)
    assert changed.status_code==200
    current=changed.json()
    assert current['label']=='金额' and current['constraints']=={'min':'2.00','max':'10.00'}
    assert current['searchable'] and current['filterable'] and not current['is_active']
    assert current['key']=='decimal' and current['type']=='decimal'
    with TestClient(create_app('archive',settings),base_url='https://archive.test') as restarted:
        assert current in restarted.get('/api/v1/field-definitions',headers={'Cookie':'; '.join(k+'='+v for k,v in client.cookies.items())}).json()
    assert update(client,headers,current['id'],constraints={},is_active=True).json()['constraints']=={}


@pytest.mark.parametrize('values',[
    {'key':'Wrong-Key'},{'key':'2amount'},{'type':'multi_select'},{'label':'   '},{'label':'bad\x00label'},
    {'label':None},{'constraints':[]},{'constraints':None},{'searchable':1},{'filterable':'true'},
    {'is_active':False},{'unknown':'extra'},
])
def test_strict_create_validation(api,values):
    _,_,client,headers,space=api
    assert create(client,headers,space,**values).status_code==422


def test_auth_unknown_scope_and_immutable_identity(api):
    _,_,client,headers,space=api
    with TestClient(client.app,base_url='https://archive.test') as anonymous:
        assert anonymous.get('/api/v1/field-definitions').status_code==401
    assert create(client,{},space).status_code==403
    assert create(client,headers,'missing').status_code==404
    assert client.get('/api/v1/field-definitions?space_id=missing').status_code==404
    id=create(client,headers,space).json()['id']
    for values in ({},{'key':'new'},{'type':'text'},{'space_id':space},{'constraints':None},{'label':None},{'is_active':None},{'searchable':1}):
        assert update(client,headers,id,**values).status_code==422
    assert update(client,headers,'missing',label='Missing').status_code==404
    assert client.delete('/api/v1/field-definitions/'+id,headers=headers).status_code==405
    assert client.get('/api/v1/field-definitions').json()[0]['key']=='amount'


def test_key_unique_including_inactive_but_reusable_in_other_space(api):
    _,_,client,headers,space=api
    first=create(client,headers,space).json()
    update(client,headers,first['id'],is_active=False)
    assert create(client,headers,space).status_code==409
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    assert create(client,headers,other).status_code==201
    def concurrent(_):return create(client,headers,space,key='race').status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(concurrent,range(2)))==[201,409]


def test_constraints_are_bounded_json_preserved_without_claiming_value_validation(api):
    _,_,client,headers,space=api
    constraints={'options':[{'id':'stable','label':'选项'}]}
    saved=create(client,headers,space,type='single_select',constraints=constraints).json()
    assert saved['constraints']==constraints
    deep={}
    for _ in range(10):deep={'nested':deep}
    assert create(client,headers,space,key='deep',constraints=deep).status_code==422
    assert create(client,headers,space,key='large',constraints={'text':'x'*17000}).status_code==422
    assert update(client,headers,saved['id'],label='Must rollback',constraints={'text':'x'*17000}).status_code==422
    assert client.get('/api/v1/field-definitions').json()[0]==saved
    response=client.post('/api/v1/field-definitions',headers={**headers,'Content-Type':'application/json'},content=json.dumps({
        'space_id':space,'key':'invalid_float','label':'Invalid','type':'decimal','constraints':{'min':float('nan')}}))
    assert response.status_code==422


def test_template_disabled_fields_and_history_are_preserved(api):
    _,settings,client,headers,space=api
    field=create(client,headers,space,key='count',type='integer').json()
    binding={'field_definition_id':field['id'],'required_for_filing':True,'display_order':3}
    def template(key,fields):return client.post('/api/v1/document-types',headers=headers,json={'space_id':space,'key':key,'label':key,'fields':fields})
    type=template('invoice',[binding]).json()
    id=upload(client,headers,space)['document_id']
    patch(client,headers,id,1,document_type_id=type['id'])
    with connect(settings.database) as db:
        db.execute("INSERT INTO metadata_values(id,document_id,space_id,field_definition_id,value_integer,origin,updated_at) VALUES ('history',?,?,?,12,'manual','now')",(id,space,field['id']))
        db.commit()
    update(client,headers,field['id'],is_active=False,label='New label')
    assert template('blocked',[binding]).status_code==422
    assert all(t['key']!='blocked' for t in client.get('/api/v1/document-types').json())
    # Existing inactive references can be retained/reordered, never silently stripped.
    binding['display_order']=1
    assert client.patch('/api/v1/document-types/'+type['id'],headers=headers,json={'fields':[binding]}).status_code==200
    before=detail(client,id)
    assert client.patch('/api/v1/document-types/'+type['id'],headers=headers,json={'fields':[]}).status_code==200
    assert patch(client,headers,id,2,document_type_id=None).status_code==200
    with connect(settings.database) as db:
        assert db.execute("SELECT value_integer FROM metadata_values WHERE id='history'").fetchone()==(12,)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert before['document_version']==2
    assert client.patch('/api/v1/document-types/'+type['id'],headers=headers,json={'fields':[binding]}).status_code==422
    update(client,headers,field['id'],is_active=True)
    assert template('allowed',[binding]).status_code==201


def test_field_limit_is_transactional_includes_disabled_and_scope_isolated(api):
    _,settings,client,headers,space=api
    with connect(settings.database) as db:
        db.executemany("INSERT INTO field_definitions(id,space_id,field_key,label,field_type,is_active,created_at) VALUES (?,?,?,'Label','text',0,'now')",[(f'f{i}',space,f'key_{i}') for i in range(999)])
        db.commit()
    def concurrent(i):return create(client,headers,space,key='last_'+str(i)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(concurrent,range(2)))==[201,409]
    assert create(client,headers,space,key='overflow').json()['error']['code']=='FIELD_LIMIT_REACHED'
    assert len(client.get('/api/v1/field-definitions?space_id='+space).json())==1000
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    assert create(client,headers,other).status_code==201
