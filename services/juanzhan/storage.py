"""Local managed objects: bounded streaming, atomic no-clobber publication.

This module never accepts client paths, writes external sources or creates Documents.
Requires a local POSIX filesystem supporting hard links, flock and directory fsync.
"""
import fcntl
import hashlib
import os
import re
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

CHUNK_BYTES = 64 * 1024
KEY = re.compile(r'sha256/([0-9a-f]{2})/([0-9a-f]{64})-(0|[1-9][0-9]*)', re.ASCII)
STAGED = re.compile(r'[0-9a-f]{32}\.part', re.ASCII)
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class StorageError(Exception):
    pass


class IntegrityError(StorageError):
    pass


class SizeLimitExceeded(StorageError):
    pass


class StorageBusy(StorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    sha256: str
    size_bytes: int
    created: bool


def parse_key(key):
    match = KEY.fullmatch(key)
    if not match or match[1] != match[2][:2]:
        raise ValueError('Invalid managed storage key')
    return match[2], int(match[3])


@contextmanager
def directory(parent, name, create=False):
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
        # Also sync when another writer just created this directory.
        os.fsync(parent)
    fd = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


@contextmanager
def verified_file(parent, name, expected_hash, expected_size):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
    try:
        with os.fdopen(fd, 'rb') as file:
            fd = None
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
                raise IntegrityError('Managed object type or size mismatch')
            checksum = hashlib.file_digest(file, 'sha256').hexdigest()
            if not secrets.compare_digest(checksum, expected_hash):
                raise IntegrityError('Managed object checksum mismatch')
            file.seek(0)
            yield file
    finally:
        if fd is not None:
            os.close(fd)


class ManagedStore:
    def __init__(self, root: Path):
        # Root is administrator configuration, never a user-supplied file path.
        self.root = Path(root)

    @contextmanager
    def locked(self, exclusive=False):
        root = os.open(self.root, DIRECTORY_FLAGS)
        lock = None
        try:
            lock = os.open('.store.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                           0o600, dir_fd=root)
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise StorageError('Invalid storage lock')
            operation = fcntl.LOCK_EX | fcntl.LOCK_NB if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(lock, operation)
            except BlockingIOError:
                raise StorageBusy('Active storage operations; recovery deferred') from None
            yield root
        finally:
            if lock is not None:
                os.close(lock)
            os.close(root)

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.locked() as root:
            with directory(root, '.staging', create=True):
                pass
            with directory(root, 'sha256', create=True):
                pass

    def put(self, source: BinaryIO, *, max_bytes: int,
            expected_sha256: str | None = None, expected_size: int | None = None) -> StoredObject:
        """Read bounded chunks; publish only after complete validation and fsync.

        Caller owns source and must supply a size limit. Return is safe to reference
        from a later DB transaction. On failure after publication an orphan may remain;
        never remove it here since another concurrent transaction can reference it.
        """
        if type(max_bytes) is not int or max_bytes < 0:
            raise ValueError('max_bytes must be a nonnegative integer')
        if expected_size is not None and (type(expected_size) is not int or expected_size < 0):
            raise ValueError('expected_size must be a nonnegative integer')
        if expected_sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
            raise ValueError('Expected SHA-256 must be lowercase hexadecimal')
        if expected_size is not None and expected_size > max_bytes:
            raise SizeLimitExceeded('File exceeds the configured size limit')
        with self.locked() as root, directory(root, '.staging') as staging:
            name = secrets.token_hex(16) + '.part'
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         0o600, dir_fd=staging)
            try:
                with os.fdopen(fd, 'wb') as file:
                    checksum = hashlib.sha256()
                    size = 0
                    while True:
                        # Read at most one byte beyond the limit to detect overflow.
                        chunk = source.read(min(CHUNK_BYTES, max_bytes - size + 1))
                        if not isinstance(chunk, bytes):
                            raise TypeError('Binary stream must return bytes')
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise SizeLimitExceeded('File exceeds the configured size limit')
                        file.write(chunk)
                        checksum.update(chunk)
                    sha256 = checksum.hexdigest()
                    if expected_size is not None and expected_size != size:
                        raise IntegrityError('Stream size does not match expected size')
                    if expected_sha256 is not None and not secrets.compare_digest(sha256, expected_sha256):
                        raise IntegrityError('Stream checksum does not match expected checksum')
                    file.flush()
                    os.fchmod(file.fileno(), 0o440)
                    os.fsync(file.fileno())
                key = f'sha256/{sha256[:2]}/{sha256}-{size}'
                with directory(root, 'sha256') as objects, directory(objects, sha256[:2], create=True) as bucket:
                    target = f'{sha256}-{size}'
                    created = True
                    try:
                        # Hard-link publication is atomic and refuses to replace a target.
                        os.link(name, target, src_dir_fd=staging, dst_dir_fd=bucket, follow_symlinks=False)
                    except FileExistsError:
                        created = False
                        with verified_file(bucket, target, sha256, size):
                            pass
                    os.fsync(bucket)
                return StoredObject(key, sha256, size, created)
            finally:
                os.unlink(name, dir_fd=staging)
                os.fsync(staging)

    @contextmanager
    def open(self, storage_key: str):
        """Internal reader. Authentication belongs to the eventual download API."""
        sha256, size = parse_key(storage_key)
        root = os.open(self.root, DIRECTORY_FLAGS)
        try:
            with directory(root, 'sha256') as objects, directory(objects, sha256[:2]) as bucket:
                with verified_file(bucket, f'{sha256}-{size}', sha256, size) as file:
                    yield file
        finally:
            os.close(root)

    def recover_staging(self, *, minimum_age_seconds=3600):
        """Remove only old regular staging files while no writer is active.

        No published-object deletion: DB-aware GC is a later service responsibility.
        Unknown files and symlinks are ignored, never followed.
        """
        if minimum_age_seconds < 0:
            raise ValueError('Recovery age must be nonnegative')
        cutoff = time.time() - minimum_age_seconds
        removed = 0
        with self.locked(exclusive=True) as root, directory(root, '.staging') as staging:
            for name in os.listdir(staging):
                if not STAGED.fullmatch(name):
                    continue
                info = os.stat(name, dir_fd=staging, follow_symlinks=False)
                if stat.S_ISREG(info.st_mode) and info.st_mtime <= cutoff:
                    os.unlink(name, dir_fd=staging)
                    removed += 1
            os.fsync(staging)
        return removed
