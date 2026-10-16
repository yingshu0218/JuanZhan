"""Exercise a disposable Archive container, real HTTP and the local admin CLI.
Run after building juanzhan-foundation:dev. Never touches the normal Compose volume.
"""
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def docker(*args, input=None):
    return subprocess.run(['docker', *args], input=input, text=True, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


name = 'juanzhan-auth-smoke-' + uuid.uuid4().hex[:12]
volume = name + '-data'
password = secrets.token_urlsafe(32)
cookie = ''
base = ''


def request(path, method='GET', body=None, csrf=None, bearer=None, use_cookie=True):
    headers = {}
    if cookie and use_cookie:
        # Internal HTTP hop simulates TLS termination; Secure flag checked separately.
        headers['Cookie'] = cookie
    if csrf:
        headers['X-CSRF-Token'] = csrf
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        payload = response.read()
        return response.status, json.loads(payload) if payload else None, response.headers


created = False
started = False
try:
    docker('volume', 'create', volume)
    created = True
    docker('run', '-d', '--name', name, '-p', '127.0.0.1::8000',
           '--mount', f'type=volume,source={volume},target=/data',
           '-e', 'JUANZHAN_DATA_DIR=/data', 'juanzhan-foundation:dev')
    started = True
    port = docker('port', name, '8000/tcp').split(':')[-1]
    base = 'http://127.0.0.1:' + port

    def ready():
        for _ in range(30):
            try:
                if request('/healthz')[0] == 200:
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.2)
        raise AssertionError('Container did not become ready')

    ready()
    assert request('/api/v1/documents')[0] == 401
    docker('exec', '-i', name, 'python', '-m', 'juanzhan.admin', 'set-password', '--stdin',
           input=password + '\n')
    status, session, headers = request('/api/v1/auth/session')
    assert status == 200
    assert 'HttpOnly' in headers['Set-Cookie'] and 'Secure' in headers['Set-Cookie']
    cookie = headers['Set-Cookie'].split(';')[0]
    body = {'username':'admin', 'password':password}
    assert request('/api/v1/auth/login', 'POST', body)[0] == 403
    status, logged_in, headers = request('/api/v1/auth/login', 'POST', body, session['csrf_token'])
    assert status == 200
    cookie = headers['Set-Cookie'].split(';')[0]
    csrf = logged_in['csrf_token']
    assert request('/api/v1/auth/tokens', 'POST', {'name':'blocked'})[0] == 403
    status, token, headers = request('/api/v1/auth/tokens', 'POST', {'name':'smoke'}, csrf)
    assert status == 201 and headers['Cache-Control'] == 'no-store'
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 404
    status, catalog_space, _ = request('/api/v1/spaces', 'POST', {'name':'Smoke catalog'}, csrf)
    assert status == 201
    space_id = catalog_space['id']
    status, catalog_folder, _ = request('/api/v1/folders', 'POST', {'space_id':space_id,'name':'Root'}, csrf)
    assert status == 201
    assert request('/api/v1/folders', 'POST', {'space_id':space_id,'name':'ROOT'}, csrf)[0] == 409
    assert request('/api/v1/folders/'+catalog_folder['id'], 'PATCH', {'parent_id':catalog_folder['id']}, csrf)[0] == 409
    status, catalog_tag, _ = request('/api/v1/tags', 'POST', {'space_id':space_id,'name':'important'}, csrf)
    assert status == 201
    status, catalog_type, _ = request('/api/v1/document-types', 'POST', {'space_id':space_id,'key':'contract','label':'Contract'}, csrf)
    assert status == 201
    docker('exec', '-i', name, 'python', '-', input="""
import io, os
from pathlib import Path
from juanzhan.storage import ManagedStore
from juanzhan.database import connect
store = ManagedStore(Path('/data/managed'))
result = store.put(io.BytesIO(b'container original'), max_bytes=100)
with connect('/data/database/archive.sqlite3') as db:
    db.execute('INSERT INTO managed_objects VALUES (?,?,?,?,?)',
               ('storage-smoke', result.sha256, result.size_bytes, result.storage_key, '2026-10-16T00:00:00Z'))
    db.commit()
from juanzhan.config import Settings
from juanzhan.documents import DocumentService, Registration, RevisionChange, VersionChange
service = DocumentService(Settings.from_env())
with connect('/data/database/archive.sqlite3') as db:
    space = db.execute("SELECT id FROM spaces WHERE name='Smoke catalog'").fetchone()[0]
doc = service.register_managed(result, Registration(space_id=space,title='Lifecycle smoke',
    original_filename='original.txt',mime_type='text/plain'))
next_object = store.put(io.BytesIO(b'container revision'), max_bytes=100)
updated = service.append_managed_revision(doc['id'],next_object,
    RevisionChange(expected_document_version=1,original_filename='revision.txt',mime_type='text/plain'))
assert updated['id'] == doc['id'] and updated['document_version'] == 2
service.trash(doc['id'],VersionChange(expected_document_version=2))
old = Path('/data/managed/.staging') / ('c' * 32 + '.part')
old.write_bytes(b'interrupted')
os.utime(old, (0, 0))
""")
    docker('restart', name)
    # Docker may allocate a new ephemeral host port on restart.
    port = docker('port', name, '8000/tcp').split(':')[-1]
    base = 'http://127.0.0.1:' + port
    ready()
    docker('exec', '-i', name, 'python', '-', input="""
from pathlib import Path
from juanzhan.storage import ManagedStore
from juanzhan.database import connect
with connect('/data/database/archive.sqlite3') as db:
    key = db.execute("SELECT storage_key FROM managed_objects WHERE id='storage-smoke'").fetchone()[0]
with ManagedStore(Path('/data/managed')).open(key) as file:
    assert file.read() == b'container original'
assert list(Path('/data/managed/.staging').iterdir()) == []
from juanzhan.config import Settings
from juanzhan.documents import DocumentService, VersionChange
service = DocumentService(Settings.from_env())
with connect('/data/database/archive.sqlite3') as db:
    id = db.execute("SELECT id FROM documents WHERE title='Lifecycle smoke'").fetchone()[0]
before = service.get_record(id)
assert before['document_version'] == 3 and before['deleted_at'] is not None
after = service.restore(id,VersionChange(expected_document_version=3))
assert after['document_version'] == 4 and after['deleted_at'] is None
assert [r['revision_no'] for r in service.revisions(id)] == [1,2]
with connect('/data/database/archive.sqlite3') as db:
    assert db.execute('SELECT count(*) FROM document_events WHERE document_id=?',(id,)).fetchone() == (4,)
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []

""")
    assert request('/api/v1/auth/tokens')[0] == 200
    assert any(s['id'] == space_id for s in request('/api/v1/spaces')[1])
    assert request('/api/v1/document-types?space_id='+space_id)[1][0]['id'] == catalog_type['id']
    assert request('/api/v1/document-types/'+catalog_type['id'], 'PATCH', {'is_active':False}, csrf)[0] == 200
    assert request('/api/v1/tags/'+catalog_tag['id'], 'DELETE', csrf=csrf)[0] == 204
    assert request('/api/v1/folders/'+catalog_folder['id']+'/delete', 'POST', {'mode':'only_if_empty'}, csrf)[0] == 204
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 404
    assert request('/api/v1/auth/tokens/' + token['id'], 'DELETE', csrf=csrf)[0] == 204
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 401
    assert request('/api/v1/auth/logout', 'POST', csrf=csrf)[0] == 204
    assert request('/api/v1/auth/tokens')[0] == 401
    print('PASS: container CLI setup, HTTP login/CSRF/token/revoke/logout, restart persistence, managed object/staging recovery, catalog CRUD, document/revision/audit/trash/restore')
finally:
    if started:
        docker('rm', '-f', name)
    if created:
        docker('volume', 'rm', volume)
