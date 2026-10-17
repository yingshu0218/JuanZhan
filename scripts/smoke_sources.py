"""Disposable real read-only bind mounts + SQLite + authenticated HTTP; no user sources."""
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
    result = subprocess.run(['docker', *args], input=input, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip()


name = 'juanzhan-source-smoke-' + uuid.uuid4().hex[:12]
password = secrets.token_urlsafe(32)
started = False
volume = name + '-data'
created = False
with tempfile.TemporaryDirectory(prefix='juanzhan-source-fixture-') as temporary:
    root = Path(temporary)
    root.chmod(0o755)
    (root / '资料').mkdir()
    (root / '资料').chmod(0o755)
    (root / '资料' / 'é.txt').write_bytes(b'real read-only original\n')
    (root / '资料' / 'é.txt').chmod(0o666)
    (root / 'nested').mkdir()
    (root / 'nested').chmod(0o755)
    (root / 'link-dir').symlink_to('资料', target_is_directory=True)
    (root / 'in-link').symlink_to('资料/é.txt')
    (root / 'out-link').symlink_to('/etc/passwd')
    os.mkfifo(root / 'pipe')
    clean = root / 'preview'
    clean.mkdir()
    clean.chmod(0o755)
    for filename, content in [('one.txt', b'one'), ('two.PDF', b'preview metadata only'), ('skip.bin', b'ignored')]:
        (clean / filename).write_bytes(content)
        (clean / filename).chmod(0o644)
    (clean / 'link.txt').symlink_to('one.txt')
    bulk = root / 'bulk'
    bulk.mkdir()
    bulk.chmod(0o755)
    for index in range(1000):
        entry = bulk / (str(index)+'.txt')
        entry.write_bytes(b'x')
        entry.chmod(0o644)
    (bulk / 'level').mkdir()
    (bulk / 'level').chmod(0o755)
    unsafe = root / 'unsafe-fixture'
    unsafe.mkdir()
    unsafe.chmod(0o755)
    (unsafe / 'nested').mkdir()
    (unsafe / 'nested').chmod(0o755)
    before = hashlib.sha256((root / '资料' / 'é.txt').read_bytes()).hexdigest()
    mounts = {'docs': '/sources/docs', 'writable': '/sources/writable',
              'offline': '/sources/absent', 'linked': '/sources/docs/link-dir',
              'clean': '/sources/docs/preview', 'bulk': '/sources/docs/bulk', 'same': '/sources/alias', 'unsafe': '/sources/unsafe'}
    try:
        docker('volume', 'create', volume)
        created = True
        docker('run', '-d', '--name', name, '-p', '127.0.0.1::8000',
               '--mount', f'type=bind,source={root},target=/sources/docs,readonly',
               '--mount', f'type=bind,source={root},target=/sources/writable',
               '--mount', f'type=bind,source={root},target=/sources/docs/nested',
               '--mount', f'type=bind,source={clean},target=/sources/alias,readonly',
               '--mount', f'type=bind,source={unsafe},target=/sources/unsafe,readonly',
               '--mount', f'type=bind,source={root / "nested"},target=/sources/unsafe/nested',
               '--mount', f'type=volume,source={volume},target=/data', '-e', 'JUANZHAN_DATA_DIR=/data',
               '-e', 'JUANZHAN_SOURCE_MOUNTS=' + json.dumps(mounts), 'juanzhan-foundation:dev')
        started = True
        base = 'http://127.0.0.1:' + docker('port', name, '8000/tcp').split(':')[-1]

        def request(path, body=None, cookie='', csrf=''):
            headers = {'Cookie': cookie, 'X-CSRF-Token': csrf, 'Content-Type': 'application/json'}
            req = urllib.request.Request(base + path, headers=headers,
                data=json.dumps(body).encode() if body is not None else None)
            try:
                response = urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                return response.status, json.load(response), response.headers

        for attempt in range(40):
            try:
                if request('/healthz')[0] == 200:
                    break
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.2)
        else:
            raise AssertionError('Source fixture did not become ready')
        assert request('/api/v1/source-mounts')[0] == 401
        docker('exec', '-i', name, 'python', '-m', 'juanzhan.admin', 'set-password', '--stdin', input=password + '\n')
        _, session, headers = request('/api/v1/auth/session')
        cookie = headers['Set-Cookie'].split(';')[0]
        status, logged_in, headers = request('/api/v1/auth/login', {'username': 'admin', 'password': password}, cookie, session['csrf_token'])
        assert status == 200
        cookie = headers['Set-Cookie'].split(';')[0]
        status, payload, headers = request('/api/v1/source-mounts', cookie=cookie)
        assert status == 200 and headers['Cache-Control'] == 'no-store'
        items = {x['alias']: x for x in payload['items']}
        assert items['docs']['status'] == 'ready'
        assert items['writable']['error_code'] == 'SOURCE_NOT_READ_ONLY'
        assert items['linked']['status'] == 'unavailable'
        assert items['offline']['status'] == 'offline'
        assert '/sources' not in json.dumps(payload) and str(root) not in json.dumps(payload)
        docker('exec', '-i', name, 'python', '-', input='''
import errno, os
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.source_paths import SourceMounts, SourcePathError
s = Settings.from_env()
m = SourceMounts(s.source_mounts)
with m.open('docs', '资料/é.txt') as f:
    assert f.read() == b'real read-only original\\n'
    assert not f.writable()
for path in ('../etc/passwd', '/etc/passwd', '资料/../out-link', 'in-link', 'out-link', 'link-dir/é.txt', 'pipe', '资料', 'nested/资料/é.txt'):
    try:
        with m.open('docs', path): pass
    except SourcePathError: pass
    else: raise AssertionError('Unsafe source access accepted')
try:
    fd = os.open('/sources/docs/资料/é.txt', os.O_WRONLY)
except OSError as e:
    assert e.errno == errno.EROFS
else:
    os.close(fd)
    raise AssertionError('Kernel did not enforce readonly')
# Ensure every failed probe closes descriptors; no accidental source/document records.
before = len(os.listdir('/proc/self/fd'))
for _ in range(100):
    m.list()
    try:
        with m.open('docs', 'out-link'): pass
    except SourcePathError: pass
assert len(os.listdir('/proc/self/fd')) == before
with connect(s.database) as db:
    for table in ('sources', 'source_entries', 'documents'):
        assert db.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0
''')
        # Replace the pathname after safe open: reading must stay on the checked inode.
        race_code = """
import sys
from juanzhan.config import Settings
from juanzhan.source_paths import SourceMounts
with SourceMounts(Settings.from_env().source_mounts).open('docs', '资料/é.txt') as f:
    print('opened', flush=True)
    sys.stdin.readline()
    assert f.read() == b'real read-only original\\n'
"""
        race = subprocess.Popen(['docker', 'exec', '-i', name, 'python', '-u', '-c', race_code],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert race.stdout.readline().strip() == 'opened'
            original = root / '资料' / 'é.txt'
            retained = root / '资料' / 'retained.txt'
            original.rename(retained)
            original.symlink_to('/etc/passwd')
            try:
                _, stderr = race.communicate('\n', timeout=10)
                assert race.returncode == 0, stderr
            finally:
                original.unlink()
                retained.rename(original)
        finally:
            if race.poll() is None:
                race.kill()
                race.communicate()
        csrf = logged_in['csrf_token']
        assert request('/api/v1/sources')[0] == 401
        _, space, _ = request('/api/v1/spaces', {'name': 'Preview fixtures'}, cookie, csrf)
        config = {'space_id': space['id'], 'name': 'Preview', 'kind': 'external',
                  'root_alias': 'clean', 'initial_import_policy': 'tree', 'initial_triage_status': 'needs_review'}
        assert request('/api/v1/sources', config, cookie)[0] == 403
        status, source, _ = request('/api/v1/sources', config, cookie, csrf)
        assert status == 201 and source['status'] == 'ready'
        assert request('/api/v1/sources', {**config, 'root_alias': 'same'}, cookie, csrf)[0] == 409
        assert request('/api/v1/sources', {**config, 'root_alias': 'docs'}, cookie, csrf)[0] == 409
        path = '/api/v1/sources/' + source['id']
        status, queued, _ = request(path + '/preview-scan', {}, cookie, csrf)
        assert status == 202
        assert request(path + '/preview-scan', {}, cookie, csrf)[1]['job_id'] == queued['job_id']
        assert request(path, cookie=cookie)[1]['status'] == 'scanning'
        assert json.loads(docker('exec', name, 'python', '-m', 'juanzhan.worker', '--once')) == {'job_id': queued['job_id'], 'status': 'completed'}
        job = request('/api/v1/jobs/' + queued['job_id'], cookie=cookie)[1]
        assert job['result']['estimated_files'] == 2 and job['result']['estimated_bytes'] == 24
        assert job['result']['ignored_files'] == 2
        assert job['result']['by_extension'] == {'.txt': 1, '.pdf': 1}
        assert request(path + '/entries', cookie=cookie)[1]['total'] == 0
        assert request(path, cookie=cookie)[1]['last_successful_scan_at'] is None
        assert request(path, cookie=cookie)[1]['initial_import_completed_at'] is None
        status, unsafe_source, _ = request('/api/v1/sources', {**config, 'root_alias': 'unsafe'}, cookie, csrf)
        assert status == 201
        unsafe_path = '/api/v1/sources/' + unsafe_source['id']
        queued_unsafe = request(unsafe_path + '/preview-scan', {}, cookie, csrf)[1]
        assert json.loads(docker('exec', name, 'python', '-m', 'juanzhan.worker', '--once'))['status'] == 'failed'
        failed = request('/api/v1/jobs/' + queued_unsafe['job_id'], cookie=cookie)[1]
        assert failed['error']['code'] == 'SOURCE_NOT_READ_ONLY'
        assert request(unsafe_path, cookie=cookie)[1]['status'] == 'error'
        docker('restart', name)
        base = 'http://127.0.0.1:' + docker('port', name, '8000/tcp').split(':')[-1]
        for _ in range(40):
            try:
                if request('/healthz')[0] == 200: break
            except (OSError, urllib.error.URLError): pass
            time.sleep(0.2)
        else:
            raise AssertionError('Restarted source fixture did not become ready')
        assert request('/api/v1/jobs/' + queued['job_id'], cookie=cookie)[1]['result'] == job['result']
        assert request(path, cookie=cookie)[1]['root_alias'] == 'clean'
        status, bulk_source, _ = request('/api/v1/sources', {**config, 'root_alias': 'bulk'}, cookie, csrf)
        assert status == 201
        bulk_job = request('/api/v1/sources/'+bulk_source['id']+'/preview-scan', {}, cookie, csrf)[1]
        assert json.loads(docker('exec', name, 'python', '-m', 'juanzhan.worker', '--once'))['status'] == 'completed'
        bulk_result = request('/api/v1/jobs/'+bulk_job['job_id'], cookie=cookie)[1]['result']
        assert bulk_result['estimated_files'] == 1000 and bulk_result['estimated_bytes'] == 1000
        metrics = docker('exec', '-i', name, 'python', '-', input="""
import json, resource, time
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.source_scans import preview
from juanzhan.source_paths import SourcePathError
s=Settings.from_env()
with connect(s.database) as db:
    db.row_factory=__import__('sqlite3').Row
    job=dict(db.execute("SELECT * FROM jobs WHERE target_id IN (SELECT id FROM scan_runs WHERE source_id IN (SELECT id FROM sources WHERE root_ref='bulk'))").fetchone())
for options in ({'max_entries':999}, {'max_depth':0}):
    try: preview(s,job,**options)
    except SourcePathError as e: assert e.code=='SOURCE_PREVIEW_LIMIT'
    else: raise AssertionError('Preview silently truncated instead of failing')
start=time.monotonic()
assert preview(s,job)['estimated_files']==1000
print(json.dumps({'files':1000,'seconds':round(time.monotonic()-start,3),'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
""")
        print('Preview resource baseline: '+metrics)
        docker('exec', '-i', name, 'python', '-', input="""
import json
from juanzhan.config import Settings
from juanzhan.database import connect
with connect(Settings.from_env().database) as db:
    for table in ('documents','source_entries','file_revisions'):
        assert db.execute('SELECT count(*) FROM '+table).fetchone()[0] == 0
    states = db.execute('SELECT status,result_json,error_json FROM scan_runs ORDER BY status').fetchall()
    assert [r[0] for r in states] == ['completed','completed','failed']
    assert sorted(json.loads(r[1])['estimated_files'] for r in states if r[0]=='completed') == [2,1000]
    assert json.loads(states[-1][2])['code'] == 'SOURCE_NOT_READ_ONLY'
""")
        assert hashlib.sha256((root / '资料' / 'é.txt').read_bytes()).hexdigest() == before
        print('PASS: real RO/RW/nested bind mounts, alias-only authenticated HTTP, Unicode reads, symlink/traversal/FIFO/directory rejection, kernel EROFS, descriptor cleanup, pinned-inode replacement race, unchanged original; source/preview HTTP, overlap rejection, real worker success/failure, restart persistence, no imported records')
    finally:
        if started:
            docker('rm', '-f', name)
        if created:
            docker('volume', 'rm', volume)
