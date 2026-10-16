CREATE TABLE auth_admin (
  id INTEGER PRIMARY KEY CHECK(id=1),
  password_hash TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE auth_sessions (
  token_hash TEXT PRIMARY KEY,
  csrf_token TEXT NOT NULL,
  authenticated INTEGER NOT NULL CHECK(authenticated IN (0,1)),
  expires_at INTEGER NOT NULL
);
CREATE INDEX ix_auth_sessions_expiry ON auth_sessions(expires_at);
CREATE TABLE auth_api_tokens (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX ix_auth_tokens_expiry ON auth_api_tokens(expires_at);
CREATE TABLE auth_login_throttle (
  id INTEGER PRIMARY KEY CHECK(id=1),
  failures INTEGER NOT NULL,
  window_start INTEGER NOT NULL
);
INSERT INTO schema_migrations(version,applied_at)
VALUES ('0.4.1',strftime('%Y-%m-%dT%H:%M:%fZ','now'));
