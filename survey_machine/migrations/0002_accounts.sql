CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    onboarding_digest TEXT UNIQUE,
    onboarding_expires INTEGER,
    session_version INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL
);
INSERT INTO workspaces(id, name, created_at)
VALUES ('default', 'Operator workspace', '2026-10-09T00:00:00+00:00');
-- SQLite cannot add a non-null foreign key with a default to a populated table.
-- The application always supplies workspace_id for new records.
ALTER TABLE surveys ADD COLUMN workspace_id TEXT REFERENCES workspaces(id);
ALTER TABLE api_keys ADD COLUMN workspace_id TEXT REFERENCES workspaces(id);
UPDATE surveys SET workspace_id = 'default' WHERE workspace_id IS NULL;
UPDATE api_keys SET workspace_id = 'default' WHERE workspace_id IS NULL;
CREATE INDEX surveys_workspace_updated ON surveys(workspace_id, updated_at, id);
CREATE INDEX keys_workspace ON api_keys(workspace_id);
CREATE TABLE sessions (
    digest TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    session_version INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE auth_attempts (
    bucket TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX auth_attempts_expiry ON auth_attempts(expires_at);
