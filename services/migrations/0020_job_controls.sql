CREATE TABLE job_controls (
 job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
 mode TEXT NOT NULL CHECK(mode IN ('paused','cancelled','deleted')),
 updated_at TEXT NOT NULL
);
CREATE TABLE job_control_events (
 id TEXT PRIMARY KEY,
 job_id TEXT NOT NULL REFERENCES jobs(id),
 action TEXT NOT NULL CHECK(action IN ('pause','resume','cancel','delete')),
 created_at TEXT NOT NULL
);
CREATE INDEX ix_job_controls_mode ON job_controls(mode,job_id);
CREATE INDEX ix_agent_import_document_revision ON agent_imports(document_id,revision_id);
