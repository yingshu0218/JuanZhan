"""Disposable unindex/purge/managed GC over real RO mounts, HTTP and worker."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


def docker(*args, input=None):
    result=subprocess.run(['docker',*args],input=input,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:raise RuntimeError(result.stderr)
    return result.stdout.strip()


name='juanzhan-maintenance-smoke-'+uuid.uuid4().hex[:12]
volume=name+'-data'
password=secrets.token_urlsafe(32)
started=created=False
cookie=csrf=base=''


def request(path,body=None,*,authenticated=True,with_csrf=True,method=None):
    headers={'Content-Type':'application/json'}
    if authenticated:headers['Cookie']=cookie
    if with_csrf:headers['X-CSRF-Token']=csrf
    req=urllib.request.Request(base+path,headers=headers,method=method,
        data=json.dumps(body).encode() if body is not None else None)
    try:response=urllib.request.urlopen(req,timeout=10)
    except urllib.error.HTTPError as exc:response=exc
    with response:
        payload=response.read()
        return response.status,json.loads(payload) if payload else None,response.headers


def ready():
    for _ in range(40):
        try:
            if request('/healthz')[0]==200:return
        except (OSError,urllib.error.URLError):pass
        time.sleep(0.2)
    raise AssertionError('Initial import fixture did not become ready')


def finish(id):
    for _ in range(30):
        job=request('/api/v1/jobs/'+id)[1]
        if job['status'] in ('completed','failed'):return job
        docker('exec',name,'python','-m','juanzhan.worker','--once')
    raise AssertionError('Initial import did not reach a terminal state')


def upload(space,content,policy='reject'):
    boundary='upload-'+secrets.token_hex(12)
    body=b''
    for key,value in [('space_id',space),('duplicate_policy',policy)]:
        body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n').encode()
    body+=('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="managed.txt"\r\nContent-Type: text/plain\r\n\r\n').encode()+content+('\r\n--'+boundary+'--\r\n').encode()
    req=urllib.request.Request(base+'/api/v1/documents/upload',data=body,headers={'Cookie':cookie,'X-CSRF-Token':csrf,'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)['document_id']


with tempfile.TemporaryDirectory(prefix='juanzhan-maintenance-fixture-') as temporary:
    root=Path(temporary);root.chmod(0o755)
    original=b'external original must survive'
    (root/'a.txt').write_bytes(original);(root/'a.txt').chmod(0o644)
    try:
        docker('volume','create',volume);created=True
        docker('run','-d','--name',name,'-p','127.0.0.1::8000',
            '--mount',f'type=bind,source={root},target=/sources/docs,readonly',
            '--mount',f'type=volume,source={volume},target=/data',
            '-e','JUANZHAN_DATA_DIR=/data','-e','JUANZHAN_SOURCE_MOUNTS={"docs":"/sources/docs"}',
            'juanzhan-foundation:dev')
        started=True;base='http://127.0.0.1:'+docker('port',name,'8000/tcp').split(':')[-1];ready()
        docker('exec','-i',name,'python','-m','juanzhan.admin','set-password','--stdin',input=password+'\n')
        _,session,headers=request('/api/v1/auth/session');cookie=headers['Set-Cookie'].split(';')[0];csrf=session['csrf_token']
        status,session,headers=request('/api/v1/auth/login',{'username':'admin','password':password})
        assert status==200;cookie=headers['Set-Cookie'].split(';')[0];csrf=session['csrf_token']
        space=request('/api/v1/spaces',{'name':'Maintenance'})[1]['id']
        source=request('/api/v1/sources',{'space_id':space,'name':'Readonly','kind':'external','root_alias':'docs','initial_import_policy':'flat'})[1]['id']
        path='/api/v1/sources/'+source
        assert finish(request(path+'/scan',{'mode':'initial'})[1]['job_id'])['status']=='completed'
        entry=request(path+'/entries')[1]['items'][0];external=entry['document_id']
        body={'source_entry_id':entry['id'],'expected_document_version':1,'reason':'Unindex fixture'}
        assert request(path+'/exclude-entry',body,with_csrf=False)[0]==403
        queued=request(path+'/exclude-entry',body)[1]['job_id']
        assert request(path+'/exclude-entry',body)[1]['job_id']==queued
        result=finish(queued);assert result['status']=='completed' and result['result']['external_file_deleted'] is False
        assert request('/api/v1/documents/'+external)[1]['deleted_at']
        rule=request(path+'/exclusions')[1][0]
        preview=finish(request(path+'/preview-scan',{})[1]['job_id'])
        assert preview['result']['estimated_files']==0 and preview['result']['ignored_files']==1
        assert finish(request(path+'/scan',{'mode':'incremental'})[1]['job_id'])['result']['imported_files']==0
        purge_body={'confirm_document_id':external,'expected_document_version':2}
        assert request('/api/v1/documents/'+external+'/purge',purge_body,with_csrf=False)[0]==403
        purge_id=request('/api/v1/documents/'+external+'/purge',purge_body)[1]['job_id']
        assert finish(purge_id)['status']=='completed'
        assert request('/api/v1/documents/'+external)[0]==404 and request(path+'/entries')[1]['total']==0
        assert finish(request(path+'/scan',{'mode':'incremental'})[1]['job_id'])['result']['imported_files']==0
        assert request('/api/v1/documents/'+external+'/purge',purge_body)[1]['job_id']==purge_id
        assert request(path+'/exclusions/'+rule['id'],method='DELETE')[0]==204
        assert finish(request(path+'/scan',{'mode':'incremental'})[1]['job_id'])['result']['imported_files']==1
        assert request(path+'/entries')[1]['items'][0]['document_id']!=external
        assert (root/'a.txt').read_bytes()==original

        def trash(id):
            version=request('/api/v1/documents/'+id)[1]['document_version']
            assert request('/api/v1/documents/'+id+'/trash',{'expected_document_version':version})[0]==200
            return version+1
        def remove(id,version):
            job=request('/api/v1/documents/'+id+'/purge',{'confirm_document_id':id,'expected_document_version':version})[1]['job_id']
            assert finish(job)['status']=='completed'
        def gc():
            job=json.loads(docker('exec',name,'python','-m','juanzhan.maintenance','gc'))['job_id']
            result=finish(job);assert result['status']=='completed',result
            return result['result']
        a=upload(space,b'shared original');b=upload(space,b'shared original','keep_separate')
        remove(a,trash(a));assert gc()['deleted_objects']==0
        assert request('/api/v1/documents/'+b)[1]['availability_status']=='available'
        remove(b,trash(b));assert gc()['deleted_objects']==0
        # Advance only disposable fixture ledger eligibility, never production retention config.
        docker('exec','-i',name,'python','-',input='''
import time
from juanzhan.config import Settings
from juanzhan.database import connect
with connect(Settings.from_env().database) as db:
    db.execute('UPDATE managed_gc_candidates SET eligible_after=?',(time.time()-1,));db.commit()
''')
        assert gc()['deleted_objects']==1
        c=upload(space,b'restored protected')
        version=trash(c)
        pending=request('/api/v1/documents/'+c+'/purge',{'confirm_document_id':c,'expected_document_version':version})[1]['job_id']
        assert request('/api/v1/documents/'+c+'/restore',{'expected_document_version':version})[0]==200
        failed=finish(pending)
        assert failed['status']=='failed' and failed['error']['code']=='VERSION_CONFLICT'
        assert request('/api/v1/documents/'+c)[1]['availability_status']=='available'
        # A symlink with a syntactically valid managed key is ignored, never followed.
        docker('exec','-i',name,'python','-',input='''
from juanzhan.config import Settings
s=Settings.from_env()
p=s.data_dir/'managed'/'sha256'/'aa';p.mkdir(exist_ok=True)
(p/('a'*64+'-30')).symlink_to('/sources/docs/a.txt')
''')
        assert gc()['ignored_files']>=1
        assert (root/'a.txt').read_bytes()==original
        docker('restart',name);base='http://127.0.0.1:'+docker('port',name,'8000/tcp').split(':')[-1];ready()
        assert request('/api/v1/documents/'+external+'/purge',purge_body)[1]['job_id']==purge_id
        assert request('/api/v1/documents/'+c)[1]['deleted_at'] is None
        docker('exec','-i',name,'python','-',input='''
from juanzhan.config import Settings
from juanzhan.database import connect
with connect(Settings.from_env().database) as db:
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('SELECT count(*) FROM document_purge_receipts').fetchone()[0]==3
    assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==1
    assert db.execute('SELECT count(*) FROM source_exclusion_intents').fetchone()[0]==0
''')
        print('PASS: real RO unindex/exclusion/preview/incremental, external purge never removes bytes, rule removal permits rediscovery, shared managed refs +24h grace, GC actual unlink, queued purge vs restore guard, symlink rejection, durable receipts/restart and FK consistency')
    finally:
        if started:docker('rm','-f',name)
        if created:docker('volume','rm',volume)
