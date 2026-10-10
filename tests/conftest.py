import os
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import pytest

from survey_machine.application import create_app
from survey_machine.config import Settings

ADMIN_KEY = "test-administrator-key-for-survey-machine-12345"


@pytest.fixture
def client():
    # TEST_DATABASE_URL must point to a disposable database. CI supplies its own.
    url = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    if url != "sqlite:///:memory:" and not urlsplit(url).path.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must name a disposable database ending in _test.")
    settings = Settings(admin_api_key=ADMIN_KEY, database_url=url,
                        cors_origins=("https://consumer.example",))
    with TestClient(create_app(settings)) as connection:
        connection.headers["X-API-Key"] = ADMIN_KEY
        yield connection
        if os.environ.get("TEST_DATABASE_URL"):
            # The explicit _test guard above is required because this database is cleared.
            database = connection.app.state.database
            for table in ("responses", "surveys", "api_keys", "sessions", "auth_attempts"):
                connection.portal.call(database.execute, f"DELETE FROM {table}")
            connection.portal.call(database.execute, "DELETE FROM workspaces WHERE id <> 'default'")


@pytest.fixture
def make_survey(client):
    def create(*, named=False, publish=True, questions=None):
        data = {"title": "A useful survey", "respondent_mode": "named" if named else "anonymous",
                "questions": questions if questions is not None else [
                    {"type": "short_text", "title": "What do you think?", "required": True},
                    {"type": "rating", "title": "How was it?", "required": False},
                ]}
        response = client.post("/api/v1/surveys", json=data)
        assert response.status_code == 201, response.text
        survey = response.json()
        if publish:
            response = client.post(f"/api/v1/surveys/{survey['id']}/publish")
            assert response.status_code == 200, response.text
            survey = response.json()
        return survey
    return create
