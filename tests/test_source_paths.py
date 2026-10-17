import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.source_paths import SourceMounts, SourcePathError, components, parse_mounts


@pytest.mark.parametrize('path', ['/etc/passwd', '../secret', 'a/../b', './a', 'a//b',
    'a/', 'C:/secret', r'a\b', 'file:\\secret', 'a\x00b', 'a\nb', '', '//server/x', '\ud800'])
def test_reject_noncanonical_relative_paths(path):
    with pytest.raises(SourcePathError, match='INVALID_SOURCE_PATH'):
        components(path)


def test_preserve_actual_unicode_and_case():
    assert components('资料/e\u0301.TXT') == ['资料', 'e\u0301.TXT']
    assert components('资料/é.txt') != components('资料/e\u0301.TXT')


@pytest.mark.parametrize('raw', ['[]', '{"alias":"/"}', '{"alias":"relative"}',
    '{"bad/alias":"/tmp"}', '{"x":"/tmp","x":"/sys"}', '{"x":1}',
    '{"x":"/tmp/../sys"}', '{"x":"//sys"}', '{"x":"/tmp/"}', '{'])
def test_reject_config_without_echoing_paths(raw):
    with pytest.raises(ValueError, match='^Invalid source mount configuration$'):
        parse_mounts(raw)


def test_real_readonly_and_writable_mounts(tmp_path):
    writable = tmp_path / 'writable'
    writable.mkdir()
    # chmod is not a read-only mount and must never qualify, even under root.
    writable.chmod(0o555)
    mounts = SourceMounts((('writable', str(writable)), ('offline', str(tmp_path / 'absent')),
                           ('system', '/sys')))
    statuses = {x['alias']: x for x in mounts.list()}
    assert statuses['writable']['error_code'] == 'SOURCE_NOT_READ_ONLY'
    assert statuses['offline']['status'] == 'offline'
    assert statuses['system']['status'] == 'ready'
    with mounts.open('system', 'devices/system/cpu/online') as stream:
        assert stream.read().strip()
        assert not stream.writable()
    with pytest.raises(SourcePathError, match='SOURCE_FILE_MISSING'):
        with mounts.open('system', 'this-does-not-exist'):
            pass
    assert mounts.list() == list(statuses.values())
    for alias in ('/sys', 'unknown', '../system'):
        with pytest.raises(SourcePathError, match='SOURCE_ALIAS_NOT_ALLOWED'):
            with mounts.root(alias):
                pass


def test_symlink_root_and_leaf_rejected(tmp_path):
    (tmp_path / 'link').symlink_to('/sys', target_is_directory=True)
    mounts = SourceMounts((('linked', str(tmp_path / 'link')), ('system', '/sys')))
    assert mounts.list()[0]['status'] == 'unavailable'
    # /sys/class entries resolve via symlinks; even in-root links are not followed.
    links = [p for p in Path('/sys/class').glob('*/*') if p.is_symlink()]
    assert links, 'Linux sysfs symlink fixture required'
    with pytest.raises(SourcePathError):
        with mounts.open('system', str(links[0].relative_to('/sys'))):
            pass


def test_env_and_authenticated_discovery_without_paths(tmp_path, monkeypatch):
    monkeypatch.setenv('JUANZHAN_SOURCE_MOUNTS', json.dumps({'docs': '/sys', 'offline': str(tmp_path / 'absent')}))
    monkeypatch.setenv('JUANZHAN_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('JUANZHAN_COOKIE_SECURE', 'false')
    settings = Settings.from_env()
    settings.prepare_archive()
    from juanzhan.database import migrate
    migrate(settings.database)
    set_password(settings, 'mount-test-password-42')
    with TestClient(create_app('archive', settings)) as client:
        assert client.get('/api/v1/source-mounts').status_code == 401
        session = client.get('/api/v1/auth/session').json()
        response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'mount-test-password-42'},
                               headers={'X-CSRF-Token': session['csrf_token']})
        assert response.status_code == 200
        response = client.get('/api/v1/source-mounts')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['items'] == [
            {'alias': 'docs', 'status': 'ready', 'error_code': None},
            {'alias': 'offline', 'status': 'offline', 'error_code': 'SOURCE_OFFLINE'}]
        assert str(tmp_path) not in response.text and '/sys' not in response.text
