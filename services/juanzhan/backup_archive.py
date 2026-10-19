"""Bounded ZIP transport for existing verified backup directory bundles.

This module never restores into live data. All paths are internal caller-owned
staging paths. ZIP names are validated individually; extractall is never used.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import zipfile

from .backup import digest, regular, safe_name, sync_directory

MAX_BYTES = 8 * 1024**3
MAX_FILES = 100_000
MANIFEST_BYTES = 16 * 1024**2
RESERVE_BYTES = 128 * 1024**2


def member_name(name):
    if name in ('manifest.json', 'COMPLETE'):
        return
    safe_name(name)


def inventory(bundle, *, max_bytes=MAX_BYTES, max_files=MAX_FILES):
    """Verify completeness, allowlist, lengths and hashes before export/publication."""
    bundle = Path(bundle)
    if bundle.is_symlink():
        raise ValueError('Bundle symlinks forbidden')
    manifest = regular(bundle, 'manifest.json')
    marker = regular(bundle, 'COMPLETE')
    if manifest.stat().st_size > MANIFEST_BYTES or marker.stat().st_size != 64:
        raise ValueError('Invalid backup metadata size')
    raw = manifest.read_bytes()
    if marker.read_bytes() != hashlib.sha256(raw).hexdigest().encode():
        raise ValueError('Incomplete or damaged backup')
    data = json.loads(raw)
    if data.get('format') != 'juanzhan-backup-1' or data.get('external_sources_included') is not False:
        raise ValueError('Unsupported backup format')
    entries = data.get('files')
    if not isinstance(entries, list) or not 1 <= len(entries) <= max_files:
        raise ValueError('Backup file count exceeded')
    names = {'manifest.json', 'COMPLETE'}
    total = len(raw) + 64
    for entry in entries:
        name = entry['name']
        safe_name(name)
        if name in names or type(entry.get('size')) is not int or entry['size'] < 0:
            raise ValueError('Invalid or duplicate backup member')
        names.add(name)
        total += entry['size']
        if total > max_bytes:
            raise ValueError('Backup byte limit exceeded')
        source = regular(bundle, name)
        if source.stat().st_size != entry['size'] or digest(source) != entry.get('sha256'):
            raise ValueError('Backup checksum mismatch')
    if 'database/archive.sqlite3' not in names:
        raise ValueError('Backup database missing')
    return sorted(names), total


def export_bundle(bundle, destination, *, max_bytes=MAX_BYTES, max_files=MAX_FILES):
    names, total = inventory(bundle, max_bytes=max_bytes, max_files=max_files)
    destination = Path(destination)
    # Stored members avoid CPU-heavy compression and permit conservative disk sizing.
    if shutil.disk_usage(destination.parent).free < total + len(names)*1024 + RESERVE_BYTES:
        raise ValueError('Insufficient backup transport space')
    with destination.open('xb') as output:
        try:
            os.chmod(destination, 0o600)
            with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for name in names:
                    source = regular(Path(bundle), name)
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    with source.open('rb') as src, archive.open(info, 'w', force_zip64=True) as dst:
                        shutil.copyfileobj(src, dst, 65536)
            output.flush()
            os.fsync(output.fileno())
            sync_directory(destination.parent)
        except BaseException:
            destination.unlink()
            raise
    return {'files': len(names)-2, 'bytes': destination.stat().st_size, 'sha256': digest(destination)}


def preflight(source, max_files):
    """Bound central-directory parsing before zipfile allocates all ZipInfo objects."""
    with Path(source).open('rb') as file:
        size = file.seek(0, 2)
        file.seek(max(0, size-65557))
        tail = file.read(65557)
        index = tail.rfind(b'PK\x05\x06')
        if index < 0 or len(tail)-index < 22:
            raise ValueError('ZIP end record missing')
        _, disk, central_disk, disk_count, count, length, offset, comment = struct.unpack_from('<4s4H2LH', tail, index)
        end = size-len(tail)+index
        if disk or central_disk or disk_count != count or index+22+comment != len(tail):
            raise ValueError('Split or trailing ZIP data unsupported')
        if count == 65535 or length == 0xffffffff or offset == 0xffffffff:
            if end < 20:
                raise ValueError('ZIP64 locator missing')
            file.seek(end-20)
            signature, disk, position, disks = struct.unpack('<4sLQL', file.read(20))
            if signature != b'PK\x06\x07' or disk or disks != 1 or position+56 != end-20:
                raise ValueError('Unsupported ZIP64 locator')
            file.seek(position)
            record = file.read(56)
            signature, record_size, _, _, disk, central_disk, disk_count, count, length, offset = struct.unpack('<4sQ2H2L4Q', record)
            if signature != b'PK\x06\x06' or record_size != 44 or disk or central_disk or disk_count != count:
                raise ValueError('Unsupported ZIP64 directory')
            end = position
        if count > max_files+2 or length > 64*1024**2 or offset+length != end:
            raise ValueError('Backup central directory limit exceeded')
        file.seek(offset)
        parsed = 0
        while file.tell() < end:
            header = file.read(46)
            if len(header) != 46 or header[:4] != b'PK\x01\x02':
                raise ValueError('Invalid ZIP directory')
            names, extra, comment = struct.unpack_from('<3H', header, 28)
            parsed += 1
            if parsed > max_files+2 or file.tell()+names+extra+comment > end:
                raise ValueError('Backup central directory limit exceeded')
            file.seek(names+extra+comment, 1)
        if parsed != count:
            raise ValueError('ZIP member count mismatch')


def import_bundle(source, destination, *, max_bytes=MAX_BYTES, max_files=MAX_FILES):
    """Extract a private new bundle; validate manifest before making it usable.

    The caller must still invoke backup.restore to validate SQLite integrity,
    references, storage identities and exact application migration compatibility.
    """
    source, destination = Path(source), Path(destination)
    if source.stat().st_size > max_bytes + (max_files+2)*1024:
        raise ValueError('Backup transport byte limit exceeded')
    preflight(source, max_files)
    destination.mkdir(mode=0o700)  # Never clean up an existing caller directory.
    try:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if not 3 <= len(entries) <= max_files+2:
                raise ValueError('Backup file count exceeded')
            names = set()
            total = 0
            for entry in entries:
                name = entry.filename
                if name != entry.orig_filename:
                    raise ValueError('Invalid ZIP member name')
                member_name(name)
                mode = entry.external_attr >> 16
                if (name in names or entry.is_dir() or entry.flag_bits & 1
                        or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                        or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError('Unsupported or duplicate backup member')
                names.add(name)
                total += entry.file_size
                if total > max_bytes:
                    raise ValueError('Backup byte limit exceeded')
                if name == 'manifest.json' and entry.file_size > MANIFEST_BYTES:
                    raise ValueError('Backup manifest limit exceeded')
                if name == 'COMPLETE' and entry.file_size != 64:
                    raise ValueError('Invalid completeness marker')
            if not {'manifest.json', 'COMPLETE', 'database/archive.sqlite3'} <= names:
                raise ValueError('Backup metadata missing')
            if shutil.disk_usage(destination).free < total + RESERVE_BYTES:
                raise ValueError('Insufficient backup import space')
            for entry in entries:
                target = destination / entry.filename
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                copied = 0
                with archive.open(entry) as src, target.open('xb') as dst:
                    os.chmod(target, 0o600)
                    while block := src.read(65536):
                        copied += len(block)
                        if copied > entry.file_size:
                            raise ValueError('Backup expanded beyond declared size')
                        dst.write(block)
                    dst.flush()
                    os.fsync(dst.fileno())
                if copied != entry.file_size:
                    raise ValueError('Backup member truncated')
            verified, _ = inventory(destination, max_bytes=max_bytes, max_files=max_files)
            if set(verified) != names:
                raise ValueError('Unexpected backup members')
            for directory, _, _ in os.walk(destination, topdown=False):
                sync_directory(directory)
        return {'files': len(entries)-2, 'external_sources_included': False}
    except BaseException:
        shutil.rmtree(destination)
        raise
