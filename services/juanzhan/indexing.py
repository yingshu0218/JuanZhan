"""Durable dirty outbox, bounded snapshot tokenization, fenced single-document FTS."""
import argparse
import hashlib
import json
import sqlite3

from .config import Settings
from .database import connect
from .document_events import utc_now
from .jobs import JobQueue,JobSpec
from .metadata_values import value
from .tokenizer import VERSION,indexed,TokenLimit

MAX_INPUT=8*1024*1024

class IndexFailure(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)


def schedule(settings,limit=10):
    if not 1<=limit<=100:raise ValueError('Invalid scheduling limit')
    queue=JobQueue(settings)
    with queue.write() as db:
        active=db.execute("SELECT count(*) FROM jobs WHERE kind='reindex' AND target_type='document_search' AND status IN('queued','running')").fetchone()[0]
        if active>=100:return 0
        limit=min(limit,100-active)
        candidates=db.execute("SELECT d.document_id,d.generation FROM search_dirty d LEFT JOIN document_search_state s ON s.document_id=d.document_id "
            "WHERE d.last_error IS NULL AND (d.generation>d.scheduled_generation OR s.document_id IS NULL OR s.tokenizer_version!=?) "
            "AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.kind='reindex' AND j.target_type='document_search' AND j.target_id=d.document_id AND j.status IN('queued','running')) "
            'ORDER BY d.document_id LIMIT ?',(VERSION,limit)).fetchall()
        count=0
        for id,generation in candidates:
            job=queue.enqueue(JobSpec(kind='reindex',target_type='document_search',target_id=id,
                payload={'generation':generation,'tokenizer_version':VERSION},
                idempotency_key='index:'+hashlib.sha256((id+':'+str(generation)+':'+VERSION).encode()).hexdigest(),timeout_seconds=120),db=db)
            db.execute('UPDATE search_dirty SET scheduled_generation=? WHERE document_id=?',(generation,id))
            if job['status'] in ('queued','running'):count+=1
        return count


def failed(db,job,code,terminal):
    if terminal and job['kind']=='reindex' and job['target_type']=='document_search':
        payload=json.loads(job['payload_json'])
        if code=='INDEX_VERSION_CHANGED':
            db.execute('UPDATE search_dirty SET generation=generation+1,last_error=NULL WHERE document_id=? AND generation=?',(job['target_id'],payload.get('generation')))
            return
        db.execute('UPDATE search_dirty SET last_error=? WHERE document_id=? AND generation=?',
                   (code,job['target_id'],payload.get('generation')))


def snapshot(settings,id):
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row;db.execute('BEGIN')
        doc=db.execute('SELECT d.*,s.generation FROM documents d JOIN search_dirty s ON s.document_id=d.id WHERE d.id=?',(id,)).fetchone()
        if doc is None:return None
        run=doc['current_parse_run_id']
        queries=[('SELECT text_content AS text FROM content_blocks WHERE parse_run_id=? ORDER BY block_index',(run,)),
                 ('SELECT t.name AS text FROM tags t JOIN document_tags l ON l.tag_id=t.id WHERE l.document_id=? ORDER BY t.id',(id,)),
                 ('SELECT label AS text FROM document_types WHERE id=?',(doc['document_type_id'],)),
                 ('SELECT original_filename AS text FROM file_revisions WHERE id=?',(doc['current_revision_id'],))]
        size=sum(len((doc[k] or '').encode()) for k in ('title','description','document_date'))
        for sql,params in queries:
            size+=db.execute('SELECT COALESCE(sum(length(CAST(text AS BLOB))),0) FROM ('+sql+')',params).fetchone()[0]
        metadata_sql='SELECT m.*,f.field_type FROM metadata_values m JOIN field_definitions f ON f.id=m.field_definition_id WHERE m.document_id=? AND f.searchable=1 AND f.is_active=1 ORDER BY f.id'
        size+=db.execute('SELECT COALESCE(sum(length(CAST(value_text AS BLOB))),0) FROM ('+metadata_sql+')',(id,)).fetchone()[0]
        if size>MAX_INPUT:raise IndexFailure('INDEX_INPUT_LIMIT')
        texts=[doc[k] or '' for k in ('title','description','document_date')]
        for sql,params in queries:texts.extend(r['text'] for r in db.execute(sql,params))
        for row in db.execute(metadata_sql,(id,)):
            raw=value(row,row)
            texts.append(('true' if raw else 'false') if isinstance(raw,bool) else str(raw))
        if sum(len(text.encode()) for text in texts)>MAX_INPUT:raise IndexFailure('INDEX_INPUT_LIMIT')
        encoded=json.dumps({'revision':doc['current_revision_id'],'parse_run':run,'texts':texts},ensure_ascii=False,separators=(',',':')).encode()
        return {'id':id,'generation':doc['generation'],'parse_run_id':run,'content_hash':hashlib.sha256(encoded).hexdigest(),'texts':texts}


