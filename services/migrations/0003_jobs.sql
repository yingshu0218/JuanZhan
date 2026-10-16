ALTER TABLE jobs ADD COLUMN idempotency_key TEXT;
ALTER TABLE jobs ADD COLUMN request_hash TEXT;
ALTER TABLE jobs ADD COLUMN available_at REAL NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN lease_token TEXT;
ALTER TABLE jobs ADD COLUMN lease_owner TEXT;
ALTER TABLE jobs ADD COLUMN lease_expires_at REAL;
ALTER TABLE jobs ADD COLUMN timeout_seconds REAL NOT NULL DEFAULT 60 CHECK(timeout_seconds>0 AND timeout_seconds<=3600);
ALTER TABLE jobs ADD COLUMN auto_retry INTEGER NOT NULL DEFAULT 1 CHECK(auto_retry IN(0,1));
ALTER TABLE jobs ADD COLUMN retryable INTEGER NOT NULL DEFAULT 0 CHECK(retryable IN(0,1));
CREATE UNIQUE INDEX ux_jobs_idempotency ON jobs(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX ix_jobs_ready ON jobs(status,available_at,created_at,id);
CREATE TABLE worker_heartbeats (
  id TEXT PRIMARY KEY,
  last_seen REAL NOT NULL
);
CREATE TRIGGER trg_jobs_attempts_insert BEFORE INSERT ON jobs
WHEN NEW.attempts>NEW.max_attempts
BEGIN SELECT RAISE(ABORT,'job attempt limit'); END;
CREATE TRIGGER trg_jobs_attempts_update BEFORE UPDATE OF attempts,max_attempts ON jobs
WHEN NEW.attempts>NEW.max_attempts
BEGIN SELECT RAISE(ABORT,'job attempt limit'); END;
INSERT INTO schema_migrations(version,applied_at)
VALUES ('0.4.2',strftime('%Y-%m-%dT%H:%M:%fZ','now'));
