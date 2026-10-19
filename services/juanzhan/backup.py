"""Administrator-only directory bundles; no HTTP paths, archives or in-place restore.

Use trusted private local directories. Bundles include credentials and require the same
application version; checksums detect damage, not a malicious replacement of a bundle.
External source files and mount configuration are deliberately outside this backup.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3

from .config import Settings
from .database import connect, migrate
from .storage import ManagedStore, StorageError, parse_key
from .jobs import JobQueue, row


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def digest(path):
    with path.open('rb') as file: return hashlib.file_digest(file,'sha256').hexdigest()


def references(db):
    return sorted(set([('managed/'+r[0]) for r in db.execute(
        'SELECT DISTINCT o.storage_key FROM managed_objects o JOIN file_revisions r ON r.managed_object_id=o.id')]
        + [('derived/'+r[0]) for r in db.execute('SELECT DISTINCT storage_key FROM derived_assets')]))


def safe_name(name):
    if name=='database/archive.sqlite3': return
    if not isinstance(name,str) or '/' not in name: raise ValueError('Invalid bundle member')
    store,key=name.split('/',1)
    if store not in ('managed','derived'): raise ValueError('Invalid bundle member')
    parse_key(key)


def copy_object(root, name, target, *, max_bytes=None):
    store,key=name.split('/',1)
    with ManagedStore(root/store).open(key) as source, target.open('xb') as output:
        if max_bytes is not None and os.fstat(source.fileno()).st_size>max_bytes:
            raise ValueError('Backup byte limit exceeded')
        shutil.copyfileobj(source,output,65536)
        output.flush();os.fsync(output.fileno())
    os.chmod(target,0o440)


def create(settings, destination, *, max_bytes=None, max_files=None):
    destination=Path(destination).resolve()
    if destination.is_relative_to(settings.data_dir.resolve()): raise ValueError('Backup must be outside live data')
    destination.mkdir(mode=0o700)
    try:
        # Store locks exclude object publication/GC while SQLite backup supplies
        # one coherent DB snapshot. Copy references from that snapshot, not the live
        # DB. Business writes and worker lease heartbeats remain available.
        with ExitStack() as stack:
            for name in ('managed','derived'):
                stack.enter_context(ManagedStore(settings.data_dir/name).locked(exclusive=True))
            read=stack.enter_context(connect(settings.database))
            (destination/'database').mkdir(mode=0o700)
            target=destination/'database/archive.sqlite3'
            snapshot=stack.enter_context(sqlite3.connect(target))
            read.backup(snapshot)
            names=['database/archive.sqlite3']+references(snapshot)
            if max_files is not None and len(names)>max_files:raise ValueError('Backup file count exceeded')
            entries=[];total=0
            for name in names:
                safe_name(name);target=destination/name
                if name!='database/archive.sqlite3':
                    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    copy_object(settings.data_dir,name,target,max_bytes=None if max_bytes is None else max_bytes-total)
                total+=target.stat().st_size
                if max_bytes is not None and total>max_bytes:raise ValueError('Backup byte limit exceeded')
                entries.append({'name':name,'size':target.stat().st_size,'sha256':digest(target)})
            manifest={'format':'juanzhan-backup-1','external_sources_included':False,'files':entries}
            text=json.dumps(manifest,ensure_ascii=False,sort_keys=True)
            if len(text.encode())>16*1024*1024: raise ValueError('Backup manifest limit exceeded')
            with (destination/'manifest.json').open('x') as file:
                file.write(text);file.flush();os.fsync(file.fileno())
            # Completeness marker is written last. Partial bundles are never valid.
            # Persist directory entries before advertising completeness.
            for directory, _, _ in os.walk(destination,topdown=False):
                sync_directory(directory)
            with (destination/'COMPLETE').open('x') as file:
                file.write(hashlib.sha256(text.encode()).hexdigest());file.flush();os.fsync(file.fileno())
            sync_directory(destination)
            os.chmod(destination/'database/archive.sqlite3',0o600)
        return {'files':len(entries),'external_sources_included':False}
    except BaseException:
        shutil.rmtree(destination)
        raise


def regular(root,name):
    path=root
    for part in name.split('/'):
        path=path/part
        if path.is_symlink(): raise ValueError('Bundle symlinks forbidden')
    if not path.is_file(): raise ValueError('Bundle member missing')
    return path


def restore(bundle, destination):
    bundle=Path(bundle).absolute();destination=Path(destination).resolve()
    if destination==bundle or destination.is_relative_to(bundle): raise ValueError('Separate restore target required')
    if bundle.is_symlink(): raise ValueError('Bundle symlinks forbidden')
    manifest_path=regular(bundle,'manifest.json')
    if manifest_path.stat().st_size>16*1024*1024: raise ValueError('Backup manifest limit exceeded')
    raw=manifest_path.read_bytes()
    if regular(bundle,'COMPLETE').read_text()!=hashlib.sha256(raw).hexdigest(): raise ValueError('Incomplete or damaged backup')
    manifest=json.loads(raw)
    if manifest.get('format')!='juanzhan-backup-1' or manifest.get('external_sources_included') is not False:
        raise ValueError('Unsupported backup format')
    entries=manifest['files'];names=set()
    if not isinstance(entries,list): raise ValueError('Invalid bundle manifest')
    for entry in entries:
        name=entry['name'];safe_name(name)
        if type(entry.get('size')) is not int or entry['size']<0 or not re.fullmatch('[0-9a-f]{64}',entry.get('sha256','')):
            raise ValueError('Invalid bundle member identity')
        if name in names: raise ValueError('Duplicate bundle member')
        names.add(name)
    if 'database/archive.sqlite3' not in names: raise ValueError('Backup database missing')
    destination.mkdir(mode=0o700)  # Refuse even an existing empty directory.
    try:
        with (destination/'RESTORE_IN_PROGRESS').open('x') as marker:
            marker.write('Incomplete restore; do not start Archive here.\n');marker.flush();os.fsync(marker.fileno())
        sync_directory(destination)
        for entry in entries:
            name=entry['name'];source=regular(bundle,name);target=destination/name
            if source.stat().st_size!=entry['size']: raise ValueError('Backup size mismatch')
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with source.open('rb') as src,target.open('xb') as dst:
                shutil.copyfileobj(src,dst,65536);dst.flush();os.fsync(dst.fileno())
            if target.stat().st_size!=entry['size'] or digest(target)!=entry['sha256']:
                raise ValueError('Backup checksum mismatch')
            if name!='database/archive.sqlite3' and parse_key(name.split('/',1)[1])!=(entry['sha256'],entry['size']):
                raise ValueError('Bundle storage identity mismatch')
            os.chmod(target,0o600 if name.startswith('database/') else 0o440)
        settings=Settings(destination,'')
        with connect(settings.database) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Restored database is inconsistent')
            if set(references(db))!=names-{'database/archive.sqlite3'}: raise ValueError('Backup references mismatch')
        # Do not silently migrate an older bundle: require the exact supported migration set.
        from .database import MIGRATIONS
        with connect(settings.database) as db:
            actual=dict(db.execute('SELECT name,sha256 FROM migration_checksums'))
        required={p.name:digest(p) for p in MIGRATIONS.glob('*.sql')}
        if actual!=required: raise ValueError('Backup requires matching application version')
        migrate(settings.database)
        for name in ('managed','derived'): ManagedStore(destination/name).initialize()
        queue=JobQueue(settings)
        with queue.write() as db:
            # Restored sessions/tokens and worker leases must never resume as live identities.
            db.execute('DELETE FROM auth_sessions');db.execute('DELETE FROM auth_api_tokens')
            db.execute('DELETE FROM worker_heartbeats')
            # A recovery is a separate instance: never resume copied backup plans
            # or operations against an unrelated backup storage volume.
            db.execute('UPDATE backup_schedule SET interval_minutes=0,next_due_at=NULL,last_job_id=NULL,version=version+1')
            db.execute("UPDATE jobs SET status='cancelled',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,"
                       "error_json=?,retryable=0 WHERE target_type IN ('system_backup','system_recovery') AND status IN ('queued','running')",
                       (json.dumps({'code':'RESTORED_BACKUP_OPERATION','message':'Backup operation disabled in recovered instance','retryable':False}),))
            for (id,) in db.execute("SELECT id FROM jobs WHERE status='running'").fetchall():
                queue._failure(db,row(db,id),'RESTORED_LEASE','Worker lease invalidated during restore',True,queue.clock())
        for directory, _, _ in os.walk(destination,topdown=False):sync_directory(directory)
        (destination/'RESTORE_IN_PROGRESS').unlink()
        sync_directory(destination)
        return {'files':len(entries),'credentials_revoked':True,'external_sources_included':False}
    except BaseException:
        shutil.rmtree(destination)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('create');backup.add_argument('--output',required=True,type=Path)
    recovery=commands.add_parser('restore');recovery.add_argument('--input',required=True,type=Path);recovery.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        result=create(Settings.from_env(),args.output) if args.command=='create' else restore(args.input,args.output)
    except (OSError,ValueError,KeyError,sqlite3.Error,StorageError,RuntimeError) as exc:
        parser.exit(1,'Backup operation failed ('+type(exc).__name__+'); existing data was not replaced.\n')
    print(json.dumps(result))

if __name__=='__main__': main()
