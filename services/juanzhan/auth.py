"""Single-admin authentication. Authentication secrets are hashed at rest."""
import hashlib
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from .database import connect

COOKIE = 'archive_session'
SESSION_SECONDS = 8 * 60 * 60
ANONYMOUS_SECONDS = 10 * 60


def fail(status, code, message):
    raise HTTPException(status_code=status, detail={'code': code, 'message': message})


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=32768,
                           r=8, p=1, maxmem=64 * 1024 * 1024).hex()
    return f'scrypt${salt}${value}'


def set_password(settings, password):
    if not 12 <= len(password) <= 1024:
        raise ValueError('Password must contain 12 to 1024 characters')
    encoded = password_hash(password)
    with connect(settings.database) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO auth_admin VALUES (1,?,?) ON CONFLICT(id) '
                   'DO UPDATE SET password_hash=excluded.password_hash, updated_at=excluded.updated_at',
                   (encoded, int(time.time())))
        db.execute('DELETE FROM auth_sessions')
        db.execute('DELETE FROM auth_api_tokens')
        db.execute('DELETE FROM agent_tokens')
        db.execute('DELETE FROM oauth_requests')
        db.execute('DELETE FROM oauth_codes')
        db.execute('DELETE FROM auth_login_throttle')
        db.commit()


def session(db, request):
    raw = request.cookies.get(COOKIE, '')
    if not raw or len(raw) > 256:
        return None
    return db.execute('SELECT token_hash, csrf_token, authenticated, expires_at FROM auth_sessions '
                      'WHERE token_hash=? AND expires_at>?', (digest(raw), int(time.time()))).fetchone()


def csrf(request, row):
    value = request.headers.get('x-csrf-token', '')
    if not row or not secrets.compare_digest(value.encode(), row[1].encode()):
        fail(403, 'CSRF_REJECTED', 'Valid session and CSRF token required')
    # No permissive CORS; the synchronizer token protects login and all Cookie writes.
    if request.headers.get('sec-fetch-site') == 'cross-site':
        fail(403, 'CSRF_REJECTED', 'Cross-site write rejected')


def authorize(settings, request):
    with connect(settings.database) as db:
        authorization = request.headers.get('authorization')
        if authorization is not None:
            scheme, _, token = authorization.partition(' ')
            if scheme.lower() != 'bearer' or not token or len(token) > 256:
                fail(401, 'UNAUTHORIZED', 'Valid authentication required')
            if token.startswith('jza_'):
                from .agent_access import authorize_agent
                return authorize_agent(settings, request, token)
            row = db.execute('SELECT id FROM auth_api_tokens WHERE token_hash=? AND expires_at>?',
                             (digest(token), int(time.time()))).fetchone()
            if row is None:
                fail(401, 'UNAUTHORIZED', 'Valid authentication required')
            return 'bearer'
        row = session(db, request)
        if not row or not row[2]:
            fail(401, 'UNAUTHORIZED', 'Valid authentication required')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            csrf(request, row)
        return 'session'


def require_session(request):
    if request.state.auth_mode != 'session':
        fail(403, 'SESSION_REQUIRED', 'Administrator Cookie session required')


@contextmanager
def session_write(settings, request):
    require_session(request)
    with connect(settings.database) as db:
        db.execute('BEGIN IMMEDIATE')
        # Recheck under the write lock so reset/logout cannot race token creation.
        row = session(db, request)
        if not row or not row[2]:
            fail(401, 'UNAUTHORIZED', 'Valid authentication required')
        csrf(request, row)
        yield db
        db.commit()


def issue_session(db, response, settings, authenticated):
    now = int(time.time())
    db.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (now,))
    if not authenticated and db.execute(
        'SELECT count(*) FROM auth_sessions WHERE authenticated=0'
    ).fetchone()[0] >= 1000:
        fail(429, 'SESSION_CAPACITY', 'Anonymous session capacity reached; retry later')
    raw = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    ttl = SESSION_SECONDS if authenticated else ANONYMOUS_SECONDS
    db.execute('INSERT INTO auth_sessions VALUES (?,?,?,?)',
               (digest(raw), csrf_token, int(authenticated), now + ttl))
    response.set_cookie(COOKIE, raw, max_age=ttl, httponly=True, secure=settings.cookie_secure,
                        samesite='strict', path='/api/v1')
    return {'authenticated': authenticated, 'csrf_token': csrf_token, 'expires_at': timestamp(now + ttl)}


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class TokenInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: int = Field(default=90, ge=1, le=365, strict=True)


