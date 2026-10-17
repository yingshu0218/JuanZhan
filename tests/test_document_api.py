import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.documents import RevisionChange


@pytest.fixture
def api(tmp_path):
    settings=Settings(tmp_path/'archive','converter-token')
    app=create_app('archive',settings)
    with TestClient(app,base_url='https://archive.test') as client:
        set_password(settings,'document-api-password')
        csrf=client.get('/api/v1/auth/session').json()['csrf_token']
        csrf=client.post('/api/v1/auth/login',json={'username':'admin','password':'document-api-password'},headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        headers={'X-CSRF-Token':csrf}
        space=client.post('/api/v1/spaces',json={'name':'Archive'},headers=headers).json()['id']
        yield app,settings,client,headers,space


def upload(client,headers,space,content=b'original',**fields):
    response=client.post('/api/v1/documents/upload',data={'space_id':space,**fields},files={'file':('file.txt',content)},headers=headers)
    assert response.status_code==201,response.text
    return response.json()


def detail(client,id):return client.get('/api/v1/documents/'+id).json()


def patch(client,headers,id,version,**changes):
    return client.patch('/api/v1/documents/'+id,json={'expected_document_version':version,**changes},headers=headers)


def folder(client,headers,space,name,parent=None):
    return client.post('/api/v1/folders',json={'space_id':space,'parent_id':parent,'name':name},headers=headers).json()['id']


def test_upload_to_detail_list_properties_triage_and_recycle(api):
    app,settings,client,headers,space=api
    f=folder(client,headers,space,'Folder')
    saved=upload(client,headers,space,folder_id=f)
    id=saved['document_id']
    doc=detail(client,id)
    assert doc['availability_status']=='available' and doc['processing_status']=='queued'
    assert not doc['content_stale'] and doc['triage_status']=='needs_review' and doc['folder_id']==f
    assert client.get('/api/v1/documents').json()['total']==1
    tag=client.post('/api/v1/tags',json={'space_id':space,'name':'Tag'},headers=headers).json()['id']
    updated=patch(client,headers,id,1,title='Renamed',description='Description',document_date='2026-10-16',is_favorite=True,tags_add=[tag])
    assert updated.status_code==200 and updated.json()['document_version']==2
    assert updated.json()['tag_ids']==[tag] and updated.json()['is_favorite'] is True
    assert patch(client,headers,id,1,title='stale').json()['error']['current_document_version']==2
    result=client.post('/api/v1/documents/'+id+'/triage',json={'expected_document_version':2,'triage_status':'filed'},headers=headers)
    assert result.status_code==200 and result.json()['folder_id']==f and result.json()['document_version']==3
    assert client.post('/api/v1/documents/'+id+'/trash',json={'expected_document_version':3},headers=headers).status_code==200
    assert client.get('/api/v1/documents').json()['total']==0
    assert client.get('/api/v1/documents',params={'trash':'only'}).json()['total']==1
    assert patch(client,headers,id,4,title='blocked').status_code==409
    assert client.post('/api/v1/documents/'+id+'/restore',headers=headers).status_code==422
    restored=client.post('/api/v1/documents/'+id+'/restore',json={'expected_document_version':4},headers=headers)
    assert restored.status_code==200 and restored.json()['document_version']==5
    assert restored.json()['tag_ids']==[tag] and restored.json()['triage_status']=='filed'
    revisions=client.get('/api/v1/documents/'+id+'/revisions').json()
    assert revisions[0]['binary_available'] and revisions[0]['can_restore_binary']
    for secret in ('storage_key','managed_object_id','source_path_at_capture','/workspace'):
        assert secret not in json.dumps(restored.json())+json.dumps(revisions)


def test_stable_pagination_filters_and_rejected_search(api):
    app,settings,client,headers,space=api
    docs=[upload(client,headers,space,content=str(i).encode()) for i in range(4)]
    with connect(settings.database) as db:
        db.execute("UPDATE documents SET imported_at='2026-10-16T00:00:00Z'")
        db.commit()
    first=client.get('/api/v1/documents',params={'page_size':2}).json()
    second=client.get('/api/v1/documents',params={'page_size':2,'page':2}).json()
    assert first['total']==4 and second['total']==4
    assert [d['id'] for d in first['items']+second['items']]==sorted(d['document_id'] for d in docs)
    assert client.get('/api/v1/documents',params={'is_favorite':True}).json()['total']==0
    assert client.get('/api/v1/documents',params={'space_id':'missing'}).status_code==404
    for query in ({'page_size':101},{'page':0},{'sort':'title;drop table documents'},{'trash':'wrong'}):
        assert client.get('/api/v1/documents',params=query).status_code==422
    assert client.get('/api/v1/documents',params={'q':'not implemented'}).status_code==501


def test_scope_validation_tag_deltas_and_atomic_conflict(api):
    app,settings,client,headers,space=api
    saved=upload(client,headers,space)
    id=saved['document_id']
    other=client.post('/api/v1/spaces',json={'name':'Other'},headers=headers).json()['id']
    foreign=folder(client,headers,other,'Foreign')
    tag=client.post('/api/v1/tags',json={'space_id':space,'name':'Local'},headers=headers).json()['id']
    foreign_tag=client.post('/api/v1/tags',json={'space_id':other,'name':'Foreign'},headers=headers).json()['id']
    for changes in ({'folder_id':foreign},{'tags_add':[foreign_tag]},{'space_id':other},
                    {'document_date':'2026-02-30'},{'tags_add':[tag],'tags_remove':[tag]},{'title':None}):
        assert patch(client,headers,id,1,**changes).status_code==422
    assert patch(client,headers,id,1,tags_add=[tag,tag]).json()['tag_ids']==[tag]
    assert patch(client,headers,id,2,tags_add=[tag]).json()['document_version']==2
    assert patch(client,headers,id,2,tags_remove=[tag]).json()['tag_ids']==[]
    assert detail(client,id)['document_version']==3
    with ThreadPoolExecutor(max_workers=2) as executor:
        codes=list(executor.map(lambda name:patch(client,headers,id,3,title=name).status_code,['A','B']))
    assert sorted(codes)==[200,409]


def test_required_false_is_present_and_custom_constraints_are_not_silently_ignored(api):
    app,settings,client,headers,space=api
    saved=upload(client,headers,space)
    id=saved['document_id']
    with connect(settings.database) as db:
        db.execute("INSERT INTO field_definitions(id,space_id,field_key,label,field_type,created_at) VALUES ('boolean',?,'accepted','Accepted','boolean','now')",(space,))
        db.commit()
    type=client.post('/api/v1/document-types',json={'space_id':space,'key':'contract','label':'Contract',
        'fields':[{'field_definition_id':'boolean','required_for_filing':True}]},headers=headers).json()['id']
    assert patch(client,headers,id,1,document_type_id=type).status_code==200
    path='/api/v1/documents/'+id+'/triage'
    body={'expected_document_version':2,'triage_status':'filed'}
    assert client.post(path,json=body,headers=headers).status_code==422
    with connect(settings.database) as db:
        db.execute("INSERT INTO metadata_values(id,document_id,space_id,field_definition_id,value_bool,origin,updated_at) VALUES ('m',?,?,'boolean',0,'manual','now')",(id,space))
        db.commit()
    assert client.post(path,json=body,headers=headers).json()['triage_status']=='filed'
    with connect(settings.database) as db:
        db.execute("UPDATE field_definitions SET constraints_json='{"+'"special":true'+"}' WHERE id='boolean'")
        db.commit()
    assert client.post(path,json={'expected_document_version':3,'triage_status':'filed'},headers=headers).status_code==501


def test_availability_and_old_parse_snapshot_are_independent(api):
    app,settings,client,headers,space=api
    saved=upload(client,headers,space)
    id=saved['document_id']
    with connect(settings.database) as db:
        db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at) VALUES ('old',?,?,'test','1','1.0','completed','2026-10-15T00:00:00Z')",(id,saved['revision_id']))
        db.execute("UPDATE documents SET current_parse_run_id='old' WHERE id=?",(id,))
        db.commit()
    obj=app.state.storage.put(io.BytesIO(b'new original'),max_bytes=100)
    app.state.documents.append_managed_revision(id,obj,RevisionChange(expected_document_version=1,original_filename='new.txt',mime_type='text/plain'))
    assert detail(client,id)['content_stale'] is True
    assert detail(client,id)['processing_status']=='not_started'
    (app.state.storage.root/obj.storage_key).unlink()
    doc=detail(client,id)
    assert doc['availability_status']=='missing' and doc['content_stale'] is True
    revisions=client.get('/api/v1/documents/'+id+'/revisions').json()
    assert revisions[0]['binary_available'] is False and revisions[1]['binary_available'] is True


