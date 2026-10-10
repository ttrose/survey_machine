from contextlib import asynccontextmanager
from dataclasses import replace
import sqlite3
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from conftest import ADMIN_KEY
from survey_machine import Settings, create_app, mount_api


def test_api_only_service_can_run_a_complete_survey_without_the_ui(client):
    settings = replace(client.app.state.settings, serve_ui=False)
    with TestClient(create_app(settings)) as service:
        assert service.get("/health").status_code == 200
        for path in ("/", "/index.html", "/app.js", "/s/example"):
            assert service.get(path).status_code == 404
        assert service.get("/docs").status_code == 200
        assert service.get("/api/v1/surveys").status_code == 401
        key = service.post("/api/v1/api-keys", headers={"X-API-Key": ADMIN_KEY}, json={
            "name": "Existing application", "scopes": ["surveys:read", "surveys:write", "responses:read"],
        }).json()["key"]
        headers = {"X-API-Key": key}
        response = service.post("/api/v1/surveys", headers=headers, json={
            "title": "In our own application", "questions": [{"title": "Your thoughts?", "required": True}],
        })
        assert response.status_code == 201, response.text
        survey = response.json()
        assert service.post(f"/api/v1/surveys/{survey['id']}/publish", headers=headers).status_code == 200
        token = survey["public_path"].split("/")[-1]
        assert service.get(f"/api/v1/public/surveys/{token}").status_code == 200
        submission = {"submission_id": str(uuid4()), "answers": {survey["questions"][0]["id"]: "It works here too"}}
        receipt = service.post(f"/api/v1/public/surveys/{token}/responses", json=submission)
        assert receipt.status_code == 201, receipt.text
        assert service.post(f"/api/v1/public/surveys/{token}/responses", json=submission).json() == receipt.json()
        export = service.get(f"/api/v1/surveys/{survey['id']}/export?format=json", headers=headers)
        assert export.status_code == 200
        assert "It works here too" in export.text


def test_mounted_api_preserves_parent_lifespan_and_closes_its_database(tmp_path):
    events = []

    @asynccontextmanager
    async def lifespan(app):
        assert await service.state.database.fetch_one("SELECT id FROM workspaces WHERE id = 'default'")
        events.append("start")
        yield {"host_state": "preserved"}
        events.append("stop")

    parent = FastAPI(lifespan=lifespan)

    @parent.get("/")
    async def home():
        return {"host": "still works"}

    settings = Settings(admin_api_key=ADMIN_KEY, database_url=f"sqlite:///{tmp_path / 'embedded.sqlite3'}")
    service = mount_api(parent, settings, path="/surveys")
    with TestClient(parent) as client:
        assert client.get("/").json() == {"host": "still works"}
        assert client.app_state["host_state"] == "preserved"
        assert client.get("/surveys/health").status_code == 200
        assert client.get("/surveys/").status_code == 404
        docs = client.get("/surveys/docs")
        assert "/surveys/openapi.json" in docs.text
        assert "https://cdn.jsdelivr.net" in docs.headers["Content-Security-Policy"]
        assert client.get("/surveys/openapi.json").json()["servers"] == [{"url": "/surveys"}]
        assert client.get("/surveys/api/v1/surveys").status_code == 401
        assert client.get("/surveys/api/v1/surveys", headers={"X-API-Key": ADMIN_KEY}).status_code == 200
        assert events == ["start"]
    assert events == ["start", "stop"]
    with pytest.raises(sqlite3.ProgrammingError):
        service.state.database.connection.execute("SELECT 1")


def test_mounted_auth_keeps_origin_protection_and_scopes_its_cookie(tmp_path):
    parent = FastAPI()
    mount_api(parent, Settings(admin_api_key=ADMIN_KEY, database_url=f"sqlite:///{tmp_path / 'accounts.sqlite3'}"))
    with TestClient(parent) as client:
        assert client.post("/surveys/api/v1/auth/login", headers={"Origin": "https://untrusted.example"}, json={}).status_code == 403
        invitation = client.post("/surveys/api/v1/operator/customers", headers={"X-API-Key": ADMIN_KEY}, json={
            "name": "Embedded customer", "email": "embedded@example.com",
        }).json()
        login = client.post("/surveys/api/v1/auth/activate", json={
            "email": invitation["email"], "password": "A long test password 123!",
            "token": invitation["activation_path"].split("/")[-1],
        })
        assert login.status_code == 200, login.text
        assert "Path=/surveys;" in login.headers["set-cookie"]
        assert client.get("/surveys/api/v1/auth/check").status_code == 200
        logout = client.post("/surveys/api/v1/auth/logout", headers={"X-CSRF-Token": login.json()["csrf_token"]})
        assert logout.status_code == 204
        assert "Path=/surveys;" in logout.headers["set-cookie"]
        assert client.get("/surveys/api/v1/auth/check").status_code == 401
