"""Fenced incremental observations: hashes, conservative matches, two missing scans."""
import json
import sqlite3
import tempfile
import uuid

from .catalog import same_space
from .database import connect
from .document_events import record_event, utc_now
from .document_records import snapshot
from .jobs import JobQueue, JobSpec
from .source_initial import prepare, register_external
from .source_paths import SourceMounts, SourcePathError


def incremental(settings, job):
    with connect(settings.database) as db:
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT s.* FROM sources s JOIN scan_runs r ON r.source_id=s.id WHERE r.id=? AND r.mode='incremental'",(job['target_id'],)).fetchone()
        source=dict(row) if row else None
        baseline=db.execute('SELECT root_digest FROM source_root_baselines WHERE source_id=?',(source['id'],)).fetchone() if source else None
    if source is None or source['status']=='disabled' or not source['initial_import_completed_at'] or json.loads(job['payload_json'])!={}:
        raise SourcePathError('INVALID_SOURCE_SCAN')
    if baseline and SourceMounts(settings.source_mounts).digest(source['root_ref'])!=baseline[0]:
        raise SourcePathError('SOURCE_ROOT_CHANGED')
    counts={'source_id':source['id'],'mode':'incremental','scanned_files':0,'scanned_bytes':0,'ignored_files':0,
            'imported_files':0,'updated_files':0,'reassociated_files':0,'recovered_files':0,'unchanged_files':0}
    with tempfile.TemporaryFile(mode='w+t',encoding='utf-8',dir=settings.data_dir) as manifest:
        source['_root_digest']=prepare(settings,source,manifest,counts,file_counter='scanned_files',bytes_counter='scanned_bytes')
        manifest.seek(0)
        JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:publish(db,owned,source,manifest,counts,settings))


def facts(entry):
    return {k:entry[k] for k in ('id','relative_path_norm','status','sha256')}


def audit(db, entry, before, timestamp):
    db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(timestamp,entry['document_id']))
    after=snapshot(db,entry['document_id'])
    after['source_entry']=facts(db.execute('SELECT * FROM source_entries WHERE id=?',(entry['id'],)).fetchone())
    record_event(db,entry['document_id'],'source_updated',before,after,timestamp=timestamp,actor='source_scan')


def before_document(db, entry):
    before=snapshot(db,entry['document_id'])
    before['source_entry']=facts(entry)
    return before


def seen(db, job, entry, item, settings, timestamp, counts):
    linked=entry['document_id'] is not None
    before=before_document(db,entry) if linked else None
    changed=moved=recovered=False
    if linked:
        revision=db.execute('SELECT * FROM file_revisions WHERE id=?',(before['current_revision_id'],)).fetchone()
        if revision is None or revision['storage_kind']!='external' or revision['source_entry_id']!=entry['id']:
            raise SourcePathError('SOURCE_DOCUMENT_STATE_CONFLICT')
        changed=(revision['sha256'],revision['size_bytes'])!=(item['sha256'],item['size_bytes'])
        moved=entry['relative_path_norm']!=item['path']
        recovered=entry['status']!='available'
        if changed:
            id=uuid.uuid4().hex
            number=db.execute('SELECT COALESCE(max(revision_no),0)+1 FROM file_revisions WHERE document_id=?',(entry['document_id'],)).fetchone()[0]
            db.execute('INSERT INTO file_revisions(id,document_id,revision_no,storage_kind,source_entry_id,source_path_at_capture,'
                       "sha256,size_bytes,original_filename,mime_type,file_modified_at,created_at) VALUES (?,?,?,'external',?,?,?,?,?,?,?,?)",
                       (id,entry['document_id'],number,entry['id'],item['path'],item['sha256'],item['size_bytes'],
                        item['path'].rsplit('/',1)[-1],item['mime_type'],item['file_modified_at'],timestamp))
            db.execute('UPDATE documents SET current_revision_id=? WHERE id=?',(id,entry['document_id']))
            JobQueue(settings).enqueue(JobSpec(kind='parse',target_type='document',target_id=entry['document_id'],
                idempotency_key='parse:'+id,payload={'revision_id':id}),db=db)
    db.execute('UPDATE source_entries SET relative_path_norm=?,relative_path_display=?,file_identity_hint=?,size_bytes=?,mtime_ns=?,'
               'sha256=?,status=?,last_seen_scan_id=?,updated_at=? WHERE id=?',
               (item['path'],item['path'],item['identity_hint'],item['size_bytes'],item['mtime_ns'],item['sha256'],
                'available' if linked else 'needs_match',job['target_id'],timestamp,entry['id']))
    db.execute('DELETE FROM source_missing_observations WHERE source_entry_id=?',(entry['id'],))
    if linked:
        if changed or moved or recovered:audit(db,entry,before,timestamp)
        counts['updated_files']+=int(changed)
        counts['reassociated_files']+=int(moved)
        counts['recovered_files']+=int(recovered)
        counts['unchanged_files']+=int(not (changed or moved or recovered))


