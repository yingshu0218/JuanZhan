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


try:
    docker('network','create',network)
    docker('volume','create',volume)
    run_with_token('run','-d','--name',converter,'--network',network,'--network-alias','converter',
           '--tmpfs','/tmp:rw,size=128m,mode=1777','-e','CONVERTER_SERVICE_TOKEN',
           'juanzhan-foundation:dev','python','-m','uvicorn','juanzhan.converter:app','--host','0.0.0.0','--port','8000')
    run_with_token('run','-d','--name',archive,'--network',network,'-p','127.0.0.1::8000',
           '--mount',f'type=volume,source={volume},target=/data','-e','JUANZHAN_DATA_DIR=/data',
           '-e','JUANZHAN_COOKIE_SECURE=false','-e','CONVERTER_SERVICE_TOKEN','-e','CONVERTER_URL=http://converter:8000',
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
        boundary='fixture-'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space["id"]}\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="original.{kind}"\r\nContent-Type: {mime}\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        status,uploaded,_=request(base,'/api/v1/documents/upload',body=body,cookie=cookie,csrf=session['csrf_token'],content_type='multipart/form-data; boundary='+boundary)
        assert status==201
    # Executes the real Archive-side client inside Archive; it has no Converter spool mount.
    code='OCR_MODE='+repr(ocr_mode)+'\n'+'''
import hashlib,uuid,time
from juanzhan.config import Settings
from juanzhan.converter_client import ConverterClient,ConverterClientError
from juanzhan.conversion_models import Options
from juanzhan.conversion_formats import SUPPORTED
from juanzhan.database import connect
from juanzhan.storage import ManagedStore
settings=Settings.from_env();client=ConverterClient.from_env()
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
finally:
    for name in (archive,converter):
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for args in (('volume','rm',volume),('network','rm',network)):
        subprocess.run(['docker',*args],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
