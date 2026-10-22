CREATE TABLE revision_markdown (
 revision_id TEXT PRIMARY KEY REFERENCES file_revisions(id) ON DELETE CASCADE,
 parse_run_id TEXT REFERENCES parse_runs(id) ON DELETE SET NULL,
 source_signature TEXT NOT NULL,
 content_status TEXT NOT NULL CHECK(content_status IN ('content','empty','unavailable')),
 storage_key TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
 created_at TEXT NOT NULL
);
CREATE INDEX ix_revision_markdown_key ON revision_markdown(storage_key);
DROP VIEW derived_object_references;
CREATE VIEW derived_object_references AS
 SELECT storage_key FROM derived_assets
 UNION SELECT storage_key FROM reading_previews
 UNION SELECT storage_key FROM revision_markdown;
CREATE TABLE markdown_dirty (
 revision_id TEXT PRIMARY KEY REFERENCES file_revisions(id) ON DELETE CASCADE,
 generation INTEGER NOT NULL DEFAULT 1,
 scheduled_generation INTEGER NOT NULL DEFAULT 0
);
INSERT INTO markdown_dirty(revision_id) SELECT id FROM file_revisions;
CREATE TRIGGER markdown_revision_insert AFTER INSERT ON file_revisions BEGIN
 INSERT INTO markdown_dirty(revision_id) VALUES (NEW.id);
END;
CREATE TRIGGER markdown_parse_insert AFTER INSERT ON parse_runs BEGIN
 INSERT INTO markdown_dirty(revision_id) VALUES (NEW.revision_id)
 ON CONFLICT(revision_id) DO UPDATE SET generation=generation+1;
END;
CREATE TRIGGER markdown_parse_status AFTER UPDATE OF status ON parse_runs WHEN OLD.status<>NEW.status BEGIN
 INSERT INTO markdown_dirty(revision_id) VALUES (NEW.revision_id)
 ON CONFLICT(revision_id) DO UPDATE SET generation=generation+1;
END;
