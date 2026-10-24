"""Opt-in scoped ingestion and versioned external-agent evidence, without a model."""
import asyncio
from contextlib import contextmanager
import sqlite3
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
from typing import Annotated,Literal
from fastapi import APIRouter,Request,Query
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .auth import fail
from .database import connect
from .catalog import transaction,ID
from .agent_access import allowed
from .document_events import utc_now
from .documents import Registration
from .jobs import JobSpec
from .uploads import sniff
from .upload_exclusions import excluded_file

CATALOG=json.loads((Path(__file__).parent/'data/analysis_templates.json').read_text())
TEMPLATES={t['id']:t for t in CATALOG['templates']}
MAX_JSON=2*1024*1024

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Citation(Input):
    start:int=Field(ge=0,strict=True,description="Unicode code-point offset, inclusive; not UTF-8 bytes or UTF-16 units")
    end:int=Field(gt=0,strict=True,description="Unicode code-point offset, exclusive")
    quote:str=Field(min_length=1,max_length=4000)
class Finding(Input):
    text:str=Field(min_length=1,max_length=4000)
    basis:Literal['explicit','inference']
    sources:list[Citation]=Field(min_length=1,max_length=10)
class Submission(Input):
    submission_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    revision_id:ID
    original_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    template_id:Literal['generic','contract','invoice','meeting','report']
    template_version:Literal[1]
    agent_name:str=Field(min_length=1,max_length=100)
    markdown:str=Field(min_length=1,max_length=1000000)
    summary:list[Finding]=Field(min_length=1,max_length=12)
    fields:dict[str,Finding|None]
    additional_points:list[Finding]=Field(default_factory=list,max_length=20)
    @model_validator(mode='after')
    def evidence(self):
        if not self.markdown.strip() or not self.agent_name.strip():raise ValueError('Markdown and Agent name must not be blank')
        if set(self.fields)!=set(TEMPLATES[self.template_id]['fields']):raise ValueError('Fill every template field; unknowns must be null')
        for finding in [*self.summary,*self.additional_points,*[v for v in self.fields.values() if v]]:
            if not finding.text.strip():raise ValueError('Finding text must not be blank')
            for source in finding.sources:
                if not source.quote.strip():raise ValueError('Evidence must not be blank')
                if source.start>=source.end or self.markdown[source.start:source.end]!=source.quote:raise ValueError('Citation must match exact Markdown offsets')
        return self

def permission(db,request,space_id):
    allowed(request,space_id)
    if request.state.auth_mode=='agent':
        row=db.execute('SELECT import_enabled FROM agent_tokens t WHERE id=? AND expires_at>unixepoch() AND EXISTS(SELECT 1 FROM agent_token_spaces s WHERE s.token_id=t.id AND s.space_id=?)',(request.state.agent_id,space_id)).fetchone()
        if not row or not row[0]:fail(403,'AGENT_IMPORT_DENIED','An explicitly enabled import credential is required')
    else:fail(403,'AGENT_IMPORT_CREDENTIAL_REQUIRED','Use an explicitly enabled scoped Agent credential')

@contextmanager
def write(settings):
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise

def receipt(row):
    return {k:row[k] for k in ('id','space_id','document_id','revision_id','original_sha256','created_at')}

def template_protocol(settings=None,request=None,body=None):
    return {**CATALOG,'submission_schema':Submission.model_json_schema(),'limits':{'request_bytes':MAX_JSON,'markdown_characters':1000000},
        'workflow':['POST /agent/imports/{request_id}?space_id=...&filename=... with raw original bytes and Content-Type application/octet-stream',
                    'GET /agent/analysis-templates; analyze externally',
                    'POST /agent/imports/{id}/analyses with version/hash-bound Submission; local parsing runs independently']}

class ReadAnalysis(Input):
    space_id:ID
    document_id:ID
    analysis_id:ID|None=None
    offset:int=Field(default=0,ge=0,le=1000000,strict=True)
    length:int=Field(default=16000,ge=1,le=32000,strict=True)

