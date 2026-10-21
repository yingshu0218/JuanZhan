-- OAuth grants share scoped agent credentials; no document or parse data changes.
CREATE TABLE oauth_clients (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 redirects_json TEXT NOT NULL,
 auth_method TEXT NOT NULL CHECK(auth_method IN ('none','client_secret_basic','client_secret_post')),
 secret_hash TEXT,
 grants_json TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 last_used_at INTEGER
);
CREATE TABLE oauth_requests (
 id TEXT PRIMARY KEY,
 client_id TEXT NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
 session_hash TEXT NOT NULL,
 params_json TEXT NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX ix_oauth_requests_expiry ON oauth_requests(expires_at);
CREATE TABLE oauth_codes (
 code_hash TEXT PRIMARY KEY,
 client_id TEXT NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
 redirect_uri TEXT NOT NULL,
 challenge TEXT NOT NULL,
 resource TEXT NOT NULL,
 spaces_json TEXT NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX ix_oauth_codes_expiry ON oauth_codes(expires_at);
CREATE TABLE oauth_grants (
 id TEXT PRIMARY KEY,
 token_id TEXT NOT NULL UNIQUE REFERENCES agent_tokens(id) ON DELETE CASCADE,
 client_id TEXT NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
 refresh_hash TEXT UNIQUE,
 expires_at INTEGER NOT NULL,
 access_expires_at INTEGER NOT NULL,
 resource TEXT NOT NULL
);
CREATE TABLE oauth_refresh_history (
 token_hash TEXT PRIMARY KEY,
 grant_id TEXT NOT NULL REFERENCES oauth_grants(id) ON DELETE CASCADE
);
CREATE TABLE oauth_rate (
 key TEXT PRIMARY KEY,
 window INTEGER NOT NULL,
 count INTEGER NOT NULL CHECK(count>=0)
);
CREATE TRIGGER oauth_client_revoke BEFORE DELETE ON oauth_clients BEGIN
 DELETE FROM agent_tokens WHERE id IN (SELECT token_id FROM oauth_grants WHERE client_id=OLD.id);
END;
