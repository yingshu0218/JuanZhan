"""Authenticated HTTP search over real business values and persisted FTS."""
import pytest

from test_document_api import api,upload,detail,patch,folder
from test_fields import create
from test_metadata import write
from test_parsing import pipeline
from test_indexing import parsed,drain
from juanzhan.database import connect
from juanzhan.indexing import rebuild


def search(client,headers,space,**body):
    return client.post('/api/v1/documents/search',headers=headers,json={'space_id':space,**body})


def ids(response):
    assert response.status_code==200,response.text
    return [x['id'] for x in response.json()['items']]


def make_values(api):
    _,settings,client,headers,space=api
    specs=[('money','decimal'),('count','integer'),('day','date'),('flag','boolean'),('note','text'),('long','long_text'),('choice','single_select')]
    for key,kind in specs:
        extra={'constraints':{'options':[{'id':'one','label':'One'},{'id':'two','label':'Two'}]}} if kind=='single_select' else {}
        assert create(client,headers,space,key=key,type=kind,filterable=True,**extra).status_code==201
    docs=[]
    for values in [dict(money='2.0001',count=-4,day='2024-02-29',flag=False,note='literal %_ 星河',long='长文本',choice='one'),
                   dict(money='10.0000',count=9223372036854775807,day='2025-01-01',flag=True,note='other',choice='two'),{}]:
        id=upload(client,headers,space,content=str(len(docs)).encode())['document_id'];docs.append(id)
        if values:assert write(client,headers,id,1,values).status_code==200
    return docs


@pytest.mark.parametrize('key,op,value,indexes',[
 ('money','between',['2.0000','2.0001'],[0]),('money','gte','10',[1]),('money','lte','2.0001',[0]),
 ('count','gte',9223372036854775807,[1]),('count','in',[-4,0],[0]),('day','between',['2024-02-28','2024-02-29'],[0]),
 ('flag','eq',False,[0]),('flag','is_null',None,[2]),('note','contains','%_',[0]),('long','eq','长文本',[0]),('choice','in',['two'],[1])])
def test_exact_typed_filters_false_absence_and_literal_contains(api,key,op,value,indexes):
    _,_,client,headers,space=api;docs=make_values(api)
    condition={'key':key,'operator':op}
    if op!='is_null':condition['value']=value
    assert set(ids(search(client,headers,space,metadata=[condition])))=={docs[i] for i in indexes}


@pytest.mark.parametrize('condition',[
 {'key':'money','operator':'eq','value':2.0001}, {'key':'money','operator':'eq','value':'0.00001'},
 {'key':'count','operator':'eq','value':True}, {'key':'flag','operator':'eq','value':0},
 {'key':'day','operator':'eq','value':'2025-02-29'}, {'key':'note','operator':'gte','value':'A'},
 {'key':'choice','operator':'contains','value':'o'}, {'key':'money','operator':'between','value':['10','2']},
 {'key':'note','operator':'in','value':[]}, {'key':'flag','operator':'is_null','value':False},
 {'key':'absent','operator':'eq','value':'x'}, {'key':'note','operator':'eq'},
])
def test_invalid_typed_filters_are_rejected(api,condition):
    _,_,client,headers,space=api;make_values(api)
    assert search(client,headers,space,metadata=[condition]).status_code==422


def test_scope_tags_any_all_folder_descendants_types_dates_and_stable_pages(api):
    _,_,client,headers,space=api
    root=folder(client,headers,space,'Root');child=folder(client,headers,space,'Child',root)
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    foreign=folder(client,headers,other,'Foreign')
    a=upload(client,headers,space,folder_id=root)['document_id'];b=upload(client,headers,space,content=b'child original',folder_id=child)['document_id']
    upload(client,headers,other)
    tags=[client.post('/api/v1/tags',headers=headers,json={'space_id':space,'name':n}).json()['id'] for n in ['A','B']]
    type_id=client.post('/api/v1/document-types',headers=headers,json={'space_id':space,'key':'report','label':'Report'}).json()['id']
    assert patch(client,headers,a,1,tags_add=tags,title='Same',document_date='2024-02-29',document_type_id=type_id).status_code==200
    assert patch(client,headers,b,1,tags_add=tags[:1],title='Same',document_date='2025-01-01').status_code==200
    assert set(ids(search(client,headers,space,folder={'id':root,'include_descendants':True})))=={a,b}
    assert ids(search(client,headers,space,folder={'id':root}))==[a]
    assert set(ids(search(client,headers,space,tags={'ids':tags,'match':'any'})))=={a,b}
    assert ids(search(client,headers,space,tags={'ids':tags+tags,'match':'all'}))==[a]
    assert ids(search(client,headers,space,document_type_ids=[type_id]))==[a]
    assert ids(search(client,headers,space,document_date_from='2024-02-28',document_date_to='2024-02-29'))==[a]
    assert search(client,headers,space,folder={'id':foreign}).status_code==422
    pages=[ids(search(client,headers,space,sort=[{'field':'title','order':'asc'}],page=i,page_size=1))[0] for i in [1,2]]
    assert pages==sorted([a,b])
    assert ids(search(client,headers,space,page=999))==[]


