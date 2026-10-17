"""Bounded literal FTS and exact, space-scoped structured search."""
import json
import sqlite3
import time
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from .auth import fail
from .catalog import ID, required, same_space, transaction
from .metadata_values import COLUMNS, scalar
from .tokenizer import VERSION, match_expression


MAX_RESPONSE=16*1024*1024
MAX_REQUEST=1024*1024
QUERY_SECONDS=3
MAX_OBSERVATIONS=5000

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')

class Folder(Input):
    id: ID
    include_descendants: bool=Field(default=False,strict=True)

class Tags(Input):
    ids: list[ID]=Field(min_length=1,max_length=100)
    match: Literal['any','all']='any'

class Metadata(Input):
    key: str=Field(min_length=1,max_length=255)
    operator: Literal['eq','in','contains','gte','lte','between','is_null']
    value: Any=None

    @model_validator(mode='after')
    def operands(self):
        if self.operator=='is_null':
            if 'value' in self.model_fields_set:raise ValueError('is_null takes no value')
        elif self.value is None:raise ValueError('A non-null operand is required')
        return self

class Sort(Input):
    field: Literal['relevance','imported_at','document_date','title','size_bytes']
    order: Literal['asc','desc']='asc'

class SearchRequest(Input):
    space_id: ID
    text: str | None=Field(default=None,max_length=512)
    folder: Folder | None=None
    document_type_ids: list[ID]=Field(default_factory=list,max_length=100)
    tags: Tags | None=None
    metadata: list[Metadata]=Field(default_factory=list,max_length=32)
    source_id: ID | None=None
    source_kind: Literal['managed','external'] | None=None
    triage_status: Literal['needs_review','filed'] | None=None
    availability_status: Literal['available','missing','suspected_missing','source_offline','unknown','needs_match'] | None=None
    processing_status: Literal['not_started','queued','running','completed','failed','unsupported','discarded'] | None=None
    is_favorite: bool | None=Field(default=None,strict=True)
    trash: Literal['exclude','only','include']='exclude'
    document_date_from: str | None=None
    document_date_to: str | None=None
    sort: list[Sort]=Field(default_factory=list,max_length=5)
    page: int=Field(default=1,ge=1,le=2147483647,strict=True)
    page_size: int=Field(default=30,ge=1,le=100,strict=True)


def expression(text):
    if text is None or text=='':return None
    try:return match_expression(text)
    except (ValueError,UnicodeError):fail(422,'INVALID_SEARCH_TEXT','Search requires bounded literal words')


def metadata_clause(db,space,condition):
    field=db.execute('SELECT * FROM field_definitions WHERE space_id=? AND field_key=?',(space,condition.key)).fetchone()
    if field is None:fail(422,'UNKNOWN_SEARCH_FIELD','Unknown metadata field in this space')
    if not field['is_active'] or not field['filterable']:fail(422,'FIELD_NOT_FILTERABLE','Field is not active and filterable')
    kind=field['field_type'];column=COLUMNS[kind];op=condition.operator;raw=condition.value
    prefix='SELECT 1 FROM metadata_values m WHERE m.field_definition_id=? AND m.document_id=d.id'
    if op=='is_null':return 'NOT EXISTS('+prefix+')',[field['id']]
    if op=='contains' and kind not in ('text','long_text'):fail(422,'INVALID_SEARCH_OPERATOR','contains requires a text field')
    if op in ('gte','lte','between') and kind not in ('integer','decimal','date'):fail(422,'INVALID_SEARCH_OPERATOR','Range requires numeric or date field')
    if op=='in':
        if not isinstance(raw,list) or not 1<=len(raw)<=100:fail(422,'INVALID_SEARCH_VALUE','in requires 1 to 100 typed values')
        values=[scalar(kind,v) for v in raw];predicate=column+' IN ('+','.join('?' for _ in values)+')'
    elif op=='between':
        if not isinstance(raw,list) or len(raw)!=2:fail(422,'INVALID_SEARCH_VALUE','between requires two typed bounds')
        values=[scalar(kind,v) for v in raw]
        if values[0]>values[1]:fail(422,'INVALID_SEARCH_VALUE','Range is reversed')
        predicate=column+' BETWEEN ? AND ?'
    else:
        values=[scalar(kind,raw)]
        predicate=('instr('+column+',?)>0') if op=='contains' else column+{'eq':'=','gte':'>=','lte':'<='}[op]+'?'
    return 'd.id IN (SELECT m.document_id FROM metadata_values m WHERE m.field_definition_id=? AND '+predicate+')',[field['id'],*values]


