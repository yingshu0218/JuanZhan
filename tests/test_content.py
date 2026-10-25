"""Public APIs backed by real uploaded files, SQLite, derived store and Converter HTTP."""
from concurrent.futures import ThreadPoolExecutor
import json
import uuid

from fastapi.testclient import TestClient
import pytest

from test_parsing import pipeline,upload,append,rows,queue_parse
from format_samples import samples
from test_metadata import field
from juanzhan.database import connect
from juanzhan.worker import Worker


def request(pipeline,uploaded,**options):
    settings,client,headers,_=pipeline
    doc=client.get('/api/v1/documents/'+uploaded['document_id']).json()
    return client.post('/api/v1/documents/'+uploaded['document_id']+'/reprocess',headers=headers,json={
        'expected_document_version':doc['document_version'],'expected_revision_id':doc['current_revision_id'],
        'request_id':uuid.uuid4().hex,**options})

@pytest.mark.parametrize('kind',list(samples()))
def test_public_three_content_formats_and_bounded_history(pipeline,kind):
    settings,client,_,_=pipeline;mime,data=samples()[kind]
    uploaded=upload(pipeline,data,'sample.'+kind);Worker(settings).run_once()
    root='/api/v1/documents/'+uploaded['document_id']
    history=client.get(root+'/parse-runs').json()
    assert history['total']==1 and history['items'][0]['is_current']
    assert 'candidates' not in history['items'][0] and 'remote_job_id' not in str(history)
    for format in ('blocks','text','markdown'):
        response=client.get(root+'/content',params={'format':format})
        assert response.status_code==200,response.text
        result=response.json();assert result['body'] and not result['stale_for_current_revision']
        assert result['parse_run_id']==history['items'][0]['id']
        assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'
        if format=='blocks':
            assert result['total']>=len(result['body']) and result['page']==1
            page=client.get(root+'/content?page_size=1').json()
            assert len(page['body'])==1 and page['body'][0]==result['body'][0]
    assert str(settings.data_dir) not in response.text


def test_auth_csrf_version_unknown_options_and_reprocess_idempotency(pipeline):
    settings,client,headers,_=pipeline;uploaded=upload(pipeline)
    root='/api/v1/documents/'+uploaded['document_id']
    with TestClient(client.app) as anonymous:
        for path in ('content','parse-runs','candidates'):
            assert anonymous.get(root+'/'+path).status_code==401
        assert anonymous.post(root+'/reprocess',json={}).status_code==401
    body={'expected_document_version':1,'expected_revision_id':uploaded['revision_id'],'request_id':'stable','force':True}
    assert client.post(root+'/reprocess',json=body).status_code==403
    assert client.post(root+'/reprocess',headers=headers,json={**body,'path':'/etc/passwd'}).status_code==422
    assert client.post(root+'/reprocess',headers=headers,json={**body,'ocr':'true'}).status_code==422
    assert client.post(root+'/reprocess',headers=headers,json={**body,'ocr':False,'ocr_languages':'eng'}).json()['error']['code']=='OCR_DISABLED'
    assert request(pipeline,uploaded,ocr=True,ocr_languages='eng,eng').status_code==422
    assert request(pipeline,uploaded,expected_document_version=999).status_code==409
    assert request(pipeline,uploaded,expected_revision_id='changed').json()['error']['code']=='REVISION_CONFLICT'
    assert request(pipeline,uploaded).json()['error']['code']=='PARSE_ALREADY_RUNNING'
    Worker(settings).run_once()
    assert request(pipeline,uploaded).json()['error']['code']=='ALREADY_PARSED'
    first=client.post(root+'/reprocess',headers=headers,json=body)
    again=client.post(root+'/reprocess',headers=headers,json=body)
    assert first.status_code==again.status_code==202 and first.json()==again.json()
    assert client.post(root+'/reprocess',headers=headers,json={**body,'ocr':False}).json()['error']['code']=='IDEMPOTENCY_CONFLICT'
    Worker(settings).run_once()
    assert client.post(root+'/reprocess',headers=headers,json=body).json()['job_id']==first.json()['job_id']
    assert len(rows(settings,'SELECT * FROM parse_runs'))==2


def test_actual_candidate_adoption_and_reprocess_never_erase_confirmed_fields(pipeline):
    settings,client,headers,space=pipeline
    uploaded=upload(pipeline,samples()['docx'][1],'document.docx');root='/api/v1/documents/'+uploaded['document_id']
    inferred=field(client,headers,space,'inferred_title','text')
    value=client.patch(root+'/metadata',headers=headers,json={'expected_document_version':1,'confirm':True,'values':{'inferred_title':'人工确认'}})
    assert value.status_code==200
    Worker(settings).run_once()
    candidates=client.get(root+'/candidates').json()
    title=next(c for c in candidates['items'] if c['key']=='title')
    assert title['value']=='真实标题' and title['provenance']['source']=='document_properties' and title['adoptable']
    assert client.get(root+'/metadata').json()[0]['value']=='人工确认'
    adopted=client.post(root+'/metadata/adopt-candidate',headers=headers,json={'expected_document_version':2,
        'extracted_metadata_id':title['id'],'field_definition_id':inferred})
    assert adopted.status_code==200 and adopted.json()[0]['source_parse_run_id']==title['parse_run_id']
    assert client.get(root).json()['title']=='document.docx'
    job=request(pipeline,uploaded,force=True);assert job.status_code==202
    Worker(settings).run_once()
    assert client.get(root+'/metadata').json()[0]['value']=='真实标题'
    assert not client.get(root+'/candidates',params={'parse_run_id':title['parse_run_id']}).json()['items'][0]['adoptable']
    stale=client.post(root+'/metadata/adopt-candidate',headers=headers,json={'expected_document_version':3,
        'extracted_metadata_id':title['id'],'field_definition_id':inferred})
    assert stale.status_code==409 and stale.json()['error']['code']=='STALE_CANDIDATE'


