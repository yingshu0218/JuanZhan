import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import COOKIE, digest, set_password
from juanzhan.config import Settings
from juanzhan.database import connect, migrate

PASSWORD = 'test-only-long-password'


@pytest.fixture
def settings(tmp_path):
    config = Settings(tmp_path / 'archive', 'converter-test-token')
    config.prepare_archive()
    migrate(config.database)
    set_password(config, PASSWORD)
    return config


@pytest.fixture
def client(settings):
    with TestClient(create_app('archive', settings), base_url='https://archive.test') as client:
        yield client


def login(client):
    initial = client.get('/api/v1/auth/session')
    assert initial.status_code == 200
    response = client.post('/api/v1/auth/login', json={'username':'admin','password':PASSWORD},
                           headers={'X-CSRF-Token':initial.json()['csrf_token']})
    assert response.status_code == 200, response.text
    return response.json()['csrf_token']


def test_login_rotation_cookie_flags_and_logout(client, settings):
    initial = client.get('/api/v1/auth/session')
    old_cookie = client.cookies.get(COOKIE)
    csrf = initial.json()['csrf_token']
    cookie_header = initial.headers['set-cookie'].lower()
    for flag in ('httponly', 'secure', 'samesite=strict', 'path=/api/v1'):
        assert flag in cookie_header
    assert initial.headers['cache-control'] == 'no-store'
    for method in (client.get, client.post):
        assert method('/api/v1/documents').status_code == 401
    assert client.post('/api/v1/auth/login', json={'username':'admin','password':PASSWORD}).status_code == 403
    response = client.post('/api/v1/auth/login', json={'username':'admin','password':PASSWORD}, headers={'X-CSRF-Token':csrf})
    assert response.status_code == 200
    assert client.cookies.get(COOKIE) != old_cookie
    assert response.json()['csrf_token'] != csrf
    with connect(settings.database) as db:
        assert not db.execute('SELECT 1 FROM auth_sessions WHERE token_hash=?', (digest(old_cookie),)).fetchone()
    assert client.get('/api/v1/auth/session').json()['authenticated']
    assert client.post('/api/v1/auth/logout').status_code == 403
    response = client.post('/api/v1/auth/logout', headers={'X-CSRF-Token':response.json()['csrf_token']})
    assert response.status_code == 204
    assert client.get('/api/v1/auth/tokens').status_code == 401


def test_token_lifecycle_and_bearer_csrf_exemption(client, settings):
    csrf = login(client)
    assert client.post('/api/v1/auth/tokens', json={'name':'automation'}).status_code == 403
    created = client.post('/api/v1/auth/tokens', json={'name':'automation'}, headers={'X-CSRF-Token':csrf})
    assert created.status_code == 201
    assert created.headers['cache-control'] == 'no-store'
    token = created.json()['token']
    id = created.json()['id']
    listed = client.get('/api/v1/auth/tokens')
    assert listed.json()[0]['id'] == id
    assert token not in listed.text and 'token_hash' not in listed.text
    with connect(settings.database) as db:
        assert db.execute('SELECT token_hash FROM auth_api_tokens').fetchone() == (digest(token),)
        assert token not in str(db.execute('SELECT * FROM auth_api_tokens').fetchall())
        assert PASSWORD not in db.execute('SELECT password_hash FROM auth_admin').fetchone()[0]
    headers = {'Authorization':'Bearer ' + token}
    # Valid Bearer reaches routing on writes without CSRF; business handler not implemented yet.
    assert client.post('/api/v1/documents/upload', headers=headers).status_code == 404
    assert client.get('/api/v1/auth/tokens', headers=headers).status_code == 403
    assert client.post('/api/v1/auth/tokens', headers=headers, json={'name':'escalation'}).status_code == 403
    assert client.get('/api/v1/documents', headers={'Authorization':'Bearer invalid'}).status_code == 401
    assert client.delete('/api/v1/auth/tokens/'+id).status_code == 403
    assert client.delete('/api/v1/auth/tokens/'+id, headers={'X-CSRF-Token':csrf}).status_code == 204
    assert client.get('/api/v1/documents', headers=headers).status_code == 401
    assert client.get('/api/v1/auth/tokens').json() == []


def test_session_and_token_expiry(client, settings):
    csrf = login(client)
    issued = client.post('/api/v1/auth/tokens', json={'name':'short'}, headers={'X-CSRF-Token':csrf}).json()
    with connect(settings.database) as db:
        db.execute('UPDATE auth_api_tokens SET expires_at=?', (int(time.time())-1,))
        db.execute('UPDATE auth_sessions SET expires_at=?', (int(time.time())-1,))
        db.commit()
    assert client.get('/api/v1/auth/tokens').status_code == 401
    assert client.get('/api/v1/documents', headers={'Authorization':'Bearer '+issued['token']}).status_code == 401
    assert not client.get('/api/v1/auth/session').json()['authenticated']


