"""Exact relative-file exclusions, including pending cancellation barriers."""
import uuid
from .source_paths import SourcePathError


def epoch(db, source_id):
    row=db.execute('SELECT version FROM source_exclusion_versions WHERE source_id=?',(source_id,)).fetchone()
    return row[0] if row else 0


def bump(db, source_id):
    db.execute('INSERT INTO source_exclusion_versions VALUES (?,1) ON CONFLICT(source_id) DO UPDATE SET version=version+1',(source_id,))


def blocked(db, source_id, path):
    return db.execute('SELECT 1 FROM source_exclusions WHERE source_id=? AND relative_path_norm=? '
        'UNION ALL SELECT 1 FROM source_exclusion_intents WHERE source_id=? AND relative_path_norm=? LIMIT 1',
        (source_id,path,source_id,path)).fetchone() is not None


def verify(db, source):
    if epoch(db,source['id'])!=source.get('_exclusion_epoch',epoch(db,source['id'])):
        raise SourcePathError('SOURCE_CHANGED')


def add(db, entry, reason, timestamp):
    existing=db.execute('SELECT id FROM source_exclusions WHERE source_id=? AND relative_path_norm=?',
                        (entry['source_id'],entry['relative_path_norm'])).fetchone()
    if existing:return existing[0]
    id=uuid.uuid4().hex
    db.execute('INSERT INTO source_exclusions VALUES (?,?,?,?,?,?)',
        (id,entry['source_id'],entry['relative_path_norm'],entry['sha256'],reason,timestamp))
    bump(db,entry['source_id'])
    return id


def failed(db, job, terminal):
    if terminal and job['target_type']=='source_exclude':
        rows=db.execute('SELECT source_id FROM source_exclusion_intents WHERE job_id=?',(job['id'],)).fetchall()
        db.execute('DELETE FROM source_exclusion_intents WHERE job_id=?',(job['id'],))
        for row in rows:bump(db,row[0])
