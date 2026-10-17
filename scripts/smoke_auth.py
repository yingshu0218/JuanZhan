"""Exercise a disposable Archive container, real HTTP and the local admin CLI.
Run after building juanzhan-foundation:dev. Never touches the normal Compose volume.
"""
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def docker(*args, input=None):
    return subprocess.run(['docker', *args], input=input, text=True, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


name = 'juanzhan-auth-smoke-' + uuid.uuid4().hex[:12]
volume = name + '-data'
password = secrets.token_urlsafe(32)
cookie = ''
base = ''


def request(path, method='GET', body=None, csrf=None, bearer=None, use_cookie=True):
    headers = {}
    if cookie and use_cookie:
        # Internal HTTP hop simulates TLS termination; Secure flag checked separately.
        headers['Cookie'] = cookie
    if csrf:
        headers['X-CSRF-Token'] = csrf
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None, response.headers


def upload_original(space_id,policy='reject'):
    boundary='upload-'+secrets.token_hex(12)
    body=b''
    for field,value in [('space_id',space_id),('duplicate_policy',policy)]:
        body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+field+'"\r\n\r\n'+value+'\r\n').encode()
    body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="network.txt"\r\nContent-Type: application/pdf\r\n\r\n').encode()
    body+=b'http original\n'*20000+('\r\n--'+boundary+'--\r\n').encode()
    req=urllib.request.Request(base+'/api/v1/documents/upload',data=body,
        headers={'Cookie':cookie,'X-CSRF-Token':csrf,'Content-Type':'multipart/form-data; boundary='+boundary})
    try:
        response=urllib.request.urlopen(req,timeout=10)
    except urllib.error.HTTPError as error:
        response=error
    with response:
        return response.status,json.load(response)


