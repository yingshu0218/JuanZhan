"""Private, bounded Converter spool. It never opens the Archive database or volumes."""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid

from .conversion_models import ParseResult


class ConversionError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


@dataclass(frozen=True)
class ConverterConfig:
    root: Path = Path('/tmp/juanzhan-converter')
    max_file_bytes: int = 4 * 1024 * 1024
    max_output_bytes: int = 16 * 1024 * 1024
    max_jobs: int = 2
    ttl_seconds: float = 3600.0
    wall_seconds: float = 30.0
    cpu_seconds: int = 10
    memory_bytes: int = 256 * 1024 * 1024
    max_blocks: int = 10000
    receive_seconds: float = 60.0
    max_pages: int = 200
    max_archive_entries: int = 1024
    max_archive_bytes: int = 16 * 1024 * 1024
    max_archive_member_bytes: int = 8 * 1024 * 1024
    max_compression_ratio: int = 200

    def __post_init__(self):
        if not (1 <= self.max_file_bytes <= 64*1024*1024 and
                1024 <= self.max_output_bytes <= 64*1024*1024 and 1 <= self.max_jobs <= 100 and
                0 < self.ttl_seconds <= 86400 and 0 < self.wall_seconds <= 300 and
                1 <= self.cpu_seconds <= 300 and 64*1024*1024 <= self.memory_bytes <= 2*1024**3 and
                1 <= self.max_blocks <= 10000 and 0 < self.receive_seconds <= 300 and
                1 <= self.max_pages <= 1000 and 1 <= self.max_archive_entries <= 10000 and
                1024 <= self.max_archive_member_bytes <= self.max_archive_bytes <= 64*1024*1024 and
                1 <= self.max_compression_ratio <= 1000):
            raise ValueError('Invalid converter resource limits')

    @classmethod
    def from_env(cls):
        defaults = cls()
        values = {}
        for name in asdict(defaults):
            raw = os.getenv('CONVERTER_' + name.upper())
            if raw is not None:
                original = getattr(defaults, name)
                values[name] = Path(raw) if name == 'root' else type(original)(raw)
        return cls(**values)


