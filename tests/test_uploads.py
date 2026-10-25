import asyncio
import io
from dataclasses import replace
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.uploads import sniff
from juanzhan.worker import Worker


@pytest.fixture
def uploads(tmp_path):
    settings=Settings(tmp_path/'archive','converter-token',upload_max_bytes=1024)
    app=create_app('archive',settings)
    with TestClient(app,base_url='https://archive.test',raise_server_exceptions=False) as client:
        set_password(settings,'upload-test-password')
        csrf=client.get('/api/v1/auth/session').json()['csrf_token']
        csrf=client.post('/api/v1/auth/login',json={'username':'admin','password':'upload-test-password'},headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        headers={'X-CSRF-Token':csrf}
        space=client.post('/api/v1/spaces',json={'name':'Uploads'},headers=headers).json()['id']
        bearer=client.post('/api/v1/auth/tokens',json={'name':'upload'},headers=headers).json()['token']
        yield app,settings,client,headers,space,bearer


def send(client,headers,space,content=b'hello',filename='file.txt',**metadata):
    return client.post('/api/v1/documents/upload',data={'space_id':space,**metadata},
                       files={'file':(filename,content,'application/pdf')},headers=headers)


@pytest.mark.parametrize('filename',['.DS_Store','.ds_store','.localized','Thumbs.db','ehthumbs_vista.db','desktop.ini','._report.docx','~$report.docx','.~lock.report.odt#','.report.swp','.git','.gitignore','.gitattributes','.gitmodules','.gitkeep','.git-credentials','.hgignore','.bzrignore'])
def test_auxiliary_uploads_are_excluded_without_persistence(uploads,filename):
    app,settings,client,headers,space,bearer=uploads
    stored=lambda: {str(path.relative_to(settings.data_dir/'managed')):path.read_bytes() for path in (settings.data_dir/'managed').rglob('*') if path.is_file()}
    files_before=stored()
    with connect(settings.database) as db:
        before={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('documents','file_revisions','managed_objects','jobs')}
    for auth in (headers,{'Authorization':'Bearer '+bearer}):
        response=send(client,auth,space,filename=filename)
        assert response.status_code==422,response.text
        assert response.json()['error']['code']=='UPLOAD_EXCLUDED'
    with connect(settings.database) as db:
        assert before=={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in before}
    assert stored()==files_before


@pytest.mark.parametrize('filename',['README.md','notes.tmp','notes.bak','report.docx~','Thumbs.db.txt','~$budget.txt','desktop.ini.pdf'])
def test_hidden_documents_and_backups_are_preserved(uploads,filename):
    app,settings,client,headers,space,bearer=uploads
    response=send(client,headers,space,filename=filename)
    assert response.status_code==201,response.text


def counts(settings):
    with connect(settings.database) as db:
        return [db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                ('documents','file_revisions','managed_objects','document_events','jobs')]


def test_real_upload_atomic_registration_and_truthful_parse_job(uploads):
    app,settings,client,headers,space,bearer=uploads
    response=send(client,headers,space,b'actual text',triage_status='filed')
    assert response.status_code==201,response.text
    result=response.json()
    assert result['upload_status']=='saved' and set(result)=={'document_id','revision_id','job_id','upload_status'}
    assert counts(settings)==[1,1,1,1,1]
    with connect(settings.database) as db:
        row=db.execute('SELECT r.mime_type,m.storage_key FROM file_revisions r JOIN managed_objects m ON m.id=r.managed_object_id').fetchone()
        assert row[0]=='text/plain'  # Ignore misleading client Content-Type.
    with app.state.storage.open(row[1]) as file:assert file.read()==b'actual text'
    assert app.state.documents.get_record(result['document_id'])['triage_status']=='filed'
    job=client.get('/api/v1/jobs/'+result['job_id']).json()
    assert job['status']=='queued'
    Worker(settings).run_once()
    job=client.get('/api/v1/jobs/'+result['job_id']).json()
    assert job['status']=='queued' and job['error']['code']=='CONVERTER_UNAVAILABLE'
    assert counts(settings)==[1,1,1,1,2]


def test_duplicate_reject_and_explicit_keep_separate(uploads):
    app,settings,client,headers,space,bearer=uploads
    first=send(client,headers,space).json()
    duplicate=send(client,headers,space)
    assert duplicate.status_code==409
    assert duplicate.json()['error']['details']['duplicates']==[first['document_id']]
    assert counts(settings)==[1,1,1,1,1]
    separate=send(client,headers,space,duplicate_policy='keep_separate')
    assert separate.status_code==201 and separate.json()['document_id']!=first['document_id']
    assert counts(settings)==[2,2,1,2,2]


def test_upload_auth_csrf_and_bearer(uploads):
    app,settings,client,headers,space,bearer=uploads
    assert send(client,{},space).status_code==403
    with TestClient(app) as anonymous:
        assert send(anonymous,{},space).status_code==401
    assert send(client,{'Authorization':'Bearer '+bearer},space).status_code==201


@pytest.mark.parametrize('metadata,filename',[({'triage_status':'invalid'},'file.txt'),
    ({'duplicate_policy':'merge'},'file.txt'),({'unexpected':'field'},'file.txt'),({},'../file.txt')])
def test_invalid_metadata_never_registers(uploads,metadata,filename):
    app,settings,client,headers,space,bearer=uploads
    assert send(client,headers,space,filename=filename,**metadata).status_code==422
    assert counts(settings)==[0,0,0,0,0]


def test_limits_unknown_scope_and_multiple_files(uploads):
    app,settings,client,headers,space,bearer=uploads
    assert send(client,headers,space,b'x'*1025).status_code==413
    assert send(client,headers,'missing').status_code==404
    other=client.post('/api/v1/spaces',json={'name':'Other'},headers=headers).json()['id']
    folder=client.post('/api/v1/folders',json={'space_id':other,'name':'Foreign'},headers=headers).json()['id']
    assert send(client,headers,space,folder_id=folder).status_code==422
    response=client.post('/api/v1/documents/upload',data={'space_id':space},files=[('file',('a',b'1')),('file',('b',b'2'))],headers=headers)
    assert response.status_code==400
    assert counts(settings)==[0,0,0,0,0]
    assert list((settings.data_dir/'managed'/'.staging').iterdir())==[]


def test_enqueue_failure_rolls_back_document_revision_and_audit(uploads):
    app,settings,client,headers,space,bearer=uploads
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER fail_job BEFORE INSERT ON jobs BEGIN SELECT RAISE(ABORT,'injected queue failure'); END;")
    result=send(client,headers,space)
    assert result.status_code==409
    assert counts(settings)==[0,0,0,0,0]
    assert len(list((settings.data_dir/'managed'/'sha256').glob('*/*')))==1


def test_chunked_total_limit_incomplete_and_timeout(uploads):
    app,settings,client,headers,space,bearer=uploads
    async def run():
        auth={'Authorization':'Bearer '+bearer,'Content-Type':'multipart/form-data; boundary=b'}
        transport=httpx.ASGITransport(app=app,raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport,base_url='http://archive') as remote:
            async def over():
                yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="file.txt"\r\n\r\nx\r\n--b--\r\n'
                for _ in range(70):yield b' '*1024
            assert (await remote.post('/api/v1/documents/upload',content=over(),headers=auth)).status_code==413
            body=(b'--b\r\nContent-Disposition: form-data; name="file"; filename="file.txt"\r\n\r\npartial')
            assert (await remote.post('/api/v1/documents/upload',content=body,headers=auth)).status_code==400
            from starlette.requests import ClientDisconnect
            async def interrupted():
                yield body
                raise ClientDisconnect()
            assert (await remote.post('/api/v1/documents/upload',content=interrupted(),headers=auth)).status_code==400
        timed=create_app('archive',replace(settings,upload_timeout_seconds=0.02))
        with TestClient(timed):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=timed,raise_app_exceptions=False),base_url='http://archive') as remote:
                async def slow():
                    yield body
                    await asyncio.sleep(0.1)
                    yield b'late'
                assert (await remote.post('/api/v1/documents/upload',content=slow(),headers=auth)).status_code==408
    asyncio.run(run())
    assert counts(settings)==[0,0,0,0,0]


