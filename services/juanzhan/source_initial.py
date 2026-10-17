"""First import: read/hash outside write locks, atomically publish metadata only."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
import tempfile
import unicodedata
import uuid

from .catalog import normalize, same_space
from .database import connect
from .document_events import record_event, utc_now
from .document_records import snapshot
from .jobs import JobQueue, JobSpec
from .source_paths import SourceMounts, SourcePathError
from .source_scans import inventory
from .uploads import sniff

MAX_MANIFEST_BYTES = 64 * 1024 * 1024


def initial(settings, job):
    with connect(settings.database) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT s.* FROM sources s JOIN scan_runs r ON r.source_id=s.id WHERE r.id=? AND r.mode='initial'",
                         (job['target_id'],)).fetchone()
        source = dict(row) if row else None
    if source is None or source['status'] == 'disabled' or source['kind'] != 'external' or json.loads(job['payload_json']) != {}:
        raise SourcePathError('INVALID_SOURCE_SCAN')
    if source['initial_import_completed_at'] is not None:
        raise SourcePathError('SOURCE_INITIAL_ALREADY_COMPLETED')
    counts = {'source_id': source['id'], 'mode': 'initial', 'imported_files': 0, 'created_folders': 0,
              'ignored_files': 0, 'imported_bytes': 0}
    with tempfile.TemporaryFile(mode='w+t', encoding='utf-8', dir=settings.data_dir) as manifest:
        source['_root_digest'] = prepare(settings,source,manifest,counts,
            include_dirs=source['initial_import_policy']=='tree')
        manifest.seek(0)
        JobQueue(settings).complete(job['id'], job['lease_token'],
            lambda db, owned: publish(db, owned, source, manifest, counts, settings))


def prepare(settings, source, manifest, counts, *, include_dirs=False,
            file_counter='imported_files', bytes_counter='imported_bytes'):
    """Shared bounded observation spool; all original bytes stay on the source."""
    mounts = SourceMounts(settings.source_mounts)
    root_digest = mounts.digest(source['root_ref'])
    size = 0
    with closing(inventory(mounts, source['root_ref'], counts)) as records:
        for kind, path, stream, info in records:
            item = {'kind': kind, 'path': path}
            if kind == 'file':
                checksum = hashlib.sha256()
                received = 0
                while chunk := stream.read(min(65536, info.st_size-received+1)):
                    received += len(chunk)
                    if received > info.st_size:
                        raise SourcePathError('SOURCE_CHANGED')
                    checksum.update(chunk)
                if received != info.st_size:
                    raise SourcePathError('SOURCE_CHANGED')
                mime = sniff(stream, os.path.basename(path))
                try:
                    modified = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat().replace('+00:00', 'Z')
                except (ValueError, OverflowError, OSError):
                    modified = None
                item.update(sha256=checksum.hexdigest(), size_bytes=received, mime_type=mime,
                            mtime_ns=info.st_mtime_ns, file_modified_at=modified,
                            identity_hint=f'{info.st_dev}:{info.st_ino}')
                counts[file_counter] += 1
                counts[bytes_counter] += received
            elif not include_dirs:
                continue
            line = json.dumps(item, ensure_ascii=False, separators=(',', ':'))+'\n'
            size += len(line.encode('utf-8'))
            if size > MAX_MANIFEST_BYTES:
                raise SourcePathError('SOURCE_MANIFEST_LIMIT')
            manifest.write(line)
    if mounts.digest(source['root_ref']) != root_digest:
        raise SourcePathError('SOURCE_ROOT_CHANGED')
    return root_digest


def publish(db, job, observed, manifest, counts, settings):
    db.row_factory = sqlite3.Row
    source = db.execute('SELECT * FROM sources WHERE id=?', (observed['id'],)).fetchone()
    keys = ('space_id', 'root_ref', 'initial_import_policy', 'initial_target_folder_id', 'initial_triage_status')
    if source is None or source['status'] == 'disabled' or any(source[k] != observed[k] for k in keys):
        raise SourcePathError('SOURCE_CHANGED')
    if source['initial_import_completed_at'] is not None:
        raise SourcePathError('SOURCE_INITIAL_ALREADY_COMPLETED')
    if db.execute('SELECT 1 FROM source_entries WHERE source_id=? LIMIT 1', (source['id'],)).fetchone():
        raise SourcePathError('SOURCE_INITIAL_STATE_CONFLICT')
    target = source['initial_target_folder_id']
    if target is not None:
        same_space(db, 'folders', target, source['space_id'])
    # Temporary mapping disappears with this connection/rollback. No durable folder mirror.
    db.execute('CREATE TEMP TABLE initial_folder_map(path TEXT PRIMARY KEY,folder_id TEXT)')
    db.execute('INSERT INTO initial_folder_map VALUES (?,?)', ('', target))
    timestamp = utc_now()
    for line in manifest:
        item = json.loads(line)
        path = item['path']
        parent_path, _, name = path.rpartition('/')
        if source['initial_import_policy'] == 'tree':
            mapped = db.execute('SELECT folder_id FROM initial_folder_map WHERE path=?', (parent_path,)).fetchone()
            if mapped is None:
                raise SourcePathError('SOURCE_FOLDER_CONFLICT')
            folder_id = mapped[0]
        else:
            folder_id = target
        if item['kind'] == 'directory':
            label = unicodedata.normalize('NFC', name.strip())
            name_norm = normalize(label)
            if not label or db.execute('SELECT 1 FROM folders WHERE space_id=? AND parent_id IS ? AND name_norm=?',
                (source['space_id'], folder_id, name_norm)).fetchone():
                raise SourcePathError('SOURCE_FOLDER_CONFLICT')
            child_id = uuid.uuid4().hex
            db.execute('INSERT INTO folders VALUES (?,?,?,?,?,?,?)',
                       (child_id, source['space_id'], folder_id, label, name_norm, timestamp, timestamp))
            db.execute('INSERT INTO initial_folder_map VALUES (?,?)', (path, child_id))
            counts['created_folders'] += 1
            continue
        register_external(db,job,source,item,folder_id,source['initial_triage_status'],settings,timestamp)
    root_digest = observed.get('_root_digest') or SourceMounts(settings.source_mounts).digest(source['root_ref'])
    db.execute('INSERT INTO source_root_baselines VALUES (?,?)', (source['id'],root_digest))
    return counts



def register_external(db, job, source, item, folder_id, triage, settings, timestamp):
    path = item['path']
    name = path.rsplit('/',1)[-1]
    document_id, entry_id, revision_id = (uuid.uuid4().hex for _ in range(3))
    db.execute('INSERT INTO documents(id,space_id,folder_id,title,triage_status,imported_at,created_at,updated_at) '
               'VALUES (?,?,?,?,?,?,?,?)',
               (document_id, source['space_id'], folder_id, unicodedata.normalize('NFC', name),
                triage, timestamp, timestamp, timestamp))
    db.execute('INSERT INTO source_entries(id,source_id,space_id,document_id,relative_path_norm,relative_path_display,'
               'file_identity_hint,size_bytes,mtime_ns,sha256,status,last_seen_scan_id,created_at,updated_at) '
               "VALUES (?,?,?,?,?,?,?,?,?,?,'available',?,?,?)",
               (entry_id, source['id'], source['space_id'], document_id, path, path, item['identity_hint'],
                item['size_bytes'], item['mtime_ns'], item['sha256'], job['target_id'], timestamp, timestamp))
    db.execute('INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,source_entry_id,source_path_at_capture,'
               'sha256,size_bytes,original_filename,mime_type,file_modified_at,created_at) '
               "VALUES (?,?,1,'external',?,?,?,?,?,?,?,?)",
               (revision_id, document_id, entry_id, path, item['sha256'], item['size_bytes'], name,
                item['mime_type'], item['file_modified_at'], timestamp))
    db.execute('UPDATE documents SET current_revision_id=? WHERE id=?', (revision_id, document_id))
    record_event(db, document_id, 'document_created', None, snapshot(db, document_id),
                 timestamp=timestamp, actor='source_scan')
    JobQueue(settings).enqueue(JobSpec(kind='parse', target_type='document', target_id=document_id,
        idempotency_key='parse:'+revision_id, payload={'revision_id': revision_id}), db=db)
    return document_id, entry_id
