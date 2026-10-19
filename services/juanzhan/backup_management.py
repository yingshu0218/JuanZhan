"""Private backup repository, fenced publication and persistent automatic plans."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import stat
import time
import uuid

from . import backup, backup_archive
from .auth import fail
from .database import connect
from .jobs import JobQueue, JobSpec, stamp
from .storage import StorageBusy

logger = logging.getLogger('juanzhan.backup')

TOKEN = re.compile(r'[0-9a-f]{32}', re.ASCII)


class Repository:
    def __init__(self, settings):
        live = settings.data_dir.resolve()
        self.root = (settings.backup_dir or live.with_name(live.name+'-backups')).absolute()
        resolved = self.root.resolve()
        for protected in [live, *(Path(path).resolve() for _, path in settings.source_mounts)]:
            if resolved.is_relative_to(protected) or protected.is_relative_to(resolved):
                raise ValueError('Backup storage must be separate from live/external data')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in [self.root, *(self.root/name for name in ('work','artifacts','incoming','recoveries'))]:
            path.mkdir(exist_ok=True, mode=0o700)
            if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
                raise ValueError('Private ordinary backup directories required')

    @contextmanager
    def locked(self, *, shared=False):
        fd = os.open(self.root/'repository.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
            except BlockingIOError:
                raise StorageBusy('Backup repository busy') from None
            yield
        finally:
            os.close(fd)

    def path(self, area, id, token):
        if area not in ('work','artifacts','incoming','recoveries') or not TOKEN.fullmatch(id) or not TOKEN.fullmatch(token):
            raise ValueError('Invalid internal backup identity')
        suffix = '.zip' if area in ('artifacts','incoming') else ''
        return self.root/area/(id+'-'+token+suffix)


def record(db, id):
    cursor = db.execute('SELECT * FROM backup_records WHERE id=?', (id,))
    value = cursor.fetchone()
    if value is None:
        fail(404,'NOT_FOUND','Backup not found')
    return dict(zip([column[0] for column in cursor.description], value))


def active(db):
    return db.execute("SELECT 1 FROM jobs WHERE target_type IN ('system_backup','system_recovery') AND status IN ('queued','running') LIMIT 1").fetchone() is not None


def enqueue(settings, db, request_id, *, origin='manual', source_token=None):
    key = 'backup-'+origin+':'+request_id
    old = db.execute('SELECT id,target_id FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
    if old:
        return {'backup_id':old[1], 'job_id':old[0], 'status':'accepted'}
    if active(db):
        fail(409,'BACKUP_OPERATION_BUSY','A backup or recovery operation is already active')
    id = uuid.uuid4().hex
    # Upload identity is internal and unrelated to its original browser filename.
    job = JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='system_backup',target_id=id,
        payload={},idempotency_key=key,timeout_seconds=3600),db=db)
    db.execute('INSERT INTO backup_records(id,origin,job_id,created_at,source_token) VALUES (?,?,?,?,?)',
        (id,origin,job['id'],stamp(time.time()),source_token))
    return {'backup_id':id, 'job_id':job['id'], 'status':'accepted'}


def schedule(settings, *, clock=time.time):
    queue = JobQueue(settings)
    now = clock()
    with queue.write() as db:
        plan = db.execute('SELECT interval_minutes,next_due_at FROM backup_schedule WHERE id=1').fetchone()
        if not plan[0] or plan[1] is None or plan[1] > now:
            return []
        # One future deadline, no catch-up storm and no duplicate active operation.
        db.execute('UPDATE backup_schedule SET next_due_at=? WHERE id=1',(now+plan[0]*60,))
        if active(db):
            return []
        result = enqueue(settings, db, uuid.uuid4().hex, origin='automatic')
        db.execute('UPDATE backup_schedule SET last_job_id=? WHERE id=1',(result['job_id'],))
        return [result['job_id']]


def verify_archive(repository, item):
    if item['deleted_at'] or not item['artifact_token']:
        fail(409,'BACKUP_NOT_READY','Backup is not available')
    path = repository.path('artifacts', item['id'], item['artifact_token'])
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW)
    file = os.fdopen(fd,'rb')
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_size != item['archive_bytes']:
            raise ValueError('Backup size mismatch')
        if hashlib.file_digest(file,'sha256').hexdigest() != item['archive_sha256']:
            raise ValueError('Backup checksum mismatch')
        file.seek(0)
        return file
    except BaseException:
        file.close()
        raise


def retire(settings, repository, id, *, request=None):
    """Called under repository exclusive lock. Commit tombstone before unlink."""
    queue = JobQueue(settings)
    with queue.write(request) as db:
        item = record(db,id)
        if db.execute("SELECT 1 FROM recovery_records r JOIN jobs j ON j.id=r.job_id WHERE r.backup_id=? AND j.status IN ('queued','running')",(id,)).fetchone():
            fail(409,'BACKUP_OPERATION_BUSY','Recovery still references this backup')
        job = db.execute('SELECT status FROM jobs WHERE id=?',(item['job_id'],)).fetchone()
        if job[0] in ('queued','running'):
            fail(409,'BACKUP_OPERATION_BUSY','Backup is still being prepared')
        if not item['deleted_at']:
            db.execute('UPDATE backup_records SET deleted_at=? WHERE id=?',(stamp(time.time()),id))
    for area, token in [('artifacts',item['artifact_token']),('incoming',item['source_token'])]:
        if token:
            repository.path(area,id,token).unlink(missing_ok=True)
    backup.sync_directory(repository.root/'artifacts')


def retain(settings, repository, *, clock=time.time):
    with connect(settings.database) as db:
        count, days = db.execute('SELECT keep_count,max_age_days FROM backup_schedule WHERE id=1').fetchone()
        items = db.execute("SELECT id,completed_at FROM backup_records WHERE origin='automatic' AND completed_at IS NOT NULL AND deleted_at IS NULL ORDER BY completed_at DESC,id DESC").fetchall()
    from datetime import datetime
    removed = []
    for index,(id,completed) in enumerate(items):
        # Always preserve the latest successful automatic backup.
        if index and (index>=count or datetime.fromisoformat(completed.replace('Z','+00:00')).timestamp()<clock()-days*86400):
            try:
                retire(settings,repository,id)
                removed.append(id)
            except Exception:
                # A retained backup must not turn a new valid backup into a failure.
                # Later successful backup ticks retry cleanup. Never unlink an active recovery.
                logger.warning('Automatic backup cleanup deferred for %s',id)
                continue
    return removed


def cleanup(settings, repository, *, clock=time.time):
    """Under exclusive repository lock, remove interrupted private work only.

    Final or incoming orphans need a full day of grace. A still-running upload
    can take one hour and does not hold the repository lock.
    """
    removed = 0
    with connect(settings.database) as db:
        owned = {
            'artifacts':{repository.path('artifacts',id,token).name for id,token in db.execute('SELECT id,artifact_token FROM backup_records WHERE deleted_at IS NULL AND artifact_token IS NOT NULL')},
            'incoming':{repository.path('incoming',id,token).name for id,token in db.execute('SELECT id,source_token FROM backup_records WHERE deleted_at IS NULL AND source_token IS NOT NULL')},
            'recoveries':{repository.path('recoveries',id,token).name for id,token in db.execute('SELECT id,artifact_token FROM recovery_records WHERE artifact_token IS NOT NULL')},
            'work':set(),
        }
    for area in ('work','artifacts','incoming','recoveries'):
        for path in (repository.root/area).iterdir():
            # Unknown administrator files and links are never followed or removed.
            pattern=r'[0-9a-f]{32}-[0-9a-f]{32}' + (r'\.zip' if area in ('artifacts','incoming') else '')
            if not re.fullmatch(pattern,path.name) or path.name in owned[area] or path.is_symlink():
                continue
            if area!='work' and path.stat().st_mtime>clock()-86400:
                continue
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
            else:
                continue
            removed += 1
            if removed>=200:
                return removed
    return removed


def execute(settings, job):
    repository = Repository(settings)
    queue = JobQueue(settings)
    id, lease = job['target_id'], job['lease_token']
    token = hashlib.sha256(lease.encode()).hexdigest()[:32]
    # Only a digest of the lease is used in internal artifact names.
    work = repository.path('work',id,token)
    with repository.locked():
        cleanup(settings,repository)
        work.mkdir(mode=0o700)
        try:
            if job['target_type']=='system_backup':
                with connect(settings.database) as db:
                    item = record(db,id)
                bundle = work/'bundle'
                if item['origin']=='imported':
                    source = repository.path('incoming',id,item['source_token'])
                    backup_archive.import_bundle(source,bundle)
                    backup.restore(bundle,work/'verified')
                    shutil.rmtree(work/'verified')
                else:
                    # Budget for both the directory snapshot and its stored ZIP.
                    with connect(settings.database) as db:
                        estimate = db.execute('SELECT COALESCE(SUM(size_bytes),0) FROM managed_objects').fetchone()[0]
                        estimate += db.execute('SELECT COALESCE(SUM(size_bytes),0) FROM derived_assets').fetchone()[0]
                    estimate += settings.database.stat().st_size
                    if estimate>backup_archive.MAX_BYTES or shutil.disk_usage(repository.root).free<estimate*2+backup_archive.RESERVE_BYTES:
                        raise ValueError('Backup exceeds size or available disk budget')
                    backup.create(settings,bundle,max_bytes=backup_archive.MAX_BYTES,max_files=backup_archive.MAX_FILES)
                output = work/'archive.zip'
                identity = backup_archive.export_bundle(bundle,output)
                destination = repository.path('artifacts',id,token)
                def publish(db, owned):
                    # All final paths include this lease token. A failed SQL commit
                    # can leave an orphan, but cannot replace another worker's result.
                    os.rename(output,destination)
                    backup.sync_directory(destination.parent)
                    db.execute('UPDATE backup_records SET artifact_token=?,archive_sha256=?,archive_bytes=?,completed_at=? WHERE id=?',
                        (token,identity['sha256'],identity['bytes'],stamp(time.time()),id))
                queue.complete(job['id'],lease,{'backup_id':id,'files':identity['files'],'external_sources_included':False},effect=publish)
                if item['source_token']:
                    repository.path('incoming',id,item['source_token']).unlink(missing_ok=True)
                if item['origin']=='automatic':
                    retain(settings,repository)
            else:
                with connect(settings.database) as db:
                    cursor = db.execute('SELECT backup_id FROM recovery_records WHERE id=?',(id,))
                    entry = cursor.fetchone()
                    if entry is None:
                        raise ValueError('Recovery not found')
                    item = record(db,entry[0])
                # Hash the same open descriptor used for reading the transport.
                # Private lock prevents deletion/publication throughout recovery.
                with verify_archive(repository,item):
                    backup_archive.import_bundle(repository.path('artifacts',item['id'],item['artifact_token']),work/'bundle')
                backup.restore(work/'bundle',work/'data')
                destination = repository.path('recoveries',id,token)
                def publish(db, owned):
                    os.rename(work/'data',destination)
                    backup.sync_directory(destination.parent)
                    db.execute('UPDATE recovery_records SET artifact_token=?,completed_at=? WHERE id=?',(token,stamp(time.time()),id))
                queue.complete(job['id'],lease,{'recovery_id':id,'credentials_revoked':True,'external_sources_included':False,
                    'activation_required':True,'automatic_backup_disabled':True},effect=publish)
        finally:
            shutil.rmtree(work,ignore_errors=True)
