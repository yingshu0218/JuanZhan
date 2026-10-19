"""Authenticated backup management. No client filesystem paths or live restore."""
import asyncio
from contextlib import ExitStack
import hashlib
import os
import shutil
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .auth import authorize, fail
from .catalog import Input
from .database import connect
from .jobs import JobQueue, JobSpec, stamp
from .storage import StorageBusy
from .backup_management import Repository, active, enqueue, record, retire, verify_archive
from .backup_archive import MAX_BYTES, MAX_FILES, RESERVE_BYTES

Identity = Annotated[str, Field(pattern=r'^[0-9a-f]{32}$')]
RequestId = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]{8,128}$')]


class Start(Input):
    request_id: RequestId


class Plan(Input):
    expected_version: Annotated[int,Field(strict=True,ge=1,le=9223372036854775806)]
    interval_minutes: Annotated[int,Field(strict=True,ge=0,le=525600)]
    keep_count: Annotated[int,Field(strict=True,ge=1,le=100)]
    max_age_days: Annotated[int,Field(strict=True,ge=1,le=3650)]


def schedule_public(db):
    version,interval,count,days,due,last = db.execute('SELECT version,interval_minutes,keep_count,max_age_days,next_due_at,last_job_id FROM backup_schedule WHERE id=1').fetchone()
    return {'version':version,'interval_minutes':interval,'keep_count':count,'max_age_days':days,
        'next_run_at':stamp(due) if due is not None else None,'last_job_id':last}


def backup_public(db, repository, item):
    job = db.execute('SELECT status,error_json FROM jobs WHERE id=?',(item['job_id'],)).fetchone()
    available = False
    if item['artifact_token'] and not item['deleted_at']:
        path = repository.path('artifacts',item['id'],item['artifact_token'])
        available = not path.is_symlink() and path.is_file() and path.stat().st_size==item['archive_bytes']
    return {'id':item['id'],'origin':item['origin'],'job_id':item['job_id'],'created_at':item['created_at'],
        'completed_at':item['completed_at'],'deleted_at':item['deleted_at'], 'bytes':item['archive_bytes'],
        'sha256':item['archive_sha256'],'available':available,
        'status':'deleted' if item['deleted_at'] else ('ready' if available else 'unavailable') if item['completed_at'] else job[0],
        'error':json_error(job[1]),'external_sources_included':False}


def json_error(value):
    import json
    return json.loads(value) if value is not None else None


