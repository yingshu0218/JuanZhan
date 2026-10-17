import hashlib
import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from test_sources import api, create
from test_source_initial import scan, source_row
from juanzhan.apps import create_app
from juanzhan.database import connect
from juanzhan.jobs import JobQueue, LostLease
from juanzhan.source_initial import publish as first_publish
from juanzhan.source_incremental import publish
from juanzhan.source_paths import SourcePathError
from juanzhan.worker import Worker


def item(path,content=b'original',hint='1:10',mtime=1000000000):
    return {'kind':'file','path':path,'sha256':hashlib.sha256(content).hexdigest(),'size_bytes':len(content),
            'mime_type':'text/plain','mtime_ns':mtime,'file_modified_at':'1970-01-01T00:00:01Z','identity_hint':hint}


def manifest(items):return io.StringIO(''.join(json.dumps(i)+'\n' for i in items))


def claim(settings,id,queue=None):
    queue=queue or JobQueue(settings)
    while job:=queue.claim('test'):
        if job['id']==id:return job
        queue.failure(job['id'],job['lease_token'],'HANDLER_NOT_AVAILABLE','Not implemented',retryable=False)
    raise AssertionError('Job not claimable')


def seed(api,items,**options):
    settings,client,headers,space=api
    source=create(client,headers,space,**options).json()['id']
    id=scan(client,headers,source).json()['job_id']
    job=claim(settings,id)
    counts={'source_id':source,'mode':'initial','imported_files':len(items),'created_folders':0,'ignored_files':0,'imported_bytes':sum(i['size_bytes'] for i in items)}
    JobQueue(settings).complete(id,job['lease_token'],lambda db,owned:first_publish(db,owned,source_row(settings,source),manifest(items),counts,settings))
    return source


def run(api,source,items,queue=None):
    settings,client,headers,_=api
    id=scan(client,headers,source,'incremental').json()['job_id']
    queue=queue or JobQueue(settings)
    job=claim(settings,id,queue)
    counts={'source_id':source,'mode':'incremental','scanned_files':len(items),'scanned_bytes':sum(i['size_bytes'] for i in items),
            'ignored_files':0,'imported_files':0,'updated_files':0,'reassociated_files':0,'recovered_files':0,'unchanged_files':0}
    queue.complete(id,job['lease_token'],lambda db,owned:publish(db,owned,source_row(settings,source),manifest(items),counts,settings))
    return queue.get(id)['result']


def entries(api,source):return api[1].get('/api/v1/sources/'+source+'/entries').json()['items']
def doc(api,id):return api[1].get('/api/v1/documents/'+id).json()


def test_hash_change_even_with_same_size_mtime_preserves_manual_fields_and_old_parse(api):
    settings,client,headers,space=api
    source=seed(api,[item('a.txt',b'old!')])
    id=entries(api,source)[0]['document_id']
    assert client.patch('/api/v1/documents/'+id,headers=headers,json={'expected_document_version':1,'title':'Human title','is_favorite':True}).status_code==200
    old=doc(api,id)
    with connect(settings.database) as db:
        db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at) VALUES ('old',?,?,'fixture','1','1.0','completed','2026-10-17')",(id,old['current_revision_id']))
        db.execute("UPDATE documents SET current_parse_run_id='old' WHERE id=?",(id,))
        db.commit()
    result=run(api,source,[item('a.txt',b'new!')])
    current=doc(api,id)
    assert result['updated_files']==1 and current['current_revision_id']!=old['current_revision_id']
    assert current['title']=='Human title' and current['is_favorite'] and current['document_version']==3
    assert current['current_parse_run_id']=='old' and current['content_stale']
    assert run(api,source,[item('a.txt',b'new!',mtime=2000000000)])['unchanged_files']==1
    assert doc(api,id)['document_version']==3
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM file_revisions WHERE document_id=?',(id,)).fetchone()[0]==2


def test_new_files_needs_review_use_new_target_and_never_recreate_tree(api):
    settings,client,headers,space=api
    target=client.post('/api/v1/folders',headers=headers,json={'space_id':space,'name':'New target'}).json()['id']
    source=seed(api,[item('a.txt')],initial_import_policy='tree',initial_triage_status='filed',new_file_target_folder_id=target)
    old=entries(api,source)[0]['document_id']
    result=run(api,source,[item('a.txt'),item('new/deep/b.txt',b'new',hint='1:20')])
    assert result['imported_files']==1
    added=next(e['document_id'] for e in entries(api,source) if e['relative_path'].endswith('b.txt'))
    assert doc(api,added)['triage_status']=='needs_review' and doc(api,added)['folder_id']==target
    assert doc(api,old)['triage_status']=='filed' and doc(api,old)['folder_id'] is None
    assert len(client.get('/api/v1/folders?space_id='+space).json())==1


@pytest.mark.parametrize('same_inode',[True,False])
def test_unique_rename_keeps_ids_and_historical_capture_path(api,same_inode):
    source=seed(api,[item('old.txt')])
    old=entries(api,source)[0]
    revision=doc(api,old['document_id'])['current_revision_id']
    result=run(api,source,[item('moved/new.txt',hint='1:10' if same_inode else '1:99')])
    current=entries(api,source)[0]
    assert result['reassociated_files']==1 and result['imported_files']==0
    assert current['id']==old['id'] and current['document_id']==old['document_id']
    assert current['relative_path']=='moved/new.txt' and doc(api,old['document_id'])['current_revision_id']==revision
    with connect(api[0].database) as db:assert db.execute('SELECT source_path_at_capture FROM file_revisions WHERE id=?',(revision,)).fetchone()[0]=='old.txt'