def structured(db,body):
    required(db,'spaces',body.space_id)
    where=['d.space_id=?'];params=[body.space_id]
    def append(sql,values):where.append(sql);params.extend(values)
    if body.folder:
        same_space(db,'folders',body.folder.id,body.space_id)
        if body.folder.include_descendants:
            append('d.folder_id IN (WITH RECURSIVE subtree(id) AS (SELECT ? UNION SELECT f.id FROM folders f JOIN subtree s ON f.parent_id=s.id WHERE f.space_id=?) SELECT id FROM subtree)',[body.folder.id,body.space_id])
        else:append('d.folder_id=?',[body.folder.id])
    if body.document_type_ids:
        ids=list(dict.fromkeys(body.document_type_ids))
        for id in ids:same_space(db,'document_types',id,body.space_id)
        append('d.document_type_id IN ('+','.join('?' for _ in ids)+')',ids)
    if body.tags:
        ids=list(dict.fromkeys(body.tags.ids))
        for id in ids:same_space(db,'tags',id,body.space_id)
        clause='(SELECT count(*) FROM document_tags dt WHERE dt.document_id=d.id AND dt.tag_id IN ('+','.join('?' for _ in ids)+'))'
        append(clause+('=?' if body.tags.match=='all' else '>0'),ids+([len(ids)] if body.tags.match=='all' else []))
    for condition in body.metadata:
        sql,values=metadata_clause(db,body.space_id,condition);append(sql,values)
    if body.source_id:
        same_space(db,'sources',body.source_id,body.space_id)
        append('r.source_entry_id IN (SELECT id FROM source_entries WHERE source_id=?)',[body.source_id])
    for column,value in [('r.storage_kind',body.source_kind),('d.triage_status',body.triage_status),('d.is_favorite',body.is_favorite)]:
        if value is not None:append(column+'=?',[value])
    if body.trash!='include':where.append('d.deleted_at IS '+('NOT NULL' if body.trash=='only' else 'NULL'))
    dates=[]
    for raw,op in [(body.document_date_from,'>='),(body.document_date_to,'<=')]:
        if raw is not None:
            dates.append(scalar('date',raw));append('d.document_date'+op+'?',[raw])
    if len(dates)==2 and dates[0]>dates[1]:fail(422,'INVALID_SEARCH_VALUE','Date range is reversed')
    return where,params


def state(row):
    if row['last_error']:return 'failed'
    if row['tokenizer_version'] is None:return 'missing'
    if row['tokenizer_version']!=VERSION or row['index_generation']!=row['dirty_generation']:return 'pending'
    return 'current'


