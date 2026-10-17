"""Shared audit insertion. Caller owns the encompassing database transaction."""
import json
import uuid
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def record_event(db, document_id, event_type, before, after, *, timestamp=None, actor='admin', batch_job_id=None):
    db.execute('INSERT INTO document_events(id,document_id,event_type,before_json,after_json,actor,created_at,batch_job_id) '
               'VALUES (?,?,?,?,?,?,?,?)',
               (uuid.uuid4().hex,document_id,event_type,
                json.dumps(before, ensure_ascii=False, sort_keys=True) if before is not None else None,
                json.dumps(after, ensure_ascii=False, sort_keys=True) if after is not None else None,
                actor,timestamp or utc_now(),batch_job_id))