def utc(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace('+00:00', 'Z')


class ConverterStore:
    def __init__(self, config):
        self.config = config
        self.root = config.root
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.process = None
        self.last_tick = time.monotonic()

    def ready(self):
        return self.thread.is_alive() and time.monotonic()-self.last_tick < self.config.wall_seconds+10

    @contextmanager
    def database(self):
        db = sqlite3.connect(self.root / 'converter.sqlite3', timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    def start(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid != os.getuid():
            raise RuntimeError('Converter spool must be private and owned by the service')
        self.root.chmod(0o700)
        self.owner = (self.root / 'owner.lock').open('a')
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner.close()
            raise RuntimeError('Only one Converter process may own a spool') from None
        with self.database() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, parse_run_id TEXT UNIQUE NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
                    finished REAL, error_code TEXT, result_json TEXT
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    ref TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, media_type TEXT NOT NULL
                );
            ''')
            db.execute("UPDATE tasks SET status='failed', finished=?, error_code='CONVERTER_RESTARTED' WHERE status='running'", (time.time(),))
            known = {r[0] for r in db.execute('SELECT id FROM tasks')}
        for path in self.root.iterdir():
            if path.is_dir() and re.fullmatch('[0-9a-f]{32}', path.name) and path.name not in known:
                shutil.rmtree(path)
        self.collect()
        self.thread = threading.Thread(target=self.run, name='converter-runner', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=self.config.wall_seconds + 5)
        if self.thread.is_alive():
            raise RuntimeError('Converter runner did not stop')
        self.owner.close()

    def collect(self):
        with self.lock, self.database() as db:
            expired = [r[0] for r in db.execute("SELECT id FROM tasks WHERE status NOT IN ('queued','running') AND created <= ?", (time.time()-self.config.ttl_seconds,))]
            for id in expired:
                self.remove_directory(id)
                db.execute('DELETE FROM tasks WHERE id=?', (id,))

    def remove_directory(self, id):
        try:
            shutil.rmtree(self.root / id)
        except FileNotFoundError:
            pass  # Cleanup is recoverable if a process exited after unlink but before COMMIT.

    def submit(self, stream, options):
        # A stable parse_run_id binds the exact bytes and options for the spool lifetime.
        with self.lock:
            self.collect()
            id = uuid.uuid4().hex
            directory = self.root / id
            directory.mkdir(mode=0o700)
            try:
                digest = hashlib.sha256()
                size = 0
                with (directory / 'input').open('xb') as output:
                    while chunk := stream.read(65536):
                        size += len(chunk)
                        if size > self.config.max_file_bytes:
                            raise ConversionError(413, 'FILE_TOO_LARGE')
                        digest.update(chunk)
                        output.write(chunk)
                data = options.model_dump()
                fingerprint = hashlib.sha256((digest.hexdigest()+json.dumps(data,sort_keys=True)).encode()).hexdigest()
                with self.database() as db:
                    old = db.execute('SELECT * FROM tasks WHERE parse_run_id=?', (options.parse_run_id,)).fetchone()
                    if old:
                        if old['fingerprint'] != fingerprint:
                            raise ConversionError(409, 'IDEMPOTENCY_CONFLICT')
                        return {'job_id': old['id'], 'status': old['status']}
                    if db.execute('SELECT count(*) FROM tasks').fetchone()[0] >= self.config.max_jobs:
                        raise ConversionError(429, 'CONVERTER_CAPACITY')
                    (directory / 'options.json').write_text(json.dumps(data))
                    limits = {key: value for key,value in asdict(self.config).items() if key != 'root'}
                    (directory / 'limits.json').write_text(json.dumps(limits))
                    db.execute("INSERT INTO tasks(id,parse_run_id,fingerprint,status,created) VALUES (?,?,?,'queued',?)", (id, options.parse_run_id, fingerprint, time.time()))
                id = None  # The DB now owns this directory.
                return {'job_id': directory.name, 'status': 'queued'}
            finally:
                if id is not None:
                    shutil.rmtree(directory)

    def row(self, db, id):
        if not re.fullmatch('[0-9a-f]{32}', id):
            raise ConversionError(404, 'NOT_FOUND')
        row = db.execute('SELECT * FROM tasks WHERE id=?', (id,)).fetchone()
        if row is None:
            raise ConversionError(404, 'NOT_FOUND')
        return row

    def get(self, id, *, result=False):
        with self.lock:
            self.collect()
            with self.database() as db:
                row = self.row(db, id)
                if result:
                    if row['status'] != 'completed':
                        raise ConversionError(409, 'RESULT_NOT_READY')
                    return json.loads(row['result_json'])
                return {'job_id': row['id'], 'status': row['status'], 'attempts': row['attempts'],
                        'created_at': utc(row['created']), 'finished_at': utc(row['finished']) if row['finished'] else None,
                        'error': {'error': {'code': row['error_code'], 'message': 'Conversion attempt failed'}} if row['error_code'] else None,
                        'warnings': json.loads(row['result_json'])['warnings'] if row['result_json'] else []}

    def delete(self, id):
        with self.lock, self.database() as db:
            row = self.row(db, id)
            if row['status'] in ('queued', 'running'):
                raise ConversionError(409, 'JOB_ACTIVE')
            self.remove_directory(id)
            db.execute('DELETE FROM tasks WHERE id=?', (id,))

    def artifact(self, ref):
        with self.lock:
            self.collect()
            if not re.fullmatch('[0-9a-f]{32}', ref):
                raise ConversionError(404, 'NOT_FOUND')
            with self.database() as db:
                row = db.execute('SELECT * FROM artifacts WHERE ref=?', (ref,)).fetchone()
                if row is None:
                    raise ConversionError(404, 'NOT_FOUND')
            # Open while holding cleanup lock. Descriptor remains valid through unlink/TTL.
            fd = os.open(self.root / row['job_id'] / ref, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            file = os.fdopen(fd, 'rb')
            if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_size != row['size_bytes']:
                file.close()
                raise ConversionError(500, 'ARTIFACT_INTEGRITY_ERROR')
            return file, dict(row)

    def run(self):
        while not self.stop.is_set():
            try:
                self.collect()
                with self.lock, self.database() as db:
                    # A previous publish may have failed after the child exited. This single
                    # runner owns all active tasks; never leave one running forever.
                    db.execute("UPDATE tasks SET status='failed',finished=?,error_code='CONVERTER_PUBLISH_FAILED' WHERE status='running'", (time.time(),))
                    row = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created,id LIMIT 1").fetchone()
                    if row:
                        db.execute("UPDATE tasks SET status='running', attempts=attempts+1 WHERE id=?", (row['id'],))
                self.last_tick = time.monotonic()
                if row:
                    self.execute(row['id'])
                else:
                    self.stop.wait(.1)
            except Exception:
                # No input, token, server path or parser exception goes to logs or public errors.
                self.stop.wait(.2)

    def execute(self, id):
        directory = self.root / id
        code = None
        result = None
        try:
            environment = {key:value for key,value in os.environ.items() if key in ('PATH','LANG')}
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
            process = subprocess.Popen([sys.executable, '-m', 'juanzhan.conversion_child', str(directory)],
                                       env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True)
            self.process = process
            deadline = time.monotonic() + self.config.wall_seconds
            while process.poll() is None:
                if self.stop.wait(.02) or time.monotonic() >= deadline:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    code = 'CONVERTER_STOPPED' if self.stop.is_set() else 'CONVERSION_TIMEOUT'
                    break
            if not code and process.returncode:
                code = 'CONVERSION_RESOURCE_LIMIT' if process.returncode < 0 else 'CONVERSION_FAILED'
            if not code:
                output = directory / 'output.json'
                if output.stat().st_size > self.config.max_output_bytes:
                    raise ValueError('Result too large')
                payload = json.loads(output.read_bytes())
                if 'error' in payload:
                    code = payload['error']['code']
                else:
                    result = ParseResult.model_validate(payload['result']).model_dump(exclude_unset=True)
                    options = json.loads((directory / 'options.json').read_bytes())
                    if any(result[key] != options[key] for key in ('file_revision_id','parse_run_id')):
                        raise ValueError('Identity mismatch')
                    total = 0
                    for asset in result['artifacts']:
                        fd = os.open(directory / asset['artifact_ref'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
                        with os.fdopen(fd, 'rb') as file:
                            if not stat.S_ISREG(os.fstat(fd).st_mode):
                                raise ValueError('Nonregular artifact')
                            data = file.read(self.config.max_output_bytes+1)
                        total += len(data)
                        if total > self.config.max_output_bytes or len(data) != asset['size_bytes'] or hashlib.sha256(data).hexdigest() != asset['sha256']:
                            raise ValueError('Artifact integrity failed')
        except Exception:
            code = 'INVALID_CONVERTER_OUTPUT'
        finally:
            self.process = None
        with self.lock, self.database() as db:
            for asset in result['artifacts'] if result and not code else []:
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?)', (asset['artifact_ref'],id,asset['sha256'],asset['size_bytes'],asset['media_type']))
            db.execute('UPDATE tasks SET status=?,finished=?,error_code=?,result_json=? WHERE id=?',
                       ('failed' if code else 'completed',time.time(),code,json.dumps(result,ensure_ascii=False) if not code else None,id))
        # All original bytes are temporary; retain only result assets until DELETE/TTL.
        for name in ('input','options.json','limits.json','output.json'):
            (directory / name).unlink(missing_ok=True)
        if code:
            for path in directory.iterdir():
                path.unlink()
