import asyncio
import hashlib
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from conftest import ADMIN_KEY
from survey_machine.application import create_app
from survey_machine.config import Settings


def test_populated_first_release_database_migrates_without_losing_data(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    survey_id, response_id, key_id = (str(uuid4()) for _ in range(3))
    old_key = "sm_legacy-integration-key-for-migration-test"
    with sqlite3.connect(path) as database:
        database.execute("PRAGMA foreign_keys = ON")
        database.executescript((Path(__file__).parents[1] / "survey_machine/migrations/0001_initial.sql").read_text())
        database.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
        database.execute("INSERT INTO schema_migrations VALUES ('0001_initial.sql')")
        database.execute("INSERT INTO surveys(id, share_token, title, respondent_mode, created_at, updated_at) VALUES (?, ?, 'Existing survey', 'anonymous', '2026-10-09', '2026-10-09')", (survey_id, "legacy-share-token"))
        database.execute("INSERT INTO responses(id, survey_id, submission_id, answers, submitted_at) VALUES (?, ?, ?, '{}', '2026-10-09')", (response_id, survey_id, str(uuid4())))
        database.execute("INSERT INTO api_keys(id, name, prefix, key_digest, scopes, created_at) VALUES (?, 'Existing key', 'sm_legacy', ?, '[\"surveys:read\"]', '2026-10-09')", (key_id, hashlib.sha256(old_key.encode()).hexdigest()))
    with TestClient(create_app(Settings(admin_api_key=ADMIN_KEY, database_url=f"sqlite:///{path}"))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/stats", headers={"X-API-Key": ADMIN_KEY}).json()["responses"] == 1
        listing = client.get("/api/v1/surveys", headers={"X-API-Key": old_key}).json()
        assert listing["items"][0]["id"] == survey_id
        assert listing["items"][0]["response_count"] == 1
    # Reopening the same database must not reapply either migration.
    with TestClient(create_app(Settings(admin_api_key=ADMIN_KEY, database_url=f"sqlite:///{path}"))) as client:
        assert client.get("/health").status_code == 200


def test_health_checks_schema_readiness(client):
    client.portal.call(client.app.state.database.execute, "ALTER TABLE auth_attempts RENAME TO unavailable_attempts")
    try:
        assert client.get("/health").status_code == 503
    finally:
        client.portal.call(client.app.state.database.execute, "ALTER TABLE unavailable_attempts RENAME TO auth_attempts")
