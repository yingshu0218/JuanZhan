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


name='juanzhan-initial-smoke-'+uuid.uuid4().hex[:12]
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


with tempfile.TemporaryDirectory(prefix='juanzhan-initial-fixture-') as temporary:
    root=Path(temporary)
    root.chmod(0o755)
    payload=b'same source bytes\n'
    contents={
        'tree/root.txt':payload,'tree/资料/one.txt':payload,'tree/资料/empty.txt':b'',
        'tree/unknown.bin':b'ignored','flat/existing/a.txt':payload,
        'flat/root.pdf':b'%PDF-1.7\nmetadata fixture\n',
        'conflict/good/a.txt':b'good','conflict/Taken/b.txt':b'taken',
    }
    for relative,content in contents.items():
        path=root/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o644)
    (root/'tree/资料/空目录').mkdir()
    (root/'flat/empty').mkdir()
    (root/'tree/link.txt').symlink_to('root.txt')
    (root/'tree/out.txt').symlink_to('/etc/passwd')
    os.mkfifo(root/'tree/pipe')
    bulk=root/'bulk'
    bulk.mkdir()
    for index in range(1000):
        path=bulk/(str(index)+'.txt')
        path.write_bytes(b'x')
        path.chmod(0o644)
    for directory,_,_ in os.walk(root):Path(directory).chmod(0o755)
    expected={p:hashlib.sha256(data).hexdigest() for p,data in contents.items()}
    aliases={alias:'/sources/fixture/'+alias for alias in ('tree','flat','conflict','bulk')}
    try:
        docker('volume','create',volume)
        created=True
        docker('run','-d','--name',name,'-p','127.0.0.1::8000',
            '--mount',f'type=bind,source={root},target=/sources/fixture,readonly',
            '--mount',f'type=volume,source={volume},target=/data',
            '-e','JUANZHAN_DATA_DIR=/data','-e','JUANZHAN_SOURCE_MOUNTS='+json.dumps(aliases),
            'juanzhan-foundation:dev')
        started=True
        base='http://127.0.0.1:'+docker('port',name,'8000/tcp').split(':')[-1]
        ready()
        docker('exec','-i',name,'python','-m','juanzhan.admin','set-password','--stdin',input=password+'\n')
        _,session,headers=request('/api/v1/auth/session')
        cookie=headers['Set-Cookie'].split(';')[0]
        csrf=session['csrf_token']
        status,session,headers=request('/api/v1/auth/login',{'username':'admin','password':password})
        assert status==200
        cookie=headers['Set-Cookie'].split(';')[0]
        csrf=session['csrf_token']
        space=request('/api/v1/spaces',{'name':'First import'})[1]['id']

        def folder(name,parent=None):
            status,result,_=request('/api/v1/folders',{'space_id':space,'name':name,'parent_id':parent})
            assert status==201
            return result['id']

        def source(alias,policy,triage,target):
            status,result,_=request('/api/v1/sources',{'space_id':space,'name':alias,'kind':'external',
                'root_alias':alias,'initial_import_policy':policy,'initial_triage_status':triage,
                'initial_target_folder_id':target})
            assert status==201
            return '/api/v1/sources/'+result['id']

        tree_target=folder('Tree target')
        tree=source('tree','tree','needs_review',tree_target)
        assert request(tree+'/scan',{'mode':'initial'},with_csrf=False)[0]==403
        assert request(tree+'/scan',{'mode':'incremental'})[0]==501
        queued=request(tree+'/scan',{'mode':'initial'})[1]
        assert request(tree+'/scan',{'mode':'initial'})[1]['job_id']==queued['job_id']
        assert request(tree+'/preview-scan',{})[0]==409
        job=finish(queued['job_id'])
        assert job['status']=='completed',job
        assert job['result']=={'source_id':tree.rsplit('/',1)[-1],'mode':'initial','imported_files':3,
            'created_folders':2,'ignored_files':4,'imported_bytes':len(payload)*2}
        entries=request(tree+'/entries')[1]['items']
        assert len(entries)==3 and len({e['document_id'] for e in entries})==3
        for entry in entries:
            assert entry['sha256']==expected['tree/'+entry['relative_path']]
        files=request('/api/v1/documents?space_id='+space+'&source_kind=external')[1]['items']
        assert len(files)==3 and all(d['triage_status']=='needs_review' and d['origin_kind']=='external' for d in files)
        assert all(d['availability_status']=='unknown' for d in files)  # No fake download/current-byte guarantee.
        root_doc=next(e['document_id'] for e in entries if e['relative_path']=='root.txt')
        assert request('/api/v1/documents/'+root_doc,{'expected_document_version':1,'title':'Human title','folder_id':None},method='PATCH')[0]==200
        folders=request('/api/v1/folders?space_id='+space)[1]
        physical_folder=next(f['id'] for f in folders if f['name']=='资料')
        assert request('/api/v1/folders/'+physical_folder,{'name':'Hand arranged'},method='PATCH')[0]==200
        (root/'tree/new.txt').write_bytes(b'later file is not part of first import replay')
        (root/'tree/new.txt').chmod(0o644)
        assert request(tree+'/scan',{'mode':'initial'})[1]=={'job_id':queued['job_id'],'status':'completed'}
        assert request(tree+'/entries')[1]['total']==3
        assert request('/api/v1/documents/'+root_doc)[1]['title']=='Human title'
        assert request('/api/v1/documents/'+root_doc)[1]['document_version']==2
        assert any(f['name']=='Hand arranged' for f in request('/api/v1/folders?space_id='+space)[1])

        flat_target=folder('Flat target')
        folder('existing',flat_target)  # flat must not collide with/copy physical directories.
        flat=source('flat','flat','filed',flat_target)
        flat_job=finish(request(flat+'/scan',{'mode':'initial'})[1]['job_id'])
        assert flat_job['status']=='completed' and flat_job['result']['imported_files']==2
        assert flat_job['result']['created_folders']==0
        flat_entries=request(flat+'/entries')[1]['items']
        for entry in flat_entries:
            doc=request('/api/v1/documents/'+entry['document_id'])[1]
            assert doc['folder_id']==flat_target and doc['triage_status']=='filed'
            assert entry['sha256']==expected['flat/'+entry['relative_path']]

        conflict_target=folder('Conflict target')
        conflict_folder=folder('Taken',conflict_target)
        conflict=source('conflict','tree','filed',conflict_target)
        before=request('/api/v1/documents?space_id='+space)[1]['total']
        bad=finish(request(conflict+'/scan',{'mode':'initial'})[1]['job_id'])
        assert bad['status']=='failed' and bad['error']['code']=='SOURCE_FOLDER_CONFLICT'
        assert request(conflict+'/entries')[1]['total']==0
        assert request(conflict)[1]['initial_import_completed_at'] is None
        assert request('/api/v1/documents?space_id='+space)[1]['total']==before
        assert not any(f['name']=='good' and f['parent_id']==conflict_target for f in request('/api/v1/folders?space_id='+space)[1])
        assert request('/api/v1/folders/'+conflict_folder,{'name':'Old Taken'},method='PATCH')[0]==200
        recovered=finish(request(conflict+'/scan',{'mode':'initial'})[1]['job_id'])
        assert recovered['status']=='completed' and recovered['result']['imported_files']==2
        assert request(conflict)[1]['initial_import_completed_at']

        bulk_source=source('bulk','flat','needs_review',None)
        bulk_id=request(bulk_source+'/scan',{'mode':'initial'})[1]['job_id']
        start=time.monotonic()
        bulk_job=finish(bulk_id)
        elapsed=time.monotonic()-start
        assert bulk_job['status']=='completed' and bulk_job['result']['imported_files']==1000
        assert request(bulk_source+'/entries')[1]['total']==1000
        print('First import resource baseline: '+json.dumps({'files':1000,'worker_and_queue_seconds':round(elapsed,3)}))

        docker('exec','-i',name,'python','-',input='''
import json, os
from juanzhan.config import Settings
from juanzhan.database import connect
s=Settings.from_env()
with connect(s.database) as db:
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==1007
    assert db.execute('SELECT count(*) FROM source_entries').fetchone()[0]==1007
    assert db.execute('SELECT count(*) FROM file_revisions').fetchone()[0]==1007
    assert db.execute("SELECT count(*) FROM file_revisions WHERE storage_kind='external' AND managed_object_id IS NULL AND length(sha256)=64").fetchone()[0]==1007
    assert db.execute('SELECT count(*) FROM managed_objects').fetchone()[0]==0
    assert db.execute("SELECT count(*) FROM document_events WHERE actor='source_scan'").fetchone()[0]==1007
    assert db.execute("SELECT count(*) FROM jobs WHERE kind='parse'").fetchone()[0]==1007
    for status,result,error in db.execute("SELECT status,result_json,error_json FROM scan_runs WHERE mode='initial'"):
        assert status in ('completed','failed')
        assert bool(result)==(status=='completed')
        assert bool(error)==(status=='failed')
    assert db.execute('SELECT count(*) FROM sources WHERE initial_import_completed_at IS NOT NULL AND last_successful_scan_at IS NOT NULL').fetchone()[0]==4
assert not any(files for _,_,files in os.walk(s.data_dir/'managed'/'sha256'))
assert not any(p.is_file() for p in s.data_dir.iterdir())  # anonymous metadata spool is gone
''')
        docker('restart',name)
        base='http://127.0.0.1:'+docker('port',name,'8000/tcp').split(':')[-1]
        ready()
        assert request(tree+'/scan',{'mode':'initial'})[1]['job_id']==queued['job_id']
        assert request('/api/v1/documents/'+root_doc)[1]['title']=='Human title'
        assert request('/api/v1/jobs/'+bulk_id)[1]['result']==bulk_job['result']
        # Host-side fixture mutation while the shared safe iterator holds an open inode.
        # It must invalidate the observation before any manifest can be published.
        race_code="""
import json,sys
from contextlib import closing
from juanzhan.config import Settings
from juanzhan.source_paths import SourceMounts,SourcePathError
from juanzhan.source_scans import inventory
with closing(inventory(SourceMounts(Settings.from_env().source_mounts),'tree',{'ignored_files':0})) as records:
    for kind,path,stream,info in records:
        if kind=='file':
            print(json.dumps(path),flush=True)
            sys.stdin.readline()
            stream.read()
            try:next(records)
            except SourcePathError as e:assert e.code=='SOURCE_CHANGED'
            else:raise AssertionError('Changed inode was accepted')
            break
    else:raise AssertionError('Missing race fixture')
"""
        race=subprocess.Popen(['docker','exec','-i',name,'python','-u','-c',race_code],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            relative=json.loads(race.stdout.readline())
            race_path=root/'tree'/relative
            original=race_path.read_bytes()
            race_path.write_bytes(b'changed during observation')
            try:
                _,stderr=race.communicate('\n',timeout=10)
                assert race.returncode==0,stderr
            finally:race_path.write_bytes(original)
        finally:
            if race.poll() is None:
                race.kill()
                race.communicate()
        for path,checksum in expected.items():assert hashlib.sha256((root/path).read_bytes()).hexdigest()==checksum
        print('PASS: real RO tree/flat first imports, independent equal hashes, empty originals/directories, logical-only mapping, rollback/retry, replay preserves edits and ignores later files, 1000-file atomic publish, parse-job/audit invariants, no managed bytes, restart persistence, live change detection and unchanged source hashes')
    finally:
        if started:docker('rm','-f',name)
        if created:docker('volume','rm',volume)
