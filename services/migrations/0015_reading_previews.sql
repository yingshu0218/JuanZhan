-- Rebuildable Office reading PDFs are separate from successful parse artifacts.
CREATE TABLE reading_previews (
 revision_id TEXT PRIMARY KEY REFERENCES file_revisions(id) ON DELETE CASCADE,
 storage_key TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
 renderer TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX ix_reading_previews_key ON reading_previews(storage_key);
CREATE VIEW derived_object_references AS
 SELECT storage_key FROM derived_assets
 UNION
 SELECT storage_key FROM reading_previews;