def read_analysis(settings,request,body):
    from .agent_api import document
    with transaction(settings) as db:
        document(db,request,body.space_id,body.document_id)
        query='SELECT a.*,i.revision_id,i.original_sha256,d.current_revision_id FROM agent_analyses a JOIN agent_imports i ON i.id=a.import_id JOIN documents d ON d.id=i.document_id WHERE i.document_id=?'
        params=[body.document_id]
        if body.analysis_id:query+=' AND a.id=?';params.append(body.analysis_id)
        row=db.execute(query+' ORDER BY (i.revision_id=d.current_revision_id) DESC,a.created_at DESC,a.id DESC LIMIT 1',params).fetchone()
        if row is None:fail(404,'NOT_FOUND','Analysis not found')
        if body.offset and not body.analysis_id:fail(422,'ANALYSIS_ID_REQUIRED','Pin analysis_id across pages')
        value=json.loads(row['analysis_json']);text=value.pop('markdown')
        if body.offset>len(text):fail(422,'INVALID_OFFSET','Offset exceeds Markdown length')
        end=min(len(text),body.offset+body.length)
        partial=False
        def compact(finding):
            nonlocal partial
            if finding is None:return None
            if len(finding['text'])>1000 or len(finding['sources'])>1 or any(len(q['quote'])>500 for q in finding['sources']):partial=True
            source=finding['sources'][0];quote=source['quote'][:500]
            return {'text':finding['text'][:1000],'basis':finding['basis'],'sources':[{'start':source['start'],'end':source['start']+len(quote),'quote':quote}]}
        value['summary']=[compact(v) for v in value['summary']]
        value['fields']={key:compact(v) for key,v in value['fields'].items()}
        value['additional_points']=[compact(v) for v in value['additional_points']]
        return {'analysis_id':row['id'],'document_id':body.document_id,'revision_id':row['revision_id'],
                'original_sha256':row['original_sha256'],'stale':row['revision_id']!=row['current_revision_id'],
                'verification':'agent_markdown_offsets_only','analysis_truncated':partial,'analysis':value,'markdown':text[body.offset:end],
                'offset':body.offset,'next_offset':end if end<len(text) else None,'total_characters':len(text)}

