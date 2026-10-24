"""Bounded import labels; explicit Agent labels supersede deterministic fallback."""
import json
import unicodedata
import uuid
from pathlib import Path
from .catalog import normalize
from .document_records import snapshot
from .document_events import record_event, utc_now

RULES = {
    '合同': ('合同', '协议', 'contract', 'agreement'),
    '账单': ('账单', '发票', 'invoice', 'billing'),
    '会议': ('会议', '纪要', 'meeting', 'minutes'),
    '报告': ('报告', '方案', 'report', 'proposal'),
}
FORMATS = {'pdf','doc','docx','xls','xlsx','ppt','pptx','txt','md','html','htm','epub','rtf','csv','tsv','png','jpg','jpeg','tif','tiff','webp','bmp','gif'}

def clean_names(names):
    result=[];seen=set()
    for name in names:
        name=unicodedata.normalize('NFC',name.strip())
        if not name or len(name)>60 or any(unicodedata.category(c).startswith('C') for c in name):
            raise ValueError('Tag names require 1–60 visible characters')
        norm=normalize(name)
        if norm not in seen:result.append(name);seen.add(norm)
    return result

def lock_manual(db, document_id):
    db.execute("INSERT INTO document_tag_policy(document_id,source,manual_locked) VALUES (?,'platform',1) "
               'ON CONFLICT(document_id) DO UPDATE SET manual_locked=1',(document_id,))

def apply(db, document_id, revision_id, *, text='', names=None, initial=False):
    # Upgrade fixtures may register legacy documents before applying newer migrations.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_tag_policy'").fetchone():return
    doc=snapshot(db,document_id)
    if doc['current_revision_id']!=revision_id or doc['deleted_at'] is not None:return
    policy=db.execute('SELECT manual_locked FROM document_tag_policy WHERE document_id=?',(document_id,)).fetchone()
    if policy and policy[0]:return
    source='agent' if names is not None else 'platform'
    if names is None:
        # Never let a later local parse undo an explicit Agent tag selection (including []).
        analyses=db.execute('SELECT a.analysis_json FROM agent_analyses a JOIN agent_imports i ON i.id=a.import_id '
                            'WHERE i.document_id=? AND i.revision_id=? ORDER BY a.created_at DESC,a.id DESC LIMIT 1',
                            (document_id,revision_id)).fetchone()
        if analyses:
            body=json.loads(analyses[0])
            if body.get('tags') is not None:names=body['tags'];source='agent'
            elif not text:text=body['markdown']
    if names is None:
        filename=db.execute('SELECT original_filename FROM file_revisions WHERE id=?',(revision_id,)).fetchone()[0]
        extension=Path(filename).suffix.lower().lstrip('.')
        content=(filename+'\n'+text[:50000]).casefold()
        names=([extension.upper()] if extension in FORMATS else [])+[label for label,words in RULES.items() if any(word in content for word in words)]
    names=clean_names(names)
    # Bound catalog growth from external clients. Existing names remain reusable.
    ids=[]
    for name in names:
        row=db.execute('SELECT id FROM tags WHERE space_id=? AND name_norm=?',(doc['space_id'],normalize(name))).fetchone()
        if row:ids.append(row[0]);continue
        if db.execute('SELECT count(*) FROM tags WHERE space_id=?',(doc['space_id'],)).fetchone()[0]>=1000:
            if source=='agent':
                from .auth import fail
                fail(413,'TAG_CAPACITY','Space tag capacity reached')
            continue
        tag_id=uuid.uuid4().hex
        db.execute('INSERT INTO tags VALUES (?,?,?,?,?,?,?)',(tag_id,doc['space_id'],name,normalize(name),None,'',utc_now()))
        ids.append(tag_id)
    owned={r[0] for r in db.execute('SELECT tag_id FROM automatic_document_tags WHERE document_id=?',(document_id,))}
    for tag_id in owned-set(ids):
        db.execute('DELETE FROM document_tags WHERE document_id=? AND tag_id=?',(document_id,tag_id))
        db.execute('DELETE FROM automatic_document_tags WHERE document_id=? AND tag_id=?',(document_id,tag_id))
    for tag_id in ids:
        # Existing manual labels must never become automatic-owned.
        existing=db.execute('SELECT 1 FROM document_tags WHERE document_id=? AND tag_id=?',(document_id,tag_id)).fetchone()
        if not existing:
            db.execute('INSERT INTO document_tags VALUES (?,?,?)',(document_id,doc['space_id'],tag_id))
            db.execute('INSERT INTO automatic_document_tags VALUES (?,?)',(document_id,tag_id))
    db.execute('INSERT INTO document_tag_policy(document_id,revision_id,source) VALUES (?,?,?) '
               'ON CONFLICT(document_id) DO UPDATE SET revision_id=excluded.revision_id,source=excluded.source',
               (document_id,revision_id,source))
    if not initial and snapshot(db,document_id)['tag_ids']!=doc['tag_ids']:
        db.execute('UPDATE documents SET document_version=document_version+1,updated_at=? WHERE id=?',(utc_now(),document_id))
        record_event(db,document_id,'document_updated',doc,snapshot(db,document_id),actor='import_tags')
