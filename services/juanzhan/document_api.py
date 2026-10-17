"""Authenticated document management and conservative public status projection."""
import json
from datetime import date
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import fail
from .catalog import ID, required, same_space, transaction
from .document_events import record_event, utc_now
from .document_records import snapshot, expected
from .documents import Registration, Version, VersionChange
from .metadata_values import filing


class DocumentPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_document_version: Version
    title: Annotated[str,Field(min_length=1,max_length=1000)] | None=None
    description: Annotated[str,Field(max_length=65536)] | None=None
    document_date: str | None=None
    folder_id: ID | None=None
    document_type_id: ID | None=None
    is_favorite: bool | None=Field(default=None,strict=True)
    tags_add: list[ID]=Field(default_factory=list,max_length=1000)
    tags_remove: list[ID]=Field(default_factory=list,max_length=1000)

    @field_validator('title')
    @classmethod
    def title_text(cls,value):
        if value is None:raise ValueError('Title cannot be null')
        return Registration.title_is_text(value)

    @field_validator('document_date')
    @classmethod
    def business_date(cls,value):
        if value is not None:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('ISO business date required')
            date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def changes(self):
        if self.model_fields_set=={'expected_document_version'}:raise ValueError('No patch fields')
        for key in self.model_fields_set-{'folder_id','document_type_id','document_date'}:
            if getattr(self,key) is None:raise ValueError('Field cannot be null')
        if set(self.tags_add)&set(self.tags_remove):raise ValueError('Tag cannot be added and removed together')
        return self


class Triage(VersionChange):
    triage_status: Literal['needs_review','filed']


def availability(db,revision,store):
    if revision is None:return 'missing',None
    if revision['storage_kind']=='managed':
        obj=db.execute('SELECT storage_key,sha256,size_bytes FROM managed_objects WHERE id=?',
                       (revision['managed_object_id'],)).fetchone()
        if obj is None:return 'missing',None
        if obj['sha256']!=revision['sha256'] or obj['size_bytes']!=revision['size_bytes']:return 'unknown',None
        return store.probe(obj['storage_key']),None
    entry=db.execute('SELECT * FROM source_entries WHERE id=?',(revision['source_entry_id'],)).fetchone()
    if entry is None:return 'missing',None
    source=db.execute('SELECT status FROM sources WHERE id=?',(entry['source_id'],)).fetchone()
    if source is None or source['status'] in ('offline','error','disabled'):return 'source_offline',entry['source_id']
    if entry['status']!='available':return entry['status'],entry['source_id']
    # T11/T14 must verify the configured read-only mount before bytes can be promised.
    return 'unknown',entry['source_id']


def project(db,id,store):
    result=snapshot(db,id)
    revision=db.execute('SELECT * FROM file_revisions WHERE id=?',(result['current_revision_id'],)).fetchone()
    result['availability_status'],result['source_id']=availability(db,revision,store)
    result['origin_kind']=revision['storage_kind'] if revision else 'managed'
    current=db.execute('SELECT revision_id,status FROM parse_runs WHERE id=?',(result['current_parse_run_id'],)).fetchone()
    result['content_stale']=bool(current and current['revision_id']!=result['current_revision_id'])
    latest=db.execute('SELECT status,COALESCE(completed_at,started_at,created_at) AS state_time FROM parse_runs WHERE document_id=? AND revision_id=? ORDER BY created_at DESC,id DESC LIMIT 1',
                      (id,result['current_revision_id'])).fetchone()
    status=latest['status'] if latest else 'not_started'
    job=db.execute("SELECT status,error_json,updated_at FROM jobs WHERE target_type='document' AND target_id=? AND kind IN ('parse','ocr') "
                   "AND json_extract(payload_json,'$.revision_id')=? ORDER BY created_at DESC,id DESC LIMIT 1",
                   (id,result['current_revision_id'])).fetchone()
    if job and (not latest or job['updated_at']>=latest['state_time']):
        if job['status'] in ('queued','running'):status=job['status']
        elif job['status']=='failed':
            error=json.loads(job['error_json']) if job['error_json'] else {}
            status='unsupported' if error.get('code')=='HANDLER_NOT_AVAILABLE' else 'failed'
        elif not latest:status='failed' if job['status']=='completed' else 'not_started'
    result['processing_status']=status
    # documents contains no backend file paths; expose the explicit public field set.
    keys=('id','space_id','folder_id','title','description','document_date','document_type_id','tag_ids',
          'triage_status','is_favorite','document_version','current_revision_id','current_parse_run_id',
          'origin_kind','source_id','availability_status','processing_status','content_stale','imported_at','deleted_at')
    return {key:result[key] for key in keys}


