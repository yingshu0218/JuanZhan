"""Real readonly sysfs source, SQLite and managed bytes; no writable source bypass."""
import hashlib
import sqlite3
from pathlib import Path
import pytest
from test_sources import api,ROOT
from test_source_incremental import seed,item,entries,claim
from juanzhan.database import connect
from juanzhan.jobs import JobQueue,JobSpec
from juanzhan.source_snapshots import ensure
from juanzhan.parsing import original
from juanzhan.storage import ManagedStore
from juanzhan.backup import references

def test_external_snapshot_survives_source_loss_and_retains_source_binding(api,tmp_path):
    settings,client,headers,space=api
    name='core_id';body=Path(ROOT,name).read_bytes()
    source=seed(api,[item(name,body)])
    document=entries(api,source)[0]['document_id']
    revision_id=client.get('/api/v1/documents/'+document).json()['current_revision_id']
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        revision=dict(db.execute('SELECT * FROM file_revisions WHERE id=?',(revision_id,)).fetchone())
    job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='snapshot_test',target_id=revision_id,idempotency_key='snapshot-test'))
    owned=claim(settings,job['id'])
    ensure(settings,revision,owned);ensure(settings,revision,owned)
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM revision_snapshots').fetchone()[0]==1
        assert db.execute('SELECT storage_kind FROM file_revisions WHERE id=?',(revision_id,)).fetchone()[0]=='external'
        assert len([r for r in references(db) if r.startswith('managed/')])==1
        db.execute("UPDATE sources SET status='disabled' WHERE id=?",(source,));db.commit()
    with original(settings,revision,1024) as file:assert file.read()==body
    response=client.get('/api/v1/documents/'+document+'/download',params={'expected_revision_id':revision_id})
    assert response.status_code==200 and response.content==body
    assert client.get('/api/v1/documents/'+document).json()['availability_status']=='available'
    assert hashlib.sha256(Path(ROOT,name).read_bytes()).hexdigest()==revision['sha256']
    from juanzhan.maintenance import run_gc
    gc=JobQueue(settings).enqueue(JobSpec(kind='gc',target_type='managed_objects',idempotency_key='snapshot-retention-gc'))
    run_gc(settings,claim(settings,gc['id']))
    with original(settings,revision,1024) as file:assert file.read()==body
    from juanzhan.backup import create,restore
    from juanzhan.config import Settings
    bundle=tmp_path/'snapshot-backup';target=tmp_path/'snapshot-restored'
    create(settings,bundle);restore(bundle,target)
    with original(Settings(target,''),revision,1024) as file:assert file.read()==body

def test_snapshot_sql_rejects_mismatched_original(api):
    settings,client,headers,space=api
    source=seed(api,[item('core_id',Path(ROOT,'core_id').read_bytes())]);document=entries(api,source)[0]['document_id']
    revision_id=client.get('/api/v1/documents/'+document).json()['current_revision_id']
    import io
    from juanzhan.documents import DocumentService
    obj=ManagedStore(settings.data_dir/'managed').put(io.BytesIO(b'wrong'),max_bytes=100)
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row;object_id=DocumentService.managed_object(db,obj)
        with pytest.raises(sqlite3.IntegrityError):db.execute('INSERT INTO revision_snapshots VALUES (?,?,?)',(revision_id,object_id,'2026-10-21T00:00:00Z'))

def test_changed_source_cannot_publish_wrong_snapshot(api):
    from juanzhan.parsing import ParseFailure
    settings,client,headers,space=api
    source=seed(api,[item('core_id',b'not the real readonly source')])
    document=entries(api,source)[0]['document_id'];revision_id=client.get('/api/v1/documents/'+document).json()['current_revision_id']
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row;revision=dict(db.execute('SELECT * FROM file_revisions WHERE id=?',(revision_id,)).fetchone())
    job=JobQueue(settings).enqueue(JobSpec(kind='batch',target_type='snapshot_test',idempotency_key='changed-snapshot'))
    owned=claim(settings,job['id'])
    with pytest.raises(ParseFailure) as rejected:ensure(settings,revision,owned)
    assert rejected.value.code=='SOURCE_REVISION_CHANGED'
    with connect(settings.database) as db:
        assert db.execute('SELECT count(*) FROM revision_snapshots').fetchone()[0]==0
