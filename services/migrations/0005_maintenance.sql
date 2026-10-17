CREATE TABLE source_exclusion_versions (
 source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
 version INTEGER NOT NULL CHECK(version>0)
);
CREATE TABLE source_exclusion_intents (
 job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
 source_entry_id TEXT NOT NULL UNIQUE REFERENCES source_entries(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
 relative_path_norm TEXT NOT NULL
);
CREATE INDEX ix_exclusion_intents_path ON source_exclusion_intents(source_id,relative_path_norm);
CREATE TABLE document_purge_receipts (
 document_id TEXT PRIMARY KEY,
 document_version INTEGER NOT NULL,
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
 created_at TEXT NOT NULL
);
CREATE TABLE managed_gc_candidates (
 storage_key TEXT PRIMARY KEY,
 eligible_after REAL NOT NULL
);
