"""Real Converter HTTP, SQLite, derived storage, scoped REST/MCP and backup."""
import hashlib
import sqlite3
import pytest
from test_parsing import pipeline,upload,append,queue_parse
from test_agents import credential,rpc,ROOT
from format_samples import samples,zipped,raster_sample,pdf
from test_office_formats import workbook,presentation,odf,ODT,ODS,ODP
from juanzhan.markdown_copies import schedule
from juanzhan.worker import Worker
from juanzhan.database import connect
from juanzhan.storage import ManagedStore
from juanzhan.backup import references,create,restore


def generate(settings):
    for _ in range(30):
        n=schedule(settings)
        if not n:return
        for _ in range(n):assert Worker(settings).run_once()['status']=='completed'
    pytest.fail('Markdown outbox did not converge')


def fetch(pipeline,id,headers=None,**params):
    _,client,_,space=pipeline
    return client.get(ROOT+'/documents/'+id+'/markdown',headers=headers or {},params={'space_id':space,**params})

CASES=[(k,v[1],'content') for k,v in samples().items()]+[
 ('xlsx',workbook(),'content'),('pptx',presentation(),'content'),('odt',odf(ODT),'content'),
 ('ods',odf(ODS),'content'),('odp',odf(ODP),'content'),('csv','设备,状态\n主机,验收'.encode(),'content'),
 ('tsv','设备\t状态\n主机\t验收'.encode(),'content'),('rtf',b'{\\rtf1\\ansi Real document text}','content'),
 ('png',raster_sample('PNG'),'empty'),('jpg',raster_sample('JPEG'),'empty'),('tiff',raster_sample('TIFF'),'empty'),
 ('zip',zipped({'a.txt':'binary original'}),'unavailable'),('bin',b'\x00binary','unavailable'),
 ('pdf',pdf(encrypted=True),'unavailable')]

@pytest.mark.parametrize('ext,data,status',CASES,ids=[str(i)+'-'+c[0] for i,c in enumerate(CASES)])
def test_all_families_persist_md_without_changing_original(pipeline,ext,data,status):
    settings,client,csrf,_=pipeline
    if ext in ('zip','bin'):
        policy=client.get('/api/v1/system/upload-policy').json()
        assert client.put('/api/v1/system/upload-policy',headers=csrf,json={'expected_version':policy['version'],'excluded_groups':[g for g in policy['excluded_groups'] if g not in ('archives','executables')],'custom_extensions':[]}).status_code==200
    saved=upload(pipeline,data,'sample.'+ext);Worker(settings).run_once()
    generate(settings)
    response=fetch(pipeline,saved['document_id']);assert response.status_code==200,response.text
    result=response.json();assert result['content_status']==status
    assert result['filename'].endswith('.md') and result['format']=='markdown'
    assert result['refresh_pending'] is False
    assert client.get('/api/v1/documents/'+saved['document_id']+'/download').content==data
    with connect(settings.database) as db:
        row=db.execute('SELECT storage_key,sha256 FROM revision_markdown').fetchone()
        assert 'derived/'+row[0] in references(db)
    with ManagedStore(settings.data_dir/'derived').open(row[0]) as stream:raw=stream.read()
    assert raw.decode()==result['body'] and hashlib.sha256(raw).hexdigest()==row[1]
    assert schedule(settings)==0


def test_agent_scope_chunk_pinning_mcp_and_revision_isolation(pipeline):
    settings,client,csrf,space=pipeline
    saved=upload(pipeline,('版本一 '*200).encode());Worker(settings).run_once();generate(settings)
    id=saved['document_id'];_,h=credential(pipeline)
    first=fetch(pipeline,id,h,length=120).json()
    assert first['next_offset']==120
    assert fetch(pipeline,id,h,offset=120).status_code==422
    rest=fetch(pipeline,id,h,offset=120,revision_id=first['revision_id'],sha256=first['sha256']).json()
    assert '版本一' in first['body']+rest['body']
    assert fetch(pipeline,id,h,sha256='0'*64).status_code==409
    other=client.post('/api/v1/spaces',headers=csrf,json={'name':'private'}).json()['id']
    _,denied=credential(pipeline,[other]);assert fetch(pipeline,id,denied).status_code==404
    response=rpc(client,h,'tools/call',{'name':'read_document_markdown','arguments':{'space_id':space,'document_id':id}})
    assert response.status_code==200 and not response.json()['result'].get('isError'),response.text
    rev=append(settings,id,b'New revision bytes')
    generate(settings)
    current=fetch(pipeline,id,h).json();assert current['revision_id']==rev and current['content_status']=='unavailable'
    assert '版本一' not in current['body']
    historical=fetch(pipeline,id,h,revision_id=first['revision_id']).json();assert historical['stale_for_current_revision'] and '版本一' in historical['body']
    queue_parse(settings,id,rev);Worker(settings).run_once();generate(settings)
    assert fetch(pipeline,id,h).json()['content_status']=='content'
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM revision_markdown').fetchone()[0]==2


def test_pending_upgrade_backfill_and_backup_restore(pipeline,tmp_path):
    settings,client,_,_=pipeline
    saved=upload(pipeline,b'Preserved content')
    assert fetch(pipeline,saved['document_id']).status_code==409
    Worker(settings).run_once();generate(settings)
    before=fetch(pipeline,saved['document_id']).json()
    bundle=tmp_path/'bundle';create(settings,bundle)
    destination=tmp_path/'restored';restore(bundle,destination)
    with connect(destination/'database/archive.sqlite3') as db:
        key=db.execute('SELECT storage_key FROM revision_markdown').fetchone()[0]
    with ManagedStore(destination/'derived').open(key) as stream:
        assert stream.read().decode()==before['body']


def test_failed_reparse_preserves_successful_md(pipeline):
    settings,client,_,_=pipeline
    saved=upload(pipeline,b'Original success');Worker(settings).run_once();generate(settings)
    before=fetch(pipeline,saved['document_id']).json()
    # A real failed ParseRun (encrypted PDF) is covered above; a retried request with
    # a converter failure must not replace the previous successful body.
    import os
    old=os.environ['CONVERTER_URL'];os.environ['CONVERTER_URL']='http://127.0.0.1:1'
    try:
        queue_parse(settings,saved['document_id'],before['revision_id'])
        Worker(settings).run_once()
    finally:os.environ['CONVERTER_URL']=old
    generate(settings)
    after=fetch(pipeline,saved['document_id']).json()
    assert after['parse_run_id']==before['parse_run_id'] and 'Original success' in after['body']


def test_missing_md_returns_explicit_error_and_superseded_job_cannot_publish(pipeline):
    from juanzhan.jobs import JobQueue
    from juanzhan.markdown_copies import execute
    settings,client,_,_=pipeline
    saved=upload(pipeline,b'Verifiable source');Worker(settings).run_once()
    assert schedule(settings)==1
    job=JobQueue(settings).claim('stale-markdown-worker')
    with connect(settings.database) as db:
        db.execute('UPDATE markdown_dirty SET generation=generation+1');db.commit()
    execute(settings,job)
    assert fetch(pipeline,saved['document_id']).status_code==409
    generate(settings)
    result=fetch(pipeline,saved['document_id']).json()
    with connect(settings.database) as db:
        key=db.execute('SELECT storage_key FROM revision_markdown').fetchone()[0]
    path=settings.data_dir/'derived'/key
    original=path.read_bytes();path.write_bytes(b'broken')
    assert fetch(pipeline,saved['document_id']).status_code==503
    path.write_bytes(original)
    assert fetch(pipeline,saved['document_id']).json()['sha256']==result['sha256']
