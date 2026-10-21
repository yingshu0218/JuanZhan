"""Bounded OAuth authorization-code/PKCE service for the read-only document resource."""
import base64
import hashlib
import json
import re
import secrets
import time
import uuid
from typing import Literal
from urllib.parse import parse_qsl,urlsplit,urlencode,unquote
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from .auth import COOKIE,digest,require_session,session_write
from .database import connect

SCOPE='documents:read'
HEADERS={'Cache-Control':'no-store','Pragma':'no-cache','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}
class OAuthError(Exception):
    def __init__(self,error,description='Request rejected',status=400):
        self.error=error;self.description=description;self.status=status
def problem(error,description='Request rejected',status=400):raise OAuthError(error,description,status)
def response_error(exc):
    headers=dict(HEADERS)
    if exc.status==401:headers['WWW-Authenticate']='Basic realm="OAuth client"'
    return JSONResponse({'error':exc.error,'error_description':exc.description},status_code=exc.status,headers=headers)
def resource(settings):return settings.public_url+'/api/v1/agent/mcp' if settings.public_url else ''
def enabled(settings):
    if not settings.public_url:problem('temporarily_unavailable','OAuth is not configured',404)
def challenge(settings):
    return 'Bearer resource_metadata="'+settings.public_url+'/.well-known/oauth-protected-resource", scope="'+SCOPE+'"' if settings.public_url else 'Bearer'

class Input(BaseModel):model_config=ConfigDict(extra='forbid')
class Registration(Input):
    client_name: str=Field(default='External Agent',min_length=1,max_length=100,pattern=r'^[^\x00-\x1f\x7f]+$')
    redirect_uris: list[str]=Field(min_length=1,max_length=10)
    token_endpoint_auth_method: Literal['none','client_secret_basic','client_secret_post']='client_secret_basic'
    grant_types: list[Literal['authorization_code','refresh_token']]=['authorization_code','refresh_token']
    response_types: list[Literal['code']]=['code']
    scope: Literal['documents:read']=SCOPE
class Authorization(Input):
    client_id: str=Field(min_length=1,max_length=128)
    redirect_uri: str=Field(min_length=1,max_length=2048)
    response_type: Literal['code']
    code_challenge: str=Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code_challenge_method: Literal['S256']
    resource: str=Field(min_length=1,max_length=2048)
    scope: Literal['documents:read']=SCOPE
    state: str=Field(default='',max_length=1024)
class Consent(Input):
    request_id: str=Field(pattern=r'^[0-9a-f]{32}$')
    decision: Literal['allow','deny']
    space_ids: list[str]=Field(default=[],max_length=50)

def validate(model,data):
    try:return model.model_validate(data)
    except (ValidationError,ValueError):problem('invalid_request','Parameters do not match the supported schema')
def redirect_valid(value):
    try:
        parsed=urlsplit(value);port=parsed.port
        return (len(value)<=2048 and not any(ord(c)<33 or ord(c)>126 for c in value) and '\\' not in value
            and bool(parsed.hostname) and not parsed.username and not parsed.password and not parsed.fragment
            and (port is None or 1<=port<=65535)
            and (parsed.scheme=='https' or (parsed.scheme=='http' and parsed.hostname in ('127.0.0.1','::1')))
            and not any(key in ('code','error','state','iss') for key,_ in parse_qsl(parsed.query)))
    except ValueError:return False
async def body(request,json_mode=False):
    expected='application/json' if json_mode else 'application/x-www-form-urlencoded'
    if request.headers.get('content-type','').split(';')[0].strip().lower()!=expected:problem('invalid_request','Unexpected content type',415)
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>16384:problem('invalid_request','Request exceeds 16 KiB',413)
    try:
        if json_mode:
            value=json.loads(data,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value,dict):raise ValueError()
            return value
        values=parse_qsl(data.decode('utf-8'),keep_blank_values=True,encoding='utf-8',errors='strict',max_num_fields=20)
        if len(dict(values))!=len(values):raise ValueError()
        return dict(values)
    except (ValueError,UnicodeError,RecursionError):problem('invalid_request','Malformed or repeated parameters')
def throttle(settings,request,kind,limit=60):
    now=int(time.time())//60;key=kind+':'+digest(request.client.host if request.client else 'unknown')
    with connect(settings.database) as db:
        db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM oauth_rate WHERE window<?',(now-2,))
        row=db.execute('SELECT window,count FROM oauth_rate WHERE key=?',(key,)).fetchone()
        count=row[1] if row and row[0]==now else 0
        if count>=limit or (not row and db.execute('SELECT count(*) FROM oauth_rate').fetchone()[0]>=4096):problem('temporarily_unavailable','Request budget exceeded',429)
        db.execute('INSERT INTO oauth_rate VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET window=excluded.window,count=excluded.count',(key,now,count+1));db.commit()
def client(db,id):
    db.row_factory=__import__('sqlite3').Row
    row=db.execute('SELECT * FROM oauth_clients WHERE id=?',(id,)).fetchone()
    if row is None:problem('invalid_client','Client authentication failed',401)
    return row
def authenticate(db,request,values):
    id=values.get('client_id');secret=values.get('client_secret');method='client_secret_post' if secret is not None else 'none'
    authorization=request.headers.get('authorization')
    if authorization:
        if len(authorization)>2048:problem('invalid_client','Client authentication failed',401)
        if id is not None or secret is not None:problem('invalid_request','Use one client authentication method')
        try:
            scheme,encoded=authorization.split(' ',1)
            if scheme.lower()!='basic':raise ValueError()
            id,secret=base64.b64decode(encoded,validate=True).decode('utf-8').split(':',1)
            id,secret=unquote(id),unquote(secret);method='client_secret_basic'
        except (ValueError,UnicodeError):problem('invalid_client','Client authentication failed',401)
    if not isinstance(id,str) or len(id)>128:problem('invalid_client','Client authentication failed',401)
    row=client(db,id)
    if method!=row['auth_method'] or (method!='none' and (not isinstance(secret,str) or not secrets.compare_digest(digest(secret),row['secret_hash'] or ''))):problem('invalid_client','Client authentication failed',401)
    return row
def checked_resource(settings,value):
    if value!=resource(settings):problem('invalid_target','Use the advertised document resource')
def token_response(raw,refresh,expires):
    return {'access_token':raw,'token_type':'Bearer','expires_in':expires,'scope':SCOPE,**({'refresh_token':refresh} if refresh else {})}

def router(settings):
    routes=APIRouter()
    @routes.get('/.well-known/oauth-authorization-server')
    def metadata():
        enabled(settings);base=settings.public_url
        return JSONResponse({'issuer':base,'authorization_endpoint':base+'/oauth/authorize','token_endpoint':base+'/oauth/token',
            'registration_endpoint':base+'/oauth/register','revocation_endpoint':base+'/oauth/revoke','scopes_supported':[SCOPE],
            'response_types_supported':['code'],'grant_types_supported':['authorization_code','refresh_token'],
            'code_challenge_methods_supported':['S256'],'token_endpoint_auth_methods_supported':['none','client_secret_basic','client_secret_post'],
            'authorization_response_iss_parameter_supported':True},headers=HEADERS)
    @routes.get('/.well-known/oauth-protected-resource')
    @routes.get('/.well-known/oauth-protected-resource/api/v1/agent/mcp')
    def protected_metadata():
        enabled(settings)
        return JSONResponse({'resource':resource(settings),'authorization_servers':[settings.public_url],'scopes_supported':[SCOPE],'bearer_methods_supported':['header']},headers=HEADERS)
    @routes.post('/oauth/register',status_code=201)
    async def register(request: Request):
        enabled(settings);throttle(settings,request,'register',10);data=validate(Registration,await body(request,True))
        if (len(set(data.redirect_uris))!=len(data.redirect_uris) or not all(redirect_valid(uri) for uri in data.redirect_uris)
            or set(data.grant_types) not in ({'authorization_code'},{'authorization_code','refresh_token'})
            or len(set(data.grant_types))!=len(data.grant_types) or data.response_types!=['code']):problem('invalid_client_metadata','Invalid client redirect or grant metadata')
        id='jzc_'+secrets.token_urlsafe(24);secret=secrets.token_urlsafe(32) if data.token_endpoint_auth_method!='none' else None;now=int(time.time())
        with connect(settings.database) as db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM oauth_clients WHERE last_used_at IS NULL AND created_at<?',(now-86400,))
            if db.execute('SELECT count(*) FROM oauth_clients').fetchone()[0]>=1000:problem('temporarily_unavailable','Client registry capacity reached',429)
            db.execute('INSERT INTO oauth_clients VALUES (?,?,?,?,?,?,?,NULL)',(id,data.client_name,json.dumps(data.redirect_uris),data.token_endpoint_auth_method,digest(secret) if secret else None,json.dumps(data.grant_types),now));db.commit()
        return JSONResponse({**data.model_dump(),'client_id':id,'client_id_issued_at':now,**({'client_secret':secret,'client_secret_expires_at':0} if secret else {})},status_code=201,headers=HEADERS)
    @routes.post('/api/v1/oauth/requests',status_code=201)
    async def prepare(request: Request):
        enabled(settings);data=validate(Authorization,await body(request,True));checked_resource(settings,data.resource);now=int(time.time());id=uuid.uuid4().hex
        with session_write(settings,request) as db:
            row=client(db,data.client_id)
            if data.redirect_uri not in json.loads(row['redirects_json']):problem('invalid_request','Redirect URI is not registered')
            db.execute('DELETE FROM oauth_requests WHERE expires_at<=?',(now,))
            if db.execute('SELECT count(*) FROM oauth_requests').fetchone()[0]>=1000:problem('temporarily_unavailable','Authorization request capacity reached',429)
            db.execute('INSERT INTO oauth_requests VALUES (?,?,?,?,?)',(id,data.client_id,digest(request.cookies.get(COOKIE,'')),data.model_dump_json(),now+600))
            spaces=[{'id':r[0],'name':r[1]} for r in db.execute('SELECT id,name FROM spaces ORDER BY name,id LIMIT 1001')]
            if len(spaces)>1000:problem('temporarily_unavailable','Space catalog exceeds authorization budget',413)
        return JSONResponse({'request_id':id,'client_name':row['name'],'redirect_uri':data.redirect_uri,'scope':SCOPE,'spaces':spaces,'expires_in':600},status_code=201,headers=HEADERS)
    @routes.post('/api/v1/oauth/authorize')
    async def consent(request: Request):
        enabled(settings);data=validate(Consent,await body(request,True));now=int(time.time())
        with session_write(settings,request) as db:
            row=db.execute('SELECT client_id,params_json FROM oauth_requests WHERE id=? AND session_hash=? AND expires_at>?',(data.request_id,digest(request.cookies.get(COOKIE,'')),now)).fetchone()
            if row is None:problem('invalid_request','Authorization request expired or already used')
            params=json.loads(row[1]);values={'iss':settings.public_url}
            if params['state']:values['state']=params['state']
            if data.decision=='allow':
                if not data.space_ids or len(set(data.space_ids))!=len(data.space_ids) or any(len(id)>255 or db.execute('SELECT 1 FROM spaces WHERE id=?',(id,)).fetchone() is None for id in data.space_ids):problem('invalid_request','Choose valid, unique space grants')
                db.execute('DELETE FROM oauth_codes WHERE expires_at<=?',(now,))
                if db.execute('SELECT count(*) FROM oauth_codes').fetchone()[0]>=1000:problem('temporarily_unavailable','Authorization code capacity reached',429)
                code='jzac_'+secrets.token_urlsafe(32)
                db.execute('INSERT INTO oauth_codes VALUES (?,?,?,?,?,?,?)',(digest(code),row[0],params['redirect_uri'],params['code_challenge'],params['resource'],json.dumps(data.space_ids),now+120));values['code']=code
                db.execute('UPDATE oauth_clients SET last_used_at=? WHERE id=?',(now,row[0]))
            else:values['error']='access_denied'
            db.execute('DELETE FROM oauth_requests WHERE id=?',(data.request_id,))
        redirect=params['redirect_uri']+('&' if '?' in params['redirect_uri'] else '?')+urlencode(values)
        return JSONResponse({'redirect_uri':redirect},headers=HEADERS)
    @routes.post('/oauth/token')
    async def exchange(request: Request):
        enabled(settings);throttle(settings,request,'token');values=await body(request)
        if set(values)-{'grant_type','client_id','client_secret','code','redirect_uri','code_verifier','refresh_token','resource','scope'}:problem('invalid_request','Unknown token parameter')
        checked_resource(settings,values.get('resource'))
        if values.get('scope',SCOPE)!=SCOPE:problem('invalid_scope')
        now=int(time.time())
        with connect(settings.database) as db:
            db.execute('BEGIN IMMEDIATE');registered=authenticate(db,request,values)
            raw='jza_'+secrets.token_urlsafe(32);refresh=None;expires=3600
            if values.get('grant_type')=='authorization_code':
                verifier=values.get('code_verifier','')
                if not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier):problem('invalid_grant')
                code=db.execute('SELECT * FROM oauth_codes WHERE code_hash=? AND client_id=? AND expires_at>?',(digest(values.get('code','')),registered['id'],now)).fetchone()
                expected=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                if code is None or values.get('redirect_uri')!=code['redirect_uri'] or code['resource']!=resource(settings) or not secrets.compare_digest(expected,code['challenge']):problem('invalid_grant')
                spaces=json.loads(code['spaces_json'])
                if any(db.execute('SELECT 1 FROM spaces WHERE id=?',(id,)).fetchone() is None for id in spaces):problem('invalid_grant')
                db.execute('DELETE FROM agent_tokens WHERE expires_at<=?',(now,))
                if db.execute('SELECT count(*) FROM agent_tokens').fetchone()[0]>=1000:problem('temporarily_unavailable','Credential capacity reached',429)
                token_id=uuid.uuid4().hex;grant_id=uuid.uuid4().hex;expiry=now+30*86400
                if 'refresh_token' in json.loads(registered['grants_json']):refresh='jzr_'+secrets.token_urlsafe(32)
                db.execute('INSERT INTO agent_tokens(id,name,token_hash,created_at,expires_at) VALUES (?,?,?,?,?)',(token_id,('OAuth '+registered['name'])[:100],digest(raw),now,expiry if refresh else now+3600))
                db.executemany('INSERT INTO agent_token_spaces VALUES (?,?)',[(token_id,id) for id in spaces])
                db.execute('INSERT INTO oauth_grants VALUES (?,?,?,?,?,?,?)',(grant_id,token_id,registered['id'],digest(refresh) if refresh else None,expiry if refresh else now+3600,now+3600,resource(settings)))
                db.execute('DELETE FROM oauth_codes WHERE code_hash=?',(code['code_hash'],))
            elif values.get('grant_type')=='refresh_token':
                hashed=digest(values.get('refresh_token',''))
                grant=db.execute('SELECT * FROM oauth_grants WHERE refresh_hash=? AND client_id=? AND expires_at>?',(hashed,registered['id'],now)).fetchone()
                if grant is None:
                    old=db.execute('SELECT g.token_id FROM oauth_refresh_history h JOIN oauth_grants g ON g.id=h.grant_id WHERE h.token_hash=? AND g.client_id=?',(hashed,registered['id'])).fetchone()
                    if old:db.execute('DELETE FROM agent_tokens WHERE id=?',(old[0],));db.commit()
                    problem('invalid_grant')
                if grant['resource']!=resource(settings):problem('invalid_target')
                if db.execute('SELECT count(*) FROM oauth_refresh_history WHERE grant_id=?',(grant['id'],)).fetchone()[0]>=1000:
                    db.execute('DELETE FROM agent_tokens WHERE id=?',(grant['token_id'],));db.commit();problem('invalid_grant','Authorize again after rotation budget')
                refresh='jzr_'+secrets.token_urlsafe(32)
                expires=min(3600,grant['expires_at']-now)
                db.execute('INSERT INTO oauth_refresh_history VALUES (?,?)',(hashed,grant['id']))
                db.execute('UPDATE oauth_grants SET refresh_hash=?,access_expires_at=? WHERE id=?',(digest(refresh),min(now+3600,grant['expires_at']),grant['id']))
                db.execute('UPDATE agent_tokens SET token_hash=? WHERE id=?',(digest(raw),grant['token_id']))
            else:problem('unsupported_grant_type')
            db.commit()
        return JSONResponse(token_response(raw,refresh,expires),headers=HEADERS)
    @routes.post('/oauth/revoke')
    async def revoke(request: Request):
        enabled(settings);throttle(settings,request,'revoke');values=await body(request)
        if set(values)-{'token','token_type_hint','client_id','client_secret'} or not 1<=len(values.get('token',''))<=256:problem('invalid_request')
        with connect(settings.database) as db:
            db.execute('BEGIN IMMEDIATE');registered=authenticate(db,request,values);hashed=digest(values['token'])
            rows=db.execute('SELECT g.token_id FROM oauth_grants g JOIN agent_tokens t ON t.id=g.token_id WHERE g.client_id=? AND (g.refresh_hash=? OR t.token_hash=? OR g.id IN (SELECT grant_id FROM oauth_refresh_history WHERE token_hash=?))',(registered['id'],hashed,hashed,hashed)).fetchall()
            for row in rows:db.execute('DELETE FROM agent_tokens WHERE id=?',(row[0],))
            db.commit()
        return JSONResponse({},headers=HEADERS)
    @routes.get('/api/v1/oauth/clients')
    def clients(request: Request):
        require_session(request)
        with connect(settings.database) as db:
            return JSONResponse([{'id':r[0],'name':r[1],'redirect_uris':json.loads(r[2]),'auth_method':r[3]} for r in db.execute('SELECT id,name,redirects_json,auth_method FROM oauth_clients ORDER BY created_at,id')],headers=HEADERS)
    @routes.delete('/api/v1/oauth/clients/{id}',status_code=204)
    def delete_client(id: str,request: Request):
        with session_write(settings,request) as db:db.execute('DELETE FROM oauth_clients WHERE id=?',(id,))
    return routes
