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
    before = hashlib.sha256((root / '资料' / 'é.txt').read_bytes()).hexdigest()
    mounts = {'docs': '/sources/docs', 'writable': '/sources/writable',
              'offline': '/sources/absent', 'linked': '/sources/docs/link-dir'}
    try:
        docker('run', '-d', '--name', name, '-p', '127.0.0.1::8000',
               '--mount', f'type=bind,source={root},target=/sources/docs,readonly',
               '--mount', f'type=bind,source={root},target=/sources/writable',
               '--mount', f'type=bind,source={root},target=/sources/docs/nested',
               '--tmpfs', '/data:mode=0777', '-e', 'JUANZHAN_DATA_DIR=/data',
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
        status, _, headers = request('/api/v1/auth/login', {'username': 'admin', 'password': password}, cookie, session['csrf_token'])
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
        assert hashlib.sha256((root / '资料' / 'é.txt').read_bytes()).hexdigest() == before
        print('PASS: real RO/RW/nested bind mounts, alias-only authenticated HTTP, Unicode reads, symlink/traversal/FIFO/directory rejection, kernel EROFS, descriptor cleanup, pinned-inode replacement race, unchanged original and no business records')
    finally:
        if started:
            docker('rm', '-f', name)