@pytest.mark.parametrize('payload,name,mime',[(b'%PDF-1.7\n','fake.txt','application/pdf'),
    (b'\x89PNG\r\n\x1a\n','image.txt','image/png'),(b'\xff\x00binary','fake.pdf','application/octet-stream'),
    (b'<html><body>text','note.txt','text/html'),('中文笔记'.encode(),'note.md','text/markdown')])
def test_sniff_is_bounded_and_does_not_trust_declarations(payload,name,mime):
    assert sniff(io.BytesIO(payload),name)==mime


def test_docx_epub_and_generic_zip_metadata_sniff():
    for entries,mime in [({'[Content_Types].xml':b'<Types/>','word/document.xml':b'<doc/>'},'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                         ({'mimetype':b'application/epub+zip'},'application/epub+zip'),
                         ({'../../escape':b'no extraction'},'application/zip')]:
        file=io.BytesIO()
        with zipfile.ZipFile(file,'w') as archive:
            for name,value in entries.items():archive.writestr(name,value)
        assert sniff(file,'untrusted.bin')==mime


def test_upload_admission_limit_does_not_queue_unbounded_bodies(uploads):
    app,settings,client,headers,space,bearer=uploads
    async def run():
        entered=[asyncio.Event(),asyncio.Event()]
        finish=asyncio.Event()
        auth={'Authorization':'Bearer '+bearer,'Content-Type':'multipart/form-data; boundary=b'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,raise_app_exceptions=False),base_url='http://archive') as remote:
            async def content(i):
                yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="file.txt"\r\n\r\nx'
                entered[i].set()
                await finish.wait()
            tasks=[asyncio.create_task(remote.post('/api/v1/documents/upload',content=content(i),headers=auth)) for i in range(2)]
            try:
                await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered)),2)
                response=await remote.post('/api/v1/documents/upload',content=b'',headers=auth)
                assert response.status_code==429
            finally:
                finish.set()
                results=await asyncio.gather(*tasks)
                assert all(result.status_code==400 for result in results)
    asyncio.run(run())
    assert counts(settings)==[0,0,0,0,0]


