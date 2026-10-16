import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .config import Settings
from .database import connect, migrate

logger = logging.getLogger("uvicorn.error")


def error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(kind, settings=None):
    settings = settings or Settings.from_env()
    if kind not in ("archive", "converter"):
        raise ValueError("Unknown service")

    @asynccontextmanager
    async def lifespan(app):
        if kind == "archive":
            settings.prepare_archive()
            migrate(settings.database)
        elif not settings.converter_token.strip():
            raise RuntimeError("CONVERTER_SERVICE_TOKEN must be configured")
        logger.info("%s skeleton ready; business operations not implemented", kind)
        yield

    app = FastAPI(title="JuanZhan " + kind, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR", "Request rejected")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if kind == "converter" and request.url.path != "/healthz":
            expected = "Bearer " + settings.converter_token
            if not settings.converter_token or not secrets.compare_digest(
                request.headers.get("authorization", "").encode(), expected.encode()
            ):
                return error(401, "UNAUTHORIZED", "Valid service token required")
            if request.url.path != "/v1/capabilities":
                return error(501, "NOT_IMPLEMENTED", "Conversion is not implemented")
        return await call_next(request)

    @app.get("/healthz")
    def health():
        if kind == "archive":
            try:
                with connect(settings.database) as db:
                    if db.execute("SELECT version FROM schema_migrations WHERE version='0.4.0'").fetchone() is None:
                        raise RuntimeError("Schema missing")
            except Exception:
                logger.exception("Archive readiness check failed")
                return error(503, "NOT_READY", "Database unavailable")
        return {"status": "ok"}

    if kind == "converter":
        @app.get("/v1/capabilities")
        def capabilities():
            return {"schema_versions": [], "supported_input_types": [], "ocr_available": False}
    return app
