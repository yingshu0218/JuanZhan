"""Document lifecycle transactions, internal API for later upload/HTTP services.

Managed bytes must already be published. A failed transaction never deletes them.
External source registration, parsing, filing validation and physical purge are later work.
"""
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .auth import authorize, fail
from .catalog import ID, required, same_space
from .database import connect
from .document_events import record_event, utc_now
from .storage import IntegrityError, ManagedStore, StoredObject, parse_key

Version = Annotated[int, Field(strict=True, ge=1, le=9223372036854775806)]
Filename = Annotated[str, Field(min_length=1, max_length=255)]
Mime = Annotated[str, Field(max_length=255, pattern=r'^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$')]


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    original_filename: Filename
    mime_type: Mime

    @field_validator('original_filename')
    @classmethod
    def filename_is_not_a_path(cls, value):
        if value in ('.','..') or '/' in value or '\\' in value or any(unicodedata.category(c)=='Cc' for c in value):
            raise ValueError('Original filename must be a name, not a path')
        return value


class Registration(RevisionInput):
    space_id: ID
    folder_id: ID | None = None
    document_type_id: ID | None = None
    title: Annotated[str, Field(min_length=1, max_length=1000)]
    duplicate_policy: Literal['reject','keep_separate'] = 'reject'
    triage_status: Literal['needs_review','filed'] = 'needs_review'

    @field_validator('title')
    @classmethod
    def title_is_text(cls, value):
        value = unicodedata.normalize('NFC', value.strip())
        if not value or any(unicodedata.category(c)=='Cc' for c in value):
            raise ValueError('Title must contain text without control characters')
        return value


class RevisionChange(RevisionInput):
    expected_document_version: Version


class VersionChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_document_version: Version


def conflict(current):
    raise HTTPException(409, detail={'code':'VERSION_CONFLICT', 'message':'Document was changed; reload before writing',
                                    'current_document_version':current})


def snapshot(db, document_id):
    row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if row is None:
        fail(404, 'NOT_FOUND', 'Document not found')
    result = dict(row)
    result['is_favorite'] = bool(result['is_favorite'])
    result['tag_ids'] = [r[0] for r in db.execute('SELECT tag_id FROM document_tags WHERE document_id=? ORDER BY tag_id', (document_id,))]
    return result


def expected(db, document_id, version):
    result = snapshot(db, document_id)
    if result['document_version'] != version:
        conflict(result['document_version'])
    return result


