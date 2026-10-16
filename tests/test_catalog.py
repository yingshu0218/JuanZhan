import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect


@pytest.fixture
def catalog(tmp_path):
    settings = Settings(tmp_path / 'archive', 'converter-token')
    app = create_app('archive', settings)
    with TestClient(app, base_url='https://archive.test') as client:
        set_password(settings, 'catalog-test-password')
        csrf = client.get('/api/v1/auth/session').json()['csrf_token']
        response = client.post('/api/v1/auth/login', json={'username':'admin','password':'catalog-test-password'}, headers={'X-CSRF-Token':csrf})
        csrf = response.json()['csrf_token']
        token = client.post('/api/v1/auth/tokens', json={'name':'catalog tests'}, headers={'X-CSRF-Token':csrf}).json()['token']
        yield client, settings, app, {'Authorization':'Bearer '+token}, {'X-CSRF-Token':csrf}


def create(client, path, body, headers):
    result = client.post('/api/v1/'+path, json=body, headers=headers)
    assert result.status_code == 201, result.text
    return result.json()


def space(client, headers, name='Archive'):
    return create(client, 'spaces', {'name':name}, headers)['id']


def folder(client, headers, space_id, name, parent_id=None):
    return create(client, 'folders', {'space_id':space_id,'name':name,'parent_id':parent_id}, headers)


def test_space_creation_auth_csrf_and_restart(catalog):
    client, settings, app, bearer, csrf = catalog
    with TestClient(app, base_url='https://archive.test') as anonymous:
        for path in ('spaces','folders','tags','document-types'):
            assert anonymous.get('/api/v1/'+path).status_code == 401
            assert anonymous.post('/api/v1/'+path, json={}).status_code == 401
    assert client.post('/api/v1/spaces', json={'name':'No CSRF'}).status_code == 403
    created = create(client, 'spaces', {'name':'  合同档案  '}, csrf)
    assert created['name'] == '合同档案' and created['created_at'].endswith('Z')
    assert client.get('/api/v1/spaces').json() == [created]
    with TestClient(create_app('archive', settings), base_url='https://archive.test') as restarted:
        assert restarted.get('/api/v1/spaces', headers=bearer).json() == [created]
    assert client.patch('/api/v1/spaces/'+created['id'], json={'name':'unsupported'}, headers=bearer).status_code == 404


def test_folder_tree_normalization_moves_and_scopes(catalog):
    client, settings, app, headers, csrf = catalog
    a, b = space(client, headers), space(client, headers, 'Second')
    root = folder(client, headers, a, '  Ｆｉｌｅｓ  ')
    assert root['name'] == 'Ｆｉｌｅｓ' and root['name_norm'] == 'files'
    conflict = client.post('/api/v1/folders', json={'space_id':a,'name':'FILES'}, headers=headers)
    assert conflict.status_code == 409
    child = folder(client, headers, a, 'child', root['id'])
    leaf = folder(client, headers, a, 'leaf', child['id'])
    other = folder(client, headers, b, 'files')
    # Cycles, including indirect ones, fail without losing the original tree.
    for parent in (root['id'], leaf['id']):
        response = client.patch('/api/v1/folders/'+root['id'], json={'parent_id':parent}, headers=headers)
        assert response.status_code == 409 and response.json()['error']['code'] == 'FOLDER_CYCLE'
    assert client.patch('/api/v1/folders/'+child['id'], json={'parent_id':other['id']}, headers=headers).status_code == 422
    assert client.post('/api/v1/folders', json={'space_id':a,'name':'cross','parent_id':other['id']}, headers=headers).status_code == 422
    result = client.get('/api/v1/folders', params={'space_id':a,'parent_id':root['id']}).json()
    assert [f['id'] for f in result] == [child['id']]
    assert client.get('/api/v1/folders', params={'space_id':b,'parent_id':root['id']}).status_code == 422
    moved = client.patch('/api/v1/folders/'+child['id'], json={'parent_id':None,'name':'renamed'}, headers=headers)
    assert moved.status_code == 200 and moved.json()['parent_id'] is None
    rows = client.get('/api/v1/folders', params={'space_id':a}).json()
    assert len(rows) == 3
    assert next(f for f in rows if f['id']==leaf['id'])['parent_id'] == child['id']
    assert len(client.get('/api/v1/folders').json()) == 4