def router(settings):
    routes = APIRouter(prefix='/api/v1/system')
    queue = JobQueue(settings)
    upload_slot = asyncio.Semaphore(1)

    def repository():
        try:
            return Repository(settings)
        except (OSError,ValueError):
            fail(503,'BACKUP_STORAGE_UNAVAILABLE','Private backup storage is not available')

    @routes.get('/backups')
    def list_backups(page: int=Query(1,ge=1,le=1000000),page_size: int=Query(25,ge=1,le=100)):
        repo = repository()
        with connect(settings.database) as db:
            ids = db.execute('SELECT id FROM backup_records ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                (page_size,(page-1)*page_size)).fetchall()
            return JSONResponse({'items':[backup_public(db,repo,record(db,id)) for (id,) in ids],
                'total':db.execute('SELECT COUNT(*) FROM backup_records').fetchone()[0], 'page':page,'page_size':page_size},headers={'Cache-Control':'no-store'})

    @routes.post('/backups',status_code=202)
    def create_backup(body: Start,request: Request):
        repository()
        with queue.write(request) as db:
            return enqueue(settings,db,body.request_id)

    @routes.get('/backup-schedule')
    def get_plan():
        with connect(settings.database) as db:
            return JSONResponse(schedule_public(db),headers={'Cache-Control':'no-store'})

    @routes.patch('/backup-schedule')
    def update_plan(body: Plan,request: Request):
        repository()
        with queue.write(request) as db:
            if schedule_public(db)['version']!=body.expected_version:
                fail(409,'BACKUP_SCHEDULE_CONFLICT','Backup schedule changed; refresh before retry')
            db.execute('UPDATE backup_schedule SET version=version+1,interval_minutes=?,keep_count=?,max_age_days=?,next_due_at=? WHERE id=1',
                (body.interval_minutes,body.keep_count,body.max_age_days,time.time()+body.interval_minutes*60 if body.interval_minutes else None))
            return schedule_public(db)

    @routes.get('/backups/{backup_id}')
    def get_backup(backup_id: Identity):
        repo = repository()
        with connect(settings.database) as db:
            return JSONResponse(backup_public(db,repo,record(db,backup_id)),headers={'Cache-Control':'no-store'})

    @routes.delete('/backups/{backup_id}')
    def delete_backup(backup_id: Identity,request: Request):
        repo = repository()
        try:
            with repo.locked():
                authorize(settings,request)
                retire(settings,repo,backup_id,request=request)
        except StorageBusy:
            fail(409,'BACKUP_OPERATION_BUSY','Backup storage is in use; retry later')
        except OSError:
            fail(503,'BACKUP_STORAGE_UNAVAILABLE','Backup deletion could not finish; retry safely')
        return {'id':backup_id,'status':'deleted'}

    @routes.get('/backups/{backup_id}/download')
    def download(backup_id: Identity,request: Request):
        repo = repository()
        stack = ExitStack()
        try:
            stack.enter_context(repo.locked(shared=True))
            with connect(settings.database) as db:
                item = record(db,backup_id)
            file = stack.enter_context(verify_archive(repo,item))
            authorize(settings,request)
        except StorageBusy:
            stack.close()
            fail(409,'BACKUP_OPERATION_BUSY','Backup storage is in use; retry later')
        except (OSError,ValueError):
            stack.close()
            fail(409,'BACKUP_UNAVAILABLE','Backup file is missing or failed integrity validation')
        except BaseException:
            stack.close()
            raise
        def chunks():
            try:
                while block := file.read(65536):
                    yield block
            finally:
                stack.close()
        return StreamingResponse(chunks(),media_type='application/octet-stream',headers={
            'Content-Disposition':f'attachment; filename="juanzhan-backup-{backup_id}.zip"',
            'Content-Length':str(item['archive_bytes']),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'},background=BackgroundTask(stack.close))

    @routes.post('/backups/{backup_id}/restore',status_code=202)
    def create_recovery(backup_id: Identity,body: Start,request: Request):
        repo = repository()
        with queue.write(request) as db:
            key = 'backup-recovery:'+body.request_id
            old = db.execute('SELECT id,target_id FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
            if old:
                previous = db.execute('SELECT backup_id FROM recovery_records WHERE id=?',(old[1],)).fetchone()
                if previous[0]!=backup_id:
                    fail(409,'IDEMPOTENCY_CONFLICT','Request identity belongs to a different backup')
                return {'recovery_id':old[1],'job_id':old[0],'status':'accepted'}
            item = record(db,backup_id)
            if not backup_public(db,repo,item)['available']:
                fail(409,'BACKUP_NOT_READY','Backup is not available')
            if active(db):
                fail(409,'BACKUP_OPERATION_BUSY','A backup or recovery operation is already active')
            id = uuid.uuid4().hex
            job = queue.enqueue(JobSpec(kind='batch',target_type='system_recovery',target_id=id,payload={},
                idempotency_key=key,timeout_seconds=3600),db=db)
            db.execute('INSERT INTO recovery_records(id,backup_id,job_id,created_at) VALUES (?,?,?,?)',
                (id,backup_id,job['id'],stamp(time.time())))
            return {'recovery_id':id,'job_id':job['id'],'status':'accepted'}

    @routes.get('/recoveries')
    def recoveries(page: int=Query(1,ge=1,le=1000000),page_size: int=Query(25,ge=1,le=100)):
        repo = repository()
        with connect(settings.database) as db:
            db.row_factory = __import__('sqlite3').Row
            items=[]
            for item in db.execute('SELECT r.*,j.status,j.error_json FROM recovery_records r JOIN jobs j ON j.id=r.job_id ORDER BY r.created_at DESC,r.id DESC LIMIT ? OFFSET ?',
                (page_size,(page-1)*page_size)):
                ready = item['artifact_token'] is not None
                if ready:
                    path=repo.path('recoveries',item['id'],item['artifact_token'])
                    ready = not path.is_symlink() and path.is_dir() and not (path/'RESTORE_IN_PROGRESS').exists()
                items.append({'id':item['id'],'backup_id':item['backup_id'],'job_id':item['job_id'],
                    'created_at':item['created_at'],'completed_at':item['completed_at'],'status':'ready' if ready else 'unavailable' if item['completed_at'] else item['status'],
                    'error':json_error(item['error_json']),'activation_required':True})
            return JSONResponse({'items':items,'total':db.execute('SELECT COUNT(*) FROM recovery_records').fetchone()[0],
                'page':page,'page_size':page_size},headers={'Cache-Control':'no-store'})

    @routes.post('/backups/import',status_code=202)
    async def import_backup(request: Request, request_id: RequestId=Query()):
        # Raw application/zip avoids unbounded multipart parsing and ignores filenames.
        if request.headers.get('content-type','').split(';')[0].strip() not in ('application/zip','application/octet-stream'):
            fail(415,'BACKUP_CONTENT_TYPE','Upload an application/zip body')
        if upload_slot.locked():
            fail(429,'BACKUP_UPLOAD_CAPACITY','Another backup upload is active')
        repo = repository()
        key = 'backup-imported:'+request_id
        with connect(settings.database) as db:
            old = db.execute('SELECT id,target_id FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
            if old:
                return {'backup_id':old[1],'job_id':old[0],'status':'accepted'}
            if active(db):
                fail(409,'BACKUP_OPERATION_BUSY','A backup or recovery operation is already active')
        limit = MAX_BYTES+(MAX_FILES+2)*1024
        try:
            declared = int(request.headers['content-length']) if 'content-length' in request.headers else None
        except ValueError:
            fail(400,'INVALID_REQUEST','Invalid request length')
        if declared is not None and not 0<declared<=limit:
            fail(413,'BACKUP_TOO_LARGE','Backup transport exceeds byte limit')
        token = uuid.uuid4().hex
        temporary = repo.path('incoming',token,token)
        saved = None
        async with upload_slot:
            try:
                total=0
                with temporary.open('xb') as output:
                    os.chmod(temporary,0o600)
                    async with asyncio.timeout(3600):
                        async for chunk in request.stream():
                            total += len(chunk)
                            if total>limit:
                                fail(413,'BACKUP_TOO_LARGE','Backup transport exceeds byte limit')
                            if shutil.disk_usage(repo.root).free<len(chunk)+RESERVE_BYTES:
                                fail(507,'BACKUP_STORAGE_FULL','Insufficient backup upload space')
                            await run_in_threadpool(output.write,chunk)
                    await run_in_threadpool(output.flush)
                    await run_in_threadpool(os.fsync,output.fileno())
                if total==0:
                    fail(400,'INVALID_REQUEST','Empty backup transport')
                with queue.write(request) as db:
                    old = db.execute('SELECT id,target_id FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
                    if old:
                        return {'backup_id':old[1],'job_id':old[0],'status':'accepted'}
                    result = enqueue(settings,db,request_id,origin='imported',source_token=token)
                    saved = repo.path('incoming',result['backup_id'],token)
                    os.rename(temporary,saved)
                    from .backup import sync_directory
                    sync_directory(saved.parent)
                saved = None  # Now owned by the durable job, including finite retries.
                return result
            except TimeoutError:
                fail(408,'BACKUP_UPLOAD_TIMEOUT','Backup upload deadline exceeded')
            except ClientDisconnect:
                fail(400,'BACKUP_UPLOAD_INTERRUPTED','Backup upload interrupted')
            except OSError:
                fail(503,'BACKUP_STORAGE_UNAVAILABLE','Backup upload could not be safely stored')
            finally:
                temporary.unlink(missing_ok=True)
                if saved is not None:
                    saved.unlink(missing_ok=True)

    return routes
