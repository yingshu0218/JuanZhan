"""Six real formats: disposable Archive upload -> Converter -> validated blocks/artifacts.

No production mounts or password changes. Converter gets tmpfs, never Archive's volume.
"""
import json
import sys
import os
from pathlib import Path
import secrets
import subprocess
import urllib.error
import urllib.request
import uuid
import time
import tempfile
import hashlib


def docker(*args, input=None):
    completed=subprocess.run(['docker',*args],input=input,text=True,capture_output=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr)
    return completed.stdout.strip()


def request(base,path,*,body=None,cookie='',csrf='',content_type='application/json'):
    req=urllib.request.Request(base+path,data=body,headers={'Cookie':cookie,'X-CSRF-Token':csrf,'Content-Type':content_type})
    try:
        response=urllib.request.urlopen(req,timeout=10)
    except urllib.error.HTTPError as error:
        response=error
    with response:
        return response.status,json.load(response),response.headers


prefix='juanzhan-formats-smoke-'+uuid.uuid4().hex[:12]
network=prefix+'-net'
archive=prefix+'-archive'
converter=prefix+'-converter'
volume=prefix+'-data'
token=secrets.token_urlsafe(32)
password=secrets.token_urlsafe(32)
# Secret values are passed over stdin, never tool output or docker command arguments.
environment=os.environ.copy()
environment['CONVERTER_SERVICE_TOKEN']=token

