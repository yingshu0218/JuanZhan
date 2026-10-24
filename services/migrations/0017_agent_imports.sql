ALTER TABLE agent_tokens ADD COLUMN import_enabled INTEGER NOT NULL DEFAULT 0 CHECK(import_enabled IN(0,1));
CREATE TABLE agent_imports (
 id TEXT PRIMARY KEY,
 agent_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 space_id TEXT NOT NULL REFERENCES spaces(id),
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 revision_id TEXT NOT NULL REFERENCES file_revisions(id) ON DELETE CASCADE,
 original_sha256 TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(agent_id,request_id)
);
CREATE TABLE agent_analyses (
 id TEXT PRIMARY KEY,
 import_id TEXT NOT NULL REFERENCES agent_imports(id) ON DELETE CASCADE,
 submission_id TEXT NOT NULL,
 template_id TEXT NOT NULL,
 template_version INTEGER NOT NULL,
 agent_name TEXT NOT NULL,
 payload_sha256 TEXT NOT NULL,
 markdown_text TEXT NOT NULL,
 analysis_json TEXT NOT NULL CHECK(json_valid(analysis_json)),
 created_at TEXT NOT NULL,
 UNIQUE(import_id,submission_id)
);
CREATE TRIGGER agent_analysis_search_insert AFTER INSERT ON agent_analyses BEGIN
 INSERT INTO search_dirty(document_id)
 SELECT document_id FROM agent_imports WHERE id=NEW.import_id
 ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
