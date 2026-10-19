CREATE TABLE source_scan_schedules (
 source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
 version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1),
 next_due_at REAL,
 last_job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL
);
CREATE INDEX source_scan_due ON source_scan_schedules(next_due_at);
INSERT INTO source_scan_schedules(source_id,next_due_at)
 SELECT id,CASE WHEN scan_interval_minutes>0 THEN unixepoch()+scan_interval_minutes*60 ELSE NULL END FROM sources;
CREATE TRIGGER source_scan_schedule_insert AFTER INSERT ON sources BEGIN
 INSERT INTO source_scan_schedules(source_id,next_due_at)
 VALUES (NEW.id,CASE WHEN NEW.scan_interval_minutes>0 THEN unixepoch()+NEW.scan_interval_minutes*60 ELSE NULL END);
END;
CREATE TRIGGER source_scan_schedule_update AFTER UPDATE OF scan_interval_minutes ON sources
 WHEN NEW.scan_interval_minutes IS NOT OLD.scan_interval_minutes BEGIN
 UPDATE source_scan_schedules SET version=version+1,
 next_due_at=CASE WHEN NEW.scan_interval_minutes>0 THEN unixepoch()+NEW.scan_interval_minutes*60 ELSE NULL END
 WHERE source_id=NEW.id;
END;