def run_with_token(*args):
    result=subprocess.run(['docker',*args],env=environment,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


external_mode='--external' in sys.argv
if external_mode and '--persist' not in sys.argv:raise SystemExit('--external requires --persist')
source_fixture=tempfile.TemporaryDirectory(prefix='juanzhan-parse-source-') if external_mode else None
mount_args=[]
if source_fixture:
    Path(source_fixture.name).chmod(0o755)
    mount_args=['--mount',f'type=bind,source={source_fixture.name},target=/fixture,readonly',
                '-e','JUANZHAN_SOURCE_MOUNTS={"fixture":"/fixture"}']
try:
    docker('network','create',network)
    docker('volume','create',volume)
    run_with_token('run','-d','--name',converter,'--network',network,'--network-alias','converter',
           '--tmpfs','/tmp:rw,size=128m,mode=1777','-e','CONVERTER_SERVICE_TOKEN',
           'juanzhan-foundation:dev','python','-m','uvicorn','juanzhan.converter:app','--host','0.0.0.0','--port','8000')
    run_with_token('run','-d','--name',archive,'--network',network,'-p','127.0.0.1::8000',
           '--mount',f'type=volume,source={volume},target=/data','-e','JUANZHAN_DATA_DIR=/data',
           '-e','JUANZHAN_COOKIE_SECURE=false','-e','CONVERTER_SERVICE_TOKEN','-e','CONVERTER_URL=http://converter:8000',*mount_args,
           'juanzhan-foundation:dev')
    base='http://127.0.0.1:'+docker('port',archive,'8000/tcp').split(':')[-1]
    for _ in range(60):
        try:
            if request(base,'/healthz')[0]==200:
                break
        except OSError:
            pass
        time.sleep(.2)
    else:
        raise AssertionError('Archive fixture did not start')
    docker('exec','-i',archive,'python','-m','juanzhan.admin','set-password','--stdin',input=password+'\n')
    _,session,headers=request(base,'/api/v1/auth/session')
    cookie=headers['Set-Cookie'].split(';')[0]
    status,session,headers=request(base,'/api/v1/auth/login',body=json.dumps({'username':'admin','password':password}).encode(),cookie=cookie,csrf=session['csrf_token'])
    assert status==200
    cookie=headers['Set-Cookie'].split(';')[0]
    status,space,_=request(base,'/api/v1/spaces',body=json.dumps({'name':'Converter real fixture'}).encode(),cookie=cookie,csrf=session['csrf_token'])
    assert status==201
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
    from format_samples import samples, raster_sample
    ocr_mode='--ocr' in sys.argv
    fixtures=samples() if not ocr_mode else {
        'png':('image/png',raster_sample(text='真实中文档案 测试识别')),
        'jpg':('image/jpeg',raster_sample('JPEG')),
        'tiff':('image/tiff',raster_sample('TIFF')),
        'pdf':('application/pdf',raster_sample('PDF'))}
    for kind,(mime,content) in fixtures.items():
        if external_mode:
            path=Path(source_fixture.name)/('original.'+kind)
            path.write_bytes(content);path.chmod(0o644)
            continue
        boundary='fixture-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space["id"]}\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="original.{kind}"\r\nContent-Type: {mime}\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        status,uploaded,_=request(base,'/api/v1/documents/upload',body=body,cookie=cookie,csrf=session['csrf_token'],content_type='multipart/form-data; boundary='+boundary)
        assert status==201
    if external_mode:
        expected_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(source_fixture.name).iterdir()}
        status,source,_=request(base,'/api/v1/sources',body=json.dumps({'space_id':space['id'],'name':'Read only parse fixture','kind':'external',
            'root_alias':'fixture','initial_import_policy':'flat'}).encode(),cookie=cookie,csrf=session['csrf_token'])
        assert status==201,source
        status,scan,_=request(base,'/api/v1/sources/'+source['id']+'/scan',body=b'{"mode":"initial"}',cookie=cookie,csrf=session['csrf_token'])
        assert status==202,scan
        outcome=json.loads(docker('exec',archive,'python','-m','juanzhan.worker','--once'))
        assert outcome['job_id']==scan['job_id'] and outcome['status']=='completed',outcome
    persist_mode='--persist' in sys.argv
    if persist_mode:
        if ocr_mode:
            code='''
import json,uuid
from juanzhan.config import Settings
from juanzhan.jobs import JobQueue,JobSpec
settings=Settings.from_env();queue=JobQueue(settings)
with queue.write() as db:
 rows=db.execute("SELECT id,target_id,payload_json FROM jobs WHERE kind='parse' AND status='queued'").fetchall()
 for id,document,payload in rows:
  db.execute("UPDATE jobs SET status='cancelled' WHERE id=?",(id,))
  queue.enqueue(JobSpec(kind='ocr',target_type='document',target_id=document,
    payload={**json.loads(payload),'ocr_languages':'chi_sim,eng'},idempotency_key='fixture-ocr:'+id),db=db)
'''
            docker('exec','-i',archive,'python','-',input=code)
        for _ in fixtures:
            outcome=json.loads(docker('exec',archive,'python','-m','juanzhan.worker','--once'))
            assert outcome['status']=='completed',outcome
    # Executes the real Archive-side client inside Archive; it has no Converter spool mount.
    code='OCR_MODE='+repr(ocr_mode)+'\nPERSIST_MODE='+repr(persist_mode)+'\n'+'''
import hashlib,uuid,time
from juanzhan.config import Settings
from juanzhan.converter_client import ConverterClient,ConverterClientError
from juanzhan.conversion_models import Options
from juanzhan.conversion_formats import SUPPORTED
from juanzhan.database import connect
from juanzhan.storage import ManagedStore
settings=Settings.from_env();client=ConverterClient.from_env()
if PERSIST_MODE:
 import json
 with connect(settings.database) as db:
  documents=db.execute('SELECT d.id,d.current_revision_id,d.current_parse_run_id,p.status,p.text_available,p.ocr_used,d.document_version FROM documents d JOIN parse_runs p ON p.id=d.current_parse_run_id').fetchall()
  assert len(documents)==(4 if OCR_MODE else 6)
  assert db.execute('SELECT count(*) FROM parse_runs').fetchone()[0]==len(documents)
  assert not db.execute('PRAGMA foreign_key_check').fetchall()
  for document,revision,run,status,text,ocr,version in documents:
   assert status=='completed' and text and bool(ocr)==OCR_MODE and version==1
   assert db.execute('SELECT count(*) FROM content_blocks WHERE parse_run_id=?',(run,)).fetchone()[0]>0
   assert db.execute('SELECT revision_id FROM parse_runs WHERE id=?',(run,)).fetchone()[0]==revision
  assets=db.execute('SELECT storage_key,sha256,asset_kind FROM derived_assets').fetchall()
  assert len(assets)>=3*len(documents)
 store=ManagedStore(settings.data_dir/'derived')
 for key,sha,kind in assets:
  with store.open(key) as file:
   data=file.read();assert hashlib.sha256(data).hexdigest()==sha
   if kind=='json':assert json.loads(data)['status']=='completed'
 print('PASS: automatic persistent parse runs/blocks/candidates/assets/current pointers and verified files; OCR='+str(OCR_MODE))
 raise SystemExit(0)

for _ in range(60):
 try:
  capabilities=client.capabilities()
  break
 except ConverterClientError:time.sleep(.1)
else:raise AssertionError('Converter fixture not ready')
assert capabilities['supported_input_types']==SUPPORTED+['image/png','image/jpeg','image/tiff']
with connect(settings.database) as db:
 rows=db.execute('SELECT r.id,r.sha256,o.storage_key,r.mime_type,d.id,d.title,d.current_parse_run_id FROM file_revisions r JOIN managed_objects o ON o.id=r.managed_object_id JOIN documents d ON d.id=r.document_id').fetchall()
 assert len(rows)==(4 if OCR_MODE else 6) and db.execute('SELECT count(*) FROM parse_runs').fetchone()[0]==0
store=ManagedStore(settings.data_dir/'managed')
for revision,sha,key,mime,document,title,current in rows:
 with store.open(key) as file:original=file.read()
 options=Options(file_revision_id=revision,parse_run_id=uuid.uuid4().hex,declared_mime=mime,generate_preview=OCR_MODE,ocr_enabled=OCR_MODE,ocr_languages='chi_sim,eng' if OCR_MODE else '')
 with store.open(key) as file:job=client.submit(file,options)
 assert client.wait(job['job_id'])['status']=='completed'
 result=client.result(job['job_id'],file_revision_id=revision,parse_run_id=options.parse_run_id)
 assert result['status']=='completed' and result['source_mime']==mime and result['extraction']['text_available']
 if OCR_MODE:
  text=''.join(block['text'] for block in result['blocks']).replace(' ','')
  assert result['extraction']['ocr_used'] and result['page_count']==1
  assert ('真实中文档案' in text) if mime=='image/png' else ('scannedarchive2026' in text)
  assert any(block['confidence'] is not None for block in result['blocks'])
  assert len([a for a in result['artifacts'] if a['kind']=='thumbnail'])==1
 else:
  assert all(block['confidence'] is None for block in result['blocks'])
  if mime=='application/pdf':
   assert result['page_count']==2 and {block['locator']['page'] for block in result['blocks']}=={1,2}
  else:assert result['page_count'] is None and all('page' not in block['locator'] for block in result['blocks'])
  if mime=='application/epub+zip':assert [block['locator']['spine_index'] for block in result['blocks']]==[0,0,1,1]
 for asset in result['artifacts']:
  with client.artifact(asset) as file:assert hashlib.sha256(file.read()).hexdigest()==asset['sha256']
 with store.open(key) as file:assert hashlib.sha256(file.read()).hexdigest()==sha
 client.delete(job['job_id'])
 with connect(settings.database) as db:assert db.execute('SELECT title,current_parse_run_id FROM documents WHERE id=?',(document,)).fetchone()==(title,current)
 print('PASS: real '+mime+' upload, normalized blocks, provenance/locators, verified text/Markdown and cleanup')
with connect(settings.database) as db:
 assert db.execute('SELECT count(*) FROM parse_runs').fetchone()[0]==0 and not db.execute('PRAGMA foreign_key_check').fetchall()
print('PASS: all original objects and Archive business parse state preserved; OCR mode='+str(OCR_MODE))
'''
    print(docker('exec','-i',archive,'python','-',input=code))
    if external_mode:
        # Host-side fault injection changes a read-only source after capture; Archive must reject it.
        path=sorted(Path(source_fixture.name).iterdir())[0];original=path.read_bytes()
        path.write_bytes(bytes([original[0]^1])+original[1:])
        try:
            code='FILENAME='+repr(path.name)+'\n'+'''
import json,uuid
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.jobs import JobQueue,JobSpec
settings=Settings.from_env()
with connect(settings.database) as db:
 document,revision,current=db.execute('SELECT d.id,r.id,d.current_parse_run_id FROM documents d JOIN file_revisions r ON r.id=d.current_revision_id WHERE r.original_filename=?',(FILENAME,)).fetchone()
job=JobQueue(settings).enqueue(JobSpec(kind='parse',target_type='document',target_id=document,payload={'revision_id':revision},idempotency_key='changed-source:'+uuid.uuid4().hex))
print(json.dumps({'job_id':job['id'],'document_id':document,'current':current}))
'''
            retry=json.loads(docker('exec','-i',archive,'python','-',input=code))
            outcome=json.loads(docker('exec',archive,'python','-m','juanzhan.worker','--once'))
            assert outcome['job_id']==retry['job_id'] and outcome['status']=='failed'
            _,failed,_=request(base,'/api/v1/jobs/'+retry['job_id'],cookie=cookie)
            assert failed['error']['code']=='SOURCE_REVISION_CHANGED'
            _,shown,_=request(base,'/api/v1/documents/'+retry['document_id'],cookie=cookie)
            assert shown['current_parse_run_id']==retry['current'] and shown['content_stale']
        finally:path.write_bytes(original)
        assert expected_hashes=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(source_fixture.name).iterdir()}
        print('PASS: kernel read-only source import/persist; changed bytes rejected with old content retained; fixture restored')
finally:
    for name in (archive,converter):
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if source_fixture:source_fixture.cleanup()
    for args in (('volume','rm',volume),('network','rm',network)):
        subprocess.run(['docker',*args],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
