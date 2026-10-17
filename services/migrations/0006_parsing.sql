CREATE TABLE parse_requests (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
 document_id TEXT NOT NULL,
 revision_id TEXT NOT NULL,
 FOREIGN KEY(document_id,revision_id) REFERENCES file_revisions(document_id,id) ON DELETE CASCADE
);
CREATE INDEX ix_parse_requests_document ON parse_requests(document_id,sequence);
INSERT INTO parse_requests(job_id,document_id,revision_id)
 SELECT j.id,j.target_id,r.id FROM jobs j JOIN file_revisions r
 ON r.id=json_extract(j.payload_json,'$.revision_id') AND r.document_id=j.target_id
 WHERE j.kind IN('parse','ocr') AND j.target_type='document' ORDER BY j.created_at,j.id;
CREATE TABLE parse_attempts (
 parse_run_id TEXT PRIMARY KEY REFERENCES parse_runs(id) ON DELETE CASCADE,
 request_sequence INTEGER NOT NULL REFERENCES parse_requests(sequence) ON DELETE CASCADE,
 attempt INTEGER NOT NULL CHECK(attempt>0),
 remote_job_id TEXT,
 UNIQUE(request_sequence,attempt)
);
CREATE TABLE derived_gc_candidates (
 storage_key TEXT PRIMARY KEY,
 eligible_after REAL NOT NULL
);
CREATE TABLE parse_asset_order (
 parse_run_id TEXT NOT NULL REFERENCES parse_runs(id) ON DELETE CASCADE,
 asset_index INTEGER NOT NULL CHECK(asset_index>=0),
 derived_asset_id TEXT NOT NULL REFERENCES derived_assets(id) ON DELETE CASCADE,
 source_artifact_ref TEXT,
 PRIMARY KEY(parse_run_id,asset_index)
);
