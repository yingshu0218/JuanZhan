"""Cross-feature acceptance with real network refusal, conversion and cached source IO."""
from dataclasses import replace
import hashlib
import os
import socket
import sqlite3
import uuid

from fastapi.testclient import TestClient
from test_parsing import pipeline, upload, append, rows
from test_metadata import field
from test_sources import api as source_api, create as create_source
from test_source_initial import source_row, scan
from juanzhan.apps import create_app
from juanzhan.document_events import utc_now
from juanzhan.indexing import schedule, rebuild
from juanzhan.jobs import JobQueue
from juanzhan.source_initial import register_external
from juanzhan.source_paths import SourceMounts
from juanzhan.worker import Worker


def test_converter_outage_keeps_manual_data_old_content_then_recovers_same_job(pipeline,monkeypatch):
    settings,client,headers,space=pipeline
    receipt=upload(pipeline,'原先成功正文 Archive A-001'.encode());root='/api/v1/documents/'+receipt['document_id']
    assert Worker(settings).run_once()['status']=='completed'
    old=client.get(root+'/content?format=text').json()
    field(client,headers,space,'contract','text')
    assert client.patch(root+'/metadata',headers=headers,json={'expected_document_version':1,'confirm':True,
        'values':{'contract':'人工合同 HT-001'}}).status_code==200
    tag=client.post('/api/v1/tags',headers=headers,json={'space_id':space,'name':'人工标签'}).json()['id']
    assert client.patch(root,headers=headers,json={'expected_document_version':2,'tags_add':[tag]}).status_code==200
    revision=append(settings,receipt['document_id'],'更新成功正文 Archive B-002'.encode())
    document=client.get(root).json()
    body={'expected_document_version':document['document_version'],'expected_revision_id':revision,
          'request_id':uuid.uuid4().hex,'force':True}
    response=client.post(root+'/reprocess',headers=headers,json=body);assert response.status_code==202
    job=response.json()['job_id'];base=os.environ['CONVERTER_URL']
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1',0))  # Reserved but not listening: real connection refusal.
        monkeypatch.setenv('CONVERTER_URL','http://127.0.0.1:'+str(unavailable.getsockname()[1]))
        assert Worker(settings).run_once()['status']=='queued'
    failed=client.get('/api/v1/jobs/'+job).json()
    assert failed['attempts']==1 and failed['can_retry'] and failed['error']['code']=='CONVERTER_UNAVAILABLE'
    cached=client.get(root+'/content?format=text').json()
    assert cached['parse_run_id']==old['parse_run_id'] and cached['body']==old['body'] and cached['stale_for_current_revision']
    assert client.get(root+'/metadata').json()[0]['value']=='人工合同 HT-001'
    assert client.get(root).json()['tag_ids']==[tag]
    assert client.get(root+'/download').content=='更新成功正文 Archive B-002'.encode()
    monkeypatch.setenv('CONVERTER_URL',base)
    assert client.post(root+'/reprocess',headers=headers,json=body).json()['job_id']==job
    assert client.post('/api/v1/jobs/'+job+'/retry',headers=headers).status_code==202
    assert Worker(settings).run_once()['status']=='completed'
    complete=client.get('/api/v1/jobs/'+job).json();assert complete['attempts']==2 and not complete['can_retry']
    current=client.get(root+'/content?format=text').json()
    assert 'B-002' in current['body'] and not current['stale_for_current_revision']
    assert client.get(root+'/metadata').json()[0]['value']=='人工合同 HT-001'
    assert client.get(root).json()['tag_ids']==[tag]
    assert client.get(root+'/content',params={'format':'text','parse_run_id':old['parse_run_id']}).json()['body']==old['body']
    schedule(settings);Worker(settings).run_once(prefer_index=True)
    rebuild(settings,receipt['document_id']);schedule(settings);Worker(settings).run_once(prefer_index=True)
    assert len(rows(settings,'SELECT * FROM document_search WHERE document_id=?',receipt['document_id']))==1
    assert rows(settings,'PRAGMA foreign_key_check')==[]


