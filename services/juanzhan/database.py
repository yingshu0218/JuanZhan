"""Serialized, checksum-verified migrations. Baseline SQL remains unchanged."""
import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


@contextmanager
def connect(path):
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        yield connection
    finally:
        connection.close()


def migrate(path, migrations=MIGRATIONS):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        if sqlite3.sqlite_version_info < (3, 38):
            raise RuntimeError("SQLite >=3.38 required")
        db.execute("SELECT json_valid('{}')")
        db.execute("CREATE VIRTUAL TABLE temp.fts_probe USING fts5(text)")
        # Initial WAL transition can return SQLITE_BUSY without honoring busy_timeout.
        deadline = time.monotonic() + 5
        while True:
            try:
                db.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as exc:
                if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("CREATE TABLE IF NOT EXISTS migration_checksums "
                       "(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL)")
            files = sorted(migrations.glob("*.sql"))
            if not files:
                raise RuntimeError("No migrations found")
            known = dict(db.execute("SELECT name, sha256 FROM migration_checksums"))
            if set(known) - {p.name for p in files}:
                raise RuntimeError("Database contains unknown migrations")
            for file in files:
                content = file.read_text()
                checksum = hashlib.sha256(file.read_bytes()).hexdigest()
                if file.name in known:
                    if known[file.name] != checksum:
                        raise RuntimeError("Applied migration checksum changed: " + file.name)
                    continue
                statement = ""
                for line in content.splitlines(keepends=True):
                    if line.lstrip().startswith("--"):
                        continue
                    statement += line
                    if sqlite3.complete_statement(statement):
                        sql = statement.strip()
                        # Transaction/connection policy belongs to this runner.
                        if not (sql.upper().startswith("PRAGMA ") or sql.upper() in ("BEGIN;", "COMMIT;")):
                            db.execute(sql)
                        statement = ""
                if statement.strip():
                    raise RuntimeError("Incomplete migration: " + file.name)
                db.execute("INSERT INTO migration_checksums VALUES (?, ?)", (file.name, checksum))
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError("Foreign key violations after migration")
            db.commit()
        except BaseException:
            db.rollback()
            raise
