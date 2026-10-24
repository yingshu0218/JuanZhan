import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.documents import Registration, RevisionChange, VersionChange
from juanzhan.storage import IntegrityError


@pytest.fixture
def documents(tmp_path):
    settings = Settings(tmp_path / 'archive', 'converter-token')
    app = create_app('archive', settings)
    with TestClient(app, base_url='https://archive.test') as client:
        set_password(settings, 'document-test-password')
        csrf = client.get('/api/v1/auth/session').json()['csrf_token']
        csrf = client.post('/api/v1/auth/login', json={'username':'admin','password':'document-test-password'}, headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        headers = {'X-CSRF-Token':csrf}
        space = client.post('/api/v1/spaces', json={'name':'Archive'}, headers=headers).json()['id']
        yield app.state.documents, app.state.storage, settings, client, headers, space, app


def published(store, payload=b'original'):
    return store.put(io.BytesIO(payload), max_bytes=1024)


def register(service, store, space, payload=b'original', **kwargs):
    obj = published(store, payload)
    result = service.register_managed(obj, Registration(space_id=space,title='Contract',
               original_filename='contract.txt',mime_type='text/plain',**kwargs))
    return result, obj


def change(version):
    return VersionChange(expected_document_version=version)


def revision(version):
    return RevisionChange(expected_document_version=version,original_filename='revision.txt',mime_type='text/plain')


def test_register_atomic_identity_and_audit(documents):
    service, store, settings, client, headers, space, app = documents
    folder = client.post('/api/v1/folders',json={'space_id':space,'name':'Contracts'},headers=headers).json()['id']
    doc, obj = register(service,store,space,folder_id=folder)
    assert doc['document_version']==1 and doc['triage_status']=='needs_review'
    assert doc['folder_id']==folder and doc['current_revision_id'] is not None
    with connect(settings.database) as db:
        row = db.execute('SELECT document_id,revision_no,managed_object_id FROM file_revisions').fetchone()
        assert row[0]==doc['id'] and row[1]==1
        event = db.execute('SELECT event_type,before_json,after_json FROM document_events').fetchone()
        assert event[0]=='document_created' and event[1] is None
        assert json.loads(event[2])==doc
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    with store.open(obj.storage_key) as file:
        assert file.read()==b'original'


def test_duplicate_policy_and_cross_space_physical_reuse(documents):
    service, store, settings, client, headers, space, app = documents
    first, obj = register(service,store,space)
    info = Registration(space_id=space,title='Separate',original_filename='copy.txt',mime_type='text/plain')
    with pytest.raises(HTTPException) as caught:
        service.register_managed(obj,info)
    assert caught.value.status_code==409
    assert caught.value.detail['code']=='DUPLICATE_DETECTED'
    assert caught.value.detail['details']['duplicates']==[first['id']]
    second = service.register_managed(obj,info.model_copy(update={'duplicate_policy':'keep_separate'}))
    assert second['id']!=first['id'] and second['current_revision_id']!=first['current_revision_id']
    other = client.post('/api/v1/spaces',json={'name':'Other'},headers=headers).json()['id']
    third = service.register_managed(obj,info.model_copy(update={'space_id':other}))
    assert len({first['id'],second['id'],third['id']})==3
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM documents').fetchone()==(3,)
        assert db.execute('SELECT count(*) FROM document_events').fetchone()==(3,)


def test_revision_keeps_id_old_content_and_manual_facts(documents):
    service, store, settings, client, headers, space, app = documents
    doc, original = register(service,store,space)
    tag = client.post('/api/v1/tags',json={'space_id':space,'name':'manual'},headers=headers).json()['id']
    with connect(settings.database) as db:
        db.execute('INSERT INTO document_tags VALUES (?,?,?)',(doc['id'],space,tag))
        db.execute("INSERT INTO field_definitions(id,space_id,field_key,label,field_type,created_at) VALUES ('f',?,'contract_no','Number','text','now')",(space,))
        db.execute("INSERT INTO metadata_values(id,document_id,space_id,field_definition_id,value_text,origin,is_confirmed,updated_at) VALUES ('v',?,?,'f','MANUAL','manual',1,'now')",(doc['id'],space))
        db.execute("INSERT INTO parse_runs(id,document_id,revision_id,parser_name,parser_version,schema_version,status,created_at) VALUES ('parse',?,?,'parser','1','1.0','completed','now')",(doc['id'],doc['current_revision_id']))
        db.execute("UPDATE documents SET current_parse_run_id='parse' WHERE id=?",(doc['id'],))
        db.commit()
    updated = service.append_managed_revision(doc['id'],published(store,b'new bytes'),revision(1))
    assert updated['id']==doc['id'] and updated['document_version']==2
    assert updated['current_revision_id']!=doc['current_revision_id']
    assert updated['current_parse_run_id']=='parse' and set(updated['tag_ids'])==set(doc['tag_ids'])|{tag}
    assert [r['revision_no'] for r in service.revisions(doc['id'])]==[1,2]
    with connect(settings.database) as db:
        assert db.execute("SELECT value_text,is_confirmed FROM metadata_values WHERE id='v'").fetchone()==('MANUAL',1)
    with store.open(original.storage_key) as file:
        assert file.read()==b'original'


def test_revision_concurrency_is_one_success_one_conflict(documents):
    service, store, settings, client, headers, space, app = documents
    doc,_ = register(service,store,space)
    objects = [published(store,b'first'),published(store,b'second')]
    def append(obj):
        try:
            return service.append_managed_revision(doc['id'],obj,revision(1))['document_version']
        except HTTPException as exc:
            assert exc.detail['current_document_version']==2
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(append,objects))==[2,409]
    assert [r['revision_no'] for r in service.revisions(doc['id'])]==[1,2]
    with connect(settings.database) as db:
        assert db.execute("SELECT count(*) FROM document_events WHERE event_type='revision_added'").fetchone()==(1,)


