"""Public compiled shell; all archive data remains behind the API boundary."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

WEB_ROOT = Path(__file__).resolve().parents[2] / 'web' / 'dist'
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"


def install(app):
    routes=APIRouter()

    @routes.api_route('/',methods=['GET','HEAD'])
    def index():
        if not (WEB_ROOT/'index.html').is_file():
            return JSONResponse({'error':{'code':'WEB_NOT_BUILT','message':'Web client is not built'}},status_code=503)
        return FileResponse(WEB_ROOT/'index.html',headers={'Cache-Control':'no-store','Content-Security-Policy':CSP,'X-Content-Type-Options':'nosniff'})

    @routes.api_route('/favicon.svg',methods=['GET','HEAD'])
    def favicon():
        if not (WEB_ROOT/'favicon.svg').is_file():
            return JSONResponse({'error':{'code':'NOT_FOUND','message':'Not found'}},status_code=404)
        return FileResponse(WEB_ROOT/'favicon.svg',media_type='image/svg+xml',headers={'X-Content-Type-Options':'nosniff'})

    app.include_router(routes)
    if (WEB_ROOT/'assets').is_dir():
        app.mount('/assets',StaticFiles(directory=WEB_ROOT/'assets'),name='web-assets')
