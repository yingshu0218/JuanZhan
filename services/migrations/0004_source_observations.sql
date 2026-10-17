-- Private mount baseline and consecutive successful missing observations.
CREATE TABLE source_root_baselines (
  source_id TEXT PRIMARY KEY REFERENCES sources(id) ON DELETE CASCADE,
  root_digest TEXT NOT NULL CHECK(length(root_digest)=64)
);
CREATE TABLE source_missing_observations (
  source_entry_id TEXT PRIMARY KEY REFERENCES source_entries(id) ON DELETE CASCADE,
  scan_run_id TEXT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE
);
