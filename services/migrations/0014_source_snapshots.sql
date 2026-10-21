-- Preserve source associations while retaining immutable server-side original bytes.
CREATE TABLE revision_snapshots (
 revision_id TEXT PRIMARY KEY REFERENCES file_revisions(id) ON DELETE CASCADE,
 managed_object_id TEXT NOT NULL REFERENCES managed_objects(id) ON DELETE RESTRICT,
 created_at TEXT NOT NULL
);
CREATE INDEX ix_revision_snapshots_object ON revision_snapshots(managed_object_id);
CREATE TRIGGER revision_snapshot_validate BEFORE INSERT ON revision_snapshots
WHEN NOT EXISTS (
 SELECT 1 FROM file_revisions r JOIN managed_objects o ON o.id=NEW.managed_object_id
 WHERE r.id=NEW.revision_id AND r.storage_kind='external'
 AND r.sha256=o.sha256 AND r.size_bytes=o.size_bytes
) BEGIN SELECT RAISE(ABORT,'Snapshot must match the registered external revision'); END;
CREATE VIEW original_object_references AS
 SELECT document_id,id AS revision_id,managed_object_id FROM file_revisions WHERE managed_object_id IS NOT NULL
 UNION ALL
 SELECT r.document_id,s.revision_id,s.managed_object_id FROM revision_snapshots s JOIN file_revisions r ON r.id=s.revision_id;
