"""Authenticated, version-pinned originals and passive raster previews only."""
import hashlib
import sqlite3
import tempfile
import threading
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask
from PIL import Image

from .auth import fail
from .database import connect
from .parsing import original, ParseFailure
from .source_paths import SourcePathError
from .storage import ManagedStore, StorageError, parse_key

HEADERS = {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
           'Content-Security-Policy':"default-src 'none'; sandbox",'Referrer-Policy':'no-referrer'}
MAX_BYTES = 1024 * 1024 * 1024
COPIES = threading.BoundedSemaphore(2)


def current(db, id, expected=None):
    doc = db.execute('SELECT current_revision_id,current_parse_run_id FROM documents WHERE id=?',(id,)).fetchone()
    if not doc: fail(404,'NOT_FOUND','Document not found')
    if expected and doc['current_revision_id'] != expected:
        fail(409,'REVISION_CONFLICT','Current original changed; reload')
    revision = db.execute('SELECT * FROM file_revisions WHERE id=? AND document_id=?',(doc['current_revision_id'],id)).fetchone()
    if not revision: fail(404,'ORIGINAL_NOT_AVAILABLE','No current original')
    return doc, dict(revision)


def previews(db, id, expected=None):
    doc, revision = current(db,id,expected)
    run = db.execute("SELECT id,revision_id,status FROM parse_runs WHERE id=? AND document_id=?",
                     (doc['current_parse_run_id'],id)).fetchone()
    if not run or run['status'] != 'completed': return revision, []
    if run['revision_id'] != revision['id']:
        fail(409,'PREVIEW_STALE','Preview belongs to an older original')
    assets = db.execute("SELECT a.*,o.asset_index FROM derived_assets a JOIN parse_asset_order o ON o.derived_asset_id=a.id "
                        "WHERE a.parse_run_id=? AND a.asset_kind IN ('preview','thumbnail') AND a.media_type='image/png' "
                        'ORDER BY o.asset_index LIMIT 100',(run['id'],)).fetchall()
    return revision, assets


def router(settings):
    routes = APIRouter(prefix='/api/v1/documents')
    @routes.get('/{id}/download')
    def download(id: str, expected_revision_id: str | None = Query(default=None,min_length=1,max_length=255)):
        if not COPIES.acquire(blocking=False): fail(429,'DOWNLOAD_CAPACITY','Download preparation is busy')
        copy = None
        try:
            with connect(settings.database) as db:
                db.row_factory=sqlite3.Row
                _, revision=current(db,id,expected_revision_id)
            if revision['size_bytes']>MAX_BYTES: fail(413,'DOWNLOAD_LIMIT','Original exceeds download limit')
            copy=tempfile.TemporaryFile(); digest=hashlib.sha256(); size=0
            try:
                with original(settings,revision,MAX_BYTES) as file:
                    while chunk:=file.read(min(65536,MAX_BYTES-size+1)):
                        size+=len(chunk)
                        if size>MAX_BYTES: fail(413,'DOWNLOAD_LIMIT','Original exceeds download limit')
                        copy.write(chunk);digest.update(chunk)
            except (ParseFailure,SourcePathError,StorageError,OSError,ValueError):
                fail(409,'ORIGINAL_UNAVAILABLE','Original unavailable, changed or failed integrity verification')
            if size!=revision['size_bytes'] or digest.hexdigest()!=revision['sha256']:
                fail(409,'ORIGINAL_UNAVAILABLE','Original no longer matches recorded revision')
            with connect(settings.database) as db:
                db.row_factory=sqlite3.Row;current(db,id,revision['id'])
            copy.seek(0)
            pinned=copy
            def chunks():
                try:
                    while chunk:=pinned.read(65536): yield chunk
                finally: pinned.close()
            # Always attachment/octet-stream, including HTML/SVG/PDF. Never execute active originals.
            name=quote(revision['original_filename'],safe='')
            response=StreamingResponse(chunks(),media_type='application/octet-stream',headers={**HEADERS,
                'Content-Length':str(size),'Content-Disposition':f"attachment; filename=original; filename*=UTF-8''{name}",
                'X-Revision-ID':revision['id']},background=BackgroundTask(pinned.close))
            copy=None
            return response
        finally:
            if copy is not None: copy.close()
            COPIES.release()

    @routes.get('/{id}/preview')
    def preview(id: str, expected_revision_id: str | None = Query(default=None,min_length=1,max_length=255)):
        with connect(settings.database) as db:
            db.row_factory=sqlite3.Row
            revision, assets=previews(db,id,expected_revision_id)
            import json
            return Response(json.dumps({'revision_id':revision['id'],'items':[{'id':a['id'],'sequence':index+1,
                'mime_type':'image/png'} for index,a in enumerate(assets)]}),media_type='application/json',headers=HEADERS)

    @routes.get('/{id}/preview/{asset_id}')
    def image(id: str, asset_id: str, expected_revision_id: str = Query(min_length=1,max_length=255)):
        with connect(settings.database) as db:
            db.row_factory=sqlite3.Row
            _, assets=previews(db,id,expected_revision_id)
            asset=next((a for a in assets if a['id']==asset_id),None)
            if asset is None: fail(404,'NOT_FOUND','Current raster preview not found')
            try:
                if asset['size_bytes']>4*1024*1024 or parse_key(asset['storage_key'])!=(asset['sha256'],asset['size_bytes']):
                    raise ValueError()
                with ManagedStore(settings.data_dir/'derived').open(asset['storage_key']) as file:
                    raster=Image.open(file)
                    if raster.format!='PNG' or not 0<raster.width<=1024 or not 0<raster.height<=1024: raise ValueError()
                    raster.verify();file.seek(0);data=file.read(4*1024*1024+1)
            except (OSError,StorageError,ValueError,Image.DecompressionBombError):
                fail(409,'PREVIEW_UNAVAILABLE','Raster preview could not be verified')
            current(db,id,expected_revision_id)
            return Response(data,media_type='image/png',headers=HEADERS)
    return routes
