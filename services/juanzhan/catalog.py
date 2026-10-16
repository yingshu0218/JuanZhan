"""Space-scoped catalog definitions. No file paths or Document lifecycle APIs."""
import json
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import authorize, fail
from .database import connect

ID = Annotated[str, Field(min_length=1, max_length=255)]
Name = Annotated[str, Field(min_length=1, max_length=255)]
TypeKey = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]*$', max_length=255)]


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def normalize(value):
    return unicodedata.normalize('NFKC', value).casefold()


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('name', 'label', check_fields=False)
    @classmethod
    def clean_name(cls, value):
        if value is None:
            raise ValueError('Name cannot be null')
        value = unicodedata.normalize('NFC', value.strip())
        if not value or any(unicodedata.category(c) == 'Cc' for c in value):
            raise ValueError('Name must contain visible text without control characters')
        return value


class Patch(Input):
    @model_validator(mode='after')
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError('Patch must contain a supported field')
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in ('parent_id', 'color'):
                raise ValueError('Field cannot be null')
        return self


class SpaceCreate(Input):
    name: Name


class FolderCreate(Input):
    space_id: ID
    parent_id: ID | None = None
    name: Name


class FolderPatch(Patch):
    name: Name | None = None
    parent_id: ID | None = None


class FolderDelete(Input):
    mode: Literal['only_if_empty', 'move_contents_to_parent', 'trash_contents']


class TagCreate(Input):
    space_id: ID
    name: Name
    color: Annotated[str, Field(max_length=100)] | None = None
    description: Annotated[str, Field(max_length=4096)] = ''


class TagPatch(Patch):
    name: Name | None = None
    color: Annotated[str, Field(max_length=100)] | None = None
    description: Annotated[str, Field(max_length=4096)] | None = None


class TypeField(Input):
    field_definition_id: ID
    required_for_filing: bool = Field(strict=True)
    display_order: int = Field(default=0, strict=True, ge=-2147483648, le=2147483647)


class TypeCreate(Input):
    space_id: ID
    key: TypeKey
    label: Name
    fields: list[TypeField] = Field(default_factory=list, max_length=1000)


class TypePatch(Patch):
    label: Name | None = None
    is_active: bool | None = Field(default=None, strict=True)
    fields: list[TypeField] | None = Field(default=None, max_length=1000)


@contextmanager
def transaction(settings, request=None):
    with connect(settings.database) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE' if request is not None else 'BEGIN')
        try:
            if request is not None:
                # Revalidate under the same writer lock used by credential reset/revoke.
                authorize(settings, request)
            yield db
            db.commit()
        except sqlite3.IntegrityError as exc:
            if str(exc) == 'folder cycle':
                fail(409, 'FOLDER_CYCLE', 'Folder cannot be its own ancestor')
            fail(409, 'CATALOG_CONFLICT', 'Name, key or referenced resource conflicts')


def required(db, table, id):
    # Table names are internal constants, never request values.
    row = db.execute(f'SELECT * FROM {table} WHERE id=?', (id,)).fetchone()
    if row is None:
        fail(404, 'NOT_FOUND', 'Catalog resource not found')
    return row


def same_space(db, table, id, space):
    row = required(db, table, id)
    if row['space_id'] != space:
        fail(422, 'CROSS_SPACE_REFERENCE', 'Referenced resource belongs to another space')
    return row


def scope(db, space_id):
    if space_id is not None:
        required(db, 'spaces', space_id)


def folder_json(row):
    return {key: row[key] for key in ('id', 'space_id', 'parent_id', 'name', 'name_norm')}


def tag_json(row):
    return {key: row[key] for key in ('id', 'space_id', 'name', 'color', 'description')}


def type_json(db, row):
    fields = db.execute('SELECT field_definition_id,required_for_filing,display_order '
                        'FROM document_type_fields WHERE document_type_id=? '
                        'ORDER BY display_order,field_definition_id', (row['id'],)).fetchall()
    return {'id': row['id'], 'space_id': row['space_id'], 'key': row['type_key'],
            'label': row['label'], 'is_active': bool(row['is_active']),
            'fields': [{'field_definition_id':f[0], 'required_for_filing':bool(f[1]),
                        'display_order':f[2]} for f in fields]}