def publish(db,job,observed,text):
    id=job['target_id']
    current=db.execute('SELECT generation FROM search_dirty WHERE document_id=?',(id,)).fetchone()
    if observed is None or current is None:return {'status':'discarded','reason':'DOCUMENT_UNAVAILABLE'}
    if current[0]!=observed['generation']:return {'status':'discarded','reason':'INDEX_INPUT_CHANGED'}
    state=db.execute('SELECT content_hash,tokenizer_version,parse_run_id FROM document_search_state WHERE document_id=?',(id,)).fetchone()
    total=db.execute('SELECT count(*) FROM document_search WHERE document_id=?',(id,)).fetchone()[0]
    same=bool(state and state[0]==observed['content_hash'] and state[1]==VERSION and state[2]==observed['parse_run_id'] and total==1 and
              db.execute('SELECT 1 FROM document_search WHERE document_id=? AND indexed_text=?',(id,text)).fetchone())
    if not same:
        db.execute('DELETE FROM document_search WHERE document_id=?',(id,))
        db.execute('INSERT INTO document_search(document_id,indexed_text) VALUES (?,?)',(id,text))
    db.execute('INSERT INTO document_search_state(document_id,parse_run_id,tokenizer_version,content_hash,indexed_at,generation) VALUES (?,?,?,?,?,?) '
               'ON CONFLICT(document_id) DO UPDATE SET parse_run_id=excluded.parse_run_id,tokenizer_version=excluded.tokenizer_version,'
               'content_hash=excluded.content_hash,indexed_at=excluded.indexed_at,generation=excluded.generation',
               (id,observed['parse_run_id'],VERSION,observed['content_hash'],utc_now(),observed['generation']))
    db.execute('UPDATE search_dirty SET scheduled_generation=max(scheduled_generation,?),last_error=NULL WHERE document_id=?',(observed['generation'],id))
    return {'status':'completed','document_id':id,'generation':observed['generation'],'tokenizer_version':VERSION,'index_changed':not same}


def execute(settings,job):
    payload=json.loads(job['payload_json'])
    if set(payload)!={'generation','tokenizer_version'} or type(payload['generation']) is not int or payload['generation']<1:
        raise IndexFailure('INVALID_INDEX_PAYLOAD')
    if payload['tokenizer_version']!=VERSION:raise IndexFailure('INDEX_VERSION_CHANGED')
    observed=snapshot(settings,job['target_id'])
    try:text=indexed(observed['texts']) if observed else ''
    except TokenLimit as exc:raise IndexFailure(str(exc)) from None
    JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,observed,text))


def rebuild(settings,document=None):
    with JobQueue(settings).write() as db:
        if document is not None and not db.execute('SELECT 1 FROM documents WHERE id=?',(document,)).fetchone():raise ValueError('Document not found')
        cursor=db.execute('INSERT INTO search_dirty(document_id) SELECT id FROM documents WHERE (? IS NULL OR id=?) '
            'ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL',(document,document))
        count=cursor.rowcount
    return count


def main():
    parser=argparse.ArgumentParser(description='Queue bounded FTS indexing; never reads original files')
    parser.add_argument('operation',choices=['queue','rebuild'])
    group=parser.add_mutually_exclusive_group();group.add_argument('--document');group.add_argument('--all',action='store_true')
    parser.add_argument('--limit',type=int,default=10)
    args=parser.parse_args();settings=Settings.from_env()
    if not 1<=args.limit<=100:parser.error('limit must be between 1 and 100')
    if args.operation=='queue' and (args.document or args.all):parser.error('document selection applies to rebuild')
    if args.operation=='rebuild' and not (args.document or args.all):parser.error('rebuild requires --document or --all')
    requested=rebuild(settings,args.document) if args.operation=='rebuild' else 0
    print(json.dumps({'requested_documents':requested,'queued_jobs':schedule(settings,args.limit),'tokenizer_version':VERSION}))

if __name__=='__main__':main()