def test_offline_readonly_source_keeps_actual_cached_content(source_api,pipeline):
    settings,client,headers,space=source_api
    settings=replace(settings,converter_token='pipeline-token')  # Real TCP Converter from pipeline fixture.
    source=create_source(client,headers,space).json()['id']
    response=scan(client,headers,source);assert response.status_code==202
    queue=JobQueue(settings);job=queue.claim('acceptance-source');assert job['id']==response.json()['job_id']
    observed=source_row(settings,source)
    # sysfs is kernel read-only; register its real bytes, without pretending extensionless
    # sysfs files were imported by the product scanner.
    with SourceMounts(settings.source_mounts).open('docs','core_id') as file:
        content=file.read();info=os.fstat(file.fileno())
    item={'path':'core_id','size_bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),
          'mtime_ns':info.st_mtime_ns,'identity_hint':f'{info.st_dev}:{info.st_ino}',
          'mime_type':'text/plain','file_modified_at':None}
    with queue.write() as db:
        db.row_factory=sqlite3.Row
        document,_=register_external(db,job,observed,item,None,'filed',settings,utc_now())
    # The scanner claim stays pending; only the actual parse is executed by the worker.
    assert Worker(settings).run_once()['status']=='completed'
    offline=replace(settings,source_mounts=(('docs',str(settings.data_dir/'absent-mount')),))
    with TestClient(create_app('archive',offline),base_url='https://archive.test') as after:
        after.cookies.update(client.cookies)
        root='/api/v1/documents/'+document
        doc=after.get(root).json();assert doc['availability_status']=='available'
        inventory=after.get(root+'/source-files').json()['items'][0]
        assert inventory['server_copy'] and inventory['storage_kind']=='external'
        assert inventory['source']['id']==source
        assert doc['processing_status']=='completed'
        cached=after.get(root+'/content?format=text').json();assert cached['body'].strip()==content.decode().strip()
        assert not cached['stale_for_current_revision'] and not doc['content_stale']
        assert after.get(root+'/download').content==content
    assert rows(settings,'PRAGMA foreign_key_check')==[]


def test_pending_ocr_never_claims_complete_text_then_real_ocr_publishes(pipeline):
    from format_samples import raster_sample
    settings,client,headers,space=pipeline
    receipt=upload(pipeline,raster_sample('PDF'),'等待OCR.pdf');root='/api/v1/documents/'+receipt['document_id']
    assert Worker(settings).run_once()['status']=='completed'
    limited=client.get(root+'/content?format=text').json()
    assert not limited['text_available'] and not limited['ocr_used']
    field(client,headers,space,'ocr_contract','text')
    assert client.patch(root+'/metadata',headers=headers,json={'expected_document_version':1,'confirm':True,
        'values':{'ocr_contract':'人工合同 OCR-2026'}}).status_code==200
    document=client.get(root).json()
    response=client.post(root+'/reprocess',headers=headers,json={
        'expected_document_version':document['document_version'],'expected_revision_id':document['current_revision_id'],
        'request_id':uuid.uuid4().hex,'ocr':True,'ocr_languages':'eng','force':True})
    assert response.status_code==202
    job=client.get('/api/v1/jobs/'+response.json()['job_id']).json()
    assert job['kind']=='ocr' and job['status']=='queued' and job['result'] is None
    pending=client.get(root+'/content?format=text').json()
    assert pending['processing_status']=='queued' and not pending['text_available'] and not pending['ocr_used']
    assert client.get(root).json()['processing_status']=='queued'
    assert Worker(settings).run_once()['status']=='completed'
    completed=client.get(root+'/content?format=text').json()
    assert completed['processing_status']=='completed' and completed['text_available'] and completed['ocr_used']
    assert 'Real scanned archive' in completed['body']
    assert completed['parse_run_id']!=limited['parse_run_id']
    assert client.get(root+'/metadata').json()[0]['value']=='人工合同 OCR-2026'