def replace_fields(db, type_id, space_id, fields):
    ids = [field.field_definition_id for field in fields]
    if len(set(ids)) != len(ids):
        fail(422, 'DUPLICATE_FIELD', 'Field definitions must not repeat')
    for id in ids:
        same_space(db, 'field_definitions', id, space_id)
    db.execute('DELETE FROM document_type_fields WHERE document_type_id=?', (type_id,))
    db.executemany('INSERT INTO document_type_fields VALUES (?,?,?,?,?)',
                   [(space_id,type_id,f.field_definition_id,int(f.required_for_filing),f.display_order)
                    for f in fields])


def router(settings):
    routes = APIRouter(prefix='/api/v1')

    @routes.get('/spaces')
    def spaces():
        with transaction(settings) as db:
            return [dict(row) for row in db.execute('SELECT id,name,created_at FROM spaces ORDER BY created_at,id')]

    @routes.post('/spaces', status_code=201)
    def create_space(body: SpaceCreate, request: Request):
        id, timestamp = uuid.uuid4().hex, now()
        with transaction(settings, request) as db:
            db.execute('INSERT INTO spaces VALUES (?,?,?,?)', (id,body.name,timestamp,timestamp))
            return {'id':id,'name':body.name,'created_at':timestamp}

    @routes.get('/folders')
    def folders(space_id: ID | None = None, parent_id: ID | None = None):
        with transaction(settings) as db:
            scope(db, space_id)
            if parent_id is not None:
                parent = required(db, 'folders', parent_id)
                if space_id is not None and parent['space_id'] != space_id:
                    fail(422, 'CROSS_SPACE_REFERENCE', 'Parent belongs to another space')
            rows = db.execute('SELECT * FROM folders WHERE (? IS NULL OR space_id=?) '
                              'AND (? IS NULL OR parent_id=?) ORDER BY space_id,name_norm,id',
                              (space_id,space_id,parent_id,parent_id))
            return [folder_json(row) for row in rows]

    @routes.post('/folders', status_code=201)
    def create_folder(body: FolderCreate, request: Request):
        id, timestamp = uuid.uuid4().hex, now()
        with transaction(settings, request) as db:
            required(db, 'spaces', body.space_id)
            if body.parent_id is not None:
                same_space(db, 'folders', body.parent_id, body.space_id)
            db.execute('INSERT INTO folders VALUES (?,?,?,?,?,?,?)',
                       (id,body.space_id,body.parent_id,body.name,normalize(body.name),timestamp,timestamp))
            return folder_json(required(db, 'folders', id))

    @routes.patch('/folders/{id}')
    def patch_folder(id: str, body: FolderPatch, request: Request):
        with transaction(settings, request) as db:
            old = required(db, 'folders', id)
            parent = body.parent_id if 'parent_id' in body.model_fields_set else old['parent_id']
            if parent is not None:
                same_space(db, 'folders', parent, old['space_id'])
            name = body.name if 'name' in body.model_fields_set else old['name']
            db.execute('UPDATE folders SET parent_id=?,name=?,name_norm=?,updated_at=? WHERE id=?',
                       (parent,name,normalize(name),now(),id))
            return folder_json(required(db, 'folders', id))

    @routes.post('/folders/{id}/delete', status_code=204)
    def delete_folder(id: str, body: FolderDelete, request: Request):
        with transaction(settings, request) as db:
            required(db, 'folders', id)
            if body.mode != 'only_if_empty':
                fail(501, 'NOT_IMPLEMENTED', 'Document move/trash deletion modes await document transactions')
            if (db.execute('SELECT 1 FROM folders WHERE parent_id=? LIMIT 1', (id,)).fetchone()
                    or db.execute('SELECT 1 FROM documents WHERE folder_id=? LIMIT 1', (id,)).fetchone()
                    or db.execute('SELECT 1 FROM sources WHERE initial_target_folder_id=? '
                                  'OR new_file_target_folder_id=? LIMIT 1', (id,id)).fetchone()):
                fail(409, 'FOLDER_NOT_EMPTY', 'Folder has children, documents or source references')
            db.execute('DELETE FROM folders WHERE id=?', (id,))

    @routes.get('/tags')
    def tags(space_id: ID | None = None):
        with transaction(settings) as db:
            scope(db, space_id)
            return [tag_json(row) for row in db.execute(
                'SELECT * FROM tags WHERE (? IS NULL OR space_id=?) ORDER BY space_id,name_norm,id',
                (space_id,space_id))]

    @routes.post('/tags', status_code=201)
    def create_tag(body: TagCreate, request: Request):
        id = uuid.uuid4().hex
        with transaction(settings, request) as db:
            required(db, 'spaces', body.space_id)
            db.execute('INSERT INTO tags VALUES (?,?,?,?,?,?,?)',
                       (id,body.space_id,body.name,normalize(body.name),body.color,body.description,now()))
            return tag_json(required(db, 'tags', id))

    @routes.patch('/tags/{id}')
    def patch_tag(id: str, body: TagPatch, request: Request):
        with transaction(settings, request) as db:
            old = required(db, 'tags', id)
            values = body.model_dump(exclude_unset=True)
            name = values.get('name', old['name'])
            db.execute('UPDATE tags SET name=?,name_norm=?,color=?,description=? WHERE id=?',
                       (name,normalize(name),values.get('color',old['color']),
                        values.get('description',old['description']),id))
            return tag_json(required(db, 'tags', id))

    @routes.delete('/tags/{id}', status_code=204)
    def delete_tag(id: str, request: Request):
        with transaction(settings, request) as db:
            required(db, 'tags', id)
            documents = db.execute('SELECT document_id FROM document_tags WHERE tag_id=? ORDER BY document_id', (id,)).fetchall()
            timestamp = now()
            # Removing a binding changes document facts: invalidate optimistic versions and audit.
            for row in documents:
                db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?', (timestamp,row[0]))
                db.execute('INSERT INTO document_events(id,document_id,event_type,before_json,after_json,actor,created_at) '
                           'VALUES (?,?,?,?,?,?,?)', (uuid.uuid4().hex,row[0],'tag_deleted',
                            json.dumps({'tag_id':id}),json.dumps({'tag_id':None}),'admin',timestamp))
            db.execute('DELETE FROM document_tags WHERE tag_id=?', (id,))
            db.execute('DELETE FROM tags WHERE id=?', (id,))

    @routes.get('/document-types')
    def types(space_id: ID | None = None):
        with transaction(settings) as db:
            scope(db, space_id)
            rows = db.execute('SELECT * FROM document_types WHERE (? IS NULL OR space_id=?) '
                              'ORDER BY space_id,type_key,id', (space_id,space_id)).fetchall()
            return [type_json(db, row) for row in rows]

    @routes.post('/document-types', status_code=201)
    def create_type(body: TypeCreate, request: Request):
        id = uuid.uuid4().hex
        with transaction(settings, request) as db:
            required(db, 'spaces', body.space_id)
            db.execute('INSERT INTO document_types VALUES (?,?,?,?,?,?)',
                       (id,body.space_id,body.key,body.label,1,now()))
            replace_fields(db, id, body.space_id, body.fields)
            return type_json(db, required(db, 'document_types', id))

    @routes.patch('/document-types/{id}')
    def patch_type(id: str, body: TypePatch, request: Request):
        with transaction(settings, request) as db:
            old = required(db, 'document_types', id)
            values = body.model_dump(exclude_unset=True)
            db.execute('UPDATE document_types SET label=?,is_active=? WHERE id=?',
                       (values.get('label',old['label']),int(values.get('is_active',old['is_active'])),id))
            if 'fields' in body.model_fields_set:
                replace_fields(db, id, old['space_id'], body.fields)
            return type_json(db, required(db, 'document_types', id))

    return routes
