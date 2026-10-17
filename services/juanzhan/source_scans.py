"""Bounded source traversal and preview; never mutates external files."""
import json
import os
import stat

from .database import connect
from .source_paths import DIR_FLAGS, SourceMounts, SourcePathError, components, readonly

EXTENSIONS = {'.pdf', '.docx', '.md', '.markdown', '.html', '.htm', '.txt', '.epub'}
MAX_ENTRIES = 100000
MAX_DEPTH = 64


def job_state(db, job, status, timestamp, *, result=None, error=None):
    modes = {('scan_preview', 'source_preview'): 'preview', ('scan', 'source_initial'): 'initial', ('scan', 'source_incremental'): 'incremental'}
    mode = modes.get((job['kind'], job['target_type']))
    if mode is None:
        return
    run = db.execute('SELECT source_id FROM scan_runs WHERE id=? AND mode=?', (job['target_id'], mode)).fetchone()
    if run is None:
        # A removed/legacy target must fail in its handler, never block queue claim.
        return
    terminal = status in ('completed', 'failed')
    db.execute('UPDATE scan_runs SET status=?,started_at=CASE WHEN ?=\'running\' THEN COALESCE(started_at,?) ELSE started_at END,'
               'finished_at=?,result_json=?,error_json=? WHERE id=?',
               (status, status, timestamp, timestamp if terminal else None, result, error, job['target_id']))
    code = json.loads(error)['code'] if error else None
    health = 'ready' if status == 'completed' else ('offline' if code == 'SOURCE_OFFLINE' else ('error' if terminal else 'scanning'))
    db.execute("UPDATE sources SET status=?,updated_at=? WHERE id=? AND status!='disabled'", (health, timestamp, run[0]))
    if mode == 'incremental' and status == 'completed':
        db.execute('UPDATE sources SET last_successful_scan_at=? WHERE id=?', (timestamp,run[0]))
    if mode in ('initial','incremental') and error is not None:
        db.execute('DELETE FROM source_missing_observations WHERE source_entry_id IN (SELECT id FROM source_entries WHERE source_id=?)', (run[0],))
    if mode == 'initial' and status == 'completed':
        db.execute('UPDATE sources SET initial_import_completed_at=?,last_successful_scan_at=? WHERE id=?',
                   (timestamp, timestamp, run[0]))


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def inventory(mounts, alias, counts, *, max_entries=MAX_ENTRIES, max_depth=MAX_DEPTH, excluded=None):
    """Yield directory records and temporarily open regular candidates, bounded by depth.

    Consumers must exhaust or explicitly close the generator. Files remain open only
    across their yield. Directory/file changes invalidate the whole observation.
    """
    identity = mounts.identity(alias)
    visited = 0

    def walk(fd, prefix, depth):
        nonlocal visited
        if depth > max_depth:
            raise SourcePathError('SOURCE_PREVIEW_LIMIT')
        readonly(fd)
        before = fingerprint(os.fstat(fd))
        with os.scandir(fd) as entries:
            for entry in entries:
                visited += 1
                if visited > max_entries:
                    raise SourcePathError('SOURCE_PREVIEW_LIMIT')
                path = '/'.join((*prefix, entry.name))
                try:
                    components(path)
                except SourcePathError:
                    counts['ignored_files'] += 1
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, DIR_FLAGS, dir_fd=fd)
                    try:
                        readonly(child)
                        actual = os.fstat(child)
                        if fingerprint(actual) != fingerprint(info):
                            raise SourcePathError('SOURCE_CHANGED')
                        yield ('directory', path, None, actual)
                        yield from walk(child, (*prefix, entry.name), depth+1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    if excluded is not None and excluded(path):
                        counts['ignored_files'] += 1
                        continue
                    extension = os.path.splitext(entry.name)[1].lower()
                    if extension not in EXTENSIONS:
                        counts['ignored_files'] += 1
                        continue
                    with mounts.open(alias, path) as stream:
                        actual = os.fstat(stream.fileno())
                        if fingerprint(actual) != fingerprint(info):
                            raise SourcePathError('SOURCE_CHANGED')
                        yield ('file', path, stream, actual)
                        if fingerprint(os.fstat(stream.fileno())) != fingerprint(actual):
                            raise SourcePathError('SOURCE_CHANGED')
                else:
                    counts['ignored_files'] += 1
        if fingerprint(os.fstat(fd)) != before:
            raise SourcePathError('SOURCE_CHANGED')

    try:
        with mounts.root(alias) as root:
            yield from walk(root, (), 0)
        if mounts.identity(alias) != identity:
            raise SourcePathError('SOURCE_CHANGED')
    except FileNotFoundError:
        raise SourcePathError('SOURCE_CHANGED') from None
    except PermissionError:
        raise SourcePathError('SOURCE_UNREADABLE') from None
    except OSError:
        raise SourcePathError('SOURCE_UNSAFE_OR_UNAVAILABLE') from None


def preview(settings, job, *, max_entries=MAX_ENTRIES, max_depth=MAX_DEPTH):
    with connect(settings.database) as db:
        source = db.execute("SELECT s.id,s.root_ref,s.status FROM sources s JOIN scan_runs r ON r.source_id=s.id "
                            "WHERE r.id=? AND r.mode='preview'", (job['target_id'],)).fetchone()
    if source is None or source[2] == 'disabled' or json.loads(job['payload_json']) != {}:
        raise SourcePathError('INVALID_SOURCE_PREVIEW')
    source_id, alias, _ = source
    result = {'source_id': source_id, 'estimated_files': 0, 'estimated_bytes': 0,
              'ignored_files': 0, 'by_extension': {}, 'warnings': ['METADATA_ESTIMATE_NOT_SNAPSHOT']}
    from .exclusions import epoch, blocked
    with connect(settings.database) as db:
        db.execute('BEGIN')
        observed_epoch=epoch(db,source_id)
        for kind, path, stream, info in inventory(SourceMounts(settings.source_mounts), alias, result,
                                                max_entries=max_entries, max_depth=max_depth, excluded=lambda path: blocked(db,source_id,path)):
            if kind == 'file':
                extension = os.path.splitext(path)[1].lower()
                result['estimated_files'] += 1
                result['estimated_bytes'] += info.st_size
                result['by_extension'][extension] = result['by_extension'].get(extension, 0)+1
    with connect(settings.database) as db:
        if epoch(db,source_id)!=observed_epoch:raise SourcePathError('SOURCE_CHANGED')
    if result['ignored_files']:
        result['warnings'].append('IGNORED_UNSUPPORTED_UNSAFE_OR_INVALID_ENTRIES')
    return result