@pytest.mark.parametrize('hint',['1:99','1:10'])
def test_duplicate_hash_move_is_ambiguous_and_does_not_create_or_merge_documents(api,hint):
    source=seed(api,[item('a.txt',hint='1:10'),item('b.txt',hint='1:20')])
    old_ids={e['document_id'] for e in entries(api,source)}
    result=run(api,source,[item('new.txt',hint=hint)])
    current=entries(api,source)
    assert result['needs_match']==3 and result['imported_files']==0 and result['reassociated_files']==0
    assert {e['document_id'] for e in current if e['document_id']}==old_ids
    assert next(e for e in current if e['relative_path']=='new.txt')['document_id'] is None
    again=run(api,source,[item('new.txt',hint=hint)])
    assert again['needs_match']==3 and len(entries(api,source))==3


def test_missing_requires_two_distinct_completed_scans_and_return_recovers(api):
    source=seed(api,[item('gone.txt')])
    id=entries(api,source)[0]['document_id']
    first=run(api,source,[])
    assert first['suspected_missing']==1 and entries(api,source)[0]['status']=='suspected_missing'
    assert run(api,source,[])['missing']==1
    assert entries(api,source)[0]['status']=='missing'
    assert run(api,source,[item('gone.txt')])['recovered_files']==1
    assert entries(api,source)[0]['status']=='available' and entries(api,source)[0]['document_id']==id


def test_failure_breaks_missing_evidence_without_changing_entries(api):
    settings,client,headers,_=api
    source=seed(api,[item('gone.txt')])
    run(api,source,[])
    id=scan(client,headers,source,'incremental').json()['job_id']
    owned=claim(settings,id)
    JobQueue(settings).failure(id,owned['lease_token'],'SOURCE_OFFLINE','Source unavailable',retryable=False)
    assert entries(api,source)[0]['status']=='suspected_missing'
    assert run(api,source,[])['suspected_missing']==1
    assert run(api,source,[])['missing']==1


def test_changed_root_and_unanchored_upgrade_do_not_mark_entries_missing(api):
    settings,_,_,_=api
    source=seed(api,[item('keep.txt')])
    with connect(settings.database) as db:
        db.execute("UPDATE source_root_baselines SET root_digest=? WHERE source_id=?",('0'*64,source))
        db.commit()
    with pytest.raises(SourcePathError,match='SOURCE_ROOT_CHANGED'):run(api,source,[])
    assert entries(api,source)[0]['status']=='available'
    # End the failed attempt before testing a legacy baseline.
    with connect(settings.database) as db:
        job=db.execute("SELECT id,lease_token FROM jobs WHERE status='running' AND kind='scan'").fetchone()
    JobQueue(settings).failure(job[0],job[1],'SOURCE_ROOT_CHANGED','Root changed',retryable=False)
    with connect(settings.database) as db:
        db.execute('DELETE FROM source_root_baselines WHERE source_id=?',(source,));db.commit()
    with pytest.raises(SourcePathError,match='SOURCE_ROOT_UNVERIFIED'):run(api,source,[])
    assert entries(api,source)[0]['status']=='available'


def test_legacy_upgrade_anchors_once_and_lease_expiry_rolls_back_all_changes(api):
    settings,client,headers,_=api
    source=seed(api,[item('a.txt')])
    with connect(settings.database) as db:db.execute('DELETE FROM source_root_baselines WHERE source_id=?',(source,));db.commit()
    assert run(api,source,[item('a.txt')])['unchanged_files']==1
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM source_root_baselines WHERE source_id=?',(source,)).fetchone()[0]==1
    id=scan(client,headers,source,'incremental').json()['job_id']
    clock=[2000000000.0]
    queue=JobQueue(settings,clock=lambda:clock[0]);owned=claim(settings,id,queue)
    before=entries(api,source)
    counts={'imported_files':0,'updated_files':0,'reassociated_files':0,'recovered_files':0,'unchanged_files':0}
    def effect(db,job):
        result=publish(db,job,source_row(settings,source),manifest([item('b.txt',b'new',hint='1:99')]),counts,settings)
        clock[0]+=31
        return result
    with pytest.raises(LostLease):queue.complete(id,owned['lease_token'],effect)
    assert entries(api,source)==before
    with connect(settings.database) as db:assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==1


def test_live_offline_document_projection_is_independent_of_scan_and_keeps_inventory(api,tmp_path):
    settings,client,_,_=api
    source=seed(api,[item('a.txt')])
    entry=entries(api,source)[0]
    missing=replace(settings,source_mounts=(('docs',str(tmp_path/'unmounted')),))
    with TestClient(create_app('archive',missing),base_url='https://archive.test') as offline:
        offline.cookies.update(client.cookies)
        assert offline.get('/api/v1/documents/'+entry['document_id']).json()['availability_status']=='source_offline'
        assert offline.get('/api/v1/sources/'+source).json()['health']['mount_status']=='offline'
        assert offline.get('/api/v1/sources/'+source+'/entries').json()['items'][0]['status']=='available'
    assert doc(api,entry['document_id'])['availability_status']=='unknown'
    assert entries(api,source)[0]['status']=='available'
