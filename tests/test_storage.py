import hashlib
import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.auth import set_password
from juanzhan.config import Settings
from juanzhan.database import connect
from juanzhan.storage import (CHUNK_BYTES, IntegrityError, ManagedStore, SizeLimitExceeded,
                              StorageBusy)


@pytest.fixture
def store(tmp_path):
    result = ManagedStore(tmp_path / 'managed')
    result.initialize()
    return result


def stage_files(store):
    return list((store.root / '.staging').iterdir())


def test_bounded_stream_and_verified_reader(store):
    payload = b'archive bytes' * 20000
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= CHUNK_BYTES
            return super().read(size)
    result = store.put(Bounded(payload), max_bytes=len(payload),
                       expected_size=len(payload), expected_sha256=hashlib.sha256(payload).hexdigest())
    assert result.size_bytes == len(payload)
    with store.open(result.storage_key) as file:
        assert file.read() == payload
    assert not (store.root / result.storage_key).stat().st_mode & 0o222
    assert stage_files(store) == []
    empty = store.put(io.BytesIO(), max_bytes=0)
    with store.open(empty.storage_key) as file:
        assert file.read() == b''


@pytest.mark.parametrize('options,exception', [
    ({'max_bytes':3}, SizeLimitExceeded),
    ({'max_bytes':10,'expected_size':8}, IntegrityError),
    ({'max_bytes':10,'expected_sha256':'0'*64}, IntegrityError),
    ({'max_bytes':2,'expected_size':4}, SizeLimitExceeded),
])
def test_validation_failure_does_not_publish(store, options, exception):
    with pytest.raises(exception):
        store.put(io.BytesIO(b'file'), **options)
    assert stage_files(store) == []
    assert list((store.root / 'sha256').iterdir()) == []


def test_reader_interruption_cleans_partial_file(store):
    class Interrupted:
        count = 0
        def read(self, size):
            self.count += 1
            if self.count == 1:
                return b'partial'
            raise ConnectionError('client disconnected')
    with pytest.raises(ConnectionError):
        store.put(Interrupted(), max_bytes=100)
    assert stage_files(store) == []
    assert list((store.root / 'sha256').iterdir()) == []


def test_concurrent_dedup_and_new_bytes_never_overwrite(store):
    payload = b'same-content' * 10000
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: store.put(io.BytesIO(payload), max_bytes=len(payload)), range(8)))
    assert sum(result.created for result in results) == 1
    assert len({result.storage_key for result in results}) == 1
    changed = store.put(io.BytesIO(b'new revision'), max_bytes=100)
    assert changed.storage_key != results[0].storage_key
    with store.open(results[0].storage_key) as original:
        assert original.read() == payload
    assert stage_files(store) == []


def test_corrupted_existing_object_is_never_overwritten(store):
    result = store.put(io.BytesIO(b'original'), max_bytes=100)
    path = store.root / result.storage_key
    path.chmod(0o640)
    path.write_bytes(b'corrupt!')
    with pytest.raises(IntegrityError):
        with store.open(result.storage_key):
            pass
    with pytest.raises(IntegrityError):
        store.put(io.BytesIO(b'original'), max_bytes=100)
    assert path.read_bytes() == b'corrupt!'
    assert stage_files(store) == []


@pytest.mark.parametrize('key', ['../secret','/etc/passwd','sha256/aa/'+'b'*64+'-1',
                                 'sha256/aa/'+'a'*64+'-01', 'https://example.test/file'])
def test_untrusted_key_rejected(store, key):
    with pytest.raises(ValueError):
        with store.open(key):
            pass


