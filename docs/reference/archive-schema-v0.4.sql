-- Archive V0.4 — SQLite schema (first migration, SQL executable)
-- SQLite >=3.38 (JSON functions) with FTS5 enabled; app must PRAGMA foreign_keys=ON for EVERY connection.
-- All timestamps are UTC RFC3339 text with trailing Z; application generates UUID/ULID text IDs.
-- File paths are private backend-relative keys or normalized source-relative paths, never a user-provided absolute path.
-- Monetary/decimal fields: fixed 4 fractional digits, integer scale 10,000. Enforce absolute value <= 9e12 in API.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

BEGIN;
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS folders (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  parent_id TEXT,
  name TEXT NOT NULL,
  name_norm TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(space_id,id),
  FOREIGN KEY(space_id,parent_id) REFERENCES folders(space_id,id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_folders_sibling_name
  ON folders(space_id,COALESCE(parent_id,'__ROOT__'),name_norm);
CREATE INDEX IF NOT EXISTS ix_folders_parent ON folders(space_id,parent_id);
CREATE TRIGGER IF NOT EXISTS trg_folders_no_self_insert BEFORE INSERT ON folders
  WHEN NEW.parent_id=NEW.id BEGIN SELECT RAISE(ABORT,'folder cycle'); END;
CREATE TRIGGER IF NOT EXISTS trg_folders_no_cycles BEFORE UPDATE OF parent_id,space_id ON folders
  WHEN NEW.parent_id IS NOT NULL
  BEGIN
    SELECT RAISE(ABORT,'folder cycle') WHERE EXISTS (
      WITH RECURSIVE ancestors(id,parent_id) AS (
        SELECT id,parent_id FROM folders WHERE id=NEW.parent_id AND space_id=NEW.space_id
        UNION ALL
        SELECT f.id,f.parent_id FROM folders f JOIN ancestors a ON f.id=a.parent_id
      ) SELECT 1 FROM ancestors WHERE id=NEW.id
    );
  END;
CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  name_norm TEXT NOT NULL,
  color TEXT,
  description TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(space_id,id),
  UNIQUE(space_id,name_norm)
);
CREATE TABLE IF NOT EXISTS document_types (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  type_key TEXT NOT NULL,
  label TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN(0,1)),
  created_at TEXT NOT NULL,
  UNIQUE(space_id,id),
  UNIQUE(space_id,type_key)
);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN('managed','external')),
  root_ref TEXT NOT NULL, -- administrator-managed mount alias (no untrusted absolute paths)
  status TEXT NOT NULL DEFAULT 'ready' CHECK(status IN('ready','scanning','offline','error','disabled')),
  initial_import_policy TEXT NOT NULL DEFAULT 'flat' CHECK(initial_import_policy IN('tree','flat')),
  initial_target_folder_id TEXT,
  initial_triage_status TEXT NOT NULL DEFAULT 'filed' CHECK(initial_triage_status IN('filed','needs_review')),
  initial_import_completed_at TEXT,
  new_file_target_folder_id TEXT,
  scan_interval_minutes INTEGER CHECK(scan_interval_minutes IS NULL OR scan_interval_minutes >= 0),
  last_successful_scan_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(space_id,id),
  FOREIGN KEY(space_id,initial_target_folder_id) REFERENCES folders(space_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(space_id,new_file_target_folder_id) REFERENCES folders(space_id,id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS managed_objects (
  id TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL CHECK(length(sha256)=64),
  size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
  storage_key TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  UNIQUE(sha256,size_bytes)
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE RESTRICT,
  folder_id TEXT,
  document_type_id TEXT,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  document_date TEXT,
  triage_status TEXT NOT NULL DEFAULT 'needs_review' CHECK(triage_status IN('needs_review','filed')),
  is_favorite INTEGER NOT NULL DEFAULT 0 CHECK(is_favorite IN(0,1)),
  current_revision_id TEXT,
  current_parse_run_id TEXT, -- may reference an older revision when current parse failed
  document_version INTEGER NOT NULL DEFAULT 1 CHECK(document_version>0),
  imported_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT,
  UNIQUE(space_id,id),
  FOREIGN KEY(space_id,folder_id) REFERENCES folders(space_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(space_id,document_type_id) REFERENCES document_types(space_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(id,current_revision_id) REFERENCES file_revisions(document_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(id,current_parse_run_id) REFERENCES parse_runs(document_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_documents_folder ON documents(space_id,folder_id,deleted_at);
CREATE INDEX IF NOT EXISTS ix_documents_triage ON documents(space_id,triage_status,imported_at,id);
CREATE INDEX IF NOT EXISTS ix_documents_date ON documents(space_id,document_date,id);
CREATE INDEX IF NOT EXISTS ix_documents_deleted ON documents(space_id,deleted_at);
CREATE TABLE IF NOT EXISTS document_tags (
  document_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  tag_id TEXT NOT NULL,
  PRIMARY KEY(document_id,tag_id),
  FOREIGN KEY(space_id,document_id) REFERENCES documents(space_id,id) ON DELETE CASCADE,
  FOREIGN KEY(space_id,tag_id) REFERENCES tags(space_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_document_tags_tag ON document_tags(tag_id,document_id);
CREATE TABLE IF NOT EXISTS scan_runs (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  mode TEXT NOT NULL CHECK(mode IN('preview','initial','incremental')),
  status TEXT NOT NULL CHECK(status IN('queued','running','completed','failed','cancelled')),
  started_at TEXT,
  finished_at TEXT,
  result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
  error_json TEXT CHECK(error_json IS NULL OR json_valid(error_json)),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_scan_runs_source ON scan_runs(source_id,created_at DESC);
CREATE TABLE IF NOT EXISTS source_entries (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
  space_id TEXT NOT NULL,
  document_id TEXT,
  relative_path_norm TEXT NOT NULL, -- canonical + validated, never begins with '/' or contains '..' segments
  relative_path_display TEXT NOT NULL,
  file_identity_hint TEXT,
  size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
  mtime_ns INTEGER,
  sha256 TEXT CHECK(sha256 IS NULL OR length(sha256)=64),
  status TEXT NOT NULL DEFAULT 'available' CHECK(status IN('available','suspected_missing','missing','needs_match')),
  last_seen_scan_id TEXT REFERENCES scan_runs(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(source_id,relative_path_norm),
  UNIQUE(source_id,id),
  FOREIGN KEY(space_id,source_id) REFERENCES sources(space_id,id) ON DELETE RESTRICT,
  FOREIGN KEY(space_id,document_id) REFERENCES documents(space_id,id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_source_entries_doc ON source_entries(document_id);
CREATE INDEX IF NOT EXISTS ix_source_entries_status ON source_entries(source_id,status);
CREATE TABLE IF NOT EXISTS file_revisions (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  revision_no INTEGER NOT NULL CHECK(revision_no>0),
  storage_kind TEXT NOT NULL CHECK(storage_kind IN('managed','external')),
  managed_object_id TEXT REFERENCES managed_objects(id) ON DELETE RESTRICT,
  source_entry_id TEXT REFERENCES source_entries(id) ON DELETE RESTRICT,
  source_path_at_capture TEXT, -- historical hint; not proof old bytes remain
  sha256 TEXT NOT NULL CHECK(length(sha256)=64),
  size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
  original_filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_modified_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(document_id,revision_no),
  UNIQUE(document_id,id),
  CHECK ((storage_kind='managed' AND managed_object_id IS NOT NULL AND source_entry_id IS NULL)
      OR (storage_kind='external' AND source_entry_id IS NOT NULL AND managed_object_id IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_file_revisions_external ON file_revisions(source_entry_id);
CREATE TABLE IF NOT EXISTS field_definitions (
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  field_key TEXT NOT NULL CHECK(field_key GLOB '[a-z]*' AND field_key NOT GLOB '*[^a-z0-9_]*'),
  label TEXT NOT NULL,
  field_type TEXT NOT NULL CHECK(field_type IN('text','long_text','integer','decimal','date','boolean','single_select')),
  constraints_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(constraints_json)),
  searchable INTEGER NOT NULL DEFAULT 0 CHECK(searchable IN(0,1)),
  filterable INTEGER NOT NULL DEFAULT 0 CHECK(filterable IN(0,1)),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN(0,1)),
  created_at TEXT NOT NULL,
  UNIQUE(space_id,id),
  UNIQUE(space_id,field_key)
);
CREATE TABLE IF NOT EXISTS document_type_fields (
  space_id TEXT NOT NULL,
  document_type_id TEXT NOT NULL,
  field_definition_id TEXT NOT NULL,
  required_for_filing INTEGER NOT NULL DEFAULT 0 CHECK(required_for_filing IN(0,1)),
  display_order INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(document_type_id,field_definition_id),
  FOREIGN KEY(space_id,document_type_id) REFERENCES document_types(space_id,id) ON DELETE CASCADE,
  FOREIGN KEY(space_id,field_definition_id) REFERENCES field_definitions(space_id,id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS parse_runs (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  revision_id TEXT NOT NULL,
  parser_name TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('queued','running','completed','failed','unsupported')),
  text_available INTEGER NOT NULL DEFAULT 0 CHECK(text_available IN(0,1)),
  ocr_used INTEGER NOT NULL DEFAULT 0 CHECK(ocr_used IN(0,1)),
  language TEXT,
  page_count INTEGER CHECK(page_count IS NULL OR page_count > 0),
  started_at TEXT,
  completed_at TEXT,
  warnings_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(warnings_json)),
  error_json TEXT CHECK(error_json IS NULL OR json_valid(error_json)),
  created_at TEXT NOT NULL,
  UNIQUE(document_id,id),
  FOREIGN KEY(document_id,revision_id) REFERENCES file_revisions(document_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_parse_runs_revision ON parse_runs(revision_id,created_at DESC);
CREATE TABLE IF NOT EXISTS metadata_values (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  field_definition_id TEXT NOT NULL,
  value_text TEXT,
  value_integer INTEGER,
  value_decimal_scaled INTEGER CHECK(value_decimal_scaled BETWEEN -90000000000000000 AND 90000000000000000), -- fixed scale=4
  value_date TEXT,
  value_bool INTEGER CHECK(value_bool IS NULL OR value_bool IN(0,1)),
  origin TEXT NOT NULL CHECK(origin IN('manual','imported','rule','extracted')),
  is_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(is_confirmed IN(0,1)),
  source_parse_run_id TEXT REFERENCES parse_runs(id) ON DELETE SET NULL,
  updated_by TEXT NOT NULL DEFAULT 'admin',
  updated_at TEXT NOT NULL,
  UNIQUE(document_id,field_definition_id),
  FOREIGN KEY(space_id,document_id) REFERENCES documents(space_id,id) ON DELETE CASCADE,
  FOREIGN KEY(space_id,field_definition_id) REFERENCES field_definitions(space_id,id) ON DELETE RESTRICT,
  CHECK ((value_text IS NOT NULL)+(value_integer IS NOT NULL)+(value_decimal_scaled IS NOT NULL)+
         (value_date IS NOT NULL)+(value_bool IS NOT NULL)=1)
);
-- Enforce storage-backed revision consistency, not only app-level validation.
CREATE TRIGGER IF NOT EXISTS trg_revisions_external_match_insert BEFORE INSERT ON file_revisions
  WHEN NEW.storage_kind='external'
  BEGIN
    SELECT RAISE(ABORT,'source_entry belongs to another document') WHERE NOT EXISTS (
      SELECT 1 FROM source_entries s WHERE s.id=NEW.source_entry_id AND s.document_id=NEW.document_id
    );
  END;
CREATE TRIGGER IF NOT EXISTS trg_revisions_external_match_update BEFORE UPDATE OF source_entry_id,document_id,storage_kind ON file_revisions
  WHEN NEW.storage_kind='external'
  BEGIN
    SELECT RAISE(ABORT,'source_entry belongs to another document') WHERE NOT EXISTS (
      SELECT 1 FROM source_entries s WHERE s.id=NEW.source_entry_id AND s.document_id=NEW.document_id
    );
  END;
CREATE TRIGGER IF NOT EXISTS trg_revisions_managed_checksum_insert BEFORE INSERT ON file_revisions
  WHEN NEW.storage_kind='managed'
  BEGIN
    SELECT RAISE(ABORT,'managed_object hash/size mismatch') WHERE NOT EXISTS (
      SELECT 1 FROM managed_objects m WHERE m.id=NEW.managed_object_id
        AND m.sha256=NEW.sha256 AND m.size_bytes=NEW.size_bytes
    );
  END;
CREATE TRIGGER IF NOT EXISTS trg_metadata_value_type_insert BEFORE INSERT ON metadata_values
  BEGIN
    SELECT RAISE(ABORT,'metadata value type mismatch') WHERE NOT EXISTS (
      SELECT 1 FROM field_definitions f WHERE f.id=NEW.field_definition_id
        AND ((f.field_type IN('text','long_text','single_select') AND NEW.value_text IS NOT NULL)
          OR (f.field_type='integer' AND NEW.value_integer IS NOT NULL)
          OR (f.field_type='decimal' AND NEW.value_decimal_scaled IS NOT NULL)
          OR (f.field_type='date' AND NEW.value_date IS NOT NULL)
          OR (f.field_type='boolean' AND NEW.value_bool IS NOT NULL))
    );
  END;
CREATE TRIGGER IF NOT EXISTS trg_metadata_value_type_update BEFORE UPDATE OF field_definition_id,value_text,value_integer,value_decimal_scaled,value_date,value_bool ON metadata_values
  BEGIN
    SELECT RAISE(ABORT,'metadata value type mismatch') WHERE NOT EXISTS (
      SELECT 1 FROM field_definitions f WHERE f.id=NEW.field_definition_id
        AND ((f.field_type IN('text','long_text','single_select') AND NEW.value_text IS NOT NULL)
          OR (f.field_type='integer' AND NEW.value_integer IS NOT NULL)
          OR (f.field_type='decimal' AND NEW.value_decimal_scaled IS NOT NULL)
          OR (f.field_type='date' AND NEW.value_date IS NOT NULL)
          OR (f.field_type='boolean' AND NEW.value_bool IS NOT NULL))
    );
  END;
CREATE TRIGGER IF NOT EXISTS trg_field_type_immutable BEFORE UPDATE OF field_type,field_key ON field_definitions
  BEGIN
    SELECT RAISE(ABORT,'field key/type immutable; use a migration');
  END;
CREATE INDEX IF NOT EXISTS ix_metadata_integer ON metadata_values(field_definition_id,value_integer);
CREATE INDEX IF NOT EXISTS ix_metadata_decimal ON metadata_values(field_definition_id,value_decimal_scaled);
CREATE INDEX IF NOT EXISTS ix_metadata_date ON metadata_values(field_definition_id,value_date);
CREATE INDEX IF NOT EXISTS ix_metadata_bool ON metadata_values(field_definition_id,value_bool);
CREATE INDEX IF NOT EXISTS ix_metadata_text ON metadata_values(field_definition_id,value_text);
CREATE TABLE IF NOT EXISTS derived_assets (
  id TEXT PRIMARY KEY,
  parse_run_id TEXT NOT NULL REFERENCES parse_runs(id) ON DELETE CASCADE,
  asset_kind TEXT NOT NULL CHECK(asset_kind IN('plain_text','markdown','json','preview_pdf','thumbnail','image')),
  storage_key TEXT NOT NULL,
  sha256 TEXT NOT NULL CHECK(length(sha256)=64),
  size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
  media_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(parse_run_id,asset_kind,storage_key)
);
CREATE TABLE IF NOT EXISTS content_blocks (
  id TEXT PRIMARY KEY,
  parse_run_id TEXT NOT NULL REFERENCES parse_runs(id) ON DELETE CASCADE,
  block_id TEXT NOT NULL,
  block_index INTEGER NOT NULL CHECK(block_index>=0),
  block_type TEXT NOT NULL CHECK(block_type IN('heading','paragraph','list_item','table','image','page_break','unknown')),
  text_content TEXT NOT NULL DEFAULT '',
  structural_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(structural_json)),
  locator_json TEXT NOT NULL DEFAULT '{"kind":"unknown"}' CHECK(json_valid(locator_json)),
  confidence REAL CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1)),
  UNIQUE(parse_run_id,block_id),
  UNIQUE(parse_run_id,block_index)
);
CREATE INDEX IF NOT EXISTS ix_content_blocks_run ON content_blocks(parse_run_id,block_index);
CREATE TABLE IF NOT EXISTS extracted_metadata (
  id TEXT PRIMARY KEY,
  parse_run_id TEXT NOT NULL REFERENCES parse_runs(id) ON DELETE CASCADE,
  candidate_key TEXT NOT NULL,
  candidate_value_json TEXT NOT NULL CHECK(json_valid(candidate_value_json)),
  provenance_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(provenance_json)),
  confidence REAL CHECK(confidence IS NULL OR (confidence>=0 AND confidence<=1))
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN('upload','scan','scan_preview','parse','ocr','reindex','batch','purge','gc')),
  target_type TEXT NOT NULL,
  target_id TEXT,
  status TEXT NOT NULL CHECK(status IN('queued','running','completed','failed','cancelled')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
  max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts>=1),
  progress_done INTEGER NOT NULL DEFAULT 0 CHECK(progress_done>=0),
  progress_total INTEGER CHECK(progress_total IS NULL OR progress_total>=0),
  payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),
  result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
  error_json TEXT CHECK(error_json IS NULL OR json_valid(error_json)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_jobs_status_created ON jobs(status,created_at);
CREATE TABLE IF NOT EXISTS document_events (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  before_json TEXT CHECK(before_json IS NULL OR json_valid(before_json)),
  after_json TEXT CHECK(after_json IS NULL OR json_valid(after_json)),
  actor TEXT NOT NULL DEFAULT 'admin',
  batch_job_id TEXT REFERENCES jobs(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_document_events_doc ON document_events(document_id,created_at DESC);
CREATE TABLE IF NOT EXISTS source_exclusions (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  relative_path_norm TEXT NOT NULL,
  sha256_hint TEXT CHECK(sha256_hint IS NULL OR length(sha256_hint)=64),
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(source_id,relative_path_norm)
);
-- Search materialization: application writes ONE row per document in a transaction.
-- The indexed_text string must be produced by a VERSIONED Chinese/English tokenizer pipeline.
CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(
  document_id UNINDEXED, indexed_text, tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS document_search_state (
  document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  parse_run_id TEXT REFERENCES parse_runs(id) ON DELETE SET NULL,
  tokenizer_version TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  indexed_at TEXT NOT NULL
);
INSERT OR IGNORE INTO schema_migrations(version,applied_at)
 VALUES('0.4.0',strftime('%Y-%m-%dT%H:%M:%fZ','now'));
COMMIT;
-- IMPORTANT: FTS virtual tables cannot enforce 1 document_id row themselves.
-- Reindex transaction must DELETE document_search WHERE document_id=? then INSERT once,
-- UPDATE document_search_state, COMMIT; hide trashed documents via documents.deleted_at IS NULL.
-- Cross-table validation (revision belongs to document, same-space links, field-value typing)
-- is enforced with composite FKs above plus mandatory application transaction validation.
-- Physical purge is separate from logical trash; managed object GC checks all referencing revisions.