created = False
started = False
try:
    docker('volume', 'create', volume)
    created = True
    docker('run', '-d', '--name', name, '-p', '127.0.0.1::8000',
           '--mount', f'type=volume,source={volume},target=/data',
           '-e', 'JUANZHAN_DATA_DIR=/data', 'juanzhan-foundation:dev')
    started = True
    port = docker('port', name, '8000/tcp').split(':')[-1]
    base = 'http://127.0.0.1:' + port

    def ready():
        for _ in range(30):
            try:
                if request('/healthz')[0] == 200:
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.2)
        raise AssertionError('Container did not become ready')

    ready()
    with urllib.request.urlopen(base+'/',timeout=5) as response:
        assert response.status==200 and 'JuanZhan' in response.read().decode()
        assert response.headers['Cache-Control']=='no-store'
    assert request('/api/v1/documents')[0] == 401
    docker('exec', '-i', name, 'python', '-m', 'juanzhan.admin', 'set-password', '--stdin',
           input=password + '\n')
    status, session, headers = request('/api/v1/auth/session')
    assert status == 200
    assert 'HttpOnly' in headers['Set-Cookie'] and 'Secure' in headers['Set-Cookie']
    cookie = headers['Set-Cookie'].split(';')[0]
    body = {'username':'admin', 'password':password}
    assert request('/api/v1/auth/login', 'POST', body)[0] == 403
    status, logged_in, headers = request('/api/v1/auth/login', 'POST', body, session['csrf_token'])
    assert status == 200
    cookie = headers['Set-Cookie'].split(';')[0]
    csrf = logged_in['csrf_token']
    assert request('/api/v1/auth/tokens', 'POST', {'name':'blocked'})[0] == 403
    status, token, headers = request('/api/v1/auth/tokens', 'POST', {'name':'smoke'}, csrf)
    assert status == 201 and headers['Cache-Control'] == 'no-store'
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 200
    status, catalog_space, _ = request('/api/v1/spaces', 'POST', {'name':'Smoke catalog'}, csrf)
    assert status == 201
    space_id = catalog_space['id']
    status, catalog_folder, _ = request('/api/v1/folders', 'POST', {'space_id':space_id,'name':'Root'}, csrf)
    assert status == 201
    assert request('/api/v1/folders', 'POST', {'space_id':space_id,'name':'ROOT'}, csrf)[0] == 409
    assert request('/api/v1/folders/'+catalog_folder['id'], 'PATCH', {'parent_id':catalog_folder['id']}, csrf)[0] == 409
    status, catalog_tag, _ = request('/api/v1/tags', 'POST', {'space_id':space_id,'name':'important'}, csrf)
    assert status == 201
    status, catalog_type, _ = request('/api/v1/document-types', 'POST', {'space_id':space_id,'key':'contract','label':'Contract'}, csrf)
    assert status == 201
    field_body={'space_id':space_id,'key':'contract_amount','label':'Amount','type':'decimal',
                'constraints':{'min':'2.00','max':'10.00'},'searchable':True,'filterable':True}
    assert request('/api/v1/field-definitions','POST',field_body)[0]==403
    status,field,_=request('/api/v1/field-definitions','POST',field_body,csrf)
    assert status==201 and field['constraints']==field_body['constraints']
    assert request('/api/v1/field-definitions','POST',field_body,csrf)[0]==409
    assert request('/api/v1/field-definitions/'+field['id'],'PATCH',{'type':'text'},csrf)[0]==422
    binding={'field_definition_id':field['id'],'required_for_filing':True,'display_order':1}
    assert request('/api/v1/document-types/'+catalog_type['id'],'PATCH',{'fields':[binding]},csrf)[0]==200
    assert request('/api/v1/field-definitions/'+field['id'],'PATCH',{'label':'Contract amount','is_active':False},csrf)[0]==200
    assert request('/api/v1/document-types','POST',{'space_id':space_id,'key':'blocked','label':'Blocked','fields':[binding]},csrf)[0]==422
    status,uploaded=upload_original(space_id)
    assert status==201 and uploaded['upload_status']=='saved'
    status,duplicate=upload_original(space_id)
    assert status==409 and duplicate['error']['details']['duplicates']==[uploaded['document_id']]
    status,separate=upload_original(space_id,'keep_separate')
    assert status==201 and separate['document_id']!=uploaded['document_id']
    expected_jobs={uploaded['job_id'],separate['job_id']}
    for _ in range(2):
        outcome=json.loads(docker('exec',name,'python','-m','juanzhan.worker','--once'))
        assert outcome['job_id'] in expected_jobs and outcome['status']=='failed'
        expected_jobs.remove(outcome['job_id'])
        assert request('/api/v1/jobs/'+outcome['job_id'])[1]['error']['code']=='HANDLER_NOT_AVAILABLE'
    document_path='/api/v1/documents/'+uploaded['document_id']
    assert request(document_path)[1]['document_version']==1
    assert request(document_path,'PATCH',{'expected_document_version':1,'is_favorite':True},csrf)[1]['document_version']==2
    assert request(document_path,'PATCH',{'expected_document_version':1,'title':'stale'},csrf)[0]==409
    assert request(document_path+'/triage','POST',{'expected_document_version':2,'triage_status':'filed'},csrf)[1]['document_version']==3
    assert request(document_path+'/trash','POST',{'expected_document_version':3},csrf)[0]==200
    assert any(d['id']==uploaded['document_id'] for d in request('/api/v1/documents?trash=only')[1]['items'])
    assert request(document_path+'/restore','POST',{'expected_document_version':4},csrf)[0]==200
    root=request('/api/v1/folders','POST',{'space_id':space_id,'name':'Disposable subtree'},csrf)[1]
    child=request('/api/v1/folders','POST',{'space_id':space_id,'parent_id':root['id'],'name':'Child'},csrf)[1]
    separate_path='/api/v1/documents/'+separate['document_id']
    assert request(separate_path,'PATCH',{'expected_document_version':1,'folder_id':child['id']},csrf)[0]==200
    assert request('/api/v1/folders/'+root['id']+'/delete','POST',{'mode':'trash_contents','confirm_folder_id':root['id']},csrf)[0]==204
    result=request(separate_path)[1]
    assert result['deleted_at'] and result['folder_id'] is None and result['document_version']==3
    assert request(separate_path+'/restore','POST',{'expected_document_version':3},csrf)[0]==200
    docker('exec', '-i', name, 'python', '-', input=r"""
import io, os
from pathlib import Path
from juanzhan.storage import ManagedStore
from juanzhan.database import connect
store = ManagedStore(Path('/data/managed'))
result = store.put(io.BytesIO(b'container original'), max_bytes=100)
with connect('/data/database/archive.sqlite3') as db:
    db.execute('INSERT INTO managed_objects VALUES (?,?,?,?,?)',
               ('storage-smoke', result.sha256, result.size_bytes, result.storage_key, '2026-10-16T00:00:00Z'))
    db.commit()
from juanzhan.config import Settings
from juanzhan.documents import DocumentService, Registration, RevisionChange, VersionChange
service = DocumentService(Settings.from_env())
with connect('/data/database/archive.sqlite3') as db:
    space = db.execute("SELECT id FROM spaces WHERE name='Smoke catalog'").fetchone()[0]
doc = service.register_managed(result, Registration(space_id=space,title='Lifecycle smoke',
    original_filename='original.txt',mime_type='text/plain'))
next_object = store.put(io.BytesIO(b'container revision'), max_bytes=100)
updated = service.append_managed_revision(doc['id'],next_object,
    RevisionChange(expected_document_version=1,original_filename='revision.txt',mime_type='text/plain'))
assert updated['id'] == doc['id'] and updated['document_version'] == 2
service.trash(doc['id'],VersionChange(expected_document_version=2))
old = Path('/data/managed/.staging') / ('c' * 32 + '.part')
old.write_bytes(b'interrupted')
os.utime(old, (0, 0))
from juanzhan.jobs import JobQueue, JobSpec
JobQueue(Settings.from_env()).enqueue(JobSpec(kind='gc',target_type='managed_staging',
    idempotency_key='container-staging-gc'))

""")
    batch_status,batch,_=request('/api/v1/documents/batch','POST',{
        'space_id':space_id,'document_ids':[uploaded['document_id'],separate['document_id']],
        'selection_mode':'snapshot','expected_versions':{uploaded['document_id']:5,separate['document_id']:4},
        'operation':'set_favorite','payload':{'is_favorite':False}},csrf)
    assert batch_status==202
    assert request(separate_path,'PATCH',{'expected_document_version':4,'title':'Concurrent change'},csrf)[0]==200
    docker('restart', name)
    # Docker may allocate a new ephemeral host port on restart.
    port = docker('port', name, '8000/tcp').split(':')[-1]
    base = 'http://127.0.0.1:' + port
    ready()
    docker('exec', '-i', name, 'python', '-', input=r"""
from pathlib import Path
from juanzhan.storage import ManagedStore
from juanzhan.database import connect
with connect('/data/database/archive.sqlite3') as db:
    key = db.execute("SELECT storage_key FROM managed_objects WHERE id='storage-smoke'").fetchone()[0]
with ManagedStore(Path('/data/managed')).open(key) as file:
    assert file.read() == b'container original'
assert list(Path('/data/managed/.staging').iterdir()) == []

with connect('/data/database/archive.sqlite3') as db:
    uploaded=db.execute("SELECT r.mime_type,r.size_bytes,m.storage_key FROM file_revisions r JOIN managed_objects m ON m.id=r.managed_object_id WHERE r.original_filename='network.txt'").fetchall()
assert len(uploaded)==2 and uploaded[0][2]==uploaded[1][2]
assert uploaded[0][0]=='text/plain' and uploaded[0][1]==len(b'http original\n'*20000)
with ManagedStore(Path('/data/managed')).open(uploaded[0][2]) as file:
    assert file.read()==b'http original\n'*20000

from juanzhan.config import Settings
from juanzhan.documents import DocumentService, VersionChange
service = DocumentService(Settings.from_env())
with connect('/data/database/archive.sqlite3') as db:
    id = db.execute("SELECT id FROM documents WHERE title='Lifecycle smoke'").fetchone()[0]
before = service.get_record(id)
assert before['document_version'] == 3 and before['deleted_at'] is not None
after = service.restore(id,VersionChange(expected_document_version=3))
assert after['document_version'] == 4 and after['deleted_at'] is None
assert [r['revision_no'] for r in service.revisions(id)] == [1,2]
with connect('/data/database/archive.sqlite3') as db:
    assert db.execute('SELECT count(*) FROM document_events WHERE document_id=?',(id,)).fetchone() == (4,)
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []

""")
    assert request('/api/v1/auth/tokens')[0] == 200
    persisted_fields=request('/api/v1/field-definitions?space_id='+space_id)[1]
    assert len(persisted_fields)==1 and persisted_fields[0]['id']==field['id']
    assert persisted_fields[0]['label']=='Contract amount' and not persisted_fields[0]['is_active']
    assert persisted_fields[0]['constraints']==field_body['constraints']
    assert request('/api/v1/document-types?space_id='+space_id)[1][0]['fields']==[binding]
    assert request('/api/v1/document-types/'+catalog_type['id'],'PATCH',{'fields':[binding]},csrf)[0]==200
    job_id = docker('exec','-i',name,'python','-',input=r"""
from pathlib import Path
import os
from juanzhan.config import Settings
from juanzhan.jobs import JobQueue,JobSpec
queue=JobQueue(Settings.from_env())
job=queue.enqueue(JobSpec(kind='gc',target_type='managed_staging',idempotency_key='container-staging-gc'))
assert job['status']=='queued' and job['attempts']==0
old=Path('/data/managed/.staging')/('e'*32+'.part')
old.write_bytes(b'worker cleanup')
os.utime(old,(0,0))
print(job['id'])
""")
    assert request('/api/v1/jobs/'+job_id)[1]['status']=='queued'
    once = json.loads(docker('exec',name,'python','-m','juanzhan.worker','--once'))
    assert once == {'job_id':job_id,'status':'completed'}
    status, completed, _ = request('/api/v1/jobs/'+job_id)
    assert status==200 and completed['result']=={'removed_staging_files':1} and completed['attempts']==1
    assert 'lease_token' not in completed and 'payload_json' not in completed
    outcome=json.loads(docker('exec',name,'python','-m','juanzhan.worker','--once'))
    assert outcome=={'job_id':batch['job_id'],'status':'completed'}
    batch_result=request('/api/v1/jobs/'+batch['job_id'])[1]['result']
    assert batch_result['succeeded']==1 and batch_result['failed']==1
    assert batch_result['items'][1]['error_code']=='VERSION_CONFLICT'
    assert request(document_path)[1]['is_favorite'] is False
    undo_status,undo,_=request('/api/v1/jobs/'+batch['job_id']+'/undo','POST',csrf=csrf)
    assert undo_status==202
    assert request('/api/v1/jobs/'+batch['job_id']+'/undo','POST',csrf=csrf)[1]['job_id']==undo['job_id']
    assert json.loads(docker('exec',name,'python','-m','juanzhan.worker','--once'))=={'job_id':undo['job_id'],'status':'completed'}
    assert request(document_path)[1]['is_favorite'] is True
    assert request(document_path)[1]['document_version']==7
    assert request(separate_path)[1]['title']=='Concurrent change'
    assert request('/api/v1/jobs/'+job_id+'/retry','POST')[0]==403
    assert request('/api/v1/jobs/'+job_id+'/retry','POST',csrf=csrf)[0]==409
    retry_id=docker('exec','-i',name,'python','-',input=r"""
from juanzhan.config import Settings
from juanzhan.jobs import JobQueue,JobSpec
queue=JobQueue(Settings.from_env())
job=queue.enqueue(JobSpec(kind='gc',target_type='managed_staging',idempotency_key='manual-retry',auto_retry=False))
claim=queue.claim('manual-test')
assert claim['id']==job['id']
queue.failure(job['id'],claim['lease_token'],'TEMPORARY','Temporary test error',retryable=True)
print(job['id'])
""")
    assert request('/api/v1/jobs/'+retry_id+'/retry','POST',csrf=csrf)[0]==202
    once=json.loads(docker('exec',name,'python','-m','juanzhan.worker','--once'))
    assert once=={'job_id':retry_id,'status':'completed'}
    assert request('/api/v1/jobs/'+retry_id)[1]['attempts']==2
    assert request('/api/v1/field-definitions/'+field['id'],'PATCH',{'is_active':True},csrf)[0]==200
    metadata_path=document_path+'/metadata'
    status,values,_=request(metadata_path,'PATCH',{'expected_document_version':7,'values':{'contract_amount':'2.00'},'confirm':True},csrf)
    assert status==200 and values[0]['value']=='2.0000'
    assert request(document_path,'PATCH',{'expected_document_version':8,'document_type_id':catalog_type['id']},csrf)[0]==200
    assert request(metadata_path,'PATCH',{'expected_document_version':9,'values':{'contract_amount':None},'confirm':True},csrf)[0]==422
    assert request(metadata_path,'PATCH',{'expected_document_version':9,'values':{'contract_amount':'10.0001'},'confirm':True},csrf)[0]==422
    # Seed a persisted candidate fixture; real parser generation belongs to T19+.
    docker('exec','-i',name,'python','-',input="""
import json
from juanzhan.database import connect
with connect('/data/database/archive.sqlite3') as db:
    db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at) VALUES ('metadata-smoke-run',?,?,'fixture','1','1','completed','now')", DOC_IDS)
    db.execute("INSERT INTO extracted_metadata(id,parse_run_id,candidate_key,candidate_value_json) VALUES ('metadata-smoke-candidate','metadata-smoke-run','amount',?)",(json.dumps('10.00'),))
    db.execute("UPDATE documents SET current_parse_run_id='metadata-smoke-run' WHERE id=?",(DOC_ID,))
    db.commit()
""".replace('DOC_IDS',repr((uploaded['document_id'],uploaded['revision_id']))).replace('DOC_ID',repr(uploaded['document_id'])))
    assert request(metadata_path)[1][0]['value']=='2.0000'
    status,values,_=request(metadata_path+'/adopt-candidate','POST',{'expected_document_version':9,
        'extracted_metadata_id':'metadata-smoke-candidate','field_definition_id':field['id']},csrf)
    assert status==200 and values[0]['value']=='10.0000' and values[0]['origin']=='extracted'
    docker('restart',name)
    port=docker('port',name,'8000/tcp').split(':')[-1]
    base='http://127.0.0.1:'+port
    ready()
    assert request(metadata_path)[1][0]['source_parse_run_id']=='metadata-smoke-run'
    assert request(document_path)[1]['document_version']==10
    for operation,version in [('trash',10),('restore',11)]:
        status,batch_restore,_=request('/api/v1/documents/batch','POST',{'space_id':space_id,
            'document_ids':[uploaded['document_id']],'selection_mode':'explicit',
            'expected_versions':{uploaded['document_id']:version},'operation':operation,'payload':{}},csrf)
        assert status==202
        assert json.loads(docker('exec',name,'python','-m','juanzhan.worker','--once'))=={'job_id':batch_restore['job_id'],'status':'completed'}
        assert request('/api/v1/jobs/'+batch_restore['job_id'])[1]['result']['succeeded']==1
    assert request(document_path)[1]['deleted_at'] is None
    assert request(document_path)[1]['document_version']==12
    assert request(metadata_path)[1][0]['value']=='10.0000'
    assert any(s['id'] == space_id for s in request('/api/v1/spaces')[1])
    assert request('/api/v1/document-types?space_id='+space_id)[1][0]['id'] == catalog_type['id']
    assert request('/api/v1/document-types/'+catalog_type['id'], 'PATCH', {'is_active':False}, csrf)[0] == 200
    assert request('/api/v1/tags/'+catalog_tag['id'], 'DELETE', csrf=csrf)[0] == 204
    assert request('/api/v1/folders/'+catalog_folder['id']+'/delete', 'POST', {'mode':'only_if_empty'}, csrf)[0] == 204
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 200
    assert request('/api/v1/auth/tokens/' + token['id'], 'DELETE', csrf=csrf)[0] == 204
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 401
    assert request('/api/v1/auth/logout', 'POST', csrf=csrf)[0] == 204
    assert request('/api/v1/auth/tokens')[0] == 401
    print('PASS: container CLI setup, HTTP login/CSRF/token/revoke/logout, restart persistence, managed object/staging recovery, catalog CRUD, document lifecycle, durable jobs/worker/retry, multipart upload/duplicate/persistence, document HTTP management/subtree trash/restore, batch snapshot/partial results/guarded undo, field definitions/template disable/persistence, typed metadata/filing/candidate adoption/persistence, durable batch trash/restore')
finally:
    if started:
        docker('rm', '-f', name)
    if created:
        docker('volume', 'rm', volume)
