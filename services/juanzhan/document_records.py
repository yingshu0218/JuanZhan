"""Internal document facts and optimistic version checks shared by lifecycle operations."""
from fastapi import HTTPException
from .auth import fail

def conflict(current):
    raise HTTPException(409, detail={'code':'VERSION_CONFLICT', 'message':'Document was changed; reload before writing',
                                    'current_document_version':current})


def snapshot(db, document_id):
    row = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if row is None:
        fail(404, 'NOT_FOUND', 'Document not found')
    result = dict(row)
    result['is_favorite'] = bool(result['is_favorite'])
    result['tag_ids'] = [r[0] for r in db.execute('SELECT tag_id FROM document_tags WHERE document_id=? ORDER BY tag_id', (document_id,))]
    return result


def expected(db, document_id, version):
    result = snapshot(db, document_id)
    if result['document_version'] != version:
        conflict(result['document_version'])
    return result

