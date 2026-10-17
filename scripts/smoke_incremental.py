"""Disposable real first imports over RO bind mounts, HTTP, SQLite and worker."""
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


name='juanzhan-incremental-smoke-'+uuid.uuid4().hex[:12]
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
    raise AssertionError('Incremental scan fixture did not become ready')


def finish(id):
    for _ in range(30):
        job=request('/api/v1/jobs/'+id)[1]
        if job['status'] in ('completed','failed'):return job
        docker('exec',name,'python','-m','juanzhan.worker','--once')
    raise AssertionError('Incremental scan did not reach a terminal state')


with tempfile.TemporaryDirectory(prefix='juanzhan-incremental-fixture-') as temporary:
    root=Path(temporary);root.chmod(0o755)
    files={'original/a.txt':b'old!','move.txt':b'unique move','gone.txt':b'gone',
           'dup1.txt':b'duplicate','dup2.txt':b'duplicate'}
    for relative,data in files.items():
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o644)
    for directory,_,_ in os.walk(root):Path(directory).chmod(0o755)
    try:
        docker('volume','create',volume);created=True
        docker('run','-d','--name',name,'-p','127.0.0.1::8000',
            '--mount',f'type=bind,source={root},target=/sources/docs,readonly',
            '--mount',f'type=volume,source={volume},target=/data',
            '--tmpfs','/sources/empty:ro,mode=0755',
            '-e','JUANZHAN_DATA_DIR=/data','-e','JUANZHAN_SOURCE_MOUNTS={"docs":"/sources/docs"}',
            'juanzhan-foundation:dev')
        started=True
        base='http://127.0.0.1:'+docker('port',name,'8000/tcp').split(':')[-1];ready()
        docker('exec','-i',name,'python','-m','juanzhan.admin','set-password','--stdin',input=password+'\n')
        _,session,headers=request('/api/v1/auth/session');cookie=headers['Set-Cookie'].split(';')[0];csrf=session['csrf_token']
        status,session,headers=request('/api/v1/auth/login',{'username':'admin','password':password})
        assert status==200;cookie=headers['Set-Cookie'].split(';')[0];csrf=session['csrf_token']
        space=request('/api/v1/spaces',{'name':'Incremental'})[1]['id']
        target=request('/api/v1/folders',{'space_id':space,'name':'Incoming'})[1]['id']
        status,source,_=request('/api/v1/sources',{'space_id':space,'name':'Docs','kind':'external','root_alias':'docs',
            'initial_import_policy':'tree','initial_triage_status':'filed','new_file_target_folder_id':target})
        assert status==201
        path='/api/v1/sources/'+source['id']
        assert request(path+'/scan',{'mode':'incremental'})[0]==409
        first=request(path+'/scan',{'mode':'initial'})[1]['job_id'];assert finish(first)['status']=='completed'
        initial_time=request(path)[1]['initial_import_completed_at']

        def inventory():return request(path+'/entries',method='GET')[1]['items']
        def by_path():return {e['relative_path']:e for e in inventory()}
        def document(id):return request('/api/v1/documents/'+id)[1]
        def scan_now():
            status,job,_=request(path+'/scan',{'mode':'incremental'})
            assert status==202
            assert request(path+'/scan',{'mode':'incremental'})[1]['job_id']==job['job_id']
            assert request(path+'/preview-scan',{})[0]==409
            result=finish(job['job_id']);assert result['status']=='completed',result
            return job['job_id'],result['result']

        original=by_path();a=original['original/a.txt']['document_id'];moved=original['move.txt'];gone=original['gone.txt']['document_id']
        tag=request('/api/v1/tags',{'space_id':space,'name':'Manual'})[1]['id']
        assert request('/api/v1/field-definitions',{'space_id':space,'key':'note','type':'text','label':'Note'})[0]==201
        assert request('/api/v1/documents/'+a,{'expected_document_version':1,'title':'Human title','folder_id':None,'tags_add':[tag],'is_favorite':True},method='PATCH')[0]==200
        assert request('/api/v1/documents/'+a+'/metadata',{'expected_document_version':2,'values':{'note':'Keep confirmed'},'confirm':True},method='PATCH')[0]==200
        captured=document(a)['current_revision_id']
        # A successful old parse is a real DB fixture, not a fake converter claim.
        docker('exec','-i',name,'python','-',input=f'''
from juanzhan.config import Settings
from juanzhan.database import connect
with connect(Settings.from_env().database) as db:
    db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at) VALUES ('old',?,?,'fixture','1','1.0','completed','2026-10-17')",({a!r},{captured!r}))
    db.execute("UPDATE documents SET current_parse_run_id='old' WHERE id=?",({a!r},));db.commit()
''')
        old_stat=(root/'original/a.txt').stat()
        (root/'original/a.txt').write_bytes(b'new!')
        os.utime(root/'original/a.txt',ns=(old_stat.st_atime_ns,old_stat.st_mtime_ns))
        (root/'new/deep').mkdir(parents=True)
        (root/'new').chmod(0o755);(root/'new/deep').chmod(0o755)
        (root/'new/deep/new.txt').write_bytes(b'new incoming');(root/'new/deep/new.txt').chmod(0o644)
        (root/'move.txt').rename(root/'moved.txt')
        retained=(root/'gone.txt').read_bytes();(root/'gone.txt').unlink()
        # Force ambiguous hash-only matching: remove two old inodes, create a fresh one.
        (root/'dup-new.txt').write_bytes(b'duplicate');(root/'dup-new.txt').chmod(0o644)
        (root/'dup1.txt').unlink();(root/'dup2.txt').unlink()
        job,result=scan_now()
        assert result['imported_files']==1 and result['updated_files']==1 and result['reassociated_files']==1
        assert result['suspected_missing']==1 and result['missing']==0 and result['needs_match']==3
        current=by_path();assert current['moved.txt']['id']==moved['id'] and current['moved.txt']['document_id']==moved['document_id']
        assert current['dup-new.txt']['document_id'] is None and current['dup-new.txt']['status']=='needs_match'
        actual=document(a)
        assert actual['current_revision_id']!=captured and actual['current_parse_run_id']=='old' and actual['content_stale']
        assert actual['title']=='Human title' and actual['folder_id'] is None and actual['tag_ids']==[tag] and actual['is_favorite']
        assert request('/api/v1/documents/'+a+'/metadata')[1][0]['value']=='Keep confirmed'
        added=document(current['new/deep/new.txt']['document_id'])
        assert added['triage_status']=='needs_review' and added['folder_id']==target
        assert len(request('/api/v1/folders?space_id='+space)[1])==2  # Incoming + original; no new/deep mirror.
        second,again=scan_now();assert again['missing']==1 and by_path()['gone.txt']['status']=='missing'
        (root/'gone.txt').write_bytes(retained);(root/'gone.txt').chmod(0o644)
        _,recovered=scan_now();assert recovered['recovered_files']==1 and by_path()['gone.txt']['document_id']==gone
        assert by_path()['gone.txt']['status']=='available'
        # One missing observation, then an unavailable worker root, must not confirm missing.
        (root/'gone.txt').unlink();scan_now()
        pending=request(path+'/scan',{'mode':'incremental'})[1]['job_id']
        # Drain unrelated parse jobs, without letting the target use the healthy mount.
        for _ in range(30):
            raw=docker('exec','-e','JUANZHAN_SOURCE_MOUNTS={"docs":"/sources/absent"}',name,'python','-m','juanzhan.worker','--once')
            outcome=json.loads(raw)
            if outcome and outcome['job_id']==pending:break
        failed=request('/api/v1/jobs/'+pending)[1]
        assert failed['error']['code']=='SOURCE_OFFLINE' and by_path()['gone.txt']['status']=='suspected_missing'
        assert request('/api/v1/jobs/'+pending+'/retry',{})[0]==202
        assert finish(pending)['result']['suspected_missing']==1
        _,confirmed=scan_now();assert confirmed['missing']==1
        # An actual read-only empty root with a different identity cannot mark inventory missing.
        before=inventory();wrong=request(path+'/scan',{'mode':'incremental'})[1]['job_id']
        for _ in range(30):
            outcome=json.loads(docker('exec','-e','JUANZHAN_SOURCE_MOUNTS={"docs":"/sources/empty"}',name,'python','-m','juanzhan.worker','--once'))
            if outcome and outcome['job_id']==wrong:break
        assert request('/api/v1/jobs/'+wrong)[1]['error']['code']=='SOURCE_ROOT_CHANGED'
        assert inventory()==before
        _,last=scan_now();assert last['imported_files']==0 and last['updated_files']==0
        assert request(path)[1]['initial_import_completed_at']==initial_time
        version=document(a)['document_version']
        docker('restart',name);base='http://127.0.0.1:'+docker('port',name,'8000/tcp').split(':')[-1];ready()
        assert request('/api/v1/jobs/'+job)[1]['result']==result
        assert document(a)['document_version']==version and document(a)['title']=='Human title'
        _,after_restart=scan_now()
        assert after_restart['updated_files']==0 and after_restart['imported_files']==0
        assert after_restart['missing']==1 and after_restart['needs_match']==3
        docker('exec','-i',name,'python','-',input='''
import os
from juanzhan.config import Settings
from juanzhan.database import connect
s=Settings.from_env()
with connect(s.database) as db:
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==6
    assert db.execute('SELECT count(*) FROM source_entries').fetchone()[0]==7
    assert db.execute('SELECT count(*) FROM file_revisions').fetchone()[0]==7
    assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0
    assert db.execute('SELECT count(*) FROM source_root_baselines').fetchone()[0]==1
    assert db.execute("SELECT count(*) FROM source_entries WHERE status='needs_match'").fetchone()[0]==3
assert not any(files for _,_,files in os.walk(s.data_dir/'managed'/'sha256'))
''')
        assert (root/'original/a.txt').read_bytes()==b'new!' and (root/'moved.txt').read_bytes()==files['move.txt']
        print('PASS: real incremental hashing with unchanged size/mtime, new inbox target without tree mirror, stable rename IDs, ambiguity without document merge, two missing confirmations, recovery, offline reset, changed empty-root rejection, manual metadata/old parse preservation, no managed copy and restart durability')
    finally:
        if started:docker('rm','-f',name)
        if created:docker('volume','rm',volume)
