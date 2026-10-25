"""Current-version processing inventory derived from persisted results, never jobs."""
import hashlib
import json
from typing import Annotated
from fastapi import APIRouter,Query,Request,HTTPException
from pydantic import Field
from .catalog import Input,ID
from .jobs import JobQueue,JobSpec
from .tokenizer import VERSION
from .database import connect
from .auth import fail

AGENT="EXISTS(SELECT 1 FROM agent_analyses a JOIN agent_imports i ON i.id=a.import_id WHERE i.document_id=d.id AND i.revision_id=d.current_revision_id)"
LOCAL="COALESCE(p.status='completed' AND p.revision_id=d.current_revision_id AND p.text_available=1,0)"
MD="COALESCE(m.content_status='content' AND m.parse_run_id=d.current_parse_run_id,0)"
INDEX="COALESCE(s.generation>=x.generation AND s.tokenizer_version=? AND x.last_error IS NULL,0)"
BASE=f"SELECT d.id,d.space_id,d.title,d.current_revision_id,d.document_version,r.original_filename,({AGENT} OR {LOCAL}) AS analysis_ready,({AGENT} OR {MD}) AS markdown_ready,{INDEX} AS index_ready FROM documents d JOIN file_revisions r ON r.id=d.current_revision_id LEFT JOIN parse_runs p ON p.id=d.current_parse_run_id LEFT JOIN revision_markdown m ON m.revision_id=d.current_revision_id LEFT JOIN document_search_state s ON s.document_id=d.id LEFT JOIN search_dirty x ON x.document_id=d.id WHERE d.deleted_at IS NULL"

def facts(db,*,id=None,space_id=None):
    sql=BASE;values=[VERSION]
    if id:sql+=' AND d.id=?';values.append(id)
    if space_id:sql+=' AND d.space_id=?';values.append(space_id)
    return sql,values

def describe(row):
    value=dict(row)
    value['pending_reasons']=[key for key in ('analysis','markdown','index') if not value.pop(key+'_ready')]
    return value

class DocumentTarget(Input):
    id:ID
    revision_id:ID
class Process(Input):
    request_id:Annotated[str,Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')]
    documents:list[DocumentTarget]=Field(min_length=1,max_length=100)

def router(settings):
    routes=APIRouter(prefix='/api/v1/pending-documents');queue=JobQueue(settings)
    @routes.get('')
    def listing(space_id:ID|None=None,page:int=Query(default=1,ge=1,le=1000000),page_size:int=Query(default=20,ge=1,le=100)):
        from .upload_policy import read,reason
        from .upload_exclusions import excluded_file
        with connect(settings.database) as db:
            import sqlite3
            db.row_factory=sqlite3.Row;db.execute('BEGIN')
            sql,values=facts(db,space_id=space_id);query='SELECT * FROM ('+sql+') WHERE NOT (analysis_ready AND markdown_ready AND index_ready)'
            total=db.execute('SELECT count(*) FROM ('+query+')',values).fetchone()[0]
            policy=read(db);items=[]
            for row in db.execute(query+' ORDER BY title,id LIMIT ? OFFSET ?',(*values,page_size,(page-1)*page_size)):
                item=describe(row);item['format_excluded']=bool(reason(item['original_filename'],policy) or excluded_file(item['original_filename']))
                items.append(item)
            return {'items':items,'page':page,'page_size':page_size,'total':total}
    @routes.post('/process')
    def process(body:Process,request:Request):
        from .upload_policy import check
        from .upload_exclusions import excluded_file
        from .job_controls import control
        from .catalog import required
        results=[]
        with queue.write(request) as db:
            import sqlite3
            db.row_factory=sqlite3.Row
            for target in {d.id:d for d in body.documents}.values():
                db.execute('SAVEPOINT pending_process')
                try:
                    sql,values=facts(db,id=target.id);row=db.execute(sql,values).fetchone()
                    if not row:fail(404,'NOT_FOUND','Document not available')
                    if row['current_revision_id']!=target.revision_id:fail(409,'REVISION_CHANGED','Original changed')
                    needs=describe(row)['pending_reasons'];jobs=[]
                    specs=[]
                    if 'analysis' in needs:
                        if excluded_file(row['original_filename']):fail(422,'UPLOAD_EXCLUDED','Auxiliary files are excluded')
                        check(db,row['original_filename'])
                        specs.append(('parse','document',target.id,{'revision_id':target.revision_id}))
                    else:
                        if 'markdown' in needs:
                            db.execute('INSERT OR IGNORE INTO markdown_dirty(revision_id) VALUES (?)',(target.revision_id,))
                            generation=db.execute('SELECT generation FROM markdown_dirty WHERE revision_id=?',(target.revision_id,)).fetchone()
                            if generation:specs.append(('batch','revision_markdown',target.revision_id,{'generation':generation[0]}))
                        if 'index' in needs:
                            db.execute('INSERT OR IGNORE INTO search_dirty(document_id) VALUES (?)',(target.id,))
                            generation=db.execute('SELECT generation FROM search_dirty WHERE document_id=?',(target.id,)).fetchone()
                            if generation:
                                db.execute('UPDATE search_dirty SET last_error=NULL WHERE document_id=?',(target.id,))
                                specs.append(('reindex','document_search',target.id,{'generation':generation[0],'tokenizer_version':VERSION}))
                    for kind,type,id,payload in specs:
                        active=db.execute("SELECT j.id,c.mode FROM jobs j LEFT JOIN job_controls c ON c.job_id=j.id WHERE j.kind=? AND j.target_type=? AND j.target_id=? AND j.status IN ('queued','running') AND COALESCE(c.mode,'')!='deleted' AND (? IS NULL OR json_extract(j.payload_json,'$.revision_id')=?) ORDER BY j.created_at DESC,j.id DESC LIMIT 1",(kind,type,id,payload.get('revision_id'),payload.get('revision_id'))).fetchone()
                        if active:
                            if active['mode']=='paused':control(db,queue,active['id'],'resume')
                            jobs.append(active['id'])
                        else:
                            job=queue.enqueue(JobSpec(kind=kind,target_type=type,target_id=id,payload=payload,idempotency_key='pending:'+hashlib.sha256(json.dumps([body.request_id,target.id,target.revision_id,type]).encode()).hexdigest(),timeout_seconds=120 if kind=='reindex' else 60),db=db)
                            jobs.append(job['id'])
                    results.append({'document_id':target.id,'job_ids':jobs,'already_complete':not needs})
                    db.execute('RELEASE pending_process')
                except HTTPException as exc:
                    db.execute('ROLLBACK TO pending_process');db.execute('RELEASE pending_process')
                    results.append({'document_id':target.id,'error_code':exc.detail.get('code','NOT_FOUND')})
        return {'items':results,'succeeded':sum('error_code' not in r for r in results),'failed':sum('error_code' in r for r in results)}
    return routes
