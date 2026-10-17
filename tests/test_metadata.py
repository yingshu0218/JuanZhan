import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_document_api import api, upload, detail, patch
from test_fields import create as field_create
from juanzhan.database import connect


def field(client,headers,space,key,kind,**rules):
    response=field_create(client,headers,space,key=key,type=kind,constraints=rules)
    assert response.status_code==201,response.text
    return response.json()['id']


def write(client,headers,id,version,values,confirm=True):
    return client.patch('/api/v1/documents/'+id+'/metadata',headers=headers,json={
        'expected_document_version':version,'values':values,'confirm':confirm})


def test_seven_types_exact_storage_null_false_noop_and_audit(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    for key,kind,rules in [('title','text',{'regex':'[A-Z]+','max_length':10}),('note','long_text',{}),
        ('count','integer',{}),('money','decimal',{'min':'2.00','max':'10.00'}),('day','date',{}),
        ('flag','boolean',{}),('choice','single_select',{'options':[{'id':'stable','label':'Choice'}]})]:field(client,headers,space,key,kind,**rules)
    values={'title':'ABC','note':'正文','count':-2,'money':'2.00','day':'2024-02-29','flag':False,'choice':'stable'}
    response=write(client,headers,id,1,values)
    assert response.status_code==200,response.text
    result={r['key']:r for r in response.json()}
    assert result['money']['value']=='2.0000' and result['flag']['value'] is False
    assert all(r['origin']=='manual' and r['is_confirmed'] and r['source_parse_run_id'] is None for r in result.values())
    assert detail(client,id)['document_version']==2
    assert write(client,headers,id,2,values).json()==response.json()
    assert detail(client,id)['document_version']==2
    with connect(settings.database) as db:
        assert db.execute('SELECT value_decimal_scaled FROM metadata_values WHERE value_decimal_scaled IS NOT NULL').fetchone()==(20000,)
        assert db.execute("SELECT count(*) FROM document_events WHERE document_id=? AND event_type='metadata_updated'",(id,)).fetchone()[0]==1
    assert write(client,headers,id,2,{'flag':None}).status_code==200
    assert all(r['key']!='flag' for r in client.get('/api/v1/documents/'+id+'/metadata').json())
    assert write(client,headers,id,3,{'flag':False},False).status_code==200
    assert not next(r for r in client.get('/api/v1/documents/'+id+'/metadata').json() if r['key']=='flag')['is_confirmed']


@pytest.mark.parametrize('kind,bad',[
    ('integer',True),('integer',1.5),('integer','1'),('integer',9223372036854775808),
    ('boolean',0),('boolean','false'),('date','2026-02-29'),('date','2026-1-01'),
    ('decimal',2.0),('decimal','1e2'),('decimal','1.00001'),('decimal','9000000000000.0001'),
    ('decimal','NaN'),('decimal','+2.00'),('text',123),('single_select','unknown')])
def test_strict_values_and_atomic_failure(api,kind,bad):
    _,_,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    field(client,headers,space,'good','text')
    field(client,headers,space,'value',kind)
    response=write(client,headers,id,1,{'good':'must rollback','value':bad})
    assert response.status_code==422,response.text
    assert client.get('/api/v1/documents/'+id+'/metadata').json()==[]
    assert detail(client,id)['document_version']==1


def test_constraints_exact_range_and_filing_revalidates_optional_and_required(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    amount=field(client,headers,space,'money','decimal',min='2.00',max='10.00')
    flag=field(client,headers,space,'flag','boolean')
    type_id=client.post('/api/v1/document-types',headers=headers,json={'space_id':space,'key':'contract','label':'Contract','fields':[
        {'field_definition_id':amount,'required_for_filing':False},{'field_definition_id':flag,'required_for_filing':True}]}).json()['id']
    patch(client,headers,id,1,document_type_id=type_id)
    path='/api/v1/documents/'+id+'/triage'
    assert client.post(path,headers=headers,json={'expected_document_version':2,'triage_status':'filed'}).status_code==422
    assert write(client,headers,id,2,{'money':'10.00','flag':False}).status_code==200
    assert client.post(path,headers=headers,json={'expected_document_version':3,'triage_status':'filed'}).status_code==200
    assert write(client,headers,id,4,{'flag':None}).status_code==422
    assert detail(client,id)['document_version']==4
    assert write(client,headers,id,4,{'money':'10.0001'}).status_code==422
    assert client.patch('/api/v1/field-definitions/'+amount,headers=headers,json={'constraints':{'max':'5.00'}}).status_code==200
    assert client.post(path,headers=headers,json={'expected_document_version':4,'triage_status':'filed'}).status_code==422
    assert write(client,headers,id,4,{'money':'2.00'}).status_code==200
    with connect(settings.database) as db:
        assert db.execute('SELECT value_decimal_scaled FROM metadata_values WHERE value_decimal_scaled BETWEEN 20000 AND 100000').fetchone()==(20000,)


def test_version_csrf_inactive_cross_space_trash_and_concurrent_writes(api):
    _,_,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    f=field(client,headers,space,'count','integer')
    assert write(client,{},id,1,{'count':1}).status_code==403
    assert write(client,headers,id,1,{}).status_code==422
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    field(client,headers,other,'foreign','text')
    assert write(client,headers,id,1,{'foreign':'wrong'}).status_code==422
    def concurrent(i):return write(client,headers,id,1,{'count':i}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(concurrent,(1,2)))==[200,409]
    client.patch('/api/v1/field-definitions/'+f,headers=headers,json={'is_active':False})
    assert write(client,headers,id,2,{'count':3}).status_code==422
    client.post('/api/v1/documents/'+id+'/trash',headers=headers,json={'expected_document_version':2})
    assert write(client,headers,id,3,{'count':4}).status_code==409
    assert len(client.get('/api/v1/documents/'+id+'/metadata').json())==1


def candidate(settings,doc,revision,value,*,run='run',cid='candidate'):
    with connect(settings.database) as db:
        db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at) VALUES (?,?,?,'test','1','1','completed','now')",(run,doc,revision))
        db.execute('INSERT INTO extracted_metadata(id,parse_run_id,candidate_key,candidate_value_json) VALUES (?,?,?,?)',(cid,run,'guess',json.dumps(value)))
        db.execute('UPDATE documents SET current_parse_run_id=? WHERE id=?',(run,doc))
        db.commit()


def test_candidate_adoption_is_explicit_typed_versioned_and_keeps_provenance(api):
    _,settings,client,headers,space=api
    saved=upload(client,headers,space);id=saved['document_id']
    f=field(client,headers,space,'amount','decimal')
    write(client,headers,id,1,{'amount':'2.00'})
    candidate(settings,id,saved['revision_id'],'10.00')
    path='/api/v1/documents/'+id+'/metadata'
    assert client.get(path).json()[0]['value']=='2.0000'  # Merely parsing never replaces manual facts.
    body={'expected_document_version':2,'extracted_metadata_id':'candidate','field_definition_id':f}
    result=client.post(path+'/adopt-candidate',headers=headers,json=body)
    assert result.status_code==200,result.text
    entry=result.json()[0]
    assert entry['value']=='10.0000' and entry['origin']=='extracted' and entry['is_confirmed'] and entry['source_parse_run_id']=='run'
    assert client.post(path+'/adopt-candidate',headers=headers,json=body).status_code==409
    assert write(client,headers,id,3,{'amount':'3.00'}).json()[0]['source_parse_run_id'] is None
    with connect(settings.database) as db:
        assert db.execute('SELECT candidate_value_json FROM extracted_metadata').fetchone()==('"10.00"',)
        event=json.loads(db.execute("SELECT after_json FROM document_events WHERE event_type='metadata_candidate_adopted'").fetchone()[0])
        assert event['metadata'][0]['source_parse_run_id']=='run'


def test_candidate_cross_document_stale_null_and_invalid_values_rejected(api):
    _,settings,client,headers,space=api
    a=upload(client,headers,space,b'a');b=upload(client,headers,space,b'b')
    f=field(client,headers,space,'flag','boolean')
    candidate(settings,a['document_id'],a['revision_id'],None)
    path='/api/v1/documents/'+a['document_id']+'/metadata/adopt-candidate'
    body={'expected_document_version':1,'extracted_metadata_id':'candidate','field_definition_id':f}
    assert client.post('/api/v1/documents/'+b['document_id']+'/metadata/adopt-candidate',headers=headers,json=body).status_code==422
    assert client.post(path,headers=headers,json=body).status_code==422
    with connect(settings.database) as db:
        db.execute("UPDATE extracted_metadata SET candidate_value_json='false'")
        db.execute("UPDATE parse_runs SET status='failed'")
        db.commit()
    assert client.post(path,headers=headers,json=body).status_code==409
    with connect(settings.database) as db:
        db.execute("UPDATE parse_runs SET status='completed'")
        db.execute('UPDATE documents SET current_parse_run_id=NULL WHERE id=?',(a['document_id'],));db.commit()
    assert client.post(path,headers=headers,json=body).status_code==409
    assert detail(client,a['document_id'])['document_version']==1


def test_rules_configuration_and_timeout_are_not_silently_ignored(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    f=field(client,headers,space,'text','text',regex='(a+)+$',max_length=65536)
    response=write(client,headers,id,1,{'text':'a'*20000+'!'})
    assert response.status_code==422 and response.json()['error']['code']=='FIELD_RULE_TIMEOUT'
    for rules in ({'unknown':True},{'max_length':True},{'regex':'['},{'regex':'a{999999999}'},{'min_length':5,'max_length':2}):
        assert client.patch('/api/v1/field-definitions/'+f,headers=headers,json={'constraints':rules}).status_code==422
    with connect(settings.database) as db:
        db.execute("UPDATE field_definitions SET constraints_json='{\"legacy\":true}' WHERE id=?",(f,));db.commit()
    assert write(client,headers,id,1,{'text':'safe'}).status_code==501
    assert detail(client,id)['document_version']==1


def test_decimal_boundaries_and_failed_audit_roll_back_values_and_version(api):
    _,settings,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    field(client,headers,space,'money','decimal')
    assert write(client,headers,id,1,{'money':'-9000000000000.0000'}).status_code==200
    assert write(client,headers,id,2,{'money':'9000000000000.0000'}).status_code==200
    with connect(settings.database) as db:
        db.execute("CREATE TRIGGER block_metadata BEFORE INSERT ON document_events WHEN NEW.event_type='metadata_updated' BEGIN SELECT RAISE(ABORT,'injected'); END");db.commit()
    assert write(client,headers,id,3,{'money':'2.00'}).status_code==409
    assert detail(client,id)['document_version']==3
    assert client.get('/api/v1/documents/'+id+'/metadata').json()[0]['value']=='9000000000000.0000'


def test_bad_constraint_types_ranges_options_and_strict_confirm(api):
    _,_,client,headers,space=api
    for kind,rules in [('integer',{'min':True}),('decimal',{'min':2.0}),('date',{'min':'2026-02-30'}),
        ('decimal',{'min':'10.00','max':'2.00'}),('single_select',{'options':[{'id':'a','label':'A'},{'id':'a','label':'B'}]}),
        ('boolean',{'required':True})]:
        assert field_create(client,headers,space,key='bad',type=kind,constraints=rules).status_code==422
    id=upload(client,headers,space)['document_id'];field(client,headers,space,'value','integer')
    assert write(client,headers,id,1,{'value':1},'true').status_code==422
    assert write(client,headers,id,True,{'value':1}).status_code==422


def test_optional_values_are_still_typed_and_template_change_preserves_history(api):
    _,_,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    f=field(client,headers,space,'value','integer',min=1,max=10)
    write(client,headers,id,1,{'value':2})
    type_id=client.post('/api/v1/document-types',headers=headers,json={'space_id':space,'key':'note','label':'Note',
        'fields':[{'field_definition_id':f,'required_for_filing':False}]}).json()['id']
    patch(client,headers,id,2,document_type_id=type_id)
    client.patch('/api/v1/field-definitions/'+f,headers=headers,json={'constraints':{'min':5}})
    assert client.post('/api/v1/documents/'+id+'/triage',headers=headers,json={'expected_document_version':3,'triage_status':'filed'}).status_code==422
    assert client.get('/api/v1/documents/'+id+'/metadata').json()[0]['value']==2
    assert patch(client,headers,id,3,document_type_id=None).status_code==200
    assert client.get('/api/v1/documents/'+id+'/metadata').json()[0]['value']==2