def test_spooled_file_rollover_and_utf8_filename(tmp_path):
    settings=Settings(tmp_path/'archive','token',upload_max_bytes=2*1024*1024)
    app=create_app('archive',settings)
    with TestClient(app,base_url='https://archive.test') as client:
        set_password(settings,'large-upload-password')
        csrf=client.get('/api/v1/auth/session').json()['csrf_token']
        csrf=client.post('/api/v1/auth/login',json={'username':'admin','password':'large-upload-password'},headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        headers={'X-CSRF-Token':csrf}
        space=client.post('/api/v1/spaces',json={'name':'Large'},headers=headers).json()['id']
        payload='中文笔记\n'.encode()*20000
        response=send(client,headers,space,payload,filename='笔记.md')
        assert response.status_code==201
        with connect(settings.database) as db:
            mime,size,name,key=db.execute('SELECT r.mime_type,r.size_bytes,r.original_filename,m.storage_key FROM file_revisions r JOIN managed_objects m ON m.id=r.managed_object_id').fetchone()
        assert mime=='text/markdown' and size==len(payload) and name=='笔记.md'
        with app.state.storage.open(key) as file:assert file.read()==payload


def test_exact_file_limit_and_repeated_metadata(uploads):
    app,settings,client,headers,space,bearer=uploads
    assert send(client,headers,space,b'x'*1024).status_code==201
    boundary='b'
    body=(f'--b\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space}\r\n'
          f'--b\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space}\r\n'
          '--b\r\nContent-Disposition: form-data; name="file"; filename="second.txt"\r\n\r\nsecond\r\n--b--\r\n').encode()
    response=client.post('/api/v1/documents/upload',content=body,headers={**headers,'Content-Type':'multipart/form-data; boundary=b'})
    assert response.status_code==422 and counts(settings)==[1,1,1,1,1]
