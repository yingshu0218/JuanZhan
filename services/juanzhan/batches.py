"""Bounded durable selection snapshots, per-item savepoints, and guarded logical undo."""
import json
import sqlite3
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .auth import fail
from .catalog import ID, required, same_space
from .document_api import DocumentPatch, Triage, filing
from .document_events import record_event, utc_now
from .document_records import expected, snapshot
from .documents import Version
from .jobs import JobQueue, JobSpec, encoded, row


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    space_id: ID
    document_ids: list[ID] = Field(min_length=1, max_length=100)
    selection_mode: Literal['explicit', 'snapshot']
    expected_versions: dict[str, Version]
    operation: Literal['move_folder','add_tags','remove_tags','set_type','set_triage','set_favorite','trash','reprocess','set_metadata']
    payload: dict

    @model_validator(mode='after')
    def selection(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError('Duplicate document IDs')
        if set(self.expected_versions) != set(self.document_ids):
            raise ValueError('Every selected ID must have exactly one expected version')
        return self


def changes(body):
    """Validate operation-specific payloads before enqueue; scopes are checked per item."""
    keys = {'move_folder':'folder_id', 'add_tags':'tag_ids', 'remove_tags':'tag_ids',
            'set_type':'document_type_id', 'set_triage':'triage_status', 'set_favorite':'is_favorite', 'trash':None}
    if body.operation not in keys:
        fail(501, 'BATCH_OPERATION_NOT_IMPLEMENTED', 'This operation awaits its business handler')
    key = keys[body.operation]
    if set(body.payload) != ({key} if key else set()):
        fail(422, 'INVALID_BATCH_PAYLOAD', 'Payload must match the selected operation')
    values = dict(body.payload)
    if key == 'tag_ids':
        values = {'tags_add' if body.operation=='add_tags' else 'tags_remove':values[key]}
    # Use the same strict field rules as single-document edits.
    if body.operation=='set_triage':
        Triage(expected_document_version=1, **values)
    elif key:
        DocumentPatch(expected_document_version=1, **values)
    return values


def audit(db, id, kind, before, after, job_id):
    record_event(db, id, kind, before, after, batch_job_id=job_id)


def apply(db, id, version, body):
    before = expected(db,id,version)
    if before['space_id'] != body['space_id']:
        fail(422,'CROSS_SPACE_REFERENCE','Document belongs to another space')
    operation = body['operation']
    values = body['changes']
    if before['deleted_at'] is not None:
        if operation=='trash':return before,before
        fail(409,'DOCUMENT_TRASHED','Restore before editing')
    if operation in ('move_folder','set_type'):
        key = 'folder_id' if operation=='move_folder' else 'document_type_id'
        value = values[key]
        if value is not None:
            related=same_space(db,'folders' if operation=='move_folder' else 'document_types',value,body['space_id'])
            if operation=='set_type' and not related['is_active'] and value!=before[key]:
                fail(422,'INACTIVE_DOCUMENT_TYPE','Cannot assign disabled type')
        db.execute('UPDATE documents SET '+key+'=? WHERE id=?',(value,id))
    elif operation in ('add_tags','remove_tags'):
        tags=next(iter(values.values()))
        for tag in set(tags):same_space(db,'tags',tag,body['space_id'])
        for tag in set(tags):
            if operation=='add_tags':db.execute('INSERT OR IGNORE INTO document_tags VALUES (?,?,?)',(id,body['space_id'],tag))
            else:db.execute('DELETE FROM document_tags WHERE document_id=? AND tag_id=?',(id,tag))
    elif operation=='set_triage':
        if values['triage_status']=='filed':filing(db,before)
        db.execute('UPDATE documents SET triage_status=? WHERE id=?',(values['triage_status'],id))
    elif operation=='set_favorite':
        db.execute('UPDATE documents SET is_favorite=? WHERE id=?',(values['is_favorite'],id))
    elif operation=='trash':
        db.execute('UPDATE documents SET deleted_at=? WHERE id=?',(utc_now(),id))
    else:fail(422,'INVALID_BATCH_PAYLOAD','Invalid operation')
    after=snapshot(db,id)
    if operation=='set_type' and after['triage_status']=='filed' and after['document_type_id']!=before['document_type_id']:
        filing(db,after)
    return before,after


def undo_item(db, event):
    before,after=json.loads(event['before_json']),json.loads(event['after_json'])
    current=expected(db,event['document_id'],after['document_version'])
    # Revalidate all restored references; catalog entries may have been removed since execution.
    for key,table in (('folder_id','folders'),('document_type_id','document_types')):
        if before[key] is not None:same_space(db,table,before[key],before['space_id'])
    for tag in before['tag_ids']:same_space(db,'tags',tag,before['space_id'])
    for key in ('folder_id','document_type_id','triage_status','is_favorite','deleted_at'):
        if before[key]!=after[key]:db.execute('UPDATE documents SET '+key+'=? WHERE id=?',(before[key],current['id']))
    if before['tag_ids']!=after['tag_ids']:
        db.execute('DELETE FROM document_tags WHERE document_id=?',(current['id'],))
        db.executemany('INSERT INTO document_tags VALUES (?,?,?)',[(current['id'],before['space_id'],tag) for tag in before['tag_ids']])
    restored=snapshot(db,current['id'])
    if restored['triage_status']=='filed':filing(db,restored)
    return current,restored


def execute(db,job):
    db.row_factory=sqlite3.Row
    body=json.loads(job['payload_json'])
    undo=body.get('undo_of')
    events={}
    if undo:
        events={event['document_id']:event for event in db.execute(
            "SELECT * FROM document_events WHERE batch_job_id=? AND event_type='batch_changed'",(undo,))}
    items=[]
    for id in body['document_ids']:
        db.execute('SAVEPOINT batch_item')
        try:
            before,after=undo_item(db,events[id]) if undo else apply(db,id,body['expected_versions'][id],body)
            status='skipped'
            if before!=after:
                db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(utc_now(),id))
                after=snapshot(db,id)
                audit(db,id,'batch_undone' if undo else 'batch_changed',before,after,job['id'])
                status='succeeded'
            item={'document_id':id,'status':status,'document_version':after['document_version']}
            db.execute('RELEASE batch_item')
        except (HTTPException,sqlite3.IntegrityError) as exc:
            db.execute('ROLLBACK TO batch_item');db.execute('RELEASE batch_item')
            code=exc.detail['code'] if isinstance(exc,HTTPException) else 'INTEGRITY_CONFLICT'
            item={'document_id':id,'status':'failed','error_code':code}
        items.append(item)
    result={'job_id':job['id'],'items':items,**{status:sum(i['status']==status for i in items) for status in ('succeeded','skipped','failed')}}
    db.execute('UPDATE jobs SET progress_total=?,progress_done=? WHERE id=?',(len(items),len(items),job['id']))
    return result


