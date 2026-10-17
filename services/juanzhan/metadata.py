"""Authenticated manual values and explicit candidate adoption, with versioned audit."""
import json
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from .auth import fail
from .catalog import ID, same_space, transaction
from .document_events import record_event, utc_now
from .document_records import expected, snapshot
from .documents import VersionChange
from .metadata_values import entries, filing, validate


class MetadataPatch(VersionChange):
    values: dict[str,Any] = Field(min_length=1,max_length=1000)
    confirm: bool = Field(strict=True)

    @field_validator('values')
    @classmethod
    def bounded(cls,values):
        try:
            if len(json.dumps(values,ensure_ascii=False,allow_nan=False).encode())>262144:raise ValueError('Metadata exceeds 256 KiB')
        except (TypeError,UnicodeError,RecursionError) as exc:raise ValueError('Bounded JSON required') from exc
        return values


class Adopt(VersionChange):
    extracted_metadata_id: ID
    field_definition_id: ID


def save(db,document,field,raw,confirm,*,source=None):
    if not field['is_active']:fail(422,'INACTIVE_FIELD','Disabled fields cannot receive values')
    id=document['id']
    if raw is None:
        db.execute('DELETE FROM metadata_values WHERE document_id=? AND field_definition_id=?',(id,field['id']))
        return
    column,typed=validate(field,raw)
    current=db.execute('SELECT * FROM metadata_values WHERE document_id=? AND field_definition_id=?',(id,field['id'])).fetchone()
    origin='extracted' if source else 'manual'
    if current and current[column]==typed and current['is_confirmed']==int(confirm) and current['origin']==origin and current['source_parse_run_id']==source:return
    db.execute('DELETE FROM metadata_values WHERE document_id=? AND field_definition_id=?',(id,field['id']))
    db.execute('INSERT INTO metadata_values(id,document_id,space_id,field_definition_id,'+column+',origin,is_confirmed,source_parse_run_id,updated_at) VALUES (?,?,?,?,?,?,?,?,?)',
               (uuid.uuid4().hex,id,document['space_id'],field['id'],typed,origin,int(confirm),source,utc_now()))


def finish(db,before,previous,event,*,candidate_id=None):
    if before['triage_status']=='filed':filing(db,before)
    after=entries(db,before['id'])
    if previous!=after:
        db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(utc_now(),before['id']))
        audit_after={**snapshot(db,before['id']),'metadata':after}
        if candidate_id is not None:audit_after['extracted_metadata_id']=candidate_id
        record_event(db,before['id'],event,{**before,'metadata':previous},audit_after)
    return after


def editable(db,id,version):
    doc=expected(db,id,version)
    if doc['deleted_at'] is not None:fail(409,'DOCUMENT_TRASHED','Restore before editing metadata')
    return doc


def router(settings):
    routes=APIRouter(prefix='/api/v1/documents')

    @routes.get('/{id}/metadata')
    def read(id: str):
        with transaction(settings) as db:
            snapshot(db,id)
            return entries(db,id)

    @routes.patch('/{id}/metadata')
    def patch(id: str,body: MetadataPatch,request: Request):
        with request.app.state.documents.write(request) as db:
            doc=editable(db,id,body.expected_document_version);previous=entries(db,id)
            for key,raw in body.values.items():
                field=db.execute('SELECT * FROM field_definitions WHERE space_id=? AND field_key=?',(doc['space_id'],key)).fetchone()
                if field is None:fail(422,'UNKNOWN_FIELD','Field key does not belong to the document space')
                save(db,doc,field,raw,body.confirm)
            return finish(db,doc,previous,'metadata_updated')

    @routes.post('/{id}/metadata/adopt-candidate')
    def adopt(id: str,body: Adopt,request: Request):
        with request.app.state.documents.write(request) as db:
            doc=editable(db,id,body.expected_document_version);previous=entries(db,id)
            field=same_space(db,'field_definitions',body.field_definition_id,doc['space_id'])
            candidate=db.execute('SELECT e.*,p.document_id,p.revision_id,p.status FROM extracted_metadata e JOIN parse_runs p ON p.id=e.parse_run_id WHERE e.id=?',(body.extracted_metadata_id,)).fetchone()
            if candidate is None:fail(404,'NOT_FOUND','Candidate not found')
            if candidate['document_id']!=id:fail(422,'CROSS_DOCUMENT_CANDIDATE','Candidate belongs to another document')
            if candidate['status']!='completed' or candidate['revision_id']!=doc['current_revision_id'] or candidate['parse_run_id']!=doc['current_parse_run_id']:
                fail(409,'STALE_CANDIDATE','Candidate is not from the current successful content')
            raw=json.loads(candidate['candidate_value_json'])
            if raw is None:fail(422,'EMPTY_CANDIDATE','A null candidate cannot erase a value')
            save(db,doc,field,raw,True,source=candidate['parse_run_id'])
            return finish(db,doc,previous,'metadata_candidate_adopted',candidate_id=body.extracted_metadata_id)
    return routes
