"""Administrator allowlist and descriptor-relative, strictly read-only source access.

No filesystem mutations, path disclosure, symlink following or client absolute paths.
Linux/POSIX required; every opened mount must actually report ST_RDONLY.
"""
import json
import os
import re
import stat
import unicodedata
from contextlib import contextmanager

ALIAS = re.compile(r'[a-z][a-z0-9_-]{0,63}', re.ASCII)
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class SourcePathError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def components(value, *, absolute=False):
    if not isinstance(value, str) or not value or any(unicodedata.category(c) == 'Cs' for c in value):
        raise SourcePathError('INVALID_SOURCE_PATH')
    if len(value.encode('utf-8')) > 4096:
        raise SourcePathError('INVALID_SOURCE_PATH')
    if absolute:
        if not value.startswith('/') or value.startswith('//'):
            raise SourcePathError('INVALID_SOURCE_PATH')
        value = value[1:]
    if not value or any(unicodedata.category(c) in ('Cc', 'Cs') for c in value) or '\\' in value or ':' in value:
        raise SourcePathError('INVALID_SOURCE_PATH')
    parts = value.split('/')
    if any(part in ('', '.', '..') or len(part.encode('utf-8')) > 255 for part in parts):
        raise SourcePathError('INVALID_SOURCE_PATH')
    # Preserve exact Unicode/case: normalization must not alias distinct disk names.
    return parts


def parse_mounts(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Invalid source mount configuration')
            result[key] = value
        return result
    try:
        if len(raw) > 65536:
            raise ValueError()
        mounts = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(mounts, dict) or len(mounts) > 100:
            raise ValueError()
        for alias, path in mounts.items():
            if not ALIAS.fullmatch(alias):
                raise ValueError()
            components(path, absolute=True)
        return tuple(sorted(mounts.items()))
    except (ValueError, TypeError, SourcePathError, UnicodeError):
        # Configuration can contain private paths; never echo values.
        raise ValueError('Invalid source mount configuration') from None


def readonly(fd):
    if not os.fstatvfs(fd).f_flag & os.ST_RDONLY:
        raise SourcePathError('SOURCE_NOT_READ_ONLY')


@contextmanager
def descend(root, parts, *, file=False):
    current = os.dup(root)
    try:
        for index, part in enumerate(parts):
            flags = (os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC) if file and index == len(parts) - 1 else DIR_FLAGS
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
            # Nested mounts may have different access flags from their parent.
            readonly(current)
        if file and not stat.S_ISREG(os.fstat(current).st_mode):
            raise SourcePathError('SOURCE_NOT_REGULAR')
        yield current
    finally:
        os.close(current)


class SourceMounts:
    def __init__(self, mounts=()):
        self._mounts = dict(mounts)

    @contextmanager
    def root(self, alias):
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias) or alias not in self._mounts:
            raise SourcePathError('SOURCE_ALIAS_NOT_ALLOWED')
        parts = components(self._mounts[alias], absolute=True)
        current = os.open('/', DIR_FLAGS)
        try:
            # Ancestors can be writable; the configured root and all descendants cannot.
            for part in parts:
                child = os.open(part, DIR_FLAGS, dir_fd=current)
                os.close(current)
                current = child
            readonly(current)
        except FileNotFoundError:
            os.close(current)
            raise SourcePathError('SOURCE_OFFLINE') from None
        except PermissionError:
            os.close(current)
            raise SourcePathError('SOURCE_UNREADABLE') from None
        except OSError:
            os.close(current)
            raise SourcePathError('SOURCE_UNSAFE_OR_UNAVAILABLE') from None
        except BaseException:
            os.close(current)
            raise
        try:
            yield current
        finally:
            os.close(current)

    @contextmanager
    def open(self, alias, relative_path):
        parts = components(relative_path)
        try:
            with self.root(alias) as root:
                with descend(root, parts, file=True) as fd:
                    # O_PATH verifies regular type before opening bytes, avoiding device IO.
                    # /proc/self/fd pins the checked inode across rename/symlink replacement.
                    reader = os.open(f'/proc/self/fd/{fd}', FILE_FLAGS & ~os.O_NOFOLLOW)
                    with os.fdopen(reader, 'rb') as stream:
                        readonly(stream.fileno())
                        yield stream
        except FileNotFoundError:
            raise SourcePathError('SOURCE_FILE_MISSING') from None
        except PermissionError:
            raise SourcePathError('SOURCE_UNREADABLE') from None
        except OSError:
            raise SourcePathError('SOURCE_UNSAFE_OR_UNAVAILABLE') from None

    def list(self):
        items = []
        for alias in sorted(self._mounts):
            try:
                with self.root(alias):
                    pass
                status, code = 'ready', None
            except SourcePathError as exc:
                status = 'offline' if exc.code == 'SOURCE_OFFLINE' else 'unavailable'
                code = exc.code
            items.append({'alias': alias, 'status': status, 'error_code': code})
        return items