def test_history_content_cross_document_and_failed_revision_cache(pipeline):
    settings,client,_,_=pipeline
    a=upload(pipeline);root='/api/v1/documents/'+a['document_id'];Worker(settings).run_once()
    old=client.get(root+'/content').json()
    b=upload(pipeline,b'another');Worker(settings).run_once()
    other=client.get('/api/v1/documents/'+b['document_id']+'/content').json()['parse_run_id']
    for path in ('content','candidates'):
        assert client.get(root+'/'+path,params={'parse_run_id':other}).status_code==404
    append(settings,a['document_id'],b'%PDF-1.4\nmalformed')
    assert request(pipeline,a).status_code==202
    Worker(settings).run_once()
    cached=client.get(root+'/content').json()
    assert cached['parse_run_id']==old['parse_run_id'] and cached['body']==old['body'] and cached['stale_for_current_revision']
    history=client.get(root+'/parse-runs?page_size=1').json()
    assert history['total']==2 and history['items'][0]['status']=='failed' and history['items'][0]['error']['code']
    assert client.get(root+'/content',params={'parse_run_id':history['items'][0]['id']}).status_code==409
    assert client.get(root+'/parse-runs?page=2&page_size=1').json()['items'][0]['id']==old['parse_run_id']


def test_missing_and_corrupt_derived_assets_fail_without_path_disclosure(pipeline):
    settings,client,_,_=pipeline;a=upload(pipeline);Worker(settings).run_once()
    asset=rows(settings,"SELECT * FROM derived_assets WHERE asset_kind='plain_text'")[0]
    path=settings.data_dir/'derived'/asset['storage_key'];path.chmod(0o600);path.write_bytes(b'x'*asset['size_bytes'])
    root='/api/v1/documents/'+a['document_id']
    response=client.get(root+'/content?format=text')
    assert response.status_code==503 and str(path) not in response.text
    path.unlink();assert client.get(root+'/content?format=text').status_code==503
    assert client.get(root+'/content?format=blocks').status_code==200


def test_no_content_pagination_validation_trash_and_bearer(pipeline):
    settings,client,headers,_=pipeline;a=upload(pipeline);root='/api/v1/documents/'+a['document_id']
    assert client.get(root+'/content').json()['error']['code']=='CONTENT_NOT_AVAILABLE'
    assert client.get(root+'/candidates').json()['items']==[]
    assert client.get(root+'/parse-runs').json()['items']==[]
    for suffix in ('/content?format=html','/content?page=0','/parse-runs?page_size=101','/candidates?page=-1',
                   '/content?parse_run_id=','/candidates?parse_run_id='+('x'*256)):
        assert client.get(root+suffix).status_code==422
    Worker(settings).run_once()
    assert client.get(root+'/content?format=text&page=2').status_code==422
    token=client.post('/api/v1/auth/tokens',headers=headers,json={'name':'content'}).json()['token']
    response=client.post(root+'/reprocess',headers={'Authorization':'Bearer '+token},json={
        'request_id':'bearer','expected_document_version':1,'expected_revision_id':a['revision_id'],'force':True})
    assert response.status_code==202
    Worker(settings).run_once()
    client.post(root+'/trash',headers=headers,json={'expected_document_version':1})
    assert request(pipeline,a,force=True).json()['error']['code']=='DOCUMENT_TRASHED'
    assert client.get(root+'/content').status_code==200


def test_concurrent_distinct_requests_do_not_duplicate_active_parse(pipeline):
    settings,client,_,_=pipeline;a=upload(pipeline);Worker(settings).run_once()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:request(pipeline,a,force=True),range(2)))
    assert sorted(r.status_code for r in responses)==[202,409]
    assert len(rows(settings,"SELECT * FROM jobs WHERE kind IN ('parse','ocr') AND status='queued'"))==1


def test_response_budget_checked_in_sql_before_materializing_pages(pipeline,monkeypatch):
    import juanzhan.content as content
    settings,client,_,_=pipeline;a=upload(pipeline,samples()['docx'][1],'sample.docx');Worker(settings).run_once()
    monkeypatch.setattr(content,'MAX_BYTES',16)
    root='/api/v1/documents/'+a['document_id']
    for route in ('content','parse-runs','candidates'):
        assert client.get(root+'/'+route).status_code==413


def test_batch_reprocess_real_converter_and_force_guard(pipeline):
    settings,client,headers,space=pipeline
    uploaded=upload(pipeline,b'Batch actual converter text')
    worker=Worker(settings)
    worker.run_once()
    id=uploaded['document_id']
    body={'space_id':space,'document_ids':[id],'selection_mode':'explicit',
          'expected_versions':{id:1},'operation':'reprocess','payload':{}}
    response=client.post('/api/v1/documents/batch',headers=headers,json=body)
    assert response.status_code==202,response.text
    worker.run_once()
    result=client.get('/api/v1/jobs/'+response.json()['job_id']).json()['result']
    assert result['items'][0]['error_code']=='ALREADY_PARSED'
    body['payload']={'force':True}
    response=client.post('/api/v1/documents/batch',headers=headers,json=body)
    worker.run_once()
    result=client.get('/api/v1/jobs/'+response.json()['job_id']).json()['result']
    assert result['succeeded']==1
    child=result['items'][0]['parse_job_id']
    worker.run_once()
    assert client.get('/api/v1/jobs/'+child).json()['status']=='completed'
    history=client.get('/api/v1/documents/'+id+'/parse-runs').json()
    assert history['total']==2
    assert client.get('/api/v1/documents/'+id+'/content?format=text').json()['body']=='Batch actual converter text'