class DocumentService:
    def __init__(self, settings):
        self.settings = settings
        self.store = ManagedStore(settings.data_dir / 'managed')

    @contextmanager
    def write(self, request=None):
        with connect(self.settings.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            try:
                if request is not None:
                    authorize(self.settings, request)
                yield db
                db.commit()
            except sqlite3.IntegrityError:
                fail(409, 'DOCUMENT_CONFLICT', 'Document relationship or storage metadata conflicts')

    def get_record(self, document_id):
        """Internal facts, not the complete public Document status projection."""
        with connect(self.settings.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            return snapshot(db, document_id)

    def revisions(self, document_id):
        with connect(self.settings.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            snapshot(db, document_id)
            return [dict(row) for row in db.execute(
                'SELECT id,revision_no,storage_kind,original_filename,mime_type,sha256,size_bytes,created_at '
                'FROM file_revisions WHERE document_id=? ORDER BY revision_no', (document_id,))]

    def verify_object(self, obj: StoredObject):
        if parse_key(obj.storage_key) != (obj.sha256,obj.size_bytes):
            raise IntegrityError('Stored object descriptor does not match its key')
        with self.store.open(obj.storage_key):
            pass

    @staticmethod
    def managed_object(db, obj):
        row = db.execute('SELECT id,storage_key FROM managed_objects WHERE sha256=? AND size_bytes=?',
                         (obj.sha256,obj.size_bytes)).fetchone()
        if row is not None:
            if row['storage_key'] != obj.storage_key:
                fail(409, 'STORAGE_METADATA_CONFLICT', 'Managed object key is inconsistent')
            return row['id']
        id = uuid.uuid4().hex
        db.execute('INSERT INTO managed_objects VALUES (?,?,?,?,?)',
                   (id,obj.sha256,obj.size_bytes,obj.storage_key,utc_now()))
        return id

    @staticmethod
    def insert_revision(db, document_id, revision_no, object_id, obj, info):
        id = uuid.uuid4().hex
        db.execute('INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,managed_object_id,sha256,'
                   'size_bytes,original_filename,mime_type,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (id,document_id,revision_no,'managed',object_id,obj.sha256,obj.size_bytes,
                    info.original_filename,info.mime_type,utc_now()))
        return id

    def register_managed(self, obj: StoredObject, info: Registration, *, request=None, after_create=None):
        self.verify_object(obj)
        with self.write(request) as db:
            required(db, 'spaces', info.space_id)
            if info.folder_id is not None:
                same_space(db, 'folders', info.folder_id, info.space_id)
            if info.document_type_id is not None:
                type = same_space(db, 'document_types', info.document_type_id, info.space_id)
                if not type['is_active']:
                    fail(422, 'INACTIVE_DOCUMENT_TYPE', 'Cannot assign a disabled document type')
            if info.triage_status=='filed' and info.document_type_id is not None and db.execute(
                'SELECT 1 FROM document_type_fields WHERE document_type_id=? AND required_for_filing=1 LIMIT 1',
                (info.document_type_id,)).fetchone():
                fail(422,'MISSING_REQUIRED_FIELDS','Required metadata must be supplied before filing')
            duplicates = [row[0] for row in db.execute(
                'SELECT DISTINCT d.id FROM documents d JOIN file_revisions r ON r.document_id=d.id '
                'WHERE d.space_id=? AND r.sha256=? AND r.size_bytes=? ORDER BY d.id',
                (info.space_id,obj.sha256,obj.size_bytes))]
            if duplicates and info.duplicate_policy == 'reject':
                raise HTTPException(409, detail={'code':'DUPLICATE_DETECTED', 'message':'Matching file already registered',
                                                'details':{'duplicates':duplicates}})
            object_id = self.managed_object(db, obj)
            id, timestamp = uuid.uuid4().hex, utc_now()
            db.execute('INSERT INTO documents(id,space_id,folder_id,document_type_id,title,imported_at,created_at,updated_at) '
                       'VALUES (?,?,?,?,?,?,?,?)',
                       (id,info.space_id,info.folder_id,info.document_type_id,info.title,timestamp,timestamp,timestamp))
            revision_id = self.insert_revision(db, id, 1, object_id, obj, info)
            db.execute('UPDATE documents SET current_revision_id=?,triage_status=? WHERE id=?', (revision_id,info.triage_status,id))
            after = snapshot(db, id)
            record_event(db, id, 'document_created', None, after, timestamp=timestamp)
            if after_create is not None:
                after_create(db,after)
            return after

    def append_managed_revision(self, document_id, obj: StoredObject, info: RevisionChange, *, request=None):
        self.verify_object(obj)
        with self.write(request) as db:
            before = expected(db, document_id, info.expected_document_version)
            if before['deleted_at'] is not None:
                fail(409, 'DOCUMENT_TRASHED', 'Restore the document before adding a revision')
            current = db.execute('SELECT storage_kind FROM file_revisions WHERE id=?',
                                 (before['current_revision_id'],)).fetchone()
            if current is not None and current['storage_kind'] != 'managed':
                fail(501, 'NOT_IMPLEMENTED', 'Taking external originals into managed storage is deferred')
            object_id = self.managed_object(db, obj)
            revision_no = db.execute('SELECT COALESCE(MAX(revision_no),0)+1 FROM file_revisions WHERE document_id=?',
                                     (document_id,)).fetchone()[0]
            revision_id = self.insert_revision(db, document_id, revision_no, object_id, obj, info)
            timestamp = utc_now()
            db.execute('UPDATE documents SET current_revision_id=?,document_version=document_version+1,updated_at=? WHERE id=?',
                       (revision_id,timestamp,document_id))
            # Keep current_parse_run_id: its older successful content is still useful.
            after = snapshot(db, document_id)
            record_event(db, document_id, 'revision_added', before, after, timestamp=timestamp)
            return after

    def trash(self, document_id, change: VersionChange, *, request=None):
        with self.write(request) as db:
            before = expected(db, document_id, change.expected_document_version)
            if before['deleted_at'] is not None:
                return before
            timestamp = utc_now()
            db.execute('UPDATE documents SET deleted_at=?,updated_at=?,document_version=document_version+1 WHERE id=?',
                       (timestamp,timestamp,document_id))
            after = snapshot(db, document_id)
            record_event(db, document_id, 'document_trashed', before, after, timestamp=timestamp)
            return after

    def restore(self, document_id, change: VersionChange, *, request=None):
        with self.write(request) as db:
            before = expected(db, document_id, change.expected_document_version)
            if before['deleted_at'] is None:
                return before
            folder_id = before['folder_id']
            if folder_id is not None and db.execute('SELECT 1 FROM folders WHERE id=? AND space_id=?',
                                                   (folder_id,before['space_id'])).fetchone() is None:
                folder_id = None
            timestamp = utc_now()
            db.execute('UPDATE documents SET deleted_at=NULL,folder_id=?,updated_at=?,document_version=document_version+1 WHERE id=?',
                       (folder_id,timestamp,document_id))
            after = snapshot(db, document_id)
            record_event(db, document_id, 'document_restored', before, after, timestamp=timestamp)
            return after
