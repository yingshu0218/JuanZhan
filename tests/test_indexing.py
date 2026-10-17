"""Real SQLite FTS5, Archive HTTP writes, parser processes and durable index jobs."""
from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest

from test_parsing import pipeline,upload,rows,append,queue_parse
from test_fields import create as create_field
from juanzhan.database import connect
from juanzhan.indexing import schedule,execute,snapshot,publish,rebuild,IndexFailure
from juanzhan.jobs import JobQueue,LostLease
from juanzhan.tokenizer import VERSION,indexed,match_expression,tokens,TokenLimit
from juanzhan.worker import Worker


def drain(settings):
    for _ in range(20):
        count=schedule(settings)
        if not count:return
        for _ in range(count):assert Worker(settings).run_once()['status']=='completed'
    pytest.fail('Index dirty outbox did not converge')


def hits(settings,query,space=None):
    with connect(settings.database) as db:
        return {r[0] for r in db.execute('SELECT d.id FROM document_search JOIN documents d ON d.id=document_search.document_id '
            'WHERE document_search MATCH ? AND d.deleted_at IS NULL AND (? IS NULL OR d.space_id=?)',
            (match_expression(query),space,space))}


def parsed(pipeline,text='繁體檔案 合同AB2026 Invoice2026 數字 12345'):
    settings,_,_,_=pipeline;doc=upload(pipeline,text.encode());Worker(settings).run_once();return doc


def patch(pipeline,doc,**values):
    settings,client,headers,_=pipeline;root='/api/v1/documents/'+doc['document_id']
    version=client.get(root).json()['document_version']
    response=client.patch(root,headers=headers,json={'expected_document_version':version,**values})
    assert response.status_code==200,response.text


def test_real_chinese_short_words_traditional_mixed_ascii_and_fts_operators(pipeline):
    settings,client,_,space=pipeline;doc=parsed(pipeline);drain(settings)
    for query in ('档案','檔案','合同','AB2026','合同AB2026','ｉｎｖｏｉｃｅ２０２６','数字','12345'):
        assert hits(settings,query,space)=={doc['document_id']},query
    assert not hits(settings,'不存在')
    assert not hits(settings,'OR * NOT')  # Literal lexical tokens, never active FTS syntax.
    assert client.get('/api/v1/documents',params={'space_id':space,'q':'档案'}).status_code==501
    state=rows(settings,'SELECT * FROM document_search_state')[0]
    assert state['tokenizer_version']==VERSION and state['parse_run_id']


def test_tokenizer_boundaries_and_versioned_terms():
    values=list(tokens('合同AB2026 檔案'))
    assert values==['合','合同','同','ab2026','档','档案','案']
    assert '同档' not in values
    assert indexed(['甲','乙'])=='甲 乙'
    for query in ('',' * () ', '中'*200,'x'*513):
        with pytest.raises(ValueError):match_expression(query)


def test_http_title_tags_metadata_flags_and_adoption_increment_dirty_generation(pipeline):
    settings,client,headers,space=pipeline;doc=parsed(pipeline,'普通正文');id=doc['document_id'];root='/api/v1/documents/'+id
    field=create_field(client,headers,space,key='project',type='text',searchable=True).json()
    version=client.get(root).json()['document_version']
    assert client.patch(root+'/metadata',headers=headers,json={'expected_document_version':version,'confirm':True,'values':{'project':'海豚项目'}}).status_code==200
    patch(pipeline,doc,title='星河合同',description='采购记录')
    tag=client.post('/api/v1/tags',headers=headers,json={'space_id':space,'name':'重要分类'}).json()
    patch(pipeline,doc,tags_add=[tag['id']]);drain(settings)
    for word in ('海豚','星河','采购','重要'):assert id in hits(settings,word)
    assert client.patch('/api/v1/tags/'+tag['id'],headers=headers,json={'name':'珍藏分类'}).status_code==200
    drain(settings);assert id not in hits(settings,'重要') and id in hits(settings,'珍藏')
    assert client.patch('/api/v1/field-definitions/'+field['id'],headers=headers,json={'searchable':False}).status_code==200
    drain(settings);assert id not in hits(settings,'海豚')
    assert len(rows(settings,'SELECT * FROM document_search WHERE document_id=?',id))==1