def router(settings):
    routes = APIRouter(prefix='/api/v1/auth')

    @routes.get('/session')
    def get_session(request: Request, response: Response):
        with connect(settings.database) as db:
            db.execute('BEGIN IMMEDIATE')
            row = session(db, request)
            if row:
                return {'authenticated': bool(row[2]), 'csrf_token': row[1], 'expires_at': timestamp(row[3])}
            result = issue_session(db, response, settings, False)
            db.commit()
            return result

    @routes.post('/login')
    def login(body: Login, request: Request, response: Response):
        with connect(settings.database) as db:
            # Serialize login against password resets and the persistent failure counter.
            db.execute('BEGIN IMMEDIATE')
            old = session(db, request)
            csrf(request, old)
            admin = db.execute('SELECT password_hash FROM auth_admin WHERE id=1').fetchone()
            if not admin:
                fail(503, 'ADMIN_NOT_CONFIGURED', 'Initialize administrator using the local CLI')
            now = int(time.time())
            throttle = db.execute('SELECT failures, window_start FROM auth_login_throttle WHERE id=1').fetchone()
            if throttle and now - throttle[1] < 60 and throttle[0] >= 5:
                fail(429, 'LOGIN_THROTTLED', 'Retry after the login cooldown')
            expected = admin[0]
            salt = expected.split('$')[1]
            valid_password = secrets.compare_digest(password_hash(body.password, salt), expected)
            if body.username != 'admin' or not valid_password:
                count = throttle[0] + 1 if throttle and now - throttle[1] < 60 else 1
                start = throttle[1] if throttle and now - throttle[1] < 60 else now
                db.execute('INSERT OR REPLACE INTO auth_login_throttle VALUES (1,?,?)', (count, start))
                db.commit()
                fail(401, 'INVALID_CREDENTIALS', 'Invalid username or password')
            db.execute('DELETE FROM auth_login_throttle')
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (old[0],))
            result = issue_session(db, response, settings, True)
            db.commit()
            return result

    @routes.post('/logout', status_code=204)
    def logout(request: Request, response: Response):
        with session_write(settings, request) as db:
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(request.cookies[COOKIE]),))
        response.delete_cookie(COOKIE, path='/api/v1', secure=settings.cookie_secure,
                               httponly=True, samesite='strict')

    @routes.get('/tokens')
    def tokens(request: Request):
        require_session(request)
        with connect(settings.database) as db:
            rows = db.execute('SELECT id,name,created_at,expires_at FROM auth_api_tokens '
                              'WHERE expires_at>? ORDER BY created_at,id', (int(time.time()),)).fetchall()
            return [{'id': row[0], 'name': row[1], 'created_at': timestamp(row[2]),
                     'expires_at': timestamp(row[3])} for row in rows]

    @routes.post('/tokens', status_code=201)
    def create_token(body: TokenInput, request: Request):
        require_session(request)
        raw = 'jz_' + secrets.token_urlsafe(32)
        now = int(time.time())
        id = uuid.uuid4().hex
        expires = now + body.expires_in_days * 86400
        with session_write(settings, request) as db:
            db.execute('INSERT INTO auth_api_tokens VALUES (?,?,?,?,?)',
                       (id, body.name, digest(raw), now, expires))
        return {'id': id, 'name': body.name, 'created_at': timestamp(now), 'expires_at': timestamp(expires), 'token': raw}

    @routes.delete('/tokens/{id}', status_code=204)
    def revoke_token(id: str, request: Request):
        with session_write(settings, request) as db:
            db.execute('DELETE FROM auth_api_tokens WHERE id=?', (id,))

    return routes