def test_audit_failure_rolls_back_every_db_change_but_keeps_bytes(documents):
    service, store, settings, client, headers, space, app = documents
    doc,_ = register(service,store,space)
    obj = published(store,b'orphan if database fails')
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER inject_audit_failure BEFORE INSERT ON document_events WHEN NEW.event_type='revision_added' BEGIN SELECT RAISE(ABORT,'injected event failure'); END;")
    with pytest.raises(HTTPException):
        service.append_managed_revision(doc['id'],obj,revision(1))
    assert service.get_record(doc['id'])==doc
    assert len(service.revisions(doc['id']))==1
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM managed_objects').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM document_events').fetchone()==(1,)
    with store.open(obj.storage_key) as file:
        assert file.read()==b'orphan if database fails'


def test_soft_delete_restore_versions_and_original_are_preserved(documents):
    service, store, settings, client, headers, space, app = documents
    folder = client.post('/api/v1/folders',json={'space_id':space,'name':'Folder'},headers=headers).json()['id']
    doc,obj = register(service,store,space,folder_id=folder)
    trashed = service.trash(doc['id'],change(1))
    assert trashed['document_version']==2 and trashed['deleted_at'].endswith('Z')
    assert trashed['folder_id']==folder and trashed['triage_status']=='needs_review'
    assert service.trash(doc['id'],change(2))==trashed
    with pytest.raises(HTTPException) as caught:
        service.append_managed_revision(doc['id'],published(store,b'blocked'),revision(2))
    assert caught.value.detail['code']=='DOCUMENT_TRASHED'
    restored = service.restore(doc['id'],change(2))
    assert restored['document_version']==3 and restored['deleted_at'] is None
    assert restored['folder_id']==folder and restored['current_revision_id']==doc['current_revision_id']
    assert service.restore(doc['id'],change(3))==restored
    with pytest.raises(HTTPException):
        service.trash(doc['id'],change(1))
    with store.open(obj.storage_key) as file:
        assert file.read()==b'original'
    with connect(settings.database) as db:
        assert db.execute('SELECT event_type FROM document_events ORDER BY rowid').fetchall()==[
            ('document_created',),('document_trashed',),('document_restored',)]


def test_restore_unclassified_when_folder_link_was_removed(documents):
    service, store, settings, client, headers, space, app = documents
    folder = client.post('/api/v1/folders',json={'space_id':space,'name':'Old'},headers=headers).json()['id']
    doc,_ = register(service,store,space,folder_id=folder)
    service.trash(doc['id'],change(1))
    with connect(settings.database) as db:
        db.execute('UPDATE documents SET folder_id=NULL WHERE id=?',(doc['id'],))
        db.execute('DELETE FROM folders WHERE id=?',(folder,))
        db.commit()
    assert service.restore(doc['id'],change(2))['folder_id'] is None


def test_missing_or_forged_objects_never_create_references(documents):
    service, store, settings, client, headers, space, app = documents
    obj = published(store)
    info = Registration(space_id=space,title='Test',original_filename='test.txt',mime_type='text/plain')
    with pytest.raises(IntegrityError):
        service.register_managed(replace(obj,sha256='0'*64),info)
    (store.root/obj.storage_key).unlink()
    with pytest.raises(FileNotFoundError):
        service.register_managed(obj,info)
    with connect(settings.database) as db:
        for table in ('documents','file_revisions','managed_objects','document_events'):
            assert db.execute('SELECT count(*) FROM '+table).fetchone()==(0,)


def test_cross_space_and_inactive_type_rejections(documents):
    service, store, settings, client, headers, space, app = documents
    other = client.post('/api/v1/spaces',json={'name':'Other'},headers=headers).json()['id']
    foreign_folder = client.post('/api/v1/folders',json={'space_id':other,'name':'Foreign'},headers=headers).json()['id']
    type = client.post('/api/v1/document-types',json={'space_id':space,'key':'disabled','label':'Disabled'},headers=headers).json()['id']
    client.patch('/api/v1/document-types/'+type,json={'is_active':False},headers=headers)
    obj = published(store)
    base = dict(space_id=space,title='Test',original_filename='file.txt',mime_type='text/plain')
    for fields in ({'folder_id':foreign_folder},{'document_type_id':type}):
        with pytest.raises(HTTPException) as caught:
            service.register_managed(obj,Registration(**base,**fields))
        assert caught.value.status_code==422
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM documents').fetchone()==(0,)


