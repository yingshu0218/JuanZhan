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
    docker('restart', name)
    # Docker may allocate a new ephemeral host port on restart.
    port = docker('port', name, '8000/tcp').split(':')[-1]
    base = 'http://127.0.0.1:' + port
    ready()
    assert request('/api/v1/auth/tokens')[0] == 200
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 404
    assert request('/api/v1/auth/tokens/' + token['id'], 'DELETE', csrf=csrf)[0] == 204
    assert request('/api/v1/documents', bearer=token['token'], use_cookie=False)[0] == 401
    assert request('/api/v1/auth/logout', 'POST', csrf=csrf)[0] == 204
    assert request('/api/v1/auth/tokens')[0] == 401
    print('PASS: container CLI setup, HTTP login/CSRF/token/revoke/logout, restart persistence')
finally:
    if started:
        docker('rm', '-f', name)
    if created:
        docker('volume', 'rm', volume)
