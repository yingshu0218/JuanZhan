"""OAuth lifecycle against actual SQLite, session cookies and HTTP routing."""
import base64
import hashlib
from dataclasses import replace
from urllib.parse import urlsplit,parse_qs
import pytest
from fastapi.testclient import TestClient
from test_auth import settings,login
from juanzhan.apps import create_app
from juanzhan.database import connect
from juanzhan.auth import set_password

@pytest.fixture
def oauth_client(settings):
    settings=replace(settings,public_url='https://archive.test')
    with TestClient(create_app('archive',settings),base_url=settings.public_url) as client:
        csrf={'X-CSRF-Token':login(client)}
        space=client.post('/api/v1/spaces',headers=csrf,json={'name':'Granted'}).json()['id']
        yield settings,client,csrf,space

def grant(fixture,method='none'):
    settings,client,csrf,space=fixture
    registration=client.post('/oauth/register',json={'client_name':'Generic test','redirect_uris':['http://127.0.0.1:41234/callback'],'token_endpoint_auth_method':method})
    assert registration.status_code==201,registration.text
    info=registration.json();verifier='x'*64
    params={'client_id':info['client_id'],'redirect_uri':info['redirect_uris'][0],'response_type':'code','code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256','resource':settings.public_url+'/api/v1/agent/mcp','state':'test-state'}
    request=client.post('/api/v1/oauth/requests',headers=csrf,json=params)
    assert request.status_code==201,request.text
    consent=client.post('/api/v1/oauth/authorize',headers=csrf,json={'request_id':request.json()['request_id'],'decision':'allow','space_ids':[space]})
    assert consent.status_code==200,consent.text
    callback=parse_qs(urlsplit(consent.json()['redirect_uri']).query)
    assert callback['state']==['test-state'] and callback['iss']==[settings.public_url]
    values={'grant_type':'authorization_code','client_id':info['client_id'],'code':callback['code'][0],'redirect_uri':params['redirect_uri'],'code_verifier':verifier,'resource':params['resource']}
    headers={}
    if method=='client_secret_post':values['client_secret']=info['client_secret']
    if method=='client_secret_basic':
        headers['Authorization']='Basic '+base64.b64encode((info['client_id']+':'+info['client_secret']).encode()).decode()
        del values['client_id']
    return info,values,headers

@pytest.mark.parametrize('method',['none','client_secret_post','client_secret_basic'])
def test_pkce_rotation_reuse_revokes_family(oauth_client,method):
    settings,client,csrf,space=oauth_client
    info,values,headers=grant(oauth_client,method)
    wrong=client.post('/oauth/token',data={**values,'code_verifier':'y'*64},headers=headers)
    assert wrong.status_code==400 and wrong.json()['error']=='invalid_grant'
    issued=client.post('/oauth/token',data=values,headers=headers)
    assert issued.status_code==200,issued.text
    token=issued.json();assert token['expires_in']==3600
    assert client.post('/oauth/token',data=values,headers=headers).status_code==400
    bearer={'Authorization':'Bearer '+token['access_token']}
    assert client.get('/api/v1/agent/spaces',headers=bearer).status_code==200
    with connect(settings.database) as db:
        db.execute('UPDATE oauth_grants SET access_expires_at=0');db.commit()
    assert client.get('/api/v1/agent/spaces',headers=bearer).status_code==401
    refresh={key:value for key,value in values.items() if key in ('client_id','client_secret','resource')}
    refresh.update(grant_type='refresh_token',refresh_token=token['refresh_token'])
    rotated=client.post('/oauth/token',data=refresh,headers=headers)
    assert rotated.status_code==200,rotated.text
    current={'Authorization':'Bearer '+rotated.json()['access_token']}
    assert client.get('/api/v1/agent/spaces',headers=current).status_code==200
    assert client.get('/api/v1/documents',headers=current).status_code==403
    assert client.post('/oauth/token',data=refresh,headers=headers).status_code==400
    assert client.get('/api/v1/agent/spaces',headers=current).status_code==401

def test_discovery_csrf_redirect_resource_and_client_revoke(oauth_client):
    settings,client,csrf,space=oauth_client
    assert client.get('/.well-known/oauth-authorization-server',headers={'Host':'spoof.test'}).json()['issuer']==settings.public_url
    for uri in ('http://evil.test/callback','https://user:pass@evil.test/callback','https://evil.test/#fragment','file:///tmp/test'):
        assert client.post('/oauth/register',json={'redirect_uris':[uri]}).status_code==400
    assert client.post('/api/v1/oauth/requests',json={}).status_code in (400,403)
    info,values,headers=grant(oauth_client)
    assert client.post('/oauth/token',data={**values,'resource':'https://other.test'},headers=headers).json()['error']=='invalid_target'
    issued=client.post('/oauth/token',data=values,headers=headers).json()
    assert client.delete('/api/v1/oauth/clients/'+info['client_id'],headers=csrf).status_code==204
    assert client.get('/api/v1/agent/spaces',headers={'Authorization':'Bearer '+issued['access_token']}).status_code==401
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM oauth_grants').fetchone()[0]==0