@pytest.mark.parametrize('mode',['move_contents_to_parent','trash_contents'])
def test_subtree_delete_is_logical_confirmed_and_preserves_originals(api,mode):
    app,settings,client,headers,space=api
    parent=folder(client,headers,space,'Parent')
    root=folder(client,headers,space,'Delete',parent)
    child=folder(client,headers,space,'Child',root)
    saved=upload(client,headers,space,folder_id=child)
    id=saved['document_id']
    with connect(settings.database) as db:
        key=db.execute('SELECT storage_key FROM managed_objects').fetchone()[0]
    path='/api/v1/folders/'+root+'/delete'
    assert client.post(path,json={'mode':mode},headers=headers).status_code==422
    assert client.post(path,json={'mode':mode,'confirm_folder_id':root},headers=headers).status_code==204
    doc=detail(client,id)
    assert doc['document_version']==2
    if mode=='move_contents_to_parent':
        assert doc['folder_id']==parent and doc['deleted_at'] is None
    else:
        assert doc['folder_id'] is None and doc['deleted_at'] is not None
        assert client.post('/api/v1/documents/'+id+'/restore',json={'expected_document_version':2},headers=headers).json()['folder_id'] is None
    assert [f['id'] for f in client.get('/api/v1/folders').json()]==[parent]
    with app.state.storage.open(key) as file:assert file.read()==b'original'
    with connect(settings.database) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute("SELECT count(*) FROM document_events WHERE event_type LIKE 'folder_deleted_%'").fetchone()==(1,)