def test_rebuild_same_inputs_never_duplicates_and_repairs_duplicate_rows(pipeline):
    settings,_,_,_=pipeline;doc=parsed(pipeline);drain(settings)
    before=rows(settings,'SELECT * FROM document_search_state')[0]
    rebuild(settings,doc['document_id']);drain(settings)
    assert len(rows(settings,'SELECT * FROM document_search'))==1
    assert rows(settings,'SELECT * FROM document_search_state')[0]['content_hash']==before['content_hash']
    completed=rows(settings,"SELECT result_json FROM jobs WHERE kind='reindex' ORDER BY created_at DESC,id DESC LIMIT 1")[0]
    assert not json.loads(completed['result_json'])['index_changed']
    with connect(settings.database) as db:
        db.execute('INSERT INTO document_search SELECT document_id,indexed_text FROM document_search');db.commit()
    rebuild(settings,doc['document_id']);drain(settings)
    assert len(rows(settings,'SELECT * FROM document_search'))==1


def test_newer_input_fences_older_snapshot_and_new_job_converges(pipeline):
    settings,_,_,_=pipeline;doc=parsed(pipeline,'旧词');schedule(settings)
    queue=JobQueue(settings);job=queue.claim('old');observed=snapshot(settings,doc['document_id'])
    text=indexed(observed['texts'])
    patch(pipeline,doc,title='最新标题')
    queue.complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,observed,text))
    assert queue.get(job['id'])['result']['reason']=='INDEX_INPUT_CHANGED'
    assert not rows(settings,'SELECT * FROM document_search')
    drain(settings);assert doc['document_id'] in hits(settings,'最新')


def test_lost_lease_cannot_publish_then_bounded_retry_recovers(pipeline):
    settings,_,_,_=pipeline;doc=parsed(pipeline);schedule(settings)
    queue=JobQueue(settings);job=queue.claim('old',lease_seconds=.01)
    observed=snapshot(settings,doc['document_id']);text=indexed(observed['texts']);time.sleep(.02)
    with pytest.raises(LostLease):queue.complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,observed,text))
    queue.claim('recovery');queue.retry(job['id']);Worker(settings).run_once()
    assert doc['document_id'] in hits(settings,'档案')


def test_failed_new_revision_keeps_last_successful_text_index(pipeline):
    settings,_,_,_=pipeline;doc=parsed(pipeline,'保留档案正文');drain(settings)
    before=rows(settings,'SELECT * FROM document_search_state')[0]
    rev=append(settings,doc['document_id'],b'%PDF-1.4\ninvalid')
    queue_parse(settings,doc['document_id'],rev);assert Worker(settings).run_once()['status']=='failed'
    drain(settings)
    assert doc['document_id'] in hits(settings,'保留')
    assert rows(settings,'SELECT * FROM document_search_state')[0]['parse_run_id']==before['parse_run_id']


def test_transaction_interruption_preserves_prior_index_and_retry_rebuilds(pipeline,monkeypatch):
    import juanzhan.indexing as indexing
    settings,_,_,_=pipeline;doc=parsed(pipeline);drain(settings)
    old=rows(settings,'SELECT * FROM document_search')[0]['indexed_text']
    patch(pipeline,doc,title='事务新标题');schedule(settings);queue=JobQueue(settings);job=queue.claim('fault')
    actual=indexing.publish
    def interrupted(db,owned,observed,text):
        actual(db,owned,observed,text)
        raise OSError('Injected transaction failure')
    monkeypatch.setattr(indexing,'publish',interrupted)
    with pytest.raises(OSError):execute(settings,job)
    assert rows(settings,'SELECT * FROM document_search')[0]['indexed_text']==old
    queue.failure(job['id'],job['lease_token'],'STORAGE_IO_ERROR','Injected',retryable=True)
    monkeypatch.setattr(indexing,'publish',actual);queue.retry(job['id']);Worker(settings).run_once()
    assert doc['document_id'] in hits(settings,'事务')


