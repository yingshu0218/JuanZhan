"""Durable job state and fenced SQLite commits. No in-memory queue of record."""
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .auth import authorize, fail
from .database import connect


class JobSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['upload','scan','scan_preview','parse','ocr','reindex','batch','purge','gc']
    target_type: str = Field(min_length=1,max_length=255)
    target_id: str | None = Field(default=None,max_length=255)
    payload: dict[str,Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1,max_length=255)
    max_attempts: int = Field(default=3,strict=True,ge=1,le=10)
    timeout_seconds: float = Field(default=60,gt=0,le=3600,allow_inf_nan=False,strict=True)
    auto_retry: bool = Field(default=True,strict=True)


class LostLease(Exception):
    pass


def encoded(value):
    text = json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(text.encode())>65536:
        raise ValueError('Job JSON exceeds 64 KiB')
    return text


def stamp(value):
    return datetime.fromtimestamp(value,timezone.utc).isoformat().replace('+00:00','Z')


def row(db,id):
    cursor = db.execute('SELECT * FROM jobs WHERE id=?',(id,))
    result = cursor.fetchone()
    if result is None:
        fail(404,'NOT_FOUND','Job not found')
    return dict(zip([column[0] for column in cursor.description],result))


def public(job):
    result = {key:job[key] for key in ('id','kind','status','attempts','max_attempts','progress_done',
                                      'progress_total','created_at','updated_at')}
    result['result'] = json.loads(job['result_json']) if job['result_json'] is not None else None
    result['error'] = json.loads(job['error_json']) if job['error_json'] is not None else None
    return result