def router(settings):
    routes=APIRouter(prefix='/api/v1/documents')
    def view(request,id):
        with transaction(settings) as db:return project(db,id,request.app.state.storage)

    @routes.get('')
    def documents(request: Request,space_id: ID | None=None,folder_id: ID | None=None,
                  document_type_id: ID | None=None,triage_status: Literal['needs_review','filed'] | None=None,
                  source_kind: Literal['managed','external'] | None=None,is_favorite: bool | None=None,
                  trash: Literal['exclude','only','include']='exclude',sort: str='-imported_at',
                  page: int=Query(1,ge=1,le=2147483647),page_size: int=Query(30,ge=1,le=100),
                  q: str | None=Query(None,max_length=1000)):
        if q:fail(501,'SEARCH_NOT_IMPLEMENTED','Full text search is not implemented')
        order={'imported_at':'d.imported_at','title':'d.title','document_date':'d.document_date','size_bytes':'r.size_bytes'}
        key=sort.lstrip('-')
        if key not in order or sort not in (key,'-'+key):fail(422,'INVALID_SORT','Unsupported sort key')
        with transaction(settings) as db:
            if space_id is not None:required(db,'spaces',space_id)
            for table,id in (('folders',folder_id),('document_types',document_type_id)):
                if id is not None:
                    record=required(db,table,id)
                    if space_id is not None and record['space_id']!=space_id:fail(422,'CROSS_SPACE_REFERENCE','Filter belongs to another space')
            where=[];parameters=[]
            for column,value in (('d.space_id',space_id),('d.folder_id',folder_id),('d.document_type_id',document_type_id),
                                 ('d.triage_status',triage_status),('r.storage_kind',source_kind),('d.is_favorite',is_favorite)):
                if value is not None:where.append(column+'=?');parameters.append(value)
            if trash!='include':where.append('d.deleted_at IS '+('NOT NULL' if trash=='only' else 'NULL'))
            clause=' AND '.join(where) or '1'
            base=' FROM documents d LEFT JOIN file_revisions r ON r.id=d.current_revision_id WHERE '+clause
            total=db.execute('SELECT count(*)'+base,parameters).fetchone()[0]
            ids=db.execute('SELECT d.id'+base+' ORDER BY '+order[key]+(' DESC' if sort.startswith('-') else ' ASC')+',d.id ASC LIMIT ? OFFSET ?',
                           (*parameters,page_size,(page-1)*page_size)).fetchall()
            return {'items':[project(db,row[0],request.app.state.storage) for row in ids],
                    'page':page,'page_size':page_size,'total':total}

    @routes.get('/{id}')
    def detail(id: str,request: Request):return view(request,id)

    @routes.patch('/{id}')
    def patch(id: str,body: DocumentPatch,request: Request):
        service=request.app.state.documents
        with service.write(request) as db:
            before=expected(db,id,body.expected_document_version)
            if before['deleted_at'] is not None:fail(409,'DOCUMENT_TRASHED','Restore before editing')
            values=body.model_dump(exclude_unset=True)
            for name,table in (('folder_id','folders'),('document_type_id','document_types')):
                if name in values and values[name] is not None:
                    related=same_space(db,table,values[name],before['space_id'])
                    if name=='document_type_id' and not related['is_active'] and values[name]!=before[name]:
                        fail(422,'INACTIVE_DOCUMENT_TYPE','Cannot assign disabled type')
            for tag in set(body.tags_add+body.tags_remove):same_space(db,'tags',tag,before['space_id'])
            for tag in set(body.tags_remove):db.execute('DELETE FROM document_tags WHERE document_id=? AND tag_id=?',(id,tag))
            for tag in set(body.tags_add):db.execute('INSERT OR IGNORE INTO document_tags VALUES (?,?,?)',(id,before['space_id'],tag))
            columns=[key for key in values if key not in ('expected_document_version','tags_add','tags_remove')]
            if columns:
                db.execute('UPDATE documents SET '+','.join(key+'=?' for key in columns)+' WHERE id=?',
                           (*[values[key] for key in columns],id))
            candidate=snapshot(db,id)
            if (candidate['triage_status']=='filed' and 'document_type_id' in values
                    and candidate['document_type_id']!=before['document_type_id']):filing(db,candidate)
            if candidate!=before:
                timestamp=utc_now()
                db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(timestamp,id))
                record_event(db,id,'document_updated',before,snapshot(db,id),timestamp=timestamp)
        return view(request,id)

    @routes.post('/{id}/triage')
    def triage(id: str,body: Triage,request: Request):
        with request.app.state.documents.write(request) as db:
            before=expected(db,id,body.expected_document_version)
            if before['deleted_at'] is not None:fail(409,'DOCUMENT_TRASHED','Restore before filing')
            if body.triage_status=='filed':filing(db,before)
            if before['triage_status']!=body.triage_status:
                timestamp=utc_now()
                db.execute('UPDATE documents SET triage_status=?,document_version=document_version+1,updated_at=? WHERE id=?',
                           (body.triage_status,timestamp,id))
                record_event(db,id,'document_triaged',before,snapshot(db,id),timestamp=timestamp)
        return view(request,id)

    @routes.post('/{id}/trash')
    def trash(id: str,body: VersionChange,request: Request):
        request.app.state.documents.trash(id,body,request=request)
        return view(request,id)

    @routes.post('/{id}/restore')
    def restore(id: str,body: VersionChange,request: Request):
        request.app.state.documents.restore(id,body,request=request)
        return view(request,id)

    @routes.get('/{id}/revisions')
    def revisions(id: str,request: Request):
        with transaction(settings) as db:
            snapshot(db,id)
            rows=db.execute('SELECT * FROM file_revisions WHERE document_id=? ORDER BY revision_no DESC',(id,)).fetchall()
            result=[]
            for row in rows:
                available,_=availability(db,row,request.app.state.storage)
                item={key:row[key] for key in ('id','revision_no','storage_kind','original_filename','mime_type','sha256','size_bytes','created_at')}
                item['binary_available']=available=='available'
                item['can_restore_binary']=row['storage_kind']=='managed' and available=='available'
                result.append(item)
            return result
    return routes
