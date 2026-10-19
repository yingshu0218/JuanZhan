"""Persistent incremental scan deadlines; no system cron or unbounded catch-up."""
import sqlite3
import time
import uuid
from datetime import datetime,timezone

from .document_events import utc_now
from .jobs import JobQueue,JobSpec


def public(db,source_id):
    row=db.execute('SELECT * FROM source_scan_schedules WHERE source_id=?',(source_id,)).fetchone()
    if row is None:return {'version':1,'next_run_at':None,'last_job_id':None}
    return {'version':row['version'],'last_job_id':row['last_job_id'],
        'next_run_at':datetime.fromtimestamp(row['next_due_at'],timezone.utc).isoformat().replace('+00:00','Z') if row['next_due_at'] is not None else None}


def schedule(settings,*,clock=time.time,limit=20):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid scheduling limit')
    queue=JobQueue(settings);now=clock();queued=[]
    with queue.write() as db:
        db.row_factory=sqlite3.Row
        sources=db.execute('SELECT s.*,p.next_due_at FROM sources s JOIN source_scan_schedules p ON p.source_id=s.id '
            "WHERE s.kind='external' AND s.status!='disabled' AND s.initial_import_completed_at IS NOT NULL "
            'AND s.scan_interval_minutes>0 AND p.next_due_at<=? ORDER BY p.next_due_at,s.id LIMIT ?',
            (now,limit)).fetchall()
        for source in sources:
            # Advance even if a manual scan is active. Resume without replaying missed intervals.
            db.execute('UPDATE source_scan_schedules SET next_due_at=? WHERE source_id=?',
                (now+source['scan_interval_minutes']*60,source['id']))
            active=db.execute('SELECT 1 FROM scan_runs r JOIN jobs j ON j.target_id=r.id WHERE r.source_id=? '
                "AND j.target_type IN ('source_preview','source_initial','source_incremental') AND j.status IN ('queued','running') LIMIT 1",
                (source['id'],)).fetchone()
            if active:continue
            run_id=uuid.uuid4().hex
            db.execute("INSERT INTO scan_runs(id,source_id,mode,status,created_at) VALUES (?,?,'incremental','queued',?)",
                (run_id,source['id'],utc_now()))
            job=queue.enqueue(JobSpec(kind='scan',target_type='source_incremental',target_id=run_id,
                payload={},idempotency_key='source-scheduled:'+run_id,timeout_seconds=300),db=db)
            db.execute('UPDATE source_scan_schedules SET last_job_id=? WHERE source_id=?',(job['id'],source['id']))
            queued.append(job['id'])
    return queued
