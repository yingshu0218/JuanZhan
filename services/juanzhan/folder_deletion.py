"""Logical subtree removal, inside the caller's authenticated write transaction."""
from .auth import fail
from .document_events import record_event, utc_now
from .document_records import snapshot


def delete_subtree(db,root,mode):
    # Scope every recursive hop, and keep child-first ordering for restrictive FKs.
    folders=db.execute('WITH RECURSIVE tree(id,depth) AS (SELECT id,0 FROM folders WHERE id=? '
                       'UNION ALL SELECT f.id,t.depth+1 FROM folders f JOIN tree t ON f.parent_id=t.id '
                       'WHERE f.space_id=?) SELECT id,depth FROM tree ORDER BY depth DESC,id',
                       (root['id'],root['space_id'])).fetchall()
    ids={row[0] for row in folders}
    sources=db.execute('SELECT initial_target_folder_id,new_file_target_folder_id FROM sources WHERE space_id=?',
                       (root['space_id'],)).fetchall()
    if any(a in ids or b in ids for a,b in sources):
        fail(409,'SOURCE_FOLDER_REFERENCE','Folder subtree is referenced by a source configuration')
    timestamp=utc_now()
    documents=db.execute('SELECT id,folder_id FROM documents WHERE space_id=? ORDER BY id',(root['space_id'],)).fetchall()
    for id,folder in documents:
        if folder not in ids:continue
        before=snapshot(db,id)
        target=root['parent_id'] if mode=='move_contents_to_parent' else None
        deleted=before['deleted_at']
        if mode=='trash_contents' and deleted is None:deleted=timestamp
        db.execute('UPDATE documents SET folder_id=?,deleted_at=?,updated_at=?,document_version=document_version+1 WHERE id=?',
                   (target,deleted,timestamp,id))
        record_event(db,id,'folder_deleted_'+mode,before,snapshot(db,id),timestamp=timestamp)
    for id,_ in folders:
        db.execute('DELETE FROM folders WHERE id=?',(id,))
