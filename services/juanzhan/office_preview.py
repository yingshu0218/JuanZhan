"""Private bounded Office renderer, isolated from Archive data/source volumes."""
import ctypes
import hashlib
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,Response
from starlette.concurrency import run_in_threadpool
from .office_types import EXTENSIONS,MAX_INPUT,MAX_PDF

HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"}
BUSY=threading.BoundedSemaphore(1)
class LimitedResponse(Response):
    async def __call__(self,scope,receive,send):
        try:await super().__call__(scope,receive,send)
        finally:BUSY.release()
PROFILE='''<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting">
<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
<prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
<prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop>
<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item></oor:items>'''

def render(root,extension):
    profile=root/'profile'/'user';profile.mkdir(parents=True)
    (profile/'registrymodifications.xcu').write_text(PROFILE)
    (root/'output').mkdir();(root/'home').mkdir()
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(root/'home'),'TMPDIR':str(root),
         'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','SAL_USE_VCLPLUGIN':'svp','PYTHONPATH':'/app/services',
         'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    process=subprocess.Popen([sys.executable,'-m','juanzhan.office_child',str(root),extension],
        env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,close_fds=True)
    try:
        try:status=process.wait(timeout=90)
        except subprocess.TimeoutExpired:return None,'READING_PREVIEW_TIMEOUT'
        if status!=0:return None,'READING_PREVIEW_FAILED'
        path=root/'output'/'input.pdf'
        try:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as file:
                info=os.fstat(file.fileno())
                if not stat.S_ISREG(info.st_mode) or not 5<=info.st_size<=MAX_PDF:return None,'READING_PREVIEW_OUTPUT_LIMIT'
                data=file.read(MAX_PDF+1)
        except OSError:return None,'READING_PREVIEW_FAILED'
        if len(data)>MAX_PDF or not data.startswith(b'%PDF-'):return None,'READING_PREVIEW_INVALID'
        return data,None
    finally:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait()

def create_app():
    token=os.getenv('CONVERTER_SERVICE_TOKEN','')
    if not token.strip():raise RuntimeError('Configure a private renderer service token')
    # Native child cannot read the parent's token through /proc/<pid>/environ.
    if ctypes.CDLL(None).prctl(4,0,0,0,0)!=0:raise RuntimeError('Cannot protect renderer process metadata')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    @app.get('/healthz')
    def health():return {'status':'ok'}
    @app.post('/v1/render')
    async def convert(request:Request):
        def error(code,status):return JSONResponse({'error':{'code':code}},status_code=status,headers=HEADERS)
        if not secrets.compare_digest(request.headers.get('authorization','').encode(),('Bearer '+token).encode()):return error('UNAUTHORIZED',401)
        mime=request.headers.get('x-original-mime','')
        if mime not in EXTENSIONS:return error('READING_PREVIEW_UNSUPPORTED',422)
        if not BUSY.acquire(blocking=False):return error('READING_PREVIEW_BUSY',429)
        deferred=False
        try:
            with tempfile.TemporaryDirectory(prefix='juanzhan-office-') as directory:
                root=Path(directory);extension=EXTENSIONS[mime];size=0
                with (root/('input.'+extension)).open('xb') as file:
                    async for chunk in request.stream():
                        size+=len(chunk)
                        if size>MAX_INPUT:return error('READING_PREVIEW_INPUT_LIMIT',413)
                        file.write(chunk)
                from .uploads import sniff
                with (root/('input.'+extension)).open('rb') as file:actual=sniff(file,'input.'+extension)
                if actual!=mime:return error('READING_PREVIEW_TYPE_MISMATCH',422)
                pdf,failed=await run_in_threadpool(render,root,extension)
                if failed:return error(failed,422)
                response=LimitedResponse(pdf,media_type='application/pdf',headers={**HEADERS,'X-Renderer':os.getenv('JUANZHAN_OFFICE_RENDERER_VERSION','libreoffice'),
                    'X-Content-SHA256':hashlib.sha256(pdf).hexdigest()})
                deferred=True;return response
        finally:
            if not deferred:BUSY.release()
    return app

app=create_app()