def test_filterable_active_and_metadata_space_boundaries(api):
    _,_,client,headers,space=api
    field=create(client,headers,space,key='secret',type='text').json()
    condition=[{'key':'secret','operator':'is_null'}]
    assert search(client,headers,space,metadata=condition).status_code==422
    client.patch('/api/v1/field-definitions/'+field['id'],headers=headers,json={'filterable':True,'is_active':False})
    assert search(client,headers,space,metadata=condition).status_code==422


def test_real_fts_get_post_joint_filters_stale_failure_and_trash(pipeline):
    settings,client,headers,space=pipeline;doc=parsed(pipeline,'繁體檔案 合同 Invoice2026 12345');drain(settings);id=doc['document_id']
    for text in ['档案','檔案','Invoice2026','合同 12345']:
        response=search(client,headers,space,text=text)
        assert ids(response)==[id]
        assert response.json()['items'][0]['search_index']['status']=='current'
        assert not response.json()['search_index']['incomplete']
        assert client.get('/api/v1/documents',params={'space_id':space,'q':text}).json()['total']==1
    assert ids(search(client,headers,space,text='NOT OR " *'))==[]
    assert create(client,headers,space,key='amount',type='decimal',filterable=True).status_code==201
    assert write(client,headers,id,1,{'amount':'2.0001'}).status_code==200
    response=search(client,headers,space,text='档案',metadata=[{'key':'amount','operator':'lte','value':'2.0001'}])
    assert ids(response)==[id] and response.json()['items'][0]['search_index']['status']=='pending'
    assert response.json()['search_index']['incomplete']
    rebuild(settings,id)
    with connect(settings.database) as db:db.execute("UPDATE search_dirty SET last_error='INDEX_TOKEN_LIMIT' WHERE document_id=?",(id,));db.commit()
    response=search(client,headers,space,text='档案');assert ids(response)==[id]
    assert response.json()['items'][0]['search_index']['status']=='failed'
    assert response.json()['search_index']['failed']==1
    version=detail(client,id)['document_version']
    assert client.post('/api/v1/documents/'+id+'/trash',headers=headers,json={'expected_document_version':version}).status_code==200
    assert not ids(search(client,headers,space,text='档案'))
    assert ids(search(client,headers,space,text='档案',trash='only'))==[id]
    other=client.post('/api/v1/spaces',headers=headers,json={'name':'Other'}).json()['id']
    assert not ids(search(client,headers,other,text='档案'))


def test_zero_hits_still_reports_unindexed_scope_and_relevance_requires_text(api):
    _,_,client,headers,space=api;upload(client,headers,space)
    response=search(client,headers,space,text='不存在');assert ids(response)==[]
    summary=response.json()['search_index'];assert summary['missing']==1 and summary['total']==1 and summary['incomplete']
    assert search(client,headers,space,sort=[{'field':'relevance'}]).status_code==422


@pytest.mark.parametrize('values',[
 {'text':'* ()'}, {'text':'x'*513}, {'text':'中'*200}, {'page':True}, {'page_size':101},
 {'sort':[{'field':'title;drop table documents'}]}, {'sort':[{'field':'title'},{'field':'title'}]},
 {'document_date_from':'2025-02-29'}, {'document_date_from':'2025-01-01','document_date_to':'2024-01-01'},
 {'availability_status':'invented'}, {'unknown':True}, {'tags':{'ids':[]}},
])
def test_bounded_strict_inputs(api,values):
    _,_,client,headers,space=api
    assert search(client,headers,space,**values).status_code==422


def test_authentication_csrf_and_bearer(api):
    _,_,client,headers,space=api
    assert search(client,{},space).status_code==403
    token=client.post('/api/v1/auth/tokens',headers=headers,json={'name':'search'}).json()['token']
    response=search(client,{'Authorization':'Bearer '+token},space)
    assert response.status_code==200,response.text
    client.cookies.clear()
    assert search(client,{},space).status_code==401
    assert client.get('/api/v1/documents',params={'q':'中文'}).status_code==401


def test_request_response_and_sql_execution_budgets(api,monkeypatch):
    from juanzhan import search as module
    _,_,client,headers,space=api
    upload(client,headers,space)
    monkeypatch.setattr(module,'MAX_REQUEST',32)
    assert search(client,headers,space,text='x'*100).status_code==413
    monkeypatch.setattr(module,'MAX_REQUEST',1024*1024)
    monkeypatch.setattr(module,'MAX_RESPONSE',32)
    assert search(client,headers,space).status_code==413
    monkeypatch.setattr(module,'MAX_RESPONSE',16*1024*1024)
    monkeypatch.setattr(module,'QUERY_SECONDS',-1)
    # Progress callback runs every 1000 VM operations; enough real rows to reach it.
    with connect(api[1].database) as db:
        for i in range(100):
            db.execute("INSERT INTO documents(id,space_id,title,imported_at,created_at,updated_at) VALUES(?,?,?,'now','now','now')",('budget-'+str(i),space,'Budget'))
        db.commit()
    assert search(client,headers,space).status_code==503