def router(settings):
    routes=APIRouter(prefix='/api/v1/agent')
    @routes.get('/analysis-templates')
    def templates():return template_protocol()
    slots=asyncio.Semaphore(4)
    async def ingest(request_id:str,request:Request,space_id:ID,
                     filename:Annotated[str,Query(min_length=1,max_length=255)]):
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',request_id):fail(422,'INVALID_REQUEST','Invalid request id')
        if request.headers.get('content-type','').split(';')[0]!='application/octet-stream':fail(415,'INVALID_CONTENT_TYPE','Use raw original bytes')
        if '/' in filename or '\\' in filename or any(ord(c)<32 for c in filename):fail(422,'INVALID_FILENAME','Use a filename, not a path')
        if excluded_file(filename):fail(422,'UPLOAD_EXCLUDED','Auxiliary files are excluded')
        with transaction(settings) as db:permission(db,request,space_id)
        with tempfile.SpooledTemporaryFile(max_size=65536) as stream:
            size=0
            async with asyncio.timeout(settings.upload_timeout_seconds):
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>settings.upload_max_bytes:fail(413,'UPLOAD_TOO_LARGE','Original exceeds configured limit')
                    stream.write(chunk)
            stream.seek(0);mime=sniff(stream,filename);stream.seek(0)
            from starlette.concurrency import run_in_threadpool
            def save():
                store=request.app.state.storage
                with store.locked():
                    obj=store.put(stream,max_bytes=settings.upload_max_bytes)
                    with transaction(settings) as db:
                        permission(db,request,space_id)
                        old=db.execute('SELECT * FROM agent_imports WHERE agent_id=? AND request_id=?',(request.state.agent_id,request_id)).fetchone()
                        if old:
                            old_name=db.execute('SELECT original_filename FROM file_revisions WHERE id=?',(old['revision_id'],)).fetchone()
                            if old['space_id']!=space_id or old['original_sha256']!=obj.sha256 or not old_name or old_name[0]!=filename:fail(409,'IDEMPOTENCY_CONFLICT','Request id already names another import')
                            return receipt(old)
                    result={}
                    def record(db,doc):
                        permission(db,request,space_id)
                        if db.execute('SELECT 1 FROM agent_imports WHERE agent_id=? AND request_id=?',(request.state.agent_id,request_id)).fetchone():fail(409,'IMPORT_RACE','Retry the same request id')
                        id=uuid.uuid4().hex
                        db.execute('INSERT INTO agent_imports VALUES (?,?,?,?,?,?,?,?)',(id,request.state.agent_id,request_id,space_id,doc['id'],doc['current_revision_id'],obj.sha256,utc_now()))
                        request.app.state.jobs.enqueue(JobSpec(kind='parse',target_type='document',target_id=doc['id'],payload={'revision_id':doc['current_revision_id']},idempotency_key='parse:'+doc['current_revision_id']),db=db)
                        result.update(receipt(db.execute('SELECT * FROM agent_imports WHERE id=?',(id,)).fetchone()))
                    request.app.state.documents.register_managed(obj,Registration(space_id=space_id,title=filename,original_filename=filename,mime_type=mime,duplicate_policy="keep_separate"),after_create=record)
                    return result
            return await run_in_threadpool(save)
    @routes.post('/imports/{request_id}',status_code=201)
    async def upload(request_id:str,request:Request,space_id:ID,filename:Annotated[str,Query(min_length=1,max_length=255)]):
        if slots.locked():fail(429,'UPLOAD_CAPACITY','Import capacity reached; retry later')
        try:
            async with slots:return await ingest(request_id,request,space_id,filename)
        except TimeoutError:fail(408,'UPLOAD_TIMEOUT','Import receive deadline exceeded')
        except OSError:fail(503,'STORAGE_UNAVAILABLE','Original could not be safely saved')
    @routes.post('/imports/{id}/analyses',status_code=201)
    async def submit(id:str,request:Request):
        if request.headers.get('content-type','').split(';')[0]!='application/json':fail(415,'INVALID_CONTENT_TYPE','Use application/json')
        with transaction(settings) as db:
            entry=db.execute('SELECT * FROM agent_imports WHERE id=?',(id,)).fetchone()
            if not entry:fail(404,'NOT_FOUND','Import not found')
            permission(db,request,entry['space_id'])
            if entry['agent_id']!=request.state.agent_id:fail(404,'NOT_FOUND','Import not found')
        raw=bytearray()
        try:
            async with asyncio.timeout(settings.upload_timeout_seconds):
                async for chunk in request.stream():
                    if len(raw)+len(chunk)>MAX_JSON:fail(413,'ANALYSIS_LIMIT','Submission exceeds request budget')
                    raw.extend(chunk)
        except TimeoutError:fail(408,'ANALYSIS_TIMEOUT','Submission receive deadline exceeded')
        try:body=Submission.model_validate_json(raw)
        except ValueError:fail(422,'INVALID_ANALYSIS','Submission must follow the template and exact quote offsets')
        payload=json.dumps(body.model_dump(),ensure_ascii=False,sort_keys=True,separators=(',',':'));sha=hashlib.sha256(payload.encode()).hexdigest()
        def save_analysis():
            with write(settings) as db:
                row=db.execute('SELECT * FROM agent_imports WHERE id=?',(id,)).fetchone()
                if not row:fail(404,'NOT_FOUND','Import not found')
                permission(db,request,row['space_id'])
                if row['agent_id']!=request.state.agent_id:fail(404,'NOT_FOUND','Import not found')
                doc=db.execute('SELECT current_revision_id,deleted_at FROM documents WHERE id=?',(row['document_id'],)).fetchone()
                if doc['deleted_at'] is not None or doc['current_revision_id']!=row['revision_id']:fail(409,'REVISION_CHANGED','Import is no longer the active original')
                if body.revision_id!=row['revision_id'] or body.original_sha256!=row['original_sha256']:fail(409,'ORIGINAL_MISMATCH','Analysis must bind the imported original')
                old=db.execute('SELECT id,payload_sha256 FROM agent_analyses WHERE import_id=? AND submission_id=?',(id,body.submission_id)).fetchone()
                if old:
                    if old['payload_sha256']!=sha:fail(409,'IDEMPOTENCY_CONFLICT','Submission id already used')
                    return {'id':old['id'],'document_id':row['document_id'],'revision_id':row['revision_id']}
                if db.execute('SELECT count(*) FROM agent_analyses WHERE import_id=?',(id,)).fetchone()[0]>=50:fail(413,'ANALYSIS_CAPACITY','Import already has 50 retained analysis submissions')
                analysis_id=uuid.uuid4().hex
                db.execute('INSERT INTO agent_analyses VALUES (?,?,?,?,?,?,?,?,?,?)',(analysis_id,id,body.submission_id,body.template_id,body.template_version,body.agent_name,sha,body.markdown,payload,utc_now()))
                return {'id':analysis_id,'document_id':row['document_id'],'revision_id':row['revision_id']}
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(save_analysis)
    @routes.get('/documents/{id}/analyses')
    def analyses(id:str,space_id:ID,request:Request,page:Annotated[int,Query(ge=1,le=10000)]=1):
        from .agent_api import document
        with transaction(settings) as db:
            document(db,request,space_id,id)
            doc=db.execute('SELECT current_revision_id FROM documents WHERE id=?',(id,)).fetchone()
            rows=db.execute('SELECT a.*,i.revision_id FROM agent_analyses a JOIN agent_imports i ON i.id=a.import_id JOIN documents d ON d.id=i.document_id WHERE i.document_id=? ORDER BY (i.revision_id=d.current_revision_id) DESC,a.created_at DESC,a.id DESC LIMIT 1 OFFSET ?',(id,(page-1))).fetchall()
            return {'page':page,'total':db.execute('SELECT count(*) FROM agent_analyses a JOIN agent_imports i ON i.id=a.import_id WHERE i.document_id=?',(id,)).fetchone()[0],'items':[{'id':r['id'],'agent_name':r['agent_name'],'template_id':r['template_id'],'template_version':r['template_version'],'created_at':r['created_at'],'revision_id':r['revision_id'],'stale':r['revision_id']!=doc['current_revision_id'],'verification':'agent_markdown_offsets_only','analysis':json.loads(r['analysis_json'])} for r in rows]}
    return routes
