CREATE TABLE IF NOT EXISTS surveys (
    id TEXT PRIMARY KEY,
    share_token TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    respondent_mode TEXT NOT NULL CHECK (respondent_mode IN ('anonymous', 'named')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'closed')),
    questions TEXT NOT NULL DEFAULT '[]',
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    id TEXT PRIMARY KEY,
    survey_id TEXT NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
    submission_id TEXT NOT NULL,
    respondent_name TEXT,
    answers TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    UNIQUE (survey_id, submission_id)
);

CREATE INDEX IF NOT EXISTS responses_survey_time ON responses(survey_id, submitted_at, id);
CREATE INDEX IF NOT EXISTS surveys_updated ON surveys(updated_at, id);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    key_digest TEXT NOT NULL UNIQUE,
    scopes TEXT NOT NULL,
    created_at TEXT NOT NULL
);
