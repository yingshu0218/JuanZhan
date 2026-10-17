from pathlib import Path
from fastapi.testclient import TestClient
from juanzhan.apps import create_app
from juanzhan.config import Settings
from juanzhan import web


def test_shell_is_public_but_data_and_non_get_requests_remain_protected(tmp_path,monkeypatch):
    root=tmp_path/'web';(root/'assets').mkdir(parents=True)
    (root/'index.html').write_text('<html>Archive</html>')
    (root/'favicon.svg').write_text('<svg/>')
    (root/'assets'/'app-hash.js').write_text('console.log("compiled")')
    monkeypatch.setattr(web,'WEB_ROOT',root)
    with TestClient(create_app('archive',Settings(tmp_path/'data',''))) as client:
        response=client.get('/')
        assert response.status_code==200 and 'Archive' in response.text
        assert response.headers['Cache-Control']=='no-store'
        assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
        assert client.head('/').status_code==200
        assert client.get('/assets/app-hash.js').status_code==200
        assert client.get('/favicon.svg').status_code==200
        assert client.get('/api/v1/documents').status_code==401
        assert client.post('/assets/app-hash.js').status_code==401
        assert client.get('/assets/%2e%2e/%2e%2e/data/database/archive.sqlite3').status_code==404
        assert client.get('/assets/does-not-exist').status_code==404
        assert client.get('/arbitrary-page').status_code==401


def test_missing_build_does_not_disable_api_or_expose_paths(tmp_path,monkeypatch):
    monkeypatch.setattr(web,'WEB_ROOT',tmp_path/'missing')
    with TestClient(create_app('archive',Settings(tmp_path/'data',''))) as client:
        response=client.get('/')
        assert response.status_code==503 and response.json()['error']['code']=='WEB_NOT_BUILT'
        assert str(tmp_path) not in response.text
        assert client.get('/healthz').status_code==200
        assert client.get('/api/v1/auth/session').status_code==200
