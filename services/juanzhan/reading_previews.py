"""Durable, version-pinned Office reading PDFs; never substitute them for originals."""
import json
import os
import shutil
import sqlite3
import tempfile
from urllib.error import HTTPError,URLError
from urllib.parse import quote
from urllib.request import Request as HTTPRequest,build_opener,ProxyHandler,HTTPRedirectHandler
from fastapi import APIRouter,Request,Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from .auth import fail
from .catalog import required,transaction
from .database import connect
from .document_records import expected
from .document_events import utc_now
from .source_files import SourceRequest,revision,requested
from .source_snapshots import ensure
from .jobs import JobQueue,JobSpec
from .parsing import original,ParseFailure
from .storage import ManagedStore,parse_key,StorageError
from .files import HEADERS,COPIES
from .derived import schedule_gc

from .office_types import EXTENSIONS,MAX_INPUT,MAX_PDF
OFFICE=set(EXTENSIONS)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def router(settings):
    routes=APIRouter(prefix='/api/v1/documents')
    @routes.get('/{id}/reading-preview')
    def status(id:str,revision_id:str|None=Query(default=None,min_length=1,max_length=255)):
        with connect(settings.database) as db:
            db.row_factory=sqlite3.Row
            doc=required(db,'documents',id);rev=revision(db,id,revision_id or doc['current_revision_id'])
            saved=db.execute('SELECT renderer,created_at FROM reading_previews WHERE revision_id=?',(rev['id'],)).fetchone()
            latest=db.execute("SELECT id,status,error_json FROM jobs WHERE target_type='document_reading_preview' AND target_id=? "
                "AND json_extract(payload_json,'$.revision_id')=? ORDER BY created_at DESC,id DESC LIMIT 1",(id,rev['id'])).fetchone()
            value={'revision_id':rev['id'],'state':'ready' if saved else latest['status'] if latest and latest['status'] in ('queued','running','failed') else 'not_generated',
                   'supported':rev['mime_type'] in OFFICE,'job_id':latest['id'] if latest else None,
                   'renderer':saved['renderer'] if saved else None,'created_at':saved['created_at'] if saved else None}
            return value
    @routes.post('/{id}/reading-preview',status_code=202)
    def generate(id:str,body:SourceRequest,request:Request):
        payload=body.model_dump();key='reading-preview:'+id+':'+body.request_id
        with transaction(settings,request) as db:
            old=requested(db,key,payload)
            if old:return old
            doc=expected(db,id,body.expected_document_version);rev=revision(db,id,body.revision_id)
            if doc['deleted_at']:fail(409,'DOCUMENT_TRASHED','Restore before generating a reading preview')
            if rev['mime_type'] not in OFFICE:fail(422,'READING_PREVIEW_UNSUPPORTED','Use direct reading or download for this format')
            if rev['size_bytes']>MAX_INPUT:fail(413,'READING_PREVIEW_INPUT_LIMIT','Original exceeds the Office preview budget')
            existing=db.execute("SELECT id,status FROM jobs WHERE target_type='document_reading_preview' AND target_id=? AND status IN ('queued','running') "
                "AND json_extract(payload_json,'$.revision_id')=? LIMIT 1",(id,body.revision_id)).fetchone()
            if existing:return {'job_id':existing['id'],'status':existing['status']}
            job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='document_reading_preview',target_id=id,
                payload=payload,idempotency_key=key,timeout_seconds=180,max_attempts=3),db=db)
            return {'job_id':job['id'],'status':job['status']}
    @routes.get('/{id}/reading-preview/file')
    def read(id:str,revision_id:str=Query(min_length=1,max_length=255)):
        if not COPIES.acquire(blocking=False):fail(429,'DOWNLOAD_CAPACITY','File preparation busy')
        copy=None
        try:
            with connect(settings.database) as db:
                db.row_factory=sqlite3.Row;rev=revision(db,id,revision_id)
                row=db.execute('SELECT * FROM reading_previews WHERE revision_id=?',(revision_id,)).fetchone()
                if row is None:fail(404,'READING_PREVIEW_NOT_READY','Generate the reading preview first')
                saved=dict(row)
            if parse_key(saved['storage_key'])!=(saved['sha256'],saved['size_bytes']) or saved['size_bytes']>MAX_PDF:
                fail(409,'PREVIEW_UNAVAILABLE','Reading preview integrity check failed')
            copy=tempfile.TemporaryFile()
            with ManagedStore(settings.data_dir/'derived').open(saved['storage_key']) as source:
                shutil.copyfileobj(source,copy,65536)
            copy.seek(0);pinned=copy
            def chunks():
                try:
                    while chunk:=pinned.read(65536):yield chunk
                finally:pinned.close()
            response=StreamingResponse(chunks(),media_type='application/octet-stream',headers={**HEADERS,
                'Content-Length':str(saved['size_bytes']),'X-Revision-ID':revision_id,
                'Content-Disposition':"attachment; filename=preview.pdf; filename*=UTF-8''"+quote(rev['original_filename']+'.preview.pdf',safe='')},background=BackgroundTask(pinned.close))
            copy=None;return response
        except (StorageError,ValueError,OSError):
            fail(409,'PREVIEW_UNAVAILABLE','Reading preview integrity check failed')
        finally:
            if copy is not None:copy.close()
            COPIES.release()
    return routes