def test_oauth_disabled(settings):
    with TestClient(create_app('archive',settings)) as client:
        assert client.get('/.well-known/oauth-authorization-server').status_code==404
        assert client.post('/oauth/register',json={}).status_code==404

def test_revocation_reset_scope_and_mcp(oauth_client):
    settings,client,csrf,space=oauth_client
    info,values,headers=grant(oauth_client)
    issued=client.post('/oauth/token',data=values).json()
    bearer={'Authorization':'Bearer '+issued['access_token']}
    other=client.post('/api/v1/spaces',headers=csrf,json={'name':'Unapproved'}).json()['id']
    assert client.get('/api/v1/agent/catalog',headers=bearer,params={'space_id':other}).status_code==404
    from test_agents import rpc
    assert rpc(client,bearer,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'generic','version':'1'}}).status_code==200
    revoked=client.post('/oauth/revoke',data={'client_id':info['client_id'],'token':issued['refresh_token']})
    assert revoked.status_code==200
    assert client.get('/api/v1/agent/spaces',headers=bearer).status_code==401
    info,values,headers=grant(oauth_client)
    set_password(settings,'replacement-password')
    assert client.post('/oauth/token',data=values).status_code==400
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0]==0

def test_request_budgets_and_client_auth(oauth_client):
    settings,client,csrf,space=oauth_client
    assert client.post('/oauth/register',content='x'*17000,headers={'Content-Type':'application/json'}).status_code==413
    assert client.post('/oauth/token',content='grant_type=x&grant_type=y',headers={'Content-Type':'application/x-www-form-urlencoded'}).status_code==400
    assert client.post('/oauth/register',json={'redirect_uris':['https://client.test/callback?code=existing']}).status_code==400
    info,values,headers=grant(oauth_client,'client_secret_post')
    assert client.post('/oauth/token',data={**values,'client_secret':'wrong'}).status_code==401
    issued=client.post('/oauth/token',data=values).json()
    assert client.delete('/api/v1/oauth/clients/'+info['client_id']).status_code==403
    assert client.get('/api/v1/agent/spaces',headers={'Authorization':'Bearer '+issued['access_token']}).status_code==200

def test_consent_denial_and_one_use(oauth_client):
    settings,client,csrf,space=oauth_client
    info=client.post('/oauth/register',json={'redirect_uris':['https://client.test/callback'],'token_endpoint_auth_method':'none'}).json()
    params={'client_id':info['client_id'],'redirect_uri':info['redirect_uris'][0],'response_type':'code','code_challenge':'x'*43,'code_challenge_method':'S256','resource':settings.public_url+'/api/v1/agent/mcp','state':'preserved'}
    assert client.post('/api/v1/oauth/requests',json=params).status_code==403
    assert client.post('/api/v1/oauth/requests',headers=csrf,json={**params,'redirect_uri':'https://other.test'}).status_code==400
    prepared=client.post('/api/v1/oauth/requests',headers=csrf,json=params).json()
    payload={'request_id':prepared['request_id'],'decision':'deny'}
    denied=client.post('/api/v1/oauth/authorize',headers=csrf,json=payload)
    assert denied.status_code==200
    callback=parse_qs(urlsplit(denied.json()['redirect_uri']).query)
    assert callback['error']==['access_denied'] and callback['state']==['preserved']
    assert client.post('/api/v1/oauth/authorize',headers=csrf,json=payload).status_code==400

def test_backup_restore_clears_active_grants_and_pending_codes(oauth_client,tmp_path):
    from juanzhan.backup import create,restore
    settings,client,csrf,space=oauth_client
    info,values,headers=grant(oauth_client)
    issued=client.post('/oauth/token',data=values).json()
    grant(oauth_client)  # A second approved request leaves an unexchanged code.
    backup=tmp_path/'backup';target=tmp_path/'restored'
    create(settings,backup);restore(backup,target)
    restored=replace(settings,data_dir=target)
    with connect(restored.database) as db:
        assert db.execute('SELECT count(*) FROM oauth_grants').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM oauth_requests').fetchone()[0]==0
    with TestClient(create_app('archive',restored),base_url=restored.public_url) as after:
        assert after.get('/api/v1/agent/spaces',headers={'Authorization':'Bearer '+issued['access_token']}).status_code==401

def test_consent_is_bound_to_login_session(oauth_client):
    settings,client,csrf,space=oauth_client
    info=client.post('/oauth/register',json={'redirect_uris':['https://client.test/callback'],'token_endpoint_auth_method':'none'}).json()
    params={'client_id':info['client_id'],'redirect_uri':info['redirect_uris'][0],'response_type':'code','code_challenge':'x'*43,'code_challenge_method':'S256','resource':settings.public_url+'/api/v1/agent/mcp'}
    prepared=client.post('/api/v1/oauth/requests',headers=csrf,json=params).json()
    with TestClient(create_app('archive',settings),base_url=settings.public_url) as other:
        other_csrf={'X-CSRF-Token':login(other)}
        assert other.post('/api/v1/oauth/authorize',headers=other_csrf,json={'request_id':prepared['request_id'],'decision':'allow','space_ids':[space]}).status_code==400
    assert client.post('/api/v1/oauth/authorize',headers=csrf,json={'request_id':prepared['request_id'],'decision':'deny'}).status_code==200
