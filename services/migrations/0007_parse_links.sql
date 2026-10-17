-- Scope every logical link to its owning parse/revision; old applied SQL stays immutable.
CREATE TRIGGER parse_asset_order_scope_insert BEFORE INSERT ON parse_asset_order
WHEN NOT EXISTS(SELECT 1 FROM derived_assets WHERE id=NEW.derived_asset_id AND parse_run_id=NEW.parse_run_id)
BEGIN SELECT RAISE(ABORT,'parse asset scope mismatch'); END;
CREATE TRIGGER parse_asset_order_scope_update BEFORE UPDATE OF parse_run_id,derived_asset_id ON parse_asset_order
WHEN NOT EXISTS(SELECT 1 FROM derived_assets WHERE id=NEW.derived_asset_id AND parse_run_id=NEW.parse_run_id)
BEGIN SELECT RAISE(ABORT,'parse asset scope mismatch'); END;
CREATE TRIGGER parse_attempt_scope_insert BEFORE INSERT ON parse_attempts
WHEN NOT EXISTS(SELECT 1 FROM parse_runs p JOIN parse_requests q ON q.document_id=p.document_id AND q.revision_id=p.revision_id
                WHERE p.id=NEW.parse_run_id AND q.sequence=NEW.request_sequence)
BEGIN SELECT RAISE(ABORT,'parse attempt scope mismatch'); END;
CREATE TRIGGER parse_attempt_scope_update BEFORE UPDATE OF parse_run_id,request_sequence ON parse_attempts
WHEN NOT EXISTS(SELECT 1 FROM parse_runs p JOIN parse_requests q ON q.document_id=p.document_id AND q.revision_id=p.revision_id
                WHERE p.id=NEW.parse_run_id AND q.sequence=NEW.request_sequence)
BEGIN SELECT RAISE(ABORT,'parse attempt scope mismatch'); END;
