CREATE TABLE backup_records (
 id TEXT PRIMARY KEY,
 origin TEXT NOT NULL CHECK(origin IN ('manual','automatic','imported')),
 job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
 created_at TEXT NOT NULL,
 source_token TEXT,
 artifact_token TEXT,
 archive_sha256 TEXT,
 archive_bytes INTEGER CHECK(archive_bytes IS NULL OR archive_bytes>=0),
 completed_at TEXT,
 deleted_at TEXT,
 CHECK((artifact_token IS NULL AND archive_sha256 IS NULL AND archive_bytes IS NULL AND completed_at IS NULL)
    OR (artifact_token IS NOT NULL AND archive_sha256 IS NOT NULL AND archive_bytes IS NOT NULL AND completed_at IS NOT NULL))
);
CREATE INDEX backup_created ON backup_records(created_at,id);
CREATE TABLE recovery_records (
 id TEXT PRIMARY KEY,
 backup_id TEXT NOT NULL REFERENCES backup_records(id),
 job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
 created_at TEXT NOT NULL,
 artifact_token TEXT,
 completed_at TEXT
);
CREATE TABLE backup_schedule (
 id INTEGER PRIMARY KEY CHECK(id=1),
 version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1),
 interval_minutes INTEGER NOT NULL DEFAULT 0 CHECK(interval_minutes BETWEEN 0 AND 525600),
 keep_count INTEGER NOT NULL DEFAULT 7 CHECK(keep_count BETWEEN 1 AND 100),
 max_age_days INTEGER NOT NULL DEFAULT 30 CHECK(max_age_days BETWEEN 1 AND 3650),
 next_due_at REAL,
 last_job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL
);
INSERT INTO backup_schedule(id) VALUES (1);