def test_folder_delete_event_failure_and_source_reference_roll_back(api):
    app,settings,client,headers,space=api
    root=folder(client,headers,space,'Root')
    saved=upload(client,headers,space,folder_id=root)
    body={'mode':'trash_contents','confirm_folder_id':root}
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER fail_folder_event BEFORE INSERT ON document_events WHEN NEW.event_type LIKE 'folder_deleted_%' BEGIN SELECT RAISE(ABORT,'injected failure'); END;")
    assert client.post('/api/v1/folders/'+root+'/delete',json=body,headers=headers).status_code==409
    assert detail(client,saved['document_id'])['deleted_at'] is None
    assert detail(client,saved['document_id'])['document_version']==1
    with connect(settings.database) as db:
        db.execute("INSERT INTO sources(id,space_id,name,kind,root_ref,initial_target_folder_id,created_at,updated_at) VALUES ('s',?,'NAS','external','nas',?,'now','now')",(space,root))
        db.commit()
    assert client.post('/api/v1/folders/'+root+'/delete',json=body,headers=headers).json()['error']['code']=='SOURCE_FOLDER_REFERENCE'


def test_external_offline_and_unverified_mount_never_report_available(api):
    app,settings,client,headers,space=api
    with connect(settings.database) as db:
        db.execute("INSERT INTO sources(id,space_id,name,kind,root_ref,status,created_at,updated_at) VALUES ('nas',?,'NAS','external','nas','offline','now','now')",(space,))
        db.execute("INSERT INTO documents(id,space_id,title,imported_at,created_at,updated_at) VALUES ('external',?,'External','now','now','now')",(space,))
        db.execute("INSERT INTO source_entries(id,source_id,space_id,document_id,relative_path_norm,relative_path_display,size_bytes,created_at,updated_at) VALUES ('entry','nas',?,'external','file.txt','file.txt',1,'now','now')",(space,))
        db.execute("INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,source_entry_id,sha256,size_bytes,original_filename,mime_type,created_at) VALUES ('extrev','external',1,'external','entry',?,1,'file.txt','text/plain','now')",('a'*64,))
        db.execute("UPDATE documents SET current_revision_id='extrev' WHERE id='external'")
        db.commit()
    assert detail(client,'external')['availability_status']=='source_offline'
    with connect(settings.database) as db:
        db.execute("UPDATE sources SET status='ready' WHERE id='nas'")
        db.commit()
    assert detail(client,'external')['availability_status']=='unknown'
    row=client.get('/api/v1/documents/external/revisions').json()[0]
    assert not row['binary_available'] and not row['can_restore_binary']


def test_failed_current_parse_job_keeps_old_success_snapshot(api):
    from juanzhan.jobs import JobSpec
    app,settings,client,headers,space=api
    saved=upload(client,headers,space)
    id=saved['document_id']
    # Finish the upload's placeholder job as unsupported, then simulate a real historical success.
    with connect(settings.database) as db:
        db.execute("UPDATE jobs SET status='failed',retryable=0 WHERE id=?",(saved['job_id'],))
        db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at,completed_at) VALUES ('success',?,?,'test','1','1.0','completed','2026-01-01T00:00:00Z','2026-01-01T00:00:01Z')",(id,saved['revision_id']))
        db.execute("UPDATE documents SET current_parse_run_id='success' WHERE id=?",(id,))
        db.commit()
    assert detail(client,id)['processing_status']=='failed'
    assert detail(client,id)['current_parse_run_id']=='success'
    assert detail(client,id)['content_stale'] is True
    doc=app.state.documents.get_record(id)
    obj=app.state.storage.put(io.BytesIO(b'revision two'),max_bytes=100)
    updated=app.state.documents.append_managed_revision(id,obj,RevisionChange(expected_document_version=doc['document_version'],original_filename='two.txt',mime_type='text/plain'))
    q=app.state.jobs
    job=q.enqueue(JobSpec(kind='parse',target_type='document',target_id=id,idempotency_key='new-parse',payload={'revision_id':updated['current_revision_id']}))
    claim=q.claim('test')
    assert claim['id']==job['id']
    q.failure(job['id'],claim['lease_token'],'CONVERSION_FAILED','Conversion failed',retryable=False)
    shown=detail(client,id)
    assert shown['processing_status']=='failed' and shown['content_stale'] is True
    assert shown['current_parse_run_id']=='success'
