"""Immutable original copies without relinquishing readonly external associations."""
import sqlite3
import os
from .database import connect
from .document_events import utc_now
from .documents import DocumentService
from .jobs import JobQueue
from .storage import ManagedStore,IntegrityError,SizeLimitExceeded

MAX_BYTES=1024*1024*1024

def stored(db,revision_id):
    return db.execute('SELECT o.storage_key,o.sha256,o.size_bytes FROM revision_snapshots s '
        'JOIN managed_objects o ON o.id=s.managed_object_id WHERE s.revision_id=?',(revision_id,)).fetchone()

def ensure(settings,revision,job):
    """Store lock -> SQL ownership fence, matching GC and managed-upload lock order."""
    if revision['storage_kind']!='external':return
    from .parsing import ParseFailure
    from .source_paths import SourceMounts
    from .maintenance import gc_job
    import time
    if revision['size_bytes']>MAX_BYTES:raise ParseFailure('SNAPSHOT_INPUT_LIMIT')
    with connect(settings.database) as db:
        if stored(db,revision['id']):return
        source=db.execute('SELECT s.root_ref,s.status,e.relative_path_norm FROM source_entries e '
            'JOIN sources s ON s.id=e.source_id WHERE e.id=?',(revision['source_entry_id'],)).fetchone()
    if not source or source[1]=='disabled':raise ParseFailure('SOURCE_OFFLINE',True)
    store=ManagedStore(settings.data_dir/'managed');store.initialize()
    with store.locked():
        # Schedule orphan recovery before publishing any bytes, including failed attempts.
        with JobQueue(settings).write() as db:
            JobQueue(settings)._owned(db,job['id'],job['lease_token'])
            gc_job(db,settings,'gc-after-snapshot:'+job['id'],time.time()+86400)
        with SourceMounts(settings.source_mounts).open(source[0],source[2]) as file:
            before=os.fstat(file.fileno())
            try:obj=store.put(file,max_bytes=MAX_BYTES,expected_size=revision['size_bytes'],expected_sha256=revision['sha256'])
            except (IntegrityError,SizeLimitExceeded):raise ParseFailure('SOURCE_REVISION_CHANGED',True) from None
            after=os.fstat(file.fileno())
            if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise ParseFailure('SOURCE_CHANGED',True)
        with JobQueue(settings).write() as db:
            db.row_factory=sqlite3.Row
            JobQueue(settings)._owned(db,job['id'],job['lease_token'])
            current=db.execute('SELECT * FROM file_revisions WHERE id=?',(revision['id'],)).fetchone()
            if current is None or dict(current)!=dict(revision):raise ParseFailure('SOURCE_REVISION_CHANGED')
            object_id=DocumentService.managed_object(db,obj)
            db.execute('INSERT INTO revision_snapshots VALUES (?,?,?) ON CONFLICT(revision_id) DO NOTHING',
                       (revision['id'],object_id,utc_now()))
            db.execute('DELETE FROM managed_gc_candidates WHERE storage_key=?',(obj.storage_key,))
