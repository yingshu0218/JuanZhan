import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from starlette.exceptions import HTTPException

from . import auth, catalog, jobs, uploads, document_api, batches, fields, metadata, web, source_api, maintenance, content, oauth

from .config import Settings
from .database import connect, migrate
from .storage import ManagedStore, StorageBusy
from .documents import DocumentService

logger = logging.getLogger("uvicorn.error")


def error(status, code, message, **extra):
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status, headers=headers)


def create_app(kind, settings=None, *, converter_config=None):
    settings = settings or Settings.from_env()
    if kind not in ("archive", "converter"):
        raise ValueError("Unknown service")

    conversion_store = None
    if kind == "converter":
        from .conversion_store import ConverterConfig, ConverterStore
        conversion_store = ConverterStore(converter_config or ConverterConfig.from_env())

    @asynccontextmanager
    async def lifespan(app):
        if kind == "archive":
            settings.prepare_archive()
            migrate(settings.database)
            app.state.storage = ManagedStore(settings.data_dir / 'managed')
            app.state.storage.initialize()
            app.state.documents = DocumentService(settings)
            app.state.jobs = jobs.JobQueue(settings)
            try:
                removed = app.state.storage.recover_staging()
                logger.info("Managed staging recovery removed %d stale files", removed)
            except StorageBusy:
                logger.info("Managed staging recovery deferred while writers are active")
        elif not settings.converter_token.strip():
            raise RuntimeError("CONVERTER_SERVICE_TOKEN must be configured")
        if conversion_store:
            conversion_store.start()
        logger.info("%s ready", kind)
        try:
            yield
        finally:
            if conversion_store:
                conversion_store.close()

    app = FastAPI(title="JuanZhan " + kind, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(oauth.OAuthError)
    async def oauth_error(request, exc):
        return oauth.response_error(exc)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        if isinstance(exc.detail, dict):
            return error(exc.status_code, exc.detail['code'], exc.detail['message'],
                         **{key:exc.detail[key] for key in ('details','current_document_version') if key in exc.detail})
        return error(exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR", "Request rejected")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Never include submitted passwords or tokens in validation responses.
        return error(422, "INVALID_REQUEST", "Request does not match the API schema")

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logger.error("Unhandled request failure: %s", type(exc).__name__)
        return error(500, "INTERNAL_ERROR", "Internal server error")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if kind == "archive" and request.url.path == "/api/v1/agent/mcp" and request.headers.get("origin") is not None and request.headers["origin"] != str(request.base_url).rstrip("/"):
            return error(403,"ORIGIN_REJECTED","Origin does not match this server")
        if kind == "converter" and request.url.path != "/healthz":
            expected = "Bearer " + settings.converter_token
            if not settings.converter_token or not secrets.compare_digest(
                request.headers.get("authorization", "").encode(), expected.encode()
            ):
                return error(401, "UNAUTHORIZED", "Valid service token required")

        if kind == "archive" and request.url.path != "/healthz":
            public_web = request.method in ('GET','HEAD') and (request.url.path in ('/','/favicon.svg') or request.url.path.startswith('/assets/'))
            public = public_web or (request.method, request.url.path) in {
                ('GET', '/api/v1/auth/session'), ('POST', '/api/v1/auth/login')}
            public = public or (request.method in ('GET','HEAD') and request.url.path == '/oauth/authorize') or (request.method,request.url.path) in {
                ('GET','/.well-known/oauth-authorization-server'),
                ('GET','/.well-known/oauth-protected-resource'),
                ('GET','/.well-known/oauth-protected-resource/api/v1/agent/mcp'),
                ('POST','/oauth/register'),('POST','/oauth/token'),('POST','/oauth/revoke')}
            if not public:
                try:
                    request.state.auth_mode = await run_in_threadpool(auth.authorize, settings, request)
                except HTTPException as exc:
                    response = error(exc.status_code, exc.detail['code'], exc.detail['message'])
                    if exc.status_code == 401 and request.url.path.startswith('/api/v1/agent/'):
                        response.headers['WWW-Authenticate']=oauth.challenge(settings)
                    return response
        response = await call_next(request)
        if kind=='archive' and request.url.path.startswith('/assets/') and request.url.path.endswith(('.js','.mjs')):
            response.headers['Content-Security-Policy']=web.WORKER_CSP
            response.headers['X-Content-Type-Options']='nosniff'
        if kind == "archive" and (request.url.path in ("/api/v1/documents/search","/api/v1/system/summary") or (request.url.path=="/api/v1/documents" and "q" in request.query_params)):
            response.headers["Cache-Control"]="no-store"
            response.headers["X-Content-Type-Options"]="nosniff"
        if kind == "converter":
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        if kind == 'archive' and (request.url.path.startswith('/api/v1/agent') or request.url.path.endswith('/overview')):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
        if kind=='archive' and (request.url.path.endswith(('/source-files','/source-snapshot','/source-snapshots','/reading-preview','/reading-preview/file')) or request.url.path.startswith('/api/v1/system/storage')):
            response.headers['Cache-Control']='no-store'
            response.headers['X-Content-Type-Options']='nosniff'
        if kind == 'archive' and request.url.path.startswith('/api/v1/auth'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Pragma'] = 'no-cache'
        return response

    @app.get("/healthz")
    def health():
        if conversion_store and not conversion_store.ready():
            return error(503, "NOT_READY", "Converter runner unavailable")
        if kind == "archive":
            try:
                with connect(settings.database) as db:
                    if db.execute("SELECT version FROM schema_migrations WHERE version='0.4.0'").fetchone() is None:
                        raise RuntimeError("Schema missing")
            except Exception:
                logger.exception("Archive readiness check failed")
                return error(503, "NOT_READY", "Database unavailable")
        return {"status": "ok"}

    if kind == "archive":
        web.install(app)
        app.include_router(oauth.router(settings))
        from . import source_files,reading_previews,storage_management
        app.include_router(source_files.router(settings))
        app.include_router(reading_previews.router(settings))
        app.include_router(storage_management.router(settings))
        from . import agent_access, agent_api, agent_mcp
        app.include_router(agent_access.router(settings))
        app.include_router(agent_api.router(settings))
        from . import agent_imports
        app.include_router(agent_imports.router(settings))
        app.include_router(agent_mcp.router(settings))
        app.include_router(auth.router(settings))
        app.include_router(catalog.router(settings))
        app.include_router(source_api.router(settings))
        from . import source_matching
        app.include_router(source_matching.router(settings))
        app.include_router(maintenance.router(settings))
        from . import backup_api
        app.include_router(backup_api.router(settings))
        app.include_router(fields.router(settings))
        app.include_router(metadata.router(settings))
        from . import files
        app.include_router(files.router(settings))
        from . import adoptions
        app.include_router(adoptions.router(settings))
        app.include_router(content.router(settings))
        app.include_router(jobs.router(settings))
        from . import upload_policy
        app.include_router(upload_policy.router(settings))
        app.include_router(uploads.router(settings))
        app.include_router(batches.router(settings))
        from . import search
        app.include_router(search.router(settings))
        app.include_router(document_api.router(settings))

    if kind == "converter":
        from .conversion_api import router
        from .conversion_store import ConversionError
        @app.exception_handler(ConversionError)
        async def conversion_error(request, exc):
            return error(exc.status, exc.code, "Conversion request could not be completed")
        app.include_router(router(conversion_store))
    return app