def query(db,request,mounts,where,params,text,sort,page,page_size,status_filters=None):
    # All counts, membership and item projections use the same database snapshot.
    from .document_api import project
    match=expression(text)
    names=[s.field for s in sort]
    if len(set(names))!=len(names):fail(422,'INVALID_SORT','Duplicate sort field')
    if 'relevance' in names and not match:fail(422,'INVALID_SORT','Relevance requires search text')
    order=sort or [Sort(field='relevance',order='desc') if match else Sort(field='imported_at',order='desc')]
    columns={'relevance':'bm25(document_search)','imported_at':'d.imported_at','document_date':'d.document_date','title':'d.title','size_bytes':'r.size_bytes'}
    orders=[]
    for item in order:
        # FTS5 smaller (more negative) bm25 means greater relevance.
        descending=(item.order=='desc') != (item.field=='relevance')
        orders.append(columns[item.field]+(' DESC' if descending else ' ASC'))
    observations={};status_limit=[False]
    if status_filters:
        def observed(id,field):
            if id not in observations:
                if len(observations)>=MAX_OBSERVATIONS or time.monotonic()>deadline:
                    status_limit[0]=True
                    raise ValueError('Status observation budget exceeded')
                try:item=project(db,id,request.app.state.storage,mounts)
                except sqlite3.OperationalError:
                    status_limit[0]=time.monotonic()>deadline
                    raise
                observations[id]={key:item[key] for key in ('availability_status','processing_status')}
            return observations[id][field]
        db.create_function('search_observed_status',2,observed)
        where=list(where);params=list(params)
        for field,value in status_filters.items():
            if value is not None:
                where.append('search_observed_status(d.id,?)=?');params.extend([field,value])
    base=' FROM documents d LEFT JOIN file_revisions r ON r.id=d.current_revision_id'
    scope=' WHERE '+' AND '.join(where)
    deadline=time.monotonic()+QUERY_SECONDS
    db.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
    try:
        rows=db.execute('SELECT count(*) AS total,'
            'sum(CASE WHEN s.document_id IS NULL THEN 1 ELSE 0 END) AS missing,'
            'sum(CASE WHEN x.last_error IS NOT NULL THEN 1 ELSE 0 END) AS failed,'
            'sum(CASE WHEN s.document_id IS NOT NULL AND x.last_error IS NULL AND (s.tokenizer_version!=? OR s.generation!=x.generation) THEN 1 ELSE 0 END) AS pending,'
            'sum(CASE WHEN d.current_parse_run_id IS NULL THEN 1 ELSE 0 END) AS without_content,'
            "sum(CASE WHEN EXISTS(SELECT 1 FROM parse_runs p WHERE p.id=d.current_parse_run_id AND (p.text_available=0 OR EXISTS(SELECT 1 FROM json_each(p.warnings_json) WHERE value='NO_TEXT_LAYER_OCR_REQUIRED'))) THEN 1 ELSE 0 END) AS limited_content,"
            'sum(CASE WHEN EXISTS(SELECT 1 FROM parse_runs p WHERE p.id=d.current_parse_run_id AND p.revision_id!=d.current_revision_id) THEN 1 ELSE 0 END) AS stale_content,'
            "sum(CASE WHEN EXISTS(SELECT 1 FROM jobs j WHERE j.target_type='document' AND j.target_id=d.id AND j.kind IN ('parse','ocr') AND j.status IN ('queued','running') AND json_extract(j.payload_json,'$.revision_id')=d.current_revision_id) THEN 1 ELSE 0 END) AS processing,"
            "sum(CASE WHEN (SELECT j.status FROM jobs j LEFT JOIN parse_requests q ON q.job_id=j.id WHERE j.target_type='document' AND j.target_id=d.id AND j.kind IN ('parse','ocr') AND json_extract(j.payload_json,'$.revision_id')=d.current_revision_id ORDER BY COALESCE(q.sequence,0) DESC,j.created_at DESC,j.id DESC LIMIT 1)='failed' THEN 1 ELSE 0 END) AS failed_processing"+base+
            ' LEFT JOIN document_search_state s ON s.document_id=d.id LEFT JOIN search_dirty x ON x.document_id=d.id'+scope,[VERSION,*params]).fetchone()
        summary={key:rows[key] or 0 for key in rows.keys()}
        # Missing and failed may overlap; explicit completeness is independent of result total.
        summary['incomplete']=bool(summary['missing'] or summary['pending'] or summary['failed'] or summary['without_content'] or summary['limited_content'] or summary['stale_content'] or summary['processing'] or summary['failed_processing'])
        summary['tokenizer_version']=VERSION
        if match:
            base+=' JOIN document_search ON document_search.document_id=d.id'
            scope+=' AND document_search MATCH ?';params=[*params,match]
        total=db.execute('SELECT count(*)'+base+scope,params).fetchone()[0]
        ids=db.execute('SELECT d.id'+base+scope+' ORDER BY '+','.join(orders)+',d.id ASC LIMIT ? OFFSET ?',
                       [*params,page_size,(page-1)*page_size]).fetchall()
        # Reject oversized pages before materializing text and tag arrays.
        budget=0
        for row in ids:
            budget+=4096+6*db.execute('SELECT length(CAST(title AS BLOB))+COALESCE(length(CAST(description AS BLOB)),0) FROM documents WHERE id=?',(row[0],)).fetchone()[0]
            budget+=6*db.execute('SELECT COALESCE(sum(length(CAST(tag_id AS BLOB))),0) FROM document_tags WHERE document_id=?',(row[0],)).fetchone()[0]
        if budget>MAX_RESPONSE:fail(413,'SEARCH_RESPONSE_LIMIT','Reduce the search page size')
        items=[]
        for row in ids:
            item=project(db,row[0],request.app.state.storage,mounts)
            item.update(observations.get(row[0],{}))
            indexed=db.execute('SELECT s.tokenizer_version,s.generation AS index_generation,x.generation AS dirty_generation,x.last_error,s.indexed_at '
                'FROM search_dirty x LEFT JOIN document_search_state s ON s.document_id=x.document_id WHERE x.document_id=?',(row[0],)).fetchone()
            limited=db.execute("SELECT 1 FROM parse_runs p WHERE p.id=? AND (p.text_available=0 OR EXISTS(SELECT 1 FROM json_each(p.warnings_json) WHERE value='NO_TEXT_LAYER_OCR_REQUIRED'))",(item['current_parse_run_id'],)).fetchone()
            item['search_index']={'status':state(indexed) if indexed else 'missing','indexed_at':indexed['indexed_at'] if indexed else None,
                'content_incomplete':bool(not item['current_parse_run_id'] or limited or item['content_stale'] or item['processing_status'] in ('queued','running','failed','unsupported'))}
            items.append(item)
        result={'items':items,'total':total,'page':page,'page_size':page_size,'search_index':summary}
        if len(json.dumps(result,ensure_ascii=True).encode())>MAX_RESPONSE:fail(413,'SEARCH_RESPONSE_LIMIT','Reduce the search page size')
        return result
    except sqlite3.OperationalError as exc:
        if status_limit[0]:fail(503,'SEARCH_STATUS_LIMIT','Narrow the space or indexed filters before observing live status')
        if 'interrupt' in str(exc):fail(503,'SEARCH_TIMEOUT','Search exceeded its execution budget')
        raise
    finally:
        db.set_progress_handler(None,0)
        if status_filters:db.create_function('search_observed_status',2,None)


