"""Run ONLY inside a disposable image container with fresh /data,/backups,/recovery.

Uses production Python dependencies and real loopback HTTP/worker processes. No
host ports, external files, normal service credentials or existing data are used.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable',action='store_true',required=True)
    parser.parse_args()
    assert os.environ.get('JUANZHAN_DATA_DIR')=='/data'
    assert os.environ.get('JUANZHAN_BACKUP_DIR')=='/backups'
    assert not Path('/data/database/archive.sqlite3').exists(), 'Fresh test volume required'
    assert os.getuid()==10001
    from juanzhan.auth import set_password
    from juanzhan.config import Settings
    from juanzhan.database import connect,MIGRATIONS
    settings=Settings.from_env()
    password=secrets.token_urlsafe(24)
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    csrf='';base='http://127.0.0.1:8000';server=None;worker=None
    report={'uid':os.getuid(),'steps':[],'external_sources_touched':False}
    def request(path,body=None,method=None,raw=False):
        headers={'X-CSRF-Token':csrf}
        if body is not None:
            headers['Content-Type']='application/zip' if raw else 'application/json'
            if not raw:body=json.dumps(body).encode()
        with opener.open(urllib.request.Request(base+path,data=body,headers=headers,method=method),timeout=20) as response:
            data=response.read()
            return json.loads(data) if response.headers.get_content_type()=='application/json' else data
    def until(check,seconds=35):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            result=check()
            if result:return result
            time.sleep(.1)
        raise RuntimeError('Runtime drill deadline exceeded')
    def launch(env):
        process=subprocess.Popen([sys.executable,'-m','uvicorn','juanzhan.archive:app','--host','127.0.0.1','--port','8000','--log-level','error'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def ready():
            assert process.poll() is None
            try:return request('/healthz')['status']=='ok'
            except (OSError,urllib.error.HTTPError):return False
        until(ready)
        return process
    def login():
        nonlocal csrf
        csrf=request('/api/v1/auth/session')['csrf_token']
        csrf=request('/api/v1/auth/login',{'username':'admin','password':password})['csrf_token']
    def complete(id):
        def terminal():
            job=request('/api/v1/jobs/'+id)
            if job['status']=='failed':raise RuntimeError('Runtime job failed: '+job['error']['code'])
            return job if job['status']=='completed' else None
        return until(terminal)
    env={**os.environ,'JUANZHAN_COOKIE_SECURE':'false'}
    try:
        server=launch(env);set_password(settings,password);login()
        worker=subprocess.Popen([sys.executable,'-m','juanzhan.worker','--poll-seconds','0.05'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        space=request('/api/v1/spaces',{'name':'Disposable runtime backup drill'})['id']
        boundary='runtime-boundary';original='生产镜像备份恢复 original bytes\n'.encode()
        data=(f'--{boundary}\r\nContent-Disposition: form-data; name="space_id"\r\n\r\n{space}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="runtime.txt"\r\nContent-Type: text/plain\r\n\r\n').encode()+original+f'\r\n--{boundary}--\r\n'.encode()
        with opener.open(urllib.request.Request(base+'/api/v1/documents/upload',data=data,headers={'X-CSRF-Token':csrf,'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=20) as response:document=json.load(response)['document_id']
        request('/api/v1/system/backup-schedule',{'expected_version':1,'interval_minutes':60,'keep_count':1,'max_age_days':1},method='PATCH')
        item=request('/api/v1/system/backups',{'request_id':'runtime-manual-create'})
        complete(item['job_id'])
        archive=request('/api/v1/system/backups/'+item['backup_id']+'/download')
        assert archive.startswith(b'PK')
        imported=request('/api/v1/system/backups/import?request_id=runtime-import',archive,raw=True)
        complete(imported['job_id'])
        recovered=request('/api/v1/system/backups/'+imported['backup_id']+'/restore',{'request_id':'runtime-recovery'})
        complete(recovered['job_id'])
        report['steps'].append('http_upload_backup_download_import_and_new_directory_recovery')
        for expected in (1,2):
            with connect(settings.database) as db:
                db.execute('UPDATE backup_schedule SET next_due_at=?',(time.time()-1,));db.commit()
            def automatic():
                rows=request('/api/v1/system/backups')['items']
                automatic=[row for row in rows if row['origin']=='automatic']
                return automatic if len(automatic)==expected and sum(row['status']=='ready' for row in automatic)==1 and (expected==1 or sum(row['status']=='deleted' for row in automatic)==1) else None
            until(automatic)
        report['steps'].append('real_daemon_due_backups_and_count_retention')
        staged=subprocess.run([sys.executable,'-m','juanzhan.backup_admin','stage-recovery','--id',recovered['recovery_id'],'--output','/recovery/restored'],env=env,capture_output=True,text=True,timeout=30)
        assert staged.returncode==0, 'Operator recovery staging failed'
        assert json.loads(staged.stdout)['activation_required']
        worker.terminate();worker.wait(timeout=10);worker=None
        server.terminate();server.wait(timeout=10);server=None
        env={**env,'JUANZHAN_DATA_DIR':'/recovery/restored','JUANZHAN_BACKUP_DIR':'/recovery/new-backups'}
        server=launch(env)
        try:request('/api/v1/documents/'+document);raise AssertionError('Copied session accepted')
        except urllib.error.HTTPError as error:assert error.code==401
        login();assert request('/api/v1/documents/'+document+'/download')==original
        assert request('/api/v1/system/backup-schedule')['interval_minutes']==0
        with connect(Path('/recovery/restored/database/archive.sqlite3')) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('SELECT COUNT(*) FROM migration_checksums').fetchone()[0]==len(list(MIGRATIONS.glob('*.sql')))
        shell=request('/').decode();assert 'JuanZhan' in shell
        css=re.search(r'href="(/assets/[^\"]+\.css)"',shell).group(1)
        assert len(request(css))>10000
        assert Path('/backups').stat().st_mode&0o777==0o700
        report['steps'].append('operator_staging_new_instance_login_download_plan_reset_integrity_and_css')
        report['status']='passed';print(json.dumps(report))
    finally:
        for process in (worker,server):
            if process is not None and process.poll() is None:
                process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