class JobQueue:
    def __init__(self,settings,clock=None):
        self.settings = settings
        self.clock = clock or time.time

    @contextmanager
    def write(self,request=None):
        with connect(self.settings.database) as db:
            db.execute('BEGIN IMMEDIATE')
            if request is not None:
                authorize(self.settings,request)
            yield db
            db.commit()

    def enqueue(self,spec: JobSpec,*,db=None):
        if db is None:
            with self.write() as connection:
                return self.enqueue(spec,db=connection)
        if not db.in_transaction:
            raise ValueError('Enqueue requires an existing transaction')
        payload = encoded(spec.payload)
        fingerprint = hashlib.sha256(encoded(spec.model_dump(exclude={'idempotency_key'})).encode()).hexdigest()
        existing = db.execute('SELECT id,request_hash FROM jobs WHERE idempotency_key=?', (spec.idempotency_key,)).fetchone()
        if existing is not None:
            if existing[1]!=fingerprint:
                fail(409,'IDEMPOTENCY_CONFLICT','Idempotency key was already used for different work')
            return public(row(db,existing[0]))
        id = uuid.uuid4().hex
        now = self.clock()
        db.execute('INSERT INTO jobs(id,kind,target_type,target_id,status,payload_json,max_attempts,created_at,'
                   'updated_at,idempotency_key,request_hash,available_at,timeout_seconds,auto_retry) '
                   'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (id,spec.kind,spec.target_type,spec.target_id,'queued',payload,spec.max_attempts,
                    stamp(now),stamp(now),spec.idempotency_key,fingerprint,now,spec.timeout_seconds,int(spec.auto_retry)))
        return public(row(db,id))

    def get(self,id):
        with connect(self.settings.database) as db:
            return public(row(db,id))

    def _failure(self,db,job,code,message,retryable,now):
        again = retryable and bool(job['auto_retry']) and job['attempts']<job['max_attempts']
        delay = min(2**max(job['attempts']-1,0),60) if again else 0
        db.execute('UPDATE jobs SET status=?,error_json=?,retryable=?,available_at=?,lease_token=NULL,'
                   'lease_owner=NULL,lease_expires_at=NULL,updated_at=? WHERE id=?',
                   ('queued' if again else 'failed',encoded({'code':code,'message':message,'retryable':retryable}),
                    int(retryable),now+delay,stamp(now),job['id']))

    def claim(self,owner,*,lease_seconds=30):
        if not owner or not 0<lease_seconds<=300:
            raise ValueError('Worker owner and lease duration required')
        with self.write() as db:
            now = self.clock()
            expired = db.execute("SELECT id FROM jobs WHERE status='running' AND (lease_expires_at IS NULL OR lease_expires_at<=?)",(now,)).fetchall()
            for (id,) in expired:
                self._failure(db,row(db,id),'LEASE_EXPIRED','Previous worker lease expired',True,now)
            # Legacy/external rows with exhausted budgets must never get an extra attempt.
            db.execute("UPDATE jobs SET status='failed',retryable=0,error_json=?,updated_at=? "
                       "WHERE status='queued' AND attempts>=max_attempts",
                       (encoded({'code':'ATTEMPTS_EXHAUSTED','message':'Attempt limit reached','retryable':False}),stamp(now)))
            candidate = db.execute("SELECT id FROM jobs WHERE status='queued' AND available_at<=? AND attempts<max_attempts "
                                   'ORDER BY created_at,id LIMIT 1',(now,)).fetchone()
            if candidate is None:
                return None
            token = secrets.token_urlsafe(32)
            db.execute("UPDATE jobs SET status='running',attempts=attempts+1,lease_owner=?,lease_token=?,"
                       'lease_expires_at=?,updated_at=?,progress_done=0,progress_total=NULL WHERE id=?',
                       (owner,token,now+lease_seconds,stamp(now),candidate[0]))
            return row(db,candidate[0])

    def _owned(self,db,id,token):
        job = row(db,id)
        if (job['status']!='running' or job['lease_token']!=token
                or job['lease_expires_at'] is None or job['lease_expires_at']<=self.clock()):
            raise LostLease('Job lease is no longer owned')
        return job

    def heartbeat(self,id,token,*,lease_seconds=30):
        if not 0<lease_seconds<=300:
            raise ValueError('Invalid lease duration')
        with self.write() as db:
            self._owned(db,id,token)
            db.execute('UPDATE jobs SET lease_expires_at=?,updated_at=? WHERE id=?',
                       (self.clock()+lease_seconds,stamp(self.clock()),id))

    def progress(self,id,token,done,total=None):
        if (type(done) is not int or not 0<=done<=9223372036854775807
                or (total is not None and (type(total) is not int or not done<=total<=9223372036854775807))):
            raise ValueError('Invalid job progress')
        with self.write() as db:
            self._owned(db,id,token)
            db.execute('UPDATE jobs SET progress_done=?,progress_total=?,updated_at=? WHERE id=?',
                       (done,total,stamp(self.clock()),id))

    def complete(self,id,token,result,*,effect=None):
        """Commit database effect and job completion together. Effect must use this db."""
        result_json = encoded(result)
        with self.write() as db:
            if row(db,id)['status']=='completed':
                return False
            job = self._owned(db,id,token)
            if effect is not None:
                effect(db,job)
            self._owned(db,id,token)  # Long callbacks must not outlive the lease.
            db.execute("UPDATE jobs SET status='completed',result_json=?,error_json=NULL,retryable=0,"
                       'lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=?, '
                       'progress_done=COALESCE(progress_total,progress_done) WHERE id=?',
                       (result_json,stamp(self.clock()),id))
            return True

    def failure(self,id,token,code,message,*,retryable):
        with self.write() as db:
            job = self._owned(db,id,token)
            self._failure(db,job,code,message,retryable,self.clock())

    def retry(self,id,*,request=None):
        with self.write(request) as db:
            job = row(db,id)
            eligible = (job['status']=='failed' or (job['status']=='queued' and job['attempts']>0))
            if not eligible or not job['retryable'] or job['attempts']>=job['max_attempts']:
                fail(409,'JOB_NOT_RETRYABLE','Job is terminal, active or has exhausted its attempt budget')
            db.execute("UPDATE jobs SET status='queued',available_at=?,updated_at=? WHERE id=?",
                       (self.clock(),stamp(self.clock()),id))
            return {'job_id':id,'status':'queued'}

    def worker_heartbeat(self,owner):
        with self.write() as db:
            now = self.clock()
            db.execute('INSERT INTO worker_heartbeats VALUES (?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen', (owner,now))
            db.execute('DELETE FROM worker_heartbeats WHERE last_seen<?',(now-86400,))

    def worker_healthy(self,owner):
        with connect(self.settings.database) as db:
            heartbeat = db.execute('SELECT last_seen FROM worker_heartbeats WHERE id=?',(owner,)).fetchone()
            return heartbeat is not None and 0<=self.clock()-heartbeat[0]<10


def router(settings):
    routes = APIRouter(prefix='/api/v1/jobs')
    queue = JobQueue(settings)
    @routes.get('/{id}')
    def get_job(id: str):
        return queue.get(id)
    @routes.post('/{id}/retry',status_code=202)
    def retry_job(id: str,request: Request):
        return queue.retry(id,request=request)
    return routes