def test_folder_empty_delete_and_dependent_modes(catalog):
    client, settings, app, headers, csrf = catalog
    a = space(client, headers)
    parent = folder(client, headers, a, 'parent')
    child = folder(client, headers, a, 'child', parent['id'])
    path = '/api/v1/folders/'+parent['id']+'/delete'
    assert client.post(path, json={'mode':'only_if_empty'}, headers=headers).status_code == 409
    for mode in ('trash_contents','move_contents_to_parent'):
        assert client.post(path, json={'mode':mode}, headers=headers).status_code == 501
    assert client.post('/api/v1/folders/'+child['id']+'/delete', json={'mode':'only_if_empty'}, headers=headers).status_code == 204
    with connect(settings.database) as db:
        db.execute("INSERT INTO sources(id,space_id,name,kind,root_ref,initial_target_folder_id,created_at,updated_at) VALUES ('source',?,'NAS','external','nas',?,'now','now')", (a,parent['id']))
        db.commit()
    assert client.post(path, json={'mode':'only_if_empty'}, headers=headers).status_code == 409
    with connect(settings.database) as db:
        db.execute("DELETE FROM sources WHERE id='source'")
        db.execute("INSERT INTO documents(id,space_id,folder_id,title,imported_at,created_at,updated_at,deleted_at) VALUES ('trashed',?,?,'Existing','now','now','now','now')", (a,parent['id']))
        db.commit()
    assert client.post(path, json={'mode':'only_if_empty'}, headers=headers).status_code == 409
    with connect(settings.database) as db:
        db.execute("UPDATE documents SET folder_id=NULL WHERE id='trashed'")
        db.commit()
    assert client.post(path, json={'mode':'only_if_empty'}, headers=headers).status_code == 204
    assert client.post(path, json={'mode':'only_if_empty'}, headers=headers).status_code == 404


def test_tag_rename_delete_preserves_document_and_file(catalog):
    client, settings, app, headers, csrf = catalog
    a = space(client, headers)
    tag = create(client, 'tags', {'space_id':a,'name':'重要','color':'green','description':'note'}, headers)
    assert client.post('/api/v1/tags', json={'space_id':a,'name':' 重要 '}, headers=headers).status_code == 409
    updated = client.patch('/api/v1/tags/'+tag['id'], json={'name':'重点','color':None}, headers=headers)
    assert updated.status_code == 200 and updated.json()['description'] == 'note'
    assert updated.json()['color'] is None
    obj = app.state.storage.put(io.BytesIO(b'real original'), max_bytes=100)
    with connect(settings.database) as db:
        db.execute('INSERT INTO managed_objects VALUES (?,?,?,?,?)', ('o',obj.sha256,obj.size_bytes,obj.storage_key,'now'))
        db.execute("INSERT INTO documents(id,space_id,title,imported_at,created_at,updated_at) VALUES ('doc',?,'Document','now','now','now')", (a,))
        db.execute("INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,managed_object_id,sha256,size_bytes,original_filename,mime_type,created_at) VALUES ('rev','doc',1,'managed','o',?,?,'file.txt','text/plain','now')", (obj.sha256,obj.size_bytes))
        db.execute("UPDATE documents SET current_revision_id='rev' WHERE id='doc'")
        db.execute('INSERT INTO document_tags VALUES (?,?,?)', ('doc',a,tag['id']))
        db.commit()
    assert client.delete('/api/v1/tags/'+tag['id']).status_code == 403
    assert client.delete('/api/v1/tags/'+tag['id'], headers=headers).status_code == 204
    with connect(settings.database) as db:
        assert db.execute("SELECT document_version,current_revision_id FROM documents WHERE id='doc'").fetchone() == (2,'rev')
        assert db.execute('SELECT count(*) FROM document_tags').fetchone() == (0,)
        assert db.execute("SELECT event_type FROM document_events WHERE document_id='doc'").fetchone() == ('tag_deleted',)
    with app.state.storage.open(obj.storage_key) as original:
        assert original.read() == b'real original'


