"""Space-granted, expiring read-only agent credentials, distinct from admin API keys."""
import secrets
import time
import uuid
from typing import Annotated
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from .auth import digest, fail, require_session, session_write, timestamp
from .database import connect

PREFIX='/api/v1/agent/'

class TokenInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=100,pattern=r'^[^\x00-\x1f\x7f]+$')
    space_ids: list[Annotated[str,Field(min_length=1,max_length=255)]]=Field(min_length=1,max_length=50)
    import_enabled: bool=Field(default=False,strict=True)
    expires_in_days: int=Field(default=7,ge=1,le=30,strict=True)

def authorize_agent(settings,request,token):
    now=int(time.time())
    with connect(settings.database) as db:
        db.execute('BEGIN IMMEDIATE')
        from .oauth import resource
        row=db.execute('SELECT t.id,t.rate_window,t.rate_count FROM agent_tokens t LEFT JOIN oauth_grants g ON g.token_id=t.id '
                       'WHERE t.token_hash=? AND t.expires_at>? AND (g.id IS NULL OR (g.access_expires_at>? AND g.resource=?))',
                       (digest(token),now,now,resource(settings))).fetchone()
        if row is None:fail(401,'UNAUTHORIZED','Valid authentication required')
        if not request.url.path.startswith(PREFIX):fail(403,'AGENT_READ_ONLY','Agent credentials only access the read-only agent API')
        window=now//60;count=row[2] if row[1]==window else 0
        if count>=60:fail(429,'AGENT_RATE_LIMIT','Agent request budget exceeded; retry next minute')
        db.execute('UPDATE agent_tokens SET rate_window=?,rate_count=? WHERE id=?',(window,count+1,row[0]))
        spaces=[r[0] for r in db.execute('SELECT space_id FROM agent_token_spaces WHERE token_id=? ORDER BY space_id',(row[0],))]
        db.commit()
    request.state.agent_id=row[0];request.state.agent_spaces=spaces
    return 'agent'

def allowed(request,space_id):
    if request.state.auth_mode=='agent' and space_id not in request.state.agent_spaces:
        fail(404,'NOT_FOUND','Space or document not found')

def router(settings):
    routes=APIRouter(prefix='/api/v1/agent-tokens')
    @routes.get('')
    def tokens(request: Request):
        require_session(request)
        with connect(settings.database) as db:
            values=db.execute('SELECT id,name,created_at,expires_at,import_enabled FROM agent_tokens WHERE expires_at>? ORDER BY created_at,id',(int(time.time()),)).fetchall()
            return [{'id':row[0],'name':row[1],'import_enabled':bool(row[4]),'created_at':timestamp(row[2]),'expires_at':timestamp(row[3]),
                     'space_ids':[r[0] for r in db.execute('SELECT space_id FROM agent_token_spaces WHERE token_id=? ORDER BY space_id',(row[0],))]} for row in values]
    @routes.post('',status_code=201)
    def create(body: TokenInput,request: Request):
        if len(set(body.space_ids))!=len(body.space_ids):fail(422,'INVALID_REQUEST','Space grants must be unique')
        raw='jza_'+secrets.token_urlsafe(32);id=uuid.uuid4().hex;now=int(time.time());expiry=now+body.expires_in_days*86400
        with session_write(settings,request) as db:
            for space in body.space_ids:
                if not isinstance(space,str) or len(space)>255 or db.execute('SELECT 1 FROM spaces WHERE id=?',(space,)).fetchone() is None:
                    fail(422,'INVALID_REQUEST','Unknown space grant')
            db.execute('DELETE FROM agent_tokens WHERE expires_at<=?',(now,))
            if db.execute('SELECT count(*) FROM agent_tokens').fetchone()[0]>=1000:fail(429,'AGENT_TOKEN_CAPACITY','Revoke unused credentials before creating more')
            db.execute('INSERT INTO agent_tokens(id,name,token_hash,created_at,expires_at) VALUES (?,?,?,?,?)',(id,body.name,digest(raw),now,expiry))
            db.execute('UPDATE agent_tokens SET import_enabled=? WHERE id=?',(int(body.import_enabled),id))
            db.executemany('INSERT INTO agent_token_spaces VALUES (?,?)',[(id,space) for space in body.space_ids])
        return {'id':id,'name':body.name,'import_enabled':body.import_enabled,'space_ids':body.space_ids,'created_at':timestamp(now),'expires_at':timestamp(expiry),'token':raw}
    @routes.delete('/{id}',status_code=204)
    def revoke(id: str,request: Request):
        with session_write(settings,request) as db:db.execute('DELETE FROM agent_tokens WHERE id=?',(id,))
    return routes
