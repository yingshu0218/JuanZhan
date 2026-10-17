"""Real child processes, SQLite, bytes and HTTP contract; no fake business success."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
import threading
import time
import uuid

from fastapi.testclient import TestClient
import pytest
import uvicorn

from juanzhan.apps import create_app
from juanzhan.config import Settings
from juanzhan.conversion_models import Options, ParseResult
from juanzhan.conversion_store import ConverterConfig, ConverterStore, ConversionError
from juanzhan.converter_client import ConverterClient, ConverterClientError


@pytest.fixture
def config(tmp_path):
    return ConverterConfig(root=tmp_path/'converter')


@pytest.fixture
def app(config,tmp_path):
    return create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)


HEADERS = {'Authorization':'Bearer private-converter-token'}


def submit(client, content=b'Actual text\n', **options):
    metadata = {'file_revision_id':'revision', 'parse_run_id':uuid.uuid4().hex, **options}
    return client.post('/v1/jobs',headers=HEADERS,data=metadata,files={'file':('arbitrary.txt',content,'application/octet-stream')})


def completed(client, id):
    deadline = time.monotonic()+10
    while time.monotonic()<deadline:
        response=client.get('/v1/jobs/'+id,headers=HEADERS)
        assert response.status_code==200,response.text
        job=response.json()
        if job['status'] not in ('queued','running'):
            return job
        time.sleep(.02)
    pytest.fail('Real converter did not finish within deadline')


def test_real_text_result_download_cleanup_and_archive_separation(app,config):
    text='\ufeff真实来源 🗃️\r\nSecond line\n'
    original=text.encode()
    with TestClient(app) as client:
        response=submit(client,original,declared_mime='text/plain',generate_preview='false')
        assert response.status_code==202
        id=response.json()['job_id']
        job=completed(client,id)
        assert job['status']=='completed' and job['attempts']==1
        result=client.get('/v1/jobs/'+id+'/result',headers=HEADERS).json()
        ParseResult.model_validate(result)
        assert result['status']=='completed' and result['schema_version']=='1.0'
        assert result['language'] is None and result['page_count'] is None
        assert result['metadata_candidates']==[] and not result['extraction']['ocr_used']
        decoded=text.removeprefix('\ufeff')
        assert ''.join(b['text'] for b in result['blocks'])==decoded
        assert result['blocks'][0]['locator']=={'kind':'character','start':0,'end':len(decoded)}
        assert result['blocks'][0]['confidence'] is None
        asset=result['artifacts'][0]
        response=client.get('/v1/artifacts/'+asset['artifact_ref'],headers=HEADERS)
        assert response.content==decoded.encode()
        assert hashlib.sha256(response.content).hexdigest()==asset['sha256']
        assert response.headers['x-content-type-options']=='nosniff'
        assert response.headers['cache-control']=='no-store'
        assert not (config.root/id/'input').exists()
        assert client.delete('/v1/jobs/'+id,headers=HEADERS).status_code==204
        assert client.get('/v1/artifacts/'+asset['artifact_ref'],headers=HEADERS).status_code==404
        assert client.get('/v1/jobs/'+id,headers=HEADERS).status_code==404
        assert not (config.root.parent/'archive').exists()


@pytest.mark.parametrize('content,mime',[(b'\x00binary','application/octet-stream')])
def test_unsupported_is_a_real_result_not_claimed_conversion(app,content,mime):
    with TestClient(app) as client:
        id=submit(client,content).json()['job_id']
        assert completed(client,id)['status']=='completed'  # Protocol completed; parser result unsupported.
        result=client.get('/v1/jobs/'+id+'/result',headers=HEADERS).json()
        assert result['status']=='unsupported' and result['source_mime']==mime
        assert result['blocks']==result['artifacts']==result['metadata_candidates']==[]
        assert 'UNSUPPORTED_INPUT_TYPE' in result['warnings']


def test_authentication_unknown_fields_booleans_languages_and_limits(app):
    with TestClient(app) as client:
        for method,path in [('get','/v1/capabilities'),('post','/v1/jobs'),('get','/v1/jobs/'+'a'*32),('delete','/v1/jobs/'+'a'*32),('get','/v1/jobs/'+'a'*32+'/result'),('get','/v1/artifacts/'+'a'*32)]:
            response=getattr(client,method)(path)
            assert response.status_code==401 and 'private-converter-token' not in response.text
        assert submit(client,path='/etc/passwd').status_code==422
        assert submit(client,file_revision_id='../bad').status_code==422
        assert submit(client,ocr_enabled='yes').status_code==422
        assert submit(client,ocr_enabled='true').json()['error']['code']=='OCR_UNAVAILABLE'
        assert submit(client,ocr_languages='unknown').json()['error']['code']=='INVALID_OCR_LANGUAGE'
        assert submit(client,ocr_languages='eng').json()['error']['code']=='OCR_DISABLED'
        assert client.post('/v1/jobs',headers=HEADERS,json={'url':'https://example.test'}).status_code==400
        duplicate=client.post('/v1/jobs',headers=HEADERS,files=[('file',('a',b'a')),('file_revision_id',(None,'r')),('parse_run_id',(None,'p')),('parse_run_id',(None,'p'))])
        assert duplicate.status_code==422
        assert client.get('/v1/artifacts/not-a-controlled-ref',headers=HEADERS).status_code==404


def test_idempotency_capacity_and_expiry(app,config):
    with TestClient(app) as client:
        first=submit(client,parse_run_id='stable').json()['job_id']
        assert submit(client,parse_run_id='stable').json()['job_id']==first
        assert submit(client,b'changed',parse_run_id='stable').status_code==409
        second=submit(client).json()['job_id']
        assert submit(client).status_code==429
        assert completed(client,first)['status']=='completed'
        assert completed(client,second)['status']=='completed'
        # Advance only this fixture's creation timestamp; no timing-sensitive TTL sleep.
        import sqlite3
        with sqlite3.connect(config.root/'converter.sqlite3') as db:
            db.execute('UPDATE tasks SET created=0 WHERE id=?',(first,))
        assert client.get('/v1/jobs/'+first,headers=HEADERS).status_code==404
        assert not (config.root/first).exists()
        assert submit(client).status_code==202


@pytest.mark.parametrize('limits,content,code',[
    ({'wall_seconds':.00001},b'text','CONVERSION_TIMEOUT'),
    ({'max_blocks':1},b'a'*8192,'RESULT_LIMIT'),
    ({'max_output_bytes':1024},b'a'*3000,'RESULT_LIMIT'),
], ids=['wall','blocks','output'])
def test_real_child_resource_limits(config,tmp_path,limits,content,code):
    app=create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=replace(config,**limits))
    with TestClient(app) as client:
        id=submit(client,content).json()['job_id']
        job=completed(client,id)
        assert job['status']=='failed'
        assert job['error']['error']['code']==code
        assert client.get('/v1/jobs/'+id+'/result',headers=HEADERS).status_code==409
        assert not (config.root/id/'input').exists()


def test_input_byte_limit_and_malformed_multipart(config,tmp_path):
    app=create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=replace(config,max_file_bytes=4))
    with TestClient(app) as client:
        assert submit(client,b'12345').status_code==413
        response=client.post('/v1/jobs',headers={**HEADERS,'Content-Type':'multipart/form-data; boundary=x'},content=b'--x\r\n')
        assert response.status_code==400
        assert not list(config.root.glob('[0-9a-f]'*32))


@contextmanager
def real_server(app):
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    thread.start()
    deadline=time.monotonic()+10
    while not server.started:
        if not thread.is_alive() or time.monotonic()>deadline:
            raise AssertionError('Fixture server failed to start')
        time.sleep(.01)
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def test_archive_client_real_socket_chunked_upload_verify_and_cleanup(app):
    with real_server(app) as base:
        client=ConverterClient(base,'private-converter-token')
        from juanzhan.conversion_formats import SUPPORTED
        assert client.capabilities()['supported_input_types']==SUPPORTED
        content='真实客户端原件\n'.encode()
        options=Options(file_revision_id='r',parse_run_id='p',generate_preview=False)
        first=client.submit(BytesIO(content),options)
        assert client.submit(BytesIO(content),options)['job_id']==first['job_id']
        job=client.wait(first['job_id'])
        assert job['status']=='completed'
        result=client.result(first['job_id'],file_revision_id='r',parse_run_id='p')
        with client.artifact(result['artifacts'][0]) as file:
            assert file.read()==content
        with pytest.raises(ConverterClientError,match='CONVERTER_IDENTITY_MISMATCH'):
            client.result(first['job_id'],file_revision_id='wrong',parse_run_id='p')
        corrupt={**result['artifacts'][0],'sha256':'0'*64}
        with pytest.raises(ConverterClientError,match='CONVERTER_ARTIFACT_INTEGRITY'):
            with client.artifact(corrupt):
                pytest.fail('Unverified bytes were exposed')
        client.delete(first['job_id'])
        with pytest.raises(ConverterClientError) as error:
            client.job(first['job_id'])
        assert error.value.status==404


def test_spool_single_owner_restart_failure_and_queued_recovery(config):
    store=ConverterStore(config)
    store.start()
    try:
        with pytest.raises(RuntimeError,match='Only one'):
            ConverterStore(config).start()
    finally:
        store.close()
    # Seed via the real submit path while stopped; emulate a crashed active task in the private DB.
    first=store.submit(BytesIO(b'queued text'),Options(file_revision_id='r',parse_run_id='queued'))
    active=store.submit(BytesIO(b'active text'),Options(file_revision_id='r2',parse_run_id='active'))
    with store.database() as db:
        db.execute("UPDATE tasks SET status='running',attempts=1 WHERE id=?",(active['job_id'],))
    recovered=ConverterStore(config)
    recovered.start()
    try:
        assert recovered.get(active['job_id'])['error']['error']['code']=='CONVERTER_RESTARTED'
        deadline=time.monotonic()+10
        while recovered.get(first['job_id'])['status'] in ('queued','running'):
            assert time.monotonic()<deadline
            time.sleep(.02)
        assert recovered.get(first['job_id'])['status']=='completed'
        assert recovered.get(first['job_id'])['attempts']==1
    finally:
        recovered.close()


def test_text_decode_failure_preserves_no_partial_result(app):
    with TestClient(app) as client:
        id=submit(client,b'a'*65536+b'\xff').json()['job_id']
        job=completed(client,id)
        assert job['status']=='failed' and job['error']['error']['code']=='INVALID_TEXT_ENCODING'
        assert client.get('/v1/jobs/'+id+'/result',headers=HEADERS).status_code==409


def test_client_rejects_untrusted_protocol_and_redirects(tmp_path):
    # Deliberately fake contract peer tests validation only; real conversion is tested above.
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    state={'response':b'{}','status':200,'location':None,'hits':0}
    class Peer(BaseHTTPRequestHandler):
        def do_GET(self):
            state['hits']+=1
            self.send_response(state['status'])
            self.send_header('Content-Type','application/json')
            if state['location']:
                self.send_header('Location',state['location'])
            self.end_headers()
            self.wfile.write(state['response'])
        def log_message(self,*_):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Peer)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        client=ConverterClient(f'http://127.0.0.1:{server.server_port}','secret',max_json_bytes=1024)
        for content in (b'{"x":1,"x":2}',b'{"x":NaN}',b'['*1200,b'not json'):
            state['response']=content
            with pytest.raises(ConverterClientError):
                client.json('/peer')
        state['response']=b'x'*2048
        with pytest.raises(ConverterClientError,match='CONVERTER_RESPONSE_LIMIT'):
            client.json('/peer')
        state['response']=b'{"job_id":"not-an-id","status":"running","attempts":1}'
        with pytest.raises(ConverterClientError,match='INVALID_CONVERTER_ID'):
            client.job('a'*32)
        state['response']=b'{}'
        state['status']=302
        state['location']=f'http://127.0.0.1:{server.server_port}/redirect-target'
        before=state['hits']
        with pytest.raises(ConverterClientError) as error:
            client.capabilities()
        assert error.value.status==302 and state['hits']==before+1
        with pytest.raises(ConverterClientError):
            with client.artifact({'artifact_ref':'../../etc/passwd'}):
                pytest.fail('Unsafe reference accepted')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_publish_interruption_becomes_failed_and_does_not_block_queue(config,monkeypatch):
    store=ConverterStore(config)
    original_execute=store.execute
    calls=[]
    def interrupted(id):
        calls.append(id)
        if len(calls)==1:
            raise OSError('Injected publication/storage outage')
        original_execute(id)
    monkeypatch.setattr(store,'execute',interrupted)
    store.start()
    try:
        first=store.submit(BytesIO(b'first'),Options(file_revision_id='r',parse_run_id='first'))
        second=store.submit(BytesIO(b'second'),Options(file_revision_id='r2',parse_run_id='second'))
        deadline=time.monotonic()+10
        while store.get(second['job_id'])['status'] in ('queued','running'):
            assert time.monotonic()<deadline
            time.sleep(.02)
        failed=store.get(first['job_id'])
        assert failed['status']=='failed' and failed['attempts']==1
        assert failed['error']['error']['code']=='CONVERTER_PUBLISH_FAILED'
        assert store.get(second['job_id'])['status']=='completed'
        assert calls==[first['job_id'],second['job_id']]
        store.delete(first['job_id'])
        assert not (config.root/first['job_id']).exists()
    finally:
        store.close()
