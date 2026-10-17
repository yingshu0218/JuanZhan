"""Authenticated discovery of administrator-approved aliases; no client paths."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .auth import authorize
from .source_paths import SourceMounts


def router(settings):
    result = APIRouter(prefix='/api/v1')

    @result.get('/source-mounts')
    def mounts(request: Request):
        authorize(settings, request)
        return JSONResponse({'items': SourceMounts(settings.source_mounts).list()},
                            headers={'Cache-Control': 'no-store'})

    return result
