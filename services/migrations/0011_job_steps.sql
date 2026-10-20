-- Persist actual per-attempt processing telemetry; historical jobs remain unknown.
ALTER TABLE jobs ADD COLUMN steps_json TEXT NOT NULL DEFAULT '[]'
 CHECK(json_valid(steps_json) AND json_type(steps_json)='array');