def test_symlink_boundaries(store, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (store.root / '.staging').rmdir()
    (store.root / '.staging').symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        store.put(io.BytesIO(b'data'), max_bytes=4)
    assert list(outside.iterdir()) == []
    (store.root / '.staging').unlink()
    store.initialize()
    payload = b'no symlink writes'
    sha = hashlib.sha256(payload).hexdigest()
    (store.root / 'sha256' / sha[:2]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        store.put(io.BytesIO(payload), max_bytes=100)
    assert list(outside.iterdir()) == []
    assert stage_files(store) == []


def test_final_object_symlink_not_followed(store, tmp_path):
    result = store.put(io.BytesIO(b'data'), max_bytes=4)
    path = store.root / result.storage_key
    path.unlink()
    outside = tmp_path / 'secret'
    outside.write_bytes(b'data')
    path.symlink_to(outside)
    with pytest.raises(OSError):
        with store.open(result.storage_key):
            pass
    with pytest.raises(OSError):
        store.put(io.BytesIO(b'data'), max_bytes=4)
    assert outside.read_bytes() == b'data'


def test_recovery_never_removes_active_or_published_objects(store):
    old = store.root / '.staging' / ('a'*32+'.part')
    old.write_bytes(b'abandoned')
    os.utime(old, (0,0))
    entered, finish = threading.Event(), threading.Event()
    class Slow(io.BytesIO):
        def read(self, size):
            entered.set()
            assert finish.wait(5)
            return super().read(size)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(store.put, Slow(b'active'), max_bytes=10)
        try:
            assert entered.wait(5)
            with pytest.raises(StorageBusy):
                store.recover_staging(minimum_age_seconds=0)
            assert old.exists()
        finally:
            finish.set()
        result = future.result()
    assert store.recover_staging() == 1
    assert (store.root / result.storage_key).read_bytes() == b'active'


@pytest.mark.parametrize('phase,exit_code', [('stream',93),('published',94)])
def test_hard_crash_leaves_no_partial_references_and_recovery_is_safe(store, tmp_path, phase, exit_code):
    # A real child exits without Python finally handlers (not a simulated exception).
    code = '''
import io, os, sys
from pathlib import Path
from juanzhan.storage import ManagedStore
s = ManagedStore(Path(sys.argv[1]))
if sys.argv[2] == 'stream':
    class Crash:
        reads = 0
        def read(self, size):
            self.reads += 1
            if self.reads == 1: return b'x' * 65536
            os._exit(93)
    s.put(Crash(), max_bytes=131072)
else:
    link = os.link
    def crash(*args, **kwargs):
        link(*args, **kwargs)
        os._exit(94)
    os.link = crash
    s.put(io.BytesIO(b'complete'), max_bytes=100)
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / 'services'))
    result = subprocess.run([sys.executable,'-c',code,str(store.root),phase], env=env)
    assert result.returncode == exit_code
    assert len(stage_files(store)) == 1
    assert store.recover_staging(minimum_age_seconds=0) == 1
    assert stage_files(store) == []
    objects = list((store.root / 'sha256').glob('*/*'))
    if phase == 'stream':
        assert objects == []
    else:
        assert len(objects) == 1
        key = objects[0].relative_to(store.root).as_posix()
        with store.open(key) as file:
            assert file.read() == b'complete'


def test_disk_failure_before_publication_leaves_no_object(store, monkeypatch):
    real_fsync = os.fsync
    def disk_failure(fd):
        import stat
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('simulated disk failure')
        return real_fsync(fd)
    monkeypatch.setattr(os, 'fsync', disk_failure)
    with pytest.raises(OSError, match='disk failure'):
        store.put(io.BytesIO(b'bytes'), max_bytes=100)
    assert stage_files(store) == []
    assert list((store.root / 'sha256').iterdir()) == []


def test_http_storage_database_transaction_order(tmp_path):
    """Private test adapter, deliberately not a production upload endpoint."""
    settings = Settings(tmp_path / 'archive', 'unused')
    app = create_app('archive', settings)

    @app.post('/api/v1/_test/storage')
    async def write(request: Request):
        # HTTP adapter uses BytesIO only in this small integration fixture.
        # T08 must stream the actual multipart upload and perform business registration.
        result = app.state.storage.put(io.BytesIO(await request.body()), max_bytes=8)
        with connect(settings.database) as db:
            db.execute('INSERT INTO managed_objects VALUES (?,?,?,?,?)',
                       ('object',result.sha256,result.size_bytes,result.storage_key,'2026-10-16T00:00:00Z'))
            db.commit()
        return {'key':result.storage_key}

    with TestClient(app, base_url='https://archive.test', raise_server_exceptions=False) as client:
        set_password(settings, 'test-password-long-enough')
        csrf = client.get('/api/v1/auth/session').json()['csrf_token']
        csrf = client.post('/api/v1/auth/login', json={'username':'admin','password':'test-password-long-enough'},
                           headers={'X-CSRF-Token':csrf}).json()['csrf_token']
        assert client.post('/api/v1/_test/storage', content=b'file').status_code == 403
        failed = client.post('/api/v1/_test/storage', content=b'oversized', headers={'X-CSRF-Token':csrf})
        assert failed.status_code == 500  # Adapter has no production error mapping.
        with connect(settings.database) as db:
            assert db.execute('SELECT count(*) FROM managed_objects').fetchone() == (0,)
        success = client.post('/api/v1/_test/storage', content=b'file', headers={'X-CSRF-Token':csrf})
        assert success.status_code == 200
        key = success.json()['key']
        with connect(settings.database) as db:
            assert db.execute('SELECT storage_key FROM managed_objects').fetchone() == (key,)
        with app.state.storage.open(key) as file:
            assert file.read() == b'file'
        # A later DB failure must not delete an object that another transaction uses.
        duplicate = client.post('/api/v1/_test/storage', content=b'file', headers={'X-CSRF-Token':csrf})
        assert duplicate.status_code == 500
        with app.state.storage.open(key) as file:
            assert file.read() == b'file'
        orphan_failure = client.post('/api/v1/_test/storage', content=b'other', headers={'X-CSRF-Token':csrf})
        assert orphan_failure.status_code == 500
        orphan_key = 'sha256/' + hashlib.sha256(b'other').hexdigest()[:2] + '/' + hashlib.sha256(b'other').hexdigest() + '-5'
        assert app.state.storage.recover_staging(minimum_age_seconds=0) == 0
        with app.state.storage.open(orphan_key) as orphan:
            assert orphan.read() == b'other'
        with connect(settings.database) as db:
            assert db.execute('SELECT count(*) FROM managed_objects').fetchone() == (1,)


def test_recovery_preserves_fresh_unknown_and_symlink_entries(store, tmp_path):
    staging = store.root / '.staging'
    fresh = staging / ('f' * 32 + '.part')
    fresh.write_bytes(b'fresh')
    unknown = staging / 'operator-note'
    unknown.write_bytes(b'keep')
    outside = tmp_path / 'outside-file'
    outside.write_bytes(b'outside')
    symlink = staging / ('e' * 32 + '.part')
    symlink.symlink_to(outside)
    assert store.recover_staging() == 0
    assert fresh.read_bytes() == b'fresh'
    assert unknown.read_bytes() == b'keep'
    assert symlink.is_symlink() and outside.read_bytes() == b'outside'


def test_publication_failure_has_no_visible_target(store, monkeypatch):
    def fail_link(*args, **kwargs):
        raise OSError('publication failed')
    monkeypatch.setattr(os, 'link', fail_link)
    with pytest.raises(OSError, match='publication failed'):
        store.put(io.BytesIO(b'never visible'), max_bytes=100)
    assert stage_files(store) == []
    assert list((store.root / 'sha256').glob('*/*')) == []
