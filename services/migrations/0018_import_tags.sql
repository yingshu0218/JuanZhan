CREATE TABLE document_tag_policy (
 document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
 revision_id TEXT REFERENCES file_revisions(id) ON DELETE SET NULL,
 source TEXT NOT NULL CHECK(source IN ('platform','agent')),
 manual_locked INTEGER NOT NULL DEFAULT 0 CHECK(manual_locked IN (0,1))
);
CREATE TABLE automatic_document_tags (
 document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
 PRIMARY KEY(document_id,tag_id)
);
CREATE TABLE saved_filters (
 id TEXT PRIMARY KEY,
 space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
 name TEXT NOT NULL,
 name_norm TEXT NOT NULL,
 criteria_json TEXT NOT NULL CHECK(json_valid(criteria_json)),
 UNIQUE(space_id,name_norm)
);
