"""Durable task controls. Revoke leases; retain referenced records and originals."""
import json
import uuid
from typing import Annotated,Literal
from fastapi import APIRouter,Request,HTTPException
from pydantic import Field
from .catalog import Input
from .document_events import utc_now
from .auth import fail

class ControlInput(Input):
    action:Literal['pause','resume','cancel','delete']
    job_ids:list[Annotated[str,Field(min_length=1,max_length=255)]]=Field(min_length=1,max_length=1000)

def present(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_controls'").fetchone() is not None

def control(db,queue,id,action):
    from .jobs import row,encoded,stamp
    job=row(db,id);mode=job.get('control_state');status=job['status'];timestamp=stamp(queue.clock())
    if action=='pause':
        if mode=='paused':return 'paused'
        if mode=='deleted' or status not in ('queued','running'):fail(409,'JOB_CONTROL_CONFLICT','Only queued or running tasks may pause')
        if status=='running' and job['max_attempts']>=1000000:fail(409,'JOB_CONTROL_CONFLICT','Task pause budget exceeded')
    elif action=='resume':
        if mode!='paused':
            if not mode and status=='queued':return 'queued'
            fail(409,'JOB_CONTROL_CONFLICT','Only paused tasks may resume')
    elif action=='cancel':
        if status=='cancelled':return 'cancelled'
        if mode=='deleted' or status not in ('queued','running'):fail(409,'JOB_CONTROL_CONFLICT','Finished tasks cannot be cancelled')
    elif action=='delete' and mode=='deleted':return 'deleted'
    if action=='resume':
        if job['kind'] in ('parse','ocr') and job['target_type']=='document':
            from .upload_policy import check
            from .upload_exclusions import excluded_file
            revision=json.loads(job['payload_json']).get('revision_id')
            file=db.execute('SELECT original_filename FROM file_revisions WHERE id=? AND document_id=?',(revision,job['target_id'])).fetchone()
            if not file:fail(409,'REVISION_CHANGED','Original version is unavailable')
            if excluded_file(file[0]):fail(422,'UPLOAD_EXCLUDED','Auxiliary file excluded')
            check(db,file[0])
        db.execute('DELETE FROM job_controls WHERE job_id=?',(id,))
        db.execute("UPDATE jobs SET status='queued',available_at=?,updated_at=?,error_json=NULL,retryable=0 WHERE id=?",(queue.clock(),timestamp,id))
        effective='queued'
    else:
        if status in ('queued','running'):
            from .parsing import failed as parse_failed
            parse_failed(db,job,'JOB_PAUSED' if action=='pause' else 'JOB_CANCELLED')
            from .job_steps import finish
            finish(db,job,'discarded')
            from .indexing import failed as index_failed
            if action!='pause':index_failed(db,job,'JOB_CANCELLED',True)
            from .exclusions import failed as exclusion_failed
            exclusion_failed(db,job,action!='pause')
            from .source_scans import job_state
            job_state(db,job,'queued' if action=='pause' else 'cancelled',timestamp,
                      error=encoded({'code':'JOB_PAUSED' if action=='pause' else 'JOB_CANCELLED'}))
            db.execute("UPDATE jobs SET status=?,max_attempts=max_attempts+?,lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=?,error_json=NULL,retryable=0 WHERE id=?",
                       ('queued' if action=='pause' else 'cancelled',int(action=='pause' and status=='running'),timestamp,id))
        mode={'pause':'paused','cancel':'cancelled','delete':'deleted'}[action]
        db.execute('INSERT INTO job_controls VALUES (?,?,?) ON CONFLICT(job_id) DO UPDATE SET mode=excluded.mode,updated_at=excluded.updated_at',(id,mode,timestamp))
        effective=mode
    db.execute('INSERT INTO job_control_events VALUES (?,?,?,?)',(uuid.uuid4().hex,id,action,timestamp))
    return effective

def router(settings):
    from .jobs import JobQueue
    queue=JobQueue(settings);routes=APIRouter(prefix='/api/v1/jobs')
    @routes.post('/control')
    def apply(body:ControlInput,request:Request):
        results=[]
        with queue.write(request) as db:
            for id in dict.fromkeys(body.job_ids):
                db.execute('SAVEPOINT job_control')
                try:
                    status=control(db,queue,id,body.action)
                    db.execute('RELEASE job_control');results.append({'job_id':id,'status':status})
                except HTTPException as exc:
                    db.execute('ROLLBACK TO job_control');db.execute('RELEASE job_control')
                    detail=exc.detail;results.append({'job_id':id,'error_code':detail.get('code','NOT_FOUND')})
        return {'items':results,'succeeded':sum('error_code' not in r for r in results),'failed':sum('error_code' in r for r in results)}
    return routes