def router(settings):
    routes=APIRouter()
    queue=JobQueue(settings)

    @routes.post('/api/v1/documents/batch',status_code=202)
    def submit(body: BatchRequest,request: Request):
        # Convert Pydantic errors raised by operation validators into the safe API error shape.
        from pydantic import ValidationError
        try:values=changes(body)
        except ValidationError:fail(422,'INVALID_BATCH_PAYLOAD','Payload does not match operation schema')
        payload=body.model_dump();payload['changes']=values
        try:encoded(payload)
        except ValueError:fail(422,'BATCH_TOO_LARGE','Batch exceeds the serialized size limit')
        with queue.write(request) as db:
            required(db,'spaces',body.space_id)
            job=queue.enqueue(JobSpec(kind='batch',target_type='document_batch',target_id=body.space_id,
                                     payload=payload,idempotency_key='batch:'+uuid.uuid4().hex),db=db)
        return {'job_id':job['id'],'status':job['status']}

    @routes.post('/api/v1/jobs/{id}/undo',status_code=202)
    def undo(id: str,request: Request):
        with queue.write(request) as db:
            original=row(db,id)
            if original['kind']!='batch' or original['target_type']!='document_batch' or original['status']!='completed':
                fail(409,'BATCH_NOT_UNDOABLE','Only completed forward document batches can be undone')
            ids=[r[0] for r in db.execute("SELECT document_id FROM document_events WHERE batch_job_id=? AND event_type='batch_changed' ORDER BY document_id",(id,))]
            if not ids:fail(409,'BATCH_NOT_UNDOABLE','Batch has no successful changes to undo')
            job=queue.enqueue(JobSpec(kind='batch',target_type='document_batch_undo',target_id=original['target_id'],
                                     payload={'undo_of':id,'document_ids':ids},idempotency_key='batch-undo:'+id),db=db)
        return {'job_id':job['id'],'status':job['status']}
    return routes
