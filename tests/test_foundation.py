import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.config import Settings
from juanzhan.database import connect, migrate, MIGRATIONS


@pytest.fixture
def settings(tmp_path):
    return Settings(tmp_path / 'archive', 'test-service-token')


def test_archive_restart_and_storage(settings):
    for _ in range(2):
        with TestClient(create_app('archive', settings)) as client:
            assert client.get('/healthz').json() == {'status': 'ok'}
            assert client.get('/api/v1/documents').status_code == 404
            assert settings.database.exists()
            for directory in ('managed', 'derived'):
                path = settings.data_dir / directory / 'probe'
                path.write_bytes(b'real filesystem')
                assert path.read_bytes() == b'real filesystem'
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM migration_checksums').fetchone()[0] == 1
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_constraints_every_connection(settings):
    migrate(settings.database)
    for _ in range(2):
        with connect(settings.database) as db:
            assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
            assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
            db.execute("INSERT INTO spaces VALUES ('a','A','now','now')")
            db.execute("INSERT INTO spaces VALUES ('b','B','now','now')")
            def folder(id, space, parent, name):
                db.execute('INSERT INTO folders VALUES (?,?,?,?,?,?,?)', (id, space, parent, name, name, 'now', 'now'))
            folder('root', 'a', None, 'root')
            folder('child', 'a', 'root', 'child')
            with pytest.raises(sqlite3.IntegrityError):
                folder('cross', 'b', 'root', 'cross')
            with pytest.raises(sqlite3.IntegrityError):
                folder('duplicate', 'a', None, 'root')
            with pytest.raises(sqlite3.IntegrityError, match='cycle'):
                db.execute("UPDATE folders SET parent_id='child' WHERE id='root'")
            with pytest.raises(sqlite3.IntegrityError, match='cycle'):
                folder('self', 'a', 'self', 'self')
            # Close without commit: each iteration is an independent transaction.


def test_migration_atomicity_and_tampering(settings, tmp_path):
    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    baseline = MIGRATIONS / '0001_archive_v04.sql'
    assert baseline.read_bytes() == (Path(__file__).parents[1] / 'docs/reference/archive-schema-v0.4.sql').read_bytes()
    (migrations / baseline.name).write_bytes(baseline.read_bytes())
    broken = migrations / '0002_failure.sql'
    broken.write_text('CREATE TABLE rollback_probe(id TEXT);\nINVALID SQL;\n')
    with pytest.raises(sqlite3.OperationalError):
        migrate(settings.database, migrations)
    with connect(settings.database) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='spaces'").fetchone() is None
    broken.unlink()
    migrate(settings.database, migrations)
    (migrations / baseline.name).write_text(baseline.read_text() + '\n-- changed\n')
    with pytest.raises(RuntimeError, match='checksum'):
        migrate(settings.database, migrations)


def test_concurrent_migrations(settings):
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: migrate(settings.database), range(2)))
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM migration_checksums').fetchone()[0] == 1


def test_converter_boundary(settings):
    with TestClient(create_app('converter', settings)) as client:
        assert client.get('/healthz').status_code == 200
        assert client.get('/v1/capabilities').status_code == 401
        headers = {'Authorization': 'Bearer ' + settings.converter_token}
        assert client.get('/v1/capabilities', headers=headers).json() == {
            'schema_versions': [], 'supported_input_types': [], 'ocr_available': False}
        response = client.post('/v1/jobs', headers=headers, json={'path': '/etc/passwd'})
        assert response.status_code == 501
        assert response.json()['error']['code'] == 'NOT_IMPLEMENTED'
    assert not settings.data_dir.exists()


def test_converter_requires_token(tmp_path):
    with pytest.raises(RuntimeError, match='CONVERTER_SERVICE_TOKEN'):
        with TestClient(create_app('converter', Settings(tmp_path, ''))):
            pass


def test_document_revision_persists(settings):
    migrate(settings.database)
    managed = settings.data_dir / 'managed'
    managed.mkdir()
    (managed / 'original.txt').write_bytes(b'original')
    import hashlib
    digest = hashlib.sha256(b'original').hexdigest()
    with connect(settings.database) as db:
        db.execute("INSERT INTO spaces VALUES ('s','Space','now','now')")
        db.execute("INSERT INTO managed_objects VALUES ('o',?,8,'original.txt','now')", (digest,))
        db.execute("INSERT INTO documents(id,space_id,title,imported_at,created_at,updated_at) VALUES ('d','s','Document','now','now','now')")
        db.execute("INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,managed_object_id,sha256,size_bytes,original_filename,mime_type,created_at) VALUES ('r','d',1,'managed','o',?,8,'original.txt','text/plain','now')", (digest,))
        db.execute("UPDATE documents SET current_revision_id='r' WHERE id='d'")
        db.commit()
    migrate(settings.database)
    with connect(settings.database) as db:
        assert db.execute("SELECT current_revision_id FROM documents WHERE id='d'").fetchone() == ('r',)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert (managed / 'original.txt').read_bytes() == b'original'