def router(settings):
    from .source_paths import SourceMounts
    mounts=SourceMounts(settings.source_mounts)
    routes=APIRouter(prefix='/api/v1')
    def search_sync(body,request):
        with transaction(settings) as db:
            where,params=structured(db,body)
            return query(db,request,mounts,where,params,body.text,body.sort,body.page,body.page_size,{key:getattr(body,key) for key in ('availability_status','processing_status') if getattr(body,key) is not None})

    @routes.post('/documents/search')
    async def search(request: Request):
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>MAX_REQUEST:fail(413,'SEARCH_REQUEST_LIMIT','Search request exceeds its size budget')
            data.extend(chunk)
        try:body=SearchRequest.model_validate_json(data)
        except (ValidationError,ValueError):fail(422,'INVALID_REQUEST','Request does not match the search schema')
        return await run_in_threadpool(search_sync,body,request)

    @routes.get('/system/summary')
    def summary(space_id: ID | None=None):
        with transaction(settings) as db:
            if space_id is not None:required(db,'spaces',space_id)
            row=db.execute("SELECT count(*) AS documents_total,COALESCE(sum(d.triage_status='needs_review'),0) AS inbox_total,"
                "COALESCE(sum(r.storage_kind='managed'),0) AS managed_total,COALESCE(sum(r.storage_kind='external'),0) AS external_total "
                'FROM documents d LEFT JOIN file_revisions r ON r.id=d.current_revision_id WHERE d.deleted_at IS NULL AND (? IS NULL OR d.space_id=?)',(space_id,space_id)).fetchone()
            result=dict(row)
            result['failed_jobs']=db.execute("SELECT count(*) FROM jobs j WHERE status='failed' AND (? IS NULL OR EXISTS(SELECT 1 FROM documents d WHERE d.id=j.target_id AND d.space_id=?) OR EXISTS(SELECT 1 FROM sources s WHERE s.id=j.target_id AND s.space_id=?))",(space_id,space_id,space_id)).fetchone()[0]
            result['offline_sources']=db.execute("SELECT count(*) FROM sources WHERE status='offline' AND (? IS NULL OR space_id=?)",(space_id,space_id)).fetchone()[0]
            return result
    return routes