def test_system_summary_is_authenticated_scoped_and_excludes_trash(api):
    _,_,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    response=client.get('/api/v1/system/summary',params={'space_id':space})
    assert response.status_code==200,response.text
    assert response.json()=={'documents_total':1,'inbox_total':1,'managed_total':1,'external_total':0,'failed_jobs':0,'offline_sources':0}
    assert response.headers['cache-control']=='no-store'
    client.post('/api/v1/documents/'+id+'/trash',headers=headers,json={'expected_document_version':1})
    assert client.get('/api/v1/system/summary',params={'space_id':space}).json()['documents_total']==0
    client.cookies.clear();assert client.get('/api/v1/system/summary').status_code==401


def test_metadata_comparisons_use_existing_typed_indexes(api):
    from juanzhan.search import metadata_clause,Metadata
    from juanzhan.catalog import transaction
    _,settings,client,headers,space=api;make_values(api)
    with transaction(settings) as db:
        for key,value,index in [('money','2.00','ix_metadata_decimal'),('count',-5,'ix_metadata_integer'),('day','2024-01-01','ix_metadata_date')]:
            clause,params=metadata_clause(db,space,Metadata(key=key,operator='gte',value=value))
            plan=' '.join(str(tuple(r)) for r in db.execute('EXPLAIN QUERY PLAN SELECT d.id FROM documents d WHERE '+clause,params))
            assert index in plan,plan


def test_status_filters_use_actual_projection_and_are_bounded(api):
    _,_,client,headers,space=api
    id=upload(client,headers,space)['document_id']
    assert ids(search(client,headers,space,availability_status='available',processing_status='queued'))==[id]
    assert ids(search(client,headers,space,processing_status='completed'))==[]
    assert ids(search(client,headers,space,availability_status='source_offline'))==[]
    response=search(client,headers,space)
    assert response.json()['search_index']['processing']==1
    assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'


def test_live_status_observation_limit_returns_explicit_failure(api,monkeypatch):
    from juanzhan import search as module
    _,_,client,headers,space=api
    upload(client,headers,space,content=b'one');upload(client,headers,space,content=b'two')
    monkeypatch.setattr(module,'MAX_OBSERVATIONS',1)
    response=search(client,headers,space,processing_status='queued')
    assert response.status_code==503,response.text
    assert response.json()['error']['code']=='SEARCH_STATUS_LIMIT'


def test_failed_new_revision_remains_searchable_with_explicit_incomplete_content(pipeline):
    from test_parsing import append,queue_parse
    from juanzhan.worker import Worker
    settings,client,headers,space=pipeline
    doc=parsed(pipeline,'保留档案正文');drain(settings)
    rev=append(settings,doc['document_id'],b'%PDF-1.4\ninvalid')
    queue_parse(settings,doc['document_id'],rev)
    assert Worker(settings).run_once()['status']=='failed'
    drain(settings)
    response=search(client,headers,space,text='保留')
    assert ids(response)==[doc['document_id']]
    assert response.json()['items'][0]['content_stale']
    assert response.json()['search_index']['stale_content']==1
    assert response.json()['search_index']['failed_processing']==1
    assert response.json()['search_index']['incomplete']


def test_relevance_sort_and_secondary_order_are_reproducible(pipeline):
    from juanzhan.worker import Worker
    settings,client,headers,space=pipeline
    first=parsed(pipeline,'合同 合同 合同');second=parsed(pipeline,'合同 正文 内容 内容 内容 内容');drain(settings)
    desc=ids(search(client,headers,space,text='合同',sort=[{'field':'relevance','order':'desc'}]))
    asc=ids(search(client,headers,space,text='合同',sort=[{'field':'relevance','order':'asc'}]))
    assert set(desc)=={first['document_id'],second['document_id']}
    assert desc==list(reversed(asc))
    assert ids(search(client,headers,space,text='合同'))==desc
    assert [item['id'] for item in client.get('/api/v1/documents',params={'space_id':space,'q':'合同'}).json()['items']]==desc


def test_scanned_pdf_without_requested_ocr_reports_limited_content(pipeline):
    from test_parsing import upload as upload_file
    from format_samples import raster_sample
    from juanzhan.worker import Worker
    settings,client,headers,space=pipeline
    doc=upload_file(pipeline,raster_sample('PDF'),'scanned.pdf')
    assert Worker(settings).run_once()['status']=='completed'
    drain(settings)
    response=search(client,headers,space)
    assert ids(response)==[doc['document_id']]
    assert response.json()['search_index']['limited_content']==1
    assert response.json()['search_index']['incomplete']
    assert response.json()['items'][0]['search_index']['content_incomplete']
    assert response.json()['items'][0]['search_index']['status']=='current'
