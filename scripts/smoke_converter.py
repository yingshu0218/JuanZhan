"""Disposable real Archive upload -> internal ConverterClient -> HTTP result/assets.

No production mounts or password changes. Converter gets tmpfs, never Archive's volume.
"""
import json
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


prefix='juanzhan-converter-smoke-'+uuid.uuid4().hex[:12]
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
    boundary='fixture-'+uuid.uuid4().hex
    content='真实容器转换原件。\r\n第二行\n'.encode()
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space["id"]}\r\n'
          f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="original.txt"\r\nContent-Type: text/plain\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
    status,uploaded,_=request(base,'/api/v1/documents/upload',body=body,cookie=cookie,csrf=session['csrf_token'],content_type='multipart/form-data; boundary='+boundary)
    assert status==201
    # Executes the real Archive-side client inside Archive; it has no Converter spool mount.
    code='''
from io import BytesIO
import hashlib,time,uuid
from juanzhan.config import Settings
from juanzhan.converter_client import ConverterClient,ConverterClientError
from juanzhan.conversion_models import Options
from juanzhan.database import connect
from juanzhan.storage import ManagedStore
settings=Settings.from_env()
client=ConverterClient.from_env()
for _ in range(60):
    try:
        caps=client.capabilities()
        break
    except ConverterClientError:time.sleep(.1)
else:raise AssertionError('Converter unavailable')
from juanzhan.conversion_formats import SUPPORTED
assert caps['supported_input_types']==SUPPORTED and not caps['ocr_available']
with connect(settings.database) as db:
    row=db.execute('SELECT r.id,r.sha256,o.storage_key,d.id,d.title,d.current_parse_run_id FROM file_revisions r JOIN managed_objects o ON o.id=r.managed_object_id JOIN documents d ON d.id=r.document_id').fetchone()
    assert db.execute('SELECT count(*) FROM parse_runs').fetchone()[0]==0
store=ManagedStore(settings.data_dir/'managed')
options=Options(file_revision_id=row[0],parse_run_id=uuid.uuid4().hex,declared_mime='text/plain',generate_preview=False)
with store.open(row[2]) as file:
    original=file.read()
with store.open(row[2]) as file:
    job=client.submit(file,options)
assert client.wait(job['job_id'])['status']=='completed'
result=client.result(job['job_id'],file_revision_id=row[0],parse_run_id=options.parse_run_id)
assert result['status']=='completed' and ''.join(block['text'] for block in result['blocks'])==original.decode()
with client.artifact(result['artifacts'][0]) as file:assert file.read()==original
with store.open(row[2]) as file:assert hashlib.sha256(file.read()).hexdigest()==row[1]
# Restarting just the HTTP process on the same spool is tested by the Python suite;
# Docker restarts replace tmpfs and may expire IDs, which the protocol must tolerate.
client.delete(job['job_id'])
try:client.job(job['job_id'])
except ConverterClientError as error:assert error.status==404
else:raise AssertionError('Deleted task remains accessible')
unsupported_options=Options(file_revision_id='unsupported',parse_run_id=uuid.uuid4().hex)
unsupported=client.submit(BytesIO(b'\\x00binary unsupported'),unsupported_options)
assert client.wait(unsupported['job_id'])['status']=='completed'
result=client.result(unsupported['job_id'],file_revision_id='unsupported',parse_run_id=unsupported_options.parse_run_id)
assert result['status']=='unsupported' and result['blocks']==result['artifacts']==[]
assert client.job(unsupported['job_id'])['warnings']==['PREVIEW_NOT_AVAILABLE','UNSUPPORTED_INPUT_TYPE']
client.delete(unsupported['job_id'])
with connect(settings.database) as db:
    assert db.execute('SELECT current_parse_run_id,title FROM documents WHERE id=?',(row[3],)).fetchone()==(row[5],row[4])
    assert db.execute('SELECT count(*) FROM parse_runs').fetchone()[0]==0
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
print('PASS: real Archive SQLite/upload/original -> Converter multipart/job/result/verified artifact/delete; no business parse persistence')
'''
    print(docker('exec','-i',archive,'python','-',input=code))
finally:
    for name in (archive,converter):
        subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for args in (('volume','rm',volume),('network','rm',network)):
        subprocess.run(['docker',*args],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