def test_http_adapter_rechecks_auth_and_returns_version_details(documents):
    service, store, settings, client, headers, space, app = documents
    doc,_ = register(service,store,space)
    @app.post('/api/v1/_test/documents/{id}/trash')
    def trash(id: str, body: VersionChange, request: Request):
        return service.trash(id,body,request=request)
    assert client.post('/api/v1/_test/documents/'+doc['id']+'/trash',json={'expected_document_version':1}).status_code==403
    result = client.post('/api/v1/_test/documents/'+doc['id']+'/trash',json={'expected_document_version':1},headers=headers)
    assert result.status_code==200
    result = client.post('/api/v1/_test/documents/'+doc['id']+'/trash',json={'expected_document_version':1},headers=headers)
    assert result.status_code==409 and result.json()['error']['current_document_version']==2
    assert '/workspace' not in result.text and 'storage_key' not in result.text


@pytest.mark.parametrize('filename',['../secret','C:\\secret.txt','folder/file.txt','.', '\x00bad'])
def test_filename_metadata_is_not_a_path(filename):
    with pytest.raises(ValidationError):
        Registration(space_id='space',title='Test',original_filename=filename,mime_type='text/plain')


def test_concurrent_duplicate_registration_is_not_automatic_merge(documents):
    service, store, settings, client, headers, space, app = documents
    obj = published(store)
    info = Registration(space_id=space,title='Test',original_filename='same.txt',mime_type='text/plain')
    def register_once(_):
        try:
            service.register_managed(obj,info)
            return 201
        except HTTPException as exc:
            assert exc.detail['code']=='DUPLICATE_DETECTED'
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(register_once,range(2)))==[201,409]
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM documents').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM file_revisions').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM document_events').fetchone()==(1,)


def test_registration_audit_failure_rolls_back_document_revision_and_object(documents):
    service, store, settings, client, headers, space, app = documents
    obj = published(store)
    with connect(settings.database) as db:
        db.executescript("CREATE TRIGGER inject_create_failure BEFORE INSERT ON document_events WHEN NEW.event_type='document_created' BEGIN SELECT RAISE(ABORT,'injected creation failure'); END;")
    with pytest.raises(HTTPException):
        service.register_managed(obj,Registration(space_id=space,title='Test',original_filename='file.txt',mime_type='text/plain'))
    with connect(settings.database) as db:
        for table in ('documents','file_revisions','managed_objects','document_events'):
            assert db.execute('SELECT count(*) FROM '+table).fetchone()==(0,)
    with store.open(obj.storage_key) as file:
        assert file.read()==b'original'


def test_document_identity_and_revision_sequence_survive_restart(documents):
    service, store, settings, client, headers, space, app = documents
    doc,_ = register(service,store,space)
    with TestClient(create_app('archive',settings),base_url='https://archive.test') as restarted:
        next_service = restarted.app.state.documents
        assert next_service.get_record(doc['id'])==doc
        updated = next_service.append_managed_revision(doc['id'],published(store,b'after restart'),revision(1))
        assert updated['id']==doc['id'] and updated['document_version']==2
        assert [r['revision_no'] for r in next_service.revisions(doc['id'])]==[1,2]


def test_external_soft_delete_never_writes_original(documents, tmp_path):
    import hashlib
    service, store, settings, client, headers, space, app = documents
    original = tmp_path/'external.txt'
    original.write_bytes(b'external original')
    original.chmod(0o444)
    before_stat = original.stat()
    checksum = hashlib.sha256(original.read_bytes()).hexdigest()
    with connect(settings.database) as db:
        db.execute("INSERT INTO sources(id,space_id,name,kind,root_ref,created_at,updated_at) VALUES ('nas',?,'NAS','external','nas','now','now')",(space,))
        db.execute("INSERT INTO documents(id,space_id,title,imported_at,created_at,updated_at) VALUES ('external',?,'External','now','now','now')",(space,))
        db.execute("INSERT INTO source_entries(id,source_id,space_id,document_id,relative_path_norm,relative_path_display,size_bytes,created_at,updated_at) VALUES ('entry','nas',?,'external','external.txt','external.txt',?,'now','now')",(space,len(b'external original')))
        db.execute("INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,source_entry_id,sha256,size_bytes,original_filename,mime_type,created_at) VALUES ('external-rev','external',1,'external','entry',?,?,'external.txt','text/plain','now')",(checksum,len(b'external original')))
        db.execute("UPDATE documents SET current_revision_id='external-rev' WHERE id='external'")
        db.commit()
    service.trash('external',change(1))
    restored = service.restore('external',change(2))
    assert restored['current_revision_id']=='external-rev'
    with pytest.raises(HTTPException) as caught:
        service.append_managed_revision('external',published(store,b'not a takeover'),revision(3))
    assert caught.value.status_code==409
    assert caught.value.detail['code']=='EXTERNAL_ADOPTION_REQUIRED'
    assert original.read_bytes()==b'external original'
    assert original.stat().st_mtime_ns==before_stat.st_mtime_ns
    assert original.stat().st_ino==before_stat.st_ino