def test_invalid_login_throttle_and_validation(client, settings):
    csrf = client.get('/api/v1/auth/session').json()['csrf_token']
    headers = {'X-CSRF-Token':csrf}
    payload = {'username':'admin','password':'incorrect'}
    for _ in range(5):
        assert client.post('/api/v1/auth/login', json=payload, headers=headers).status_code == 401
    assert client.post('/api/v1/auth/login', json=payload, headers=headers).status_code == 429
    with connect(settings.database) as db:
        db.execute('UPDATE auth_login_throttle SET window_start=?', (int(time.time())-61,))
        db.commit()
    assert client.post('/api/v1/auth/login', json={'username':'admin','password':PASSWORD}, headers=headers).status_code == 200
    response = client.post('/api/v1/auth/login', json={'username':'admin','password':{'secret':PASSWORD}}, headers=headers)
    assert response.status_code == 422
    assert PASSWORD not in response.text
    assert response.json()['error']['code'] == 'INVALID_REQUEST'


def test_cross_site_login_and_cookie_writes_rejected(client):
    csrf = client.get('/api/v1/auth/session').json()['csrf_token']
    response = client.post('/api/v1/auth/login', json={'username':'admin','password':PASSWORD},
                           headers={'X-CSRF-Token':csrf,'Sec-Fetch-Site':'cross-site'})
    assert response.status_code == 403
    csrf = login(client)
    assert client.post('/api/v1/auth/tokens', json={'name':'blocked'}, headers={'X-CSRF-Token':csrf,'Sec-Fetch-Site':'cross-site'}).status_code == 403


def test_reset_password_revokes_existing_auth(client, settings):
    csrf = login(client)
    token = client.post('/api/v1/auth/tokens', json={'name':'old'}, headers={'X-CSRF-Token':csrf}).json()['token']
    set_password(settings, 'new-test-password-long')
    assert client.get('/api/v1/auth/tokens').status_code == 401
    assert client.get('/api/v1/documents', headers={'Authorization':'Bearer '+token}).status_code == 401


def test_auth_persists_across_app_restart(settings):
    with TestClient(create_app('archive', settings), base_url='https://archive.test') as first:
        login(first)
        cookie = first.cookies.get(COOKIE)
    with TestClient(create_app('archive', settings), base_url='https://archive.test') as second:
        second.cookies.set(COOKIE, cookie)
        assert second.get('/api/v1/auth/tokens').status_code == 200


def test_missing_admin_never_grants_access(tmp_path):
    settings = Settings(tmp_path, '')
    with TestClient(create_app('archive', settings), base_url='https://archive.test') as client:
        csrf = client.get('/api/v1/auth/session').json()['csrf_token']
        assert client.post('/api/v1/auth/login', json={'username':'admin','password':PASSWORD}, headers={'X-CSRF-Token':csrf}).status_code == 503
        assert client.get('/api/v1/auth/tokens').status_code == 401


def test_anonymous_session_capacity_and_expiry_cleanup(client, settings):
    with connect(settings.database) as db:
        db.executemany('INSERT INTO auth_sessions VALUES (?,?,0,?)',
                       [(str(i), 'csrf', int(time.time())+600) for i in range(1000)])
        db.commit()
    assert client.get('/api/v1/auth/session').status_code == 429
    with connect(settings.database) as db:
        db.execute('UPDATE auth_sessions SET expires_at=?', (int(time.time())-1,))
        db.commit()
    assert client.get('/api/v1/auth/session').status_code == 200
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM auth_sessions').fetchone()[0] == 1


def test_validation_and_wrong_credentials_do_not_leak(client):
    csrf = login(client)
    headers = {'X-CSRF-Token':csrf}
    for body in ({'name':' '}, {'name':'token', 'expires_in_days':0},
                 {'name':'token', 'expires_in_days':True}, {'name':'token','extra':'hidden'}):
        response = client.post('/api/v1/auth/tokens', json=body, headers=headers)
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'INVALID_REQUEST'
    response = client.post('/api/v1/auth/login', json={'username':'unknown','password':PASSWORD}, headers=headers)
    assert response.status_code == 401
    assert PASSWORD not in response.text


def test_migration_upgrade_preserves_baseline_data(tmp_path):
    from juanzhan.database import MIGRATIONS
    baseline = tmp_path / 'baseline'
    baseline.mkdir()
    (baseline / '0001_archive_v04.sql').write_bytes((MIGRATIONS / '0001_archive_v04.sql').read_bytes())
    database = tmp_path / 'archive.db'
    migrate(database, baseline)
    with connect(database) as db:
        db.execute("INSERT INTO spaces VALUES ('existing','Original','now','now')")
        db.commit()
    migrate(database)
    migrate(database)
    with connect(database) as db:
        assert db.execute("SELECT name FROM spaces WHERE id='existing'").fetchone() == ('Original',)
        assert db.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall() == [('0.4.0',), ('0.4.1',), ('0.4.2',)]
        assert db.execute('SELECT count(*) FROM auth_sessions').fetchone() == (0,)


def test_cookie_setting_rejects_typo(monkeypatch):
    monkeypatch.setenv('JUANZHAN_COOKIE_SECURE','treu')
    with pytest.raises(ValueError, match='JUANZHAN_COOKIE_SECURE'):
        Settings.from_env()
