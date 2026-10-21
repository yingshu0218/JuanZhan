"""Disposable real readonly source changes, scans, snapshots and historical downloads."""
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from urllib.request import Request,build_opener,HTTPCookieProcessor,ProxyHandler
import uuid

ROOT=Path(__file__).resolve().parents[1]
name='juanzhan-source-drill-'+uuid.uuid4().hex[:10]
image=os.environ.get('JUANZHAN_DRILL_IMAGE','juanzhan:'+ (ROOT/'VERSION').read_text().strip())
secret=secrets.token_urlsafe(32);password=secrets.token_urlsafe(32)
env={**os.environ,'CONVERTER_SERVICE_TOKEN':secret}
created=[];volumes=[];net=False

def docker(*args,input=None):
    result=subprocess.run(['docker',*args],env=env,input=input,text=True,capture_output=True,timeout=120)
    if result.returncode:raise RuntimeError(result.stderr.replace(secret,'[redacted]').replace(password,'[redacted]'))
    return result.stdout.strip()

try:
    docker('network','create',name);net=True
    volume=name+'-data';docker('volume','create',volume);volumes.append(volume)
    code=[]
    if os.environ.get('JUANZHAN_DRILL_SERVICES'):code=['-v',os.environ['JUANZHAN_DRILL_SERVICES']+':/app/services:ro']
    converter=name+'-converter';created.append(converter)
    docker('run','-d','--name',converter,'--network',name,'--network-alias','converter','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--tmpfs','/tmp:size=128m,mode=1777','-e','CONVERTER_SERVICE_TOKEN',*code,image,
        'python','-m','uvicorn','juanzhan.converter:app','--host','0.0.0.0','--port','8000')
    with tempfile.TemporaryDirectory(prefix=name) as directory:
        root=Path(directory);root.chmod(0o755);file=root/'source.txt';file.write_bytes(b'Original overview A');file.chmod(0o644)
        archive=name+'-archive';created.append(archive)
        docker('run','-d','--name',archive,'--network',name,'--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--tmpfs','/tmp:size=256m,mode=1777','-p','127.0.0.1::8000','-v',str(root)+':/sources/docs:ro','-v',volume+':/data',
            '-e','JUANZHAN_COOKIE_SECURE=false','-e','JUANZHAN_DATA_DIR=/data','-e','JUANZHAN_SOURCE_MOUNTS={"docs":"/sources/docs"}',
            '-e','CONVERTER_SERVICE_TOKEN','-e','CONVERTER_URL=http://converter:8000',*code,image)
        base='http://'+docker('port',archive,'8000/tcp').splitlines()[0]
        opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()));csrf=''
        def request(path,body=None,method=None,raw=False):
            headers={'X-CSRF-Token':csrf}
            if body is not None:headers['Content-Type']='application/json';body=json.dumps(body).encode()
            with opener.open(Request(base+path,data=body,headers=headers,method=method),timeout=15) as response:
                data=response.read();return data if raw else json.loads(data)
        for attempt in range(60):
            try:request('/healthz');break
            except OSError:
                if attempt==59:raise
                time.sleep(.2)
        docker('exec','-i',archive,'python','-m','juanzhan.admin','set-password','--stdin',input=password+'\n')
        csrf=request('/api/v1/auth/session')['csrf_token']
        csrf=request('/api/v1/auth/login',{'username':'admin','password':password})['csrf_token']
        space=request('/api/v1/spaces',{'name':'Readonly revision drill'})['id']
        source=request('/api/v1/sources',{'space_id':space,'name':'Readonly source','kind':'external','root_alias':'docs','initial_import_policy':'flat'})['id']
        def work():docker('exec',archive,'python','-m','juanzhan.worker','--once')
        def finish(id):
            for _ in range(40):
                job=request('/api/v1/jobs/'+id)
                if job['status']=='completed':return job
                assert job['status']!='failed',job
                work()
            raise AssertionError('Task deadline exceeded')
        def scan(mode):return finish(request('/api/v1/sources/'+source+'/scan',{'mode':mode})['job_id'])
        def parsed(path):
            for _ in range(40):
                doc=request(path)
                if doc['processing_status']=='completed':return doc
                assert doc['processing_status']!='failed',doc
                work()
            raise AssertionError('Parse deadline exceeded')
        scan('initial');entry=request('/api/v1/sources/'+source+'/entries')['items'][0]
        path='/api/v1/documents/'+entry['document_id'];first=parsed(path);old=first['current_revision_id']
        assert request(path+'/source-files')['items'][0]['server_copy']
        assert request(path+'/download',raw=True)==b'Original overview A'
        request(path,{'expected_document_version':first['document_version'],'description':'Manual description remains'},'PATCH')
        previous_stat=file.stat();file.write_bytes(b'Original overview B');os.utime(file,ns=(previous_stat.st_atime_ns,previous_stat.st_mtime_ns))
        scan('incremental');changed=request(path)
        assert changed['current_revision_id']!=old and changed['description']=='Manual description remains'
        assert request(path+'/overview')['stale_for_current_revision']
        assert request(path+'/download?revision_id='+old,raw=True)==b'Original overview A'
        current=parsed(path);new=current['current_revision_id']
        scan('incremental');assert request(path)['current_revision_id']==new
        inventory=request(path+'/source-files');assert inventory['total']==2
        assert all(item['server_copy'] and item['storage_kind']=='external' and item['source']['id']==source for item in inventory['items'])
        file.unlink();scan('incremental');scan('incremental')
        assert request(path+'/download',raw=True)==b'Original overview B'
        assert request(path+'/download?revision_id='+old,raw=True)==b'Original overview A'
        assert request(path)['description']=='Manual description remains'
        print(json.dumps({'readonly_source':True,'same_size_mtime_change_detected':True,'unchanged_no_new_revision':True,'historical_versions':2,'offline_both_versions_readable':True,'manual_description_preserved':True}))
finally:
    for container in reversed(created):subprocess.run(['docker','rm','-f',container],capture_output=True)
    for volume in volumes:subprocess.run(['docker','volume','rm',volume],capture_output=True)
    if net:subprocess.run(['docker','network','rm',name],capture_output=True)