def publish(db, job, observed, manifest, counts, settings):
    db.row_factory=sqlite3.Row
    source=db.execute('SELECT * FROM sources WHERE id=?',(observed['id'],)).fetchone()
    if (source is None or source['status']=='disabled' or not source['initial_import_completed_at'] or
        any(source[k]!=observed[k] for k in ('space_id','root_ref','new_file_target_folder_id'))):
        raise SourcePathError('SOURCE_CHANGED')
    root_digest=observed.get('_root_digest') or SourceMounts(settings.source_mounts).digest(source['root_ref'])
    if SourceMounts(settings.source_mounts).digest(source['root_ref'])!=root_digest:
        raise SourcePathError('SOURCE_ROOT_CHANGED')
    baseline=db.execute('SELECT root_digest FROM source_root_baselines WHERE source_id=?',(source['id'],)).fetchone()
    if baseline and baseline[0]!=root_digest:raise SourcePathError('SOURCE_ROOT_CHANGED')
    target=source['new_file_target_folder_id']
    if target is not None:same_space(db,'folders',target,source['space_id'])
    db.execute('CREATE TEMP TABLE observed_files(path TEXT PRIMARY KEY,sha TEXT,size INTEGER,hint TEXT,data TEXT,entry_id TEXT,ambiguous INTEGER DEFAULT 0)')
    db.execute('CREATE INDEX observed_hash ON observed_files(sha,size)')
    db.execute('CREATE TEMP TABLE previous_entries AS SELECT *,0 AS ambiguous FROM source_entries WHERE source_id=?',(source['id'],))
    db.execute('CREATE UNIQUE INDEX previous_path ON previous_entries(relative_path_norm)')
    db.execute('CREATE INDEX previous_hash ON previous_entries(sha256,size_bytes)')
    for line in manifest:
        item=json.loads(line)
        if item['kind']!='file':continue
        old=db.execute('SELECT id FROM previous_entries WHERE relative_path_norm=?',(item['path'],)).fetchone()
        db.execute('INSERT INTO observed_files(path,sha,size,hint,data,entry_id) VALUES (?,?,?,?,?,?)',
                   (item['path'],item['sha256'],item['size_bytes'],item['identity_hint'],line,old[0] if old else None))
    if baseline is None:
        # Legacy T13 upgrade: one exact path + hash + inode anchor, or genuinely empty inventory.
        total=db.execute('SELECT count(*) FROM previous_entries').fetchone()[0]
        anchor=db.execute('SELECT 1 FROM previous_entries e JOIN observed_files o ON o.path=e.relative_path_norm '
                          'WHERE e.document_id IS NOT NULL AND o.sha=e.sha256 AND o.size=e.size_bytes AND o.hint=e.file_identity_hint LIMIT 1').fetchone()
        if total and not anchor:raise SourcePathError('SOURCE_ROOT_UNVERIFIED')
        db.execute('INSERT INTO source_root_baselines VALUES (?,?)',(source['id'],root_digest))
    # Determine matches before mutating permanent paths or availability states.
    for item in db.execute('SELECT * FROM observed_files WHERE entry_id IS NULL ORDER BY path'):
        candidates=db.execute('SELECT e.* FROM previous_entries e WHERE e.sha256=? AND e.size_bytes=? AND e.document_id IS NOT NULL '
            'AND NOT EXISTS(SELECT 1 FROM observed_files p WHERE p.path=e.relative_path_norm)',(item['sha'],item['size'])).fetchall()
        if not candidates:continue
        old_hash=db.execute('SELECT count(*) FROM previous_entries WHERE sha256=? AND size_bytes=?',(item['sha'],item['size'])).fetchone()[0]
        new_hash=db.execute('SELECT count(*) FROM observed_files WHERE sha=? AND size=?',(item['sha'],item['size'])).fetchone()[0]
        # Inode is a hint, not proof against reuse. Duplicate hashes never auto-match.
        match=candidates[0] if len(candidates)==1 and old_hash==1 and new_hash==1 else None
        if match is not None:
            db.execute('UPDATE observed_files SET entry_id=? WHERE path=?',(match['id'],item['path']))
        else:
            db.execute('UPDATE observed_files SET ambiguous=1 WHERE path=?',(item['path'],))
            db.executemany('UPDATE previous_entries SET ambiguous=1 WHERE id=?',[(e['id'],) for e in candidates])
    timestamp=utc_now()
    for row in db.execute('SELECT * FROM observed_files ORDER BY path'):
        item=json.loads(row['data'])
        if row['entry_id'] is not None:
            entry=db.execute('SELECT * FROM source_entries WHERE id=?',(row['entry_id'],)).fetchone()
            seen(db,job,entry,item,settings,timestamp,counts)
        elif row['ambiguous']:
            db.execute('INSERT INTO source_entries(id,source_id,space_id,relative_path_norm,relative_path_display,file_identity_hint,'
                "size_bytes,mtime_ns,sha256,status,last_seen_scan_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,'needs_match',?,?,?)",
                (uuid.uuid4().hex,source['id'],source['space_id'],item['path'],item['path'],item['identity_hint'],
                 item['size_bytes'],item['mtime_ns'],item['sha256'],job['target_id'],timestamp,timestamp))
        else:
            register_external(db,job,source,item,target,'needs_review',settings,timestamp)
            counts['imported_files']+=1
    for old in db.execute('SELECT e.* FROM previous_entries e WHERE NOT EXISTS(SELECT 1 FROM observed_files o WHERE o.entry_id=e.id)'):
        if old['document_id'] is None:continue
        if old['ambiguous'] or old['status']=='needs_match':
            status='needs_match'
            db.execute('DELETE FROM source_missing_observations WHERE source_entry_id=?',(old['id'],))
        elif old['status']=='missing':status='missing'
        else:
            proof=db.execute("SELECT 1 FROM source_missing_observations m JOIN scan_runs r ON r.id=m.scan_run_id "
                "WHERE m.source_entry_id=? AND r.status='completed' AND r.mode='incremental' AND r.source_id=? AND r.id!=?",(old['id'],source['id'],job['target_id'])).fetchone()
            status='missing' if proof else 'suspected_missing'
            db.execute('INSERT INTO source_missing_observations VALUES (?,?) ON CONFLICT(source_entry_id) DO UPDATE SET scan_run_id=excluded.scan_run_id',
                       (old['id'],job['target_id']))
        if status!=old['status']:
            before=before_document(db,old)
            db.execute('UPDATE source_entries SET status=?,updated_at=? WHERE id=?',(status,timestamp,old['id']))
            audit(db,old,before,timestamp)
    for status in ('needs_match','suspected_missing','missing'):
        counts[status]=db.execute('SELECT count(*) FROM source_entries WHERE source_id=? AND status=?',(source['id'],status)).fetchone()[0]
    return counts
