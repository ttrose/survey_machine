import os

from fastapi.testclient import TestClient
import pytest

from survey_machine.application import create_app
from survey_machine.config import Settings

ADMIN_KEY = "test-administrator-key-for-survey-machine-12345"


@pytest.fixture
def client():
    # TEST_DATABASE_URL must point to a disposable database. CI supplies its own.
    settings = Settings(admin_api_key=ADMIN_KEY, database_url=os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:"),
                        cors_origins=("https://consumer.example",))
    with TestClient(create_app(settings)) as connection:
        connection.headers["X-API-Key"] = ADMIN_KEY
        yield connection
        if os.environ.get("TEST_DATABASE_URL"):
            headers = {"X-API-Key": ADMIN_KEY}
            while True:
                surveys = connection.get("/api/v1/surveys?limit=100", headers=headers).json()["items"]
                if not surveys:
                    break
                for survey in surveys:
                    connection.delete(f"/api/v1/surveys/{survey['id']}", headers=headers)
            for key in connection.get("/api/v1/api-keys", headers=headers).json():
                connection.delete(f"/api/v1/api-keys/{key['id']}", headers=headers)


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