def test_resource_failure_does_not_loop_and_explicit_rebuild_recovers(pipeline,monkeypatch):
    import juanzhan.tokenizer as tokenizer
    settings,_,_,_=pipeline;doc=parsed(pipeline);drain(settings);patch(pipeline,doc,title='新内容')
    schedule(settings);queue=JobQueue(settings);job=queue.claim('limit')
    budget=tokenizer.MAX_TOKENS
    monkeypatch.setattr(tokenizer,'MAX_TOKENS',1)
    with pytest.raises(IndexFailure) as exc:execute(settings,job)
    assert exc.value.code=='INDEX_TOKEN_LIMIT'
    queue.failure(job['id'],job['lease_token'],exc.value.code,'Index budget exceeded',retryable=False)
    assert schedule(settings)==0 and rows(settings,'SELECT last_error FROM search_dirty')[0]['last_error']=='INDEX_TOKEN_LIMIT'
    assert doc['document_id'] in hits(settings,'档案')
    monkeypatch.setattr(tokenizer,'MAX_TOKENS',budget);rebuild(settings,doc['document_id']);drain(settings)
    assert doc['document_id'] in hits(settings,'内容')


def test_trash_restore_purge_and_space_scope(pipeline):
    settings,client,headers,space=pipeline;doc=parsed(pipeline);drain(settings);id=doc['document_id'];root='/api/v1/documents/'+id
    assert not hits(settings,'档案','other-space')
    version=client.get(root).json()['document_version']
    assert client.post(root+'/trash',headers=headers,json={'expected_document_version':version}).status_code==200
    drain(settings);assert not hits(settings,'档案',space)
    version=client.get(root).json()['document_version']
    assert client.post(root+'/restore',headers=headers,json={'expected_document_version':version}).status_code==200
    drain(settings);assert id in hits(settings,'档案',space)
    version=client.get(root).json()['document_version']
    client.post(root+'/trash',headers=headers,json={'expected_document_version':version})
    version=client.get(root).json()['document_version']
    response=client.post(root+'/purge',headers=headers,json={'expected_document_version':version,'confirm_document_id':id})
    assert response.status_code==202,response.text
    Worker(settings).run_once()
    assert not rows(settings,'SELECT * FROM document_search') and not rows(settings,'SELECT * FROM document_search_state')
    assert not rows(settings,'PRAGMA foreign_key_check')


def test_concurrent_scheduler_only_queues_one_job(pipeline):
    settings,_,_,_=pipeline;parsed(pipeline)
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(lambda _:schedule(settings),range(2)))==1
    assert len(rows(settings,"SELECT * FROM jobs WHERE kind='reindex'"))==1


def test_old_version_job_is_fenced_and_new_version_is_scheduled(pipeline):
    from juanzhan.jobs import JobSpec
    settings,_,_,_=pipeline;doc=parsed(pipeline);drain(settings)
    generation=rows(settings,'SELECT generation FROM search_dirty')[0]['generation']
    queue=JobQueue(settings)
    old=queue.enqueue(JobSpec(kind='reindex',target_type='document_search',target_id=doc['document_id'],
        payload={'generation':generation,'tokenizer_version':'old-version'},idempotency_key='old-index'))
    assert Worker(settings).run_once()['status']=='failed'
    assert queue.get(old['id'])['error']['code']=='INDEX_VERSION_CHANGED'
    drain(settings)
    assert rows(settings,'SELECT tokenizer_version,generation FROM document_search_state')[0]=={'tokenizer_version':VERSION,'generation':generation+1}


def test_optional_index_priority_prevents_parse_backlog_starvation(pipeline):
    settings,_,_,_=pipeline
    a=upload(pipeline,b'first');b=upload(pipeline,b'second')
    Worker(settings).run_once();assert JobQueue(settings).get(a['job_id'])['status']=='completed'
    schedule(settings)
    queue=JobQueue(settings);job=queue.claim('priority',prefer_index=True)
    assert job['kind']=='reindex' and queue.get(b['job_id'])['status']=='queued'
    execute(settings,job)
    assert Worker(settings).run_once()['job_id']==b['job_id']
    for _ in range(5):
        if Worker(settings).run_once() is None:break
    drain(settings)
    assert len(rows(settings,'SELECT * FROM document_search'))==2


def test_input_budget_is_checked_before_reading_content(pipeline,monkeypatch):
    import juanzhan.indexing as indexing
    settings,_,_,_=pipeline;doc=parsed(pipeline)
    monkeypatch.setattr(indexing,'MAX_INPUT',1)
    with pytest.raises(IndexFailure) as error:snapshot(settings,doc['document_id'])
    assert error.value.code=='INDEX_INPUT_LIMIT'