def test_document_type_fields_are_atomic_scoped_and_preserve_values(catalog):
    client, settings, app, headers, csrf = catalog
    a, b = space(client, headers), space(client, headers, 'Second')
    with connect(settings.database) as db:
        for id, owner in (('field-a',a),('field-b',b)):
            db.execute("INSERT INTO field_definitions(id,space_id,field_key,label,field_type,created_at) VALUES (?,?,?,'Amount','integer','now')", (id,owner,'amount'))
        db.commit()
    field = {'field_definition_id':'field-a','required_for_filing':True,'display_order':2}
    type = create(client, 'document-types', {'space_id':a,'key':'contract','label':'合同','fields':[field]}, headers)
    assert type['fields'] == [field] and type['is_active'] is True
    duplicate = client.post('/api/v1/document-types', json={'space_id':a,'key':'contract','label':'重复'}, headers=headers)
    assert duplicate.status_code == 409
    assert client.patch('/api/v1/document-types/'+type['id'], json={'label':'must rollback','fields':[{'field_definition_id':'field-b','required_for_filing':False}]}, headers=headers).status_code == 422
    current = client.get('/api/v1/document-types', params={'space_id':a}).json()[0]
    assert current['label'] == '合同' and current['fields'] == [field]
    assert client.patch('/api/v1/document-types/'+type['id'], json={'fields':[field,field]}, headers=headers).status_code == 422
    with connect(settings.database) as db:
        db.execute("INSERT INTO documents(id,space_id,document_type_id,title,imported_at,created_at,updated_at) VALUES ('doc',?,?,'Document','now','now','now')", (a,type['id']))
        db.execute("INSERT INTO metadata_values(id,document_id,space_id,field_definition_id,value_integer,origin,updated_at) VALUES ('value','doc',?,'field-a',12,'manual','now')", (a,))
        db.commit()
    result = client.patch('/api/v1/document-types/'+type['id'], json={'is_active':False,'fields':[]}, headers=headers)
    assert result.status_code == 200 and result.json()['is_active'] is False
    with connect(settings.database) as db:
        assert db.execute("SELECT value_integer FROM metadata_values WHERE id='value'").fetchone() == (12,)
        assert db.execute("SELECT document_type_id FROM documents WHERE id='doc'").fetchone() == (type['id'],)


def test_concurrent_duplicate_and_cycle_requests(catalog):
    client, settings, app, headers, csrf = catalog
    a = space(client, headers)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: client.post('/api/v1/tags', json={'space_id':a,'name':'same'}, headers=headers).status_code, range(2)))
    assert sorted(results) == [201,409]
    first, second = folder(client, headers, a, 'first'), folder(client, headers, a, 'second')
    def move(pair):
        return client.patch('/api/v1/folders/'+pair[0]['id'], json={'parent_id':pair[1]['id']}, headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(move, [(first,second),(second,first)]))
    assert sorted(results) == [200,409]
    with connect(settings.database) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_invalid_and_unknown_resources_fail_without_side_effects(catalog):
    client, settings, app, headers, csrf = catalog
    a = space(client, headers)
    f = folder(client, headers, a, 'folder')
    for body in ({}, {'name':None}, {'name':' \n '}, {'name':'x'*256}, {'space_id':a}):
        assert client.patch('/api/v1/folders/'+f['id'], json=body, headers=headers).status_code == 422
    for path in ('folders','tags','document-types'):
        assert client.get('/api/v1/'+path, params={'space_id':'missing'}).status_code == 404
    assert client.post('/api/v1/folders', json={'space_id':a,'name':'child','parent_id':'missing'}, headers=headers).status_code == 404
    assert client.patch('/api/v1/folders/missing', json={'name':'new'}, headers=headers).status_code == 404
    assert client.post('/api/v1/document-types', json={'space_id':a,'key':'bad key','label':'x'}, headers=headers).status_code == 422
    assert client.post('/api/v1/document-types', json={'space_id':a,'key':'atomic','label':'x','fields':[{'field_definition_id':'missing','required_for_filing':False}]}, headers=headers).status_code == 404
    assert client.get('/api/v1/document-types', params={'space_id':a}).json() == []
    assert client.get('/api/v1/folders', params={'space_id':a}).json()[0]['name'] == 'folder'


def test_normalized_tag_uniqueness_and_atomic_folder_move(catalog):
    client, settings, app, headers, csrf = catalog
    a, b = space(client, headers), space(client, headers, 'Other')
    first = create(client,'tags',{'space_id':a,'name':'Café'},headers)
    assert client.post('/api/v1/tags',json={'space_id':a,'name':'Cafe\u0301'},headers=headers).status_code == 409
    create(client,'tags',{'space_id':b,'name':'Café'},headers)
    second = create(client,'tags',{'space_id':a,'name':'Other'},headers)
    assert client.patch('/api/v1/tags/'+second['id'],json={'name':'CAFÉ'},headers=headers).status_code == 409
    parent = folder(client, headers, a, 'parent')
    original = folder(client, headers, a, 'original')
    folder(client, headers, a, 'collision', parent['id'])
    assert client.patch('/api/v1/folders/'+original['id'],json={'name':'COLLISION','parent_id':parent['id']},headers=headers).status_code == 409
    with connect(settings.database) as db:
        assert db.execute('SELECT name,parent_id FROM folders WHERE id=?',(original['id'],)).fetchone() == ('original',None)
    assert client.patch('/api/v1/tags/'+first['id'],json={'space_id':b},headers=headers).status_code == 422
