"""Disposable Compose install/real import/index/upgrade/backup/new-volume restore.

Owns only randomly named juanzhan-release-check-* projects and their labelled volumes.
Never replaces normal services, data, .env or passwords. No registry/Git publication.
"""
import http.cookiejar
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid

ROOT=Path(__file__).resolve().parents[1]


def main():
    prefix='juanzhan-release-check-'+uuid.uuid4().hex[:10]
    names=[prefix,prefix+'-restore'];projects=[]
    version=(ROOT/'VERSION').read_text().strip();candidate='juanzhan:'+version
    token=secrets.token_urlsafe(32);password=secrets.token_urlsafe(24)
    env={**os.environ,'JUANZHAN_PORT':'0','JUANZHAN_COOKIE_SECURE':'false','JUANZHAN_SOURCE_MOUNTS':'{}',
         'JUANZHAN_DATA_DIR':'/data','CONVERTER_SERVICE_TOKEN':token}
    env.setdefault('DOCKER_CONFIG',str(ROOT/'.local/docker'))
    result={'candidate':candidate,'published':False,'steps':[]};begin=time.monotonic()
    with tempfile.TemporaryDirectory(prefix='juanzhan-release-config-') as temp:
        empty=Path(temp)/'empty.env';empty.write_text('# fixture variables supplied in process environment\n')
        override=Path(temp)/'restore.yaml'
        override.write_text('volumes:\n  archive_data:\n    external: true\n    name: '+prefix+'_archive_recovery\n')
        def docker(args,input=None):
            done=subprocess.run(['docker',*args],cwd=ROOT,env=env,input=input,text=True,capture_output=True)
            if done.returncode:raise RuntimeError(done.stderr.replace(token,'[redacted]').replace(password,'[redacted]')[-3000:])
            return done.stdout.strip()
        def compose(project,args,restored=False,input=None):
            command=['compose','--env-file',str(empty),'-p',project,'-f',str(ROOT/'deploy/compose.yaml')]
            if restored:command+=['-f',str(override)]
            return docker(command+args,input)
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        base='';csrf=''
        def request(path,body=None,method=None,extra=None):
            headers={'X-CSRF-Token':csrf}
            if body is not None:headers['Content-Type']='application/json';body=json.dumps(body).encode()
            if extra:headers.update(extra)
            with opener.open(urllib.request.Request(base+path,data=body,headers=headers,method=method),timeout=15) as response:
                data=response.read();return json.loads(data) if response.headers.get_content_type()=='application/json' else data
        def login():
            nonlocal csrf
            csrf=request('/api/v1/auth/session')['csrf_token']
            csrf=request('/api/v1/auth/login',{'username':'admin','password':password})['csrf_token']
        def address(project,restored=False):
            return 'http://'+compose(project,['port','archive','8000'],restored)
        def verify(document,space,expected):
            assert request('/api/v1/documents/'+document+'/download')==expected
            assert request('/api/v1/documents/'+document+'/content?format=text')['body'].strip()==expected.decode().strip()
            deadline=time.monotonic()+45
            while request('/api/v1/documents?space_id='+space+'&q='+urllib.parse.quote('档案'))['total']!=1:
                if time.monotonic()>deadline:raise RuntimeError('Search indexing deadline exceeded')
                time.sleep(.2)
        try:
            env['JUANZHAN_IMAGE']='juanzhan-foundation:dev'
            result['previous_image_id']=docker(['image','inspect','--format','{{.Id}}',env['JUANZHAN_IMAGE']])
            result['candidate_image_id']=docker(['image','inspect','--format','{{.Id}}',candidate])
            projects.append((prefix,False));compose(prefix,['up','-d','--wait','--no-build'])
            compose(prefix,['exec','-T','archive','python','-m','juanzhan.admin','set-password','--stdin'],input=password+'\n')
            base=address(prefix);login();space=request('/api/v1/spaces',{'name':'Release drill'})['id']
            content='真实档案 release recovery 2026\n'.encode();boundary='release'+uuid.uuid4().hex
            data=(f'--{boundary}\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="release.txt"\r\nContent-Type: text/plain\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
            with opener.open(urllib.request.Request(base+'/api/v1/documents/upload',data=data,headers={
                'Content-Type':'multipart/form-data; boundary='+boundary,'X-CSRF-Token':csrf}),timeout=15) as response:
                assert response.status==201;receipt=json.load(response)
            id=receipt['document_id'];deadline=time.monotonic()+60
            while request('/api/v1/documents/'+id)['processing_status']!='completed':
                if time.monotonic()>deadline:raise RuntimeError('Real parse deadline exceeded')
                time.sleep(.2)
            verify(id,space,content);result['steps'].append('fresh_install_real_import_and_search')
            env['JUANZHAN_IMAGE']=candidate
            compose(prefix,['up','-d','--wait','--no-build']);base=address(prefix)
            verify(id,space,content)
            with opener.open(base+'/',timeout=15) as response:
                shell=response.read().decode();assert 'JuanZhan' in shell and "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
            asset=re.search(r'src="(/assets/[^"]+\.js)"',shell).group(1)
            with opener.open(base+asset,timeout=15) as response:assert response.status==200 and len(response.read())>1000
            container=compose(prefix,['ps','-q','archive'])
            assert docker(['inspect','--format','{{.HostConfig.ReadonlyRootfs}}',container])=='true'
            assert 'ALL' in docker(['inspect','--format','{{json .HostConfig.CapDrop}}',container])
            assert docker(['exec',container,'python','-c','import os; print(os.getuid())'])=='10001'
            result['runtime_checks']={'uid':10001,'read_only_root':True,'cap_drop_all':True,'web_assets_and_csp':True}
            result['steps'].append('same_schema_image_upgrade_preserves_credentials_and_data')
            compose(prefix,['stop','archive-worker'])
            compose(prefix,['run','--rm','maintenance','python','-m','juanzhan.backup','create','--output','/backups/drill'])
            compose(prefix,['run','--rm','maintenance','python','-m','juanzhan.backup','restore','--input','/backups/drill','--output','/recovery/restored'])
            result['steps'].append('consistent_backup_and_new_directory_restore')
            env['JUANZHAN_DATA_DIR']='/data/restored'
            projects.append((names[1],True));compose(names[1],['up','-d','--wait','--no-build'],True);base=address(names[1],True)
            try:request('/api/v1/documents/'+id);raise AssertionError('Old session unexpectedly accepted')
            except urllib.error.HTTPError as error:assert error.code==401
            login();verify(id,space,content)
            checks=compose(names[1],['exec','-T','archive','python','-c',
                'import json; from juanzhan.config import Settings; from juanzhan.database import connect; '
                '\nwith connect(Settings.from_env().database) as db: print(json.dumps({"migrations":db.execute("SELECT count(*) FROM migration_checksums").fetchone()[0],"integrity":db.execute("PRAGMA integrity_check").fetchone()[0],"foreign_keys":len(db.execute("PRAGMA foreign_key_check").fetchall())}))'],True)
            result['database_checks']=json.loads(checks)
            assert result['database_checks']=={'migrations':len(list((ROOT/'services'/'migrations').glob('*.sql'))),'integrity':'ok','foreign_keys':0}
            result['steps'].append('restored_instance_login_download_content_search_and_integrity')
            result['elapsed_seconds']=round(time.monotonic()-begin,2);result['status']='passed'
        finally:
            for project,restored in reversed(projects):
                try:compose(project,['down','--remove-orphans'],restored)
                except RuntimeError:pass
            for project in names:
                # Restrict cleanup to volumes bearing this run's unpredictable project label.
                for volume in docker(['volume','ls','-q','--filter','label=com.docker.compose.project='+project]).splitlines():
                    docker(['volume','rm',volume])
    output=Path(tempfile.mkdtemp(prefix='juanzhan-release-drill-'))/'result.json'
    output.write_text(json.dumps(result,indent=2)+'\n');print(str(output))
if __name__=='__main__':main()