def execute(settings,job):
    payload=json.loads(job['payload_json'])
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row;rev=revision(db,job['target_id'],payload['revision_id'])
        cached=db.execute('SELECT storage_key FROM reading_previews WHERE revision_id=?',(rev['id'],)).fetchone()
    if cached:
        try:
            with ManagedStore(settings.data_dir/'derived').open(cached[0]):pass
        except (StorageError,OSError,ValueError):cached=None
    if cached:
        JobQueue(settings).step(job['id'],job['lease_token'],'render')
        JobQueue(settings).step(job['id'],job['lease_token'],'publish')
        JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:{'revision_id':rev['id'],'cached':True});return
    if rev['mime_type'] not in OFFICE or rev['size_bytes']>MAX_INPUT:raise ParseFailure('READING_PREVIEW_INPUT_LIMIT')
    ensure(settings,rev,job)
    JobQueue(settings).step(job['id'],job['lease_token'],'render')
    endpoint=os.getenv('OFFICE_PREVIEW_URL','http://office-preview:8000').rstrip('/')+'/v1/render'
    opener=build_opener(ProxyHandler({}),NoRedirect())
    store=ManagedStore(settings.data_dir/'derived');store.initialize()
    with store.locked():
        import time
        with JobQueue(settings).write() as db:
            JobQueue(settings)._owned(db,job['id'],job['lease_token'])
            schedule_gc(db,settings,'derived-after-reading-preview:'+job['id'],time.time()+86400)
        try:
            with original(settings,rev,MAX_INPUT) as file:
                request=HTTPRequest(endpoint,data=file,method='POST',headers={'Authorization':'Bearer '+settings.converter_token,
                    'Content-Type':'application/octet-stream','Content-Length':str(rev['size_bytes']),'X-Original-Mime':rev['mime_type']})
                with opener.open(request,timeout=110) as response:
                    if response.headers.get_content_type()!='application/pdf':raise ParseFailure('READING_PREVIEW_INVALID')
                    obj=store.put(response,max_bytes=MAX_PDF)
                    renderer=response.headers.get('X-Renderer','office-preview')[:255]
                    with store.open(obj.storage_key) as pdf:
                        if not pdf.read(5)==b'%PDF-':raise ParseFailure('READING_PREVIEW_INVALID')
        except HTTPError as exc:
            code='READING_PREVIEW_FAILED'
            try:
                value=json.loads(exc.read(4096)).get('error',{}).get('code')
                if value in ('READING_PREVIEW_TIMEOUT','READING_PREVIEW_BUSY','READING_PREVIEW_INPUT_LIMIT','READING_PREVIEW_TYPE_MISMATCH','READING_PREVIEW_UNSUPPORTED','READING_PREVIEW_OUTPUT_LIMIT'):
                    code=value
            except (ValueError,AttributeError):pass
            raise ParseFailure(code,exc.code in (408,429,500,502,503,504) or code in ('READING_PREVIEW_TIMEOUT','READING_PREVIEW_BUSY')) from None
        except (URLError,TimeoutError):raise ParseFailure('READING_PREVIEW_UNAVAILABLE',True) from None
        JobQueue(settings).step(job['id'],job['lease_token'],'publish')
        def publish(db,owned):
            revision(db,job['target_id'],rev['id'])
            db.execute('INSERT INTO reading_previews VALUES (?,?,?,?,?,?) ON CONFLICT(revision_id) DO UPDATE SET '
                'storage_key=excluded.storage_key,sha256=excluded.sha256,size_bytes=excluded.size_bytes,renderer=excluded.renderer,created_at=excluded.created_at',
                (rev['id'],obj.storage_key,obj.sha256,obj.size_bytes,renderer,utc_now()))
            db.execute('DELETE FROM derived_gc_candidates WHERE storage_key=?',(obj.storage_key,))
            return {'document_id':job['target_id'],'revision_id':rev['id'],'preview_ready':True,'original_modified':False}
        JobQueue(settings).complete(job['id'],job['lease_token'],publish)
