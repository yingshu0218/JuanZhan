CREATE TABLE search_dirty (
 document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
 generation INTEGER NOT NULL DEFAULT 1 CHECK(generation>0),
 scheduled_generation INTEGER NOT NULL DEFAULT 0 CHECK(scheduled_generation>=0),
 last_error TEXT
);
ALTER TABLE document_search_state ADD COLUMN generation INTEGER NOT NULL DEFAULT 0;
INSERT INTO search_dirty(document_id) SELECT id FROM documents;
CREATE TRIGGER documents_search_insert AFTER INSERT ON documents BEGIN
INSERT INTO search_dirty(document_id) SELECT NEW.id WHERE EXISTS(SELECT 1 FROM documents WHERE id=NEW.id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER documents_search_update AFTER UPDATE OF title,description,document_date,document_type_id,current_revision_id,current_parse_run_id,document_version,deleted_at ON documents BEGIN
INSERT INTO search_dirty(document_id) SELECT NEW.id WHERE EXISTS(SELECT 1 FROM documents WHERE id=NEW.id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER documents_search_delete AFTER DELETE ON documents BEGIN
DELETE FROM document_search WHERE document_id=OLD.id;END;
CREATE TRIGGER document_tags_search_insert AFTER INSERT ON document_tags BEGIN
INSERT INTO search_dirty(document_id) SELECT NEW.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=NEW.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER document_tags_search_delete AFTER DELETE ON document_tags BEGIN
INSERT INTO search_dirty(document_id) SELECT OLD.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER document_tags_search_update AFTER UPDATE ON document_tags BEGIN
INSERT INTO search_dirty(document_id) SELECT OLD.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
INSERT INTO search_dirty(document_id) SELECT NEW.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=NEW.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER tags_search_update AFTER UPDATE OF name ON tags BEGIN
INSERT INTO search_dirty(document_id) SELECT d.id FROM documents d JOIN document_tags t ON t.document_id=d.id WHERE t.tag_id=NEW.id ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER metadata_search_insert AFTER INSERT ON metadata_values BEGIN
INSERT INTO search_dirty(document_id) SELECT NEW.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=NEW.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER metadata_search_delete AFTER DELETE ON metadata_values BEGIN
INSERT INTO search_dirty(document_id) SELECT OLD.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER metadata_search_update AFTER UPDATE ON metadata_values BEGIN
INSERT INTO search_dirty(document_id) SELECT OLD.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=OLD.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
INSERT INTO search_dirty(document_id) SELECT NEW.document_id WHERE EXISTS(SELECT 1 FROM documents WHERE id=NEW.document_id) ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER fields_search_update AFTER UPDATE OF searchable,is_active ON field_definitions BEGIN
INSERT INTO search_dirty(document_id) SELECT DISTINCT d.id FROM documents d JOIN metadata_values m ON m.document_id=d.id WHERE m.field_definition_id=NEW.id ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE TRIGGER types_search_update AFTER UPDATE OF label ON document_types BEGIN
 INSERT INTO search_dirty(document_id) SELECT id FROM documents WHERE document_type_id=NEW.id
 ON CONFLICT(document_id) DO UPDATE SET generation=generation+1,last_error=NULL;
END;
CREATE INDEX ix_jobs_index_target ON jobs(kind,target_type,target_id,status);
