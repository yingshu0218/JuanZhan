-- Scoped read-only external agent credentials. No document/parse data changes.
CREATE TABLE agent_tokens (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
 token_hash TEXT NOT NULL UNIQUE,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 rate_window INTEGER NOT NULL DEFAULT 0,
 rate_count INTEGER NOT NULL DEFAULT 0 CHECK(rate_count>=0)
);
CREATE INDEX ix_agent_tokens_expiry ON agent_tokens(expires_at);
CREATE TABLE agent_token_spaces (
 token_id TEXT NOT NULL REFERENCES agent_tokens(id) ON DELETE CASCADE,
 space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
 PRIMARY KEY(token_id,space_id)
);
