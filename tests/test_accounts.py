"""Account boundaries are exercised through the public HTTP contract."""

from uuid import uuid4

import pytest

from conftest import ADMIN_KEY

OPERATOR = {"X-API-Key": ADMIN_KEY}
PASSWORD = "A test password with spaces 123!"


@pytest.fixture
def service(client):
    client.headers.pop("X-API-Key")
    return client


def invite(service, name="Customer"):
    email = f"{uuid4().hex}@example.com"
    response = service.post("/api/v1/operator/customers", headers=OPERATOR, json={"name": name, "email": email})
    assert response.status_code == 201, response.text
    return response.json()


def activate(service, invitation, password=PASSWORD):
    response = service.post("/api/v1/auth/activate", json={
        "email": invitation["email"], "password": password, "token": invitation["activation_path"].split("/")[-1],
    })
    assert response.status_code == 200, response.text
    return {"Cookie": f"sm_session={response.cookies['sm_session']}", "X-CSRF-Token": response.json()["csrf_token"]}


def survey(service, headers):
    result = service.post("/api/v1/surveys", headers=headers, json={
        "title": "Customer survey", "questions": [{"title": "Thoughts?", "type": "short_text", "required": True}],
    })
    assert result.status_code == 201, result.text
    return result.json()


def test_accounts_cannot_access_each_others_data_or_keys(service):
    a, b = invite(service, "A"), invite(service, "B")
    first, second = activate(service, a), activate(service, b)
    owned = survey(service, first)
    sid = owned["id"]
    service.post(f"/api/v1/surveys/{sid}/publish", headers=first).raise_for_status()
    token = owned["public_path"].split("/")[-1]
    response = service.post(f"/api/v1/public/surveys/{token}/responses", json={"answers": {owned["questions"][0]["id"]: "Private result"}})
    assert response.status_code == 201
    rid = response.json()["id"]
    assert service.get("/api/v1/surveys", headers=second).json()["total"] == 0
    assert service.get("/api/v1/stats", headers=second).json() == {"surveys": 0, "published": 0, "responses": 0}
    assert service.get("/api/v1/stats", headers=first).json()["responses"] == 1
    for suffix in ("", "/responses", "/summary", "/export?format=json", "/export?format=csv"):
        assert service.get(f"/api/v1/surveys/{sid}{suffix}", headers=second).status_code == 404
    for action in ("publish", "close", "duplicate"):
        assert service.post(f"/api/v1/surveys/{sid}/{action}", headers=second).status_code == 404
    assert service.put(f"/api/v1/surveys/{sid}", headers=second, json={"title": "Stolen", "revision": 1}).status_code == 404
    assert service.delete(f"/api/v1/surveys/{sid}", headers=second).status_code == 404
    assert service.delete(f"/api/v1/surveys/{sid}/responses/{rid}", headers=second).status_code == 404
    created = service.post("/api/v1/api-keys", headers=first, json={"name": "A integration", "scopes": ["surveys:read"]}).json()
    assert service.get("/api/v1/api-keys", headers=second).json() == []
    assert service.delete(f"/api/v1/api-keys/{created['id']}", headers=second).status_code == 404
    scoped = {"X-API-Key": created["key"], "X-Workspace-ID": b["id"]}
    assert service.get("/api/v1/surveys", headers=scoped).json()["items"][0]["id"] == sid
    assert service.get("/api/v1/operator/customers", headers=first).status_code == 403
    assert service.post("/api/v1/operator/customers", headers=first, json={"name": "No", "email": "no@example.com"}).status_code == 403
    assert service.post(f"/api/v1/operator/customers/{b['id']}/reset", headers=first).status_code == 403
    assert service.put(f"/api/v1/operator/customers/{b['id']}", headers=first, json={"enabled": False}).status_code == 403


def test_password_login_sessions_csrf_and_logout(service):
    customer = invite(service)
    first = activate(service, customer, "  Exact spaces in this password!  ")
    replay = service.post("/api/v1/auth/activate", json={"token": customer["activation_path"].split("/")[-1], "email": customer["email"], "password": PASSWORD})
    assert replay.status_code == 400
    assert service.post("/api/v1/auth/login", json={"email": customer["email"], "password": "Exact spaces in this password!"}).status_code == 401
    login = service.post("/api/v1/auth/login", json={"email": customer["email"].upper(), "password": "  Exact spaces in this password!  "})
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=43200" in cookie
    current = {"Cookie": f"sm_session={login.cookies['sm_session']}", "X-CSRF-Token": login.json()["csrf_token"]}
    assert service.get("/api/v1/auth/check", headers=current).json()["workspace_id"] == customer["id"]
    assert service.post("/api/v1/surveys", headers={"Cookie": current["Cookie"]}, json={"title": "No CSRF"}).status_code == 403
    assert service.post("/api/v1/surveys", headers={**current, "X-CSRF-Token": first["X-CSRF-Token"]}, json={"title": "Wrong CSRF"}).status_code == 403
    assert service.post("/api/v1/auth/logout", headers=current).status_code == 204
    assert service.get("/api/v1/auth/check", headers=current).status_code == 401
    assert service.get("/api/v1/auth/check", headers=first).status_code == 200


def test_recovery_and_disabling_revoke_access(service):
    customer = invite(service)
    original = activate(service, customer)
    data = survey(service, original)
    service.post(f"/api/v1/surveys/{data['id']}/publish", headers=original).raise_for_status()
    key = service.post("/api/v1/api-keys", headers=original, json={"name": "Integration"}).json()["key"]
    reset = service.post(f"/api/v1/operator/customers/{customer['id']}/reset", headers=OPERATOR).json()
    recovered = activate(service, reset, "This is the new account password")
    assert service.get("/api/v1/auth/check", headers=original).status_code == 401
    assert service.get("/api/v1/surveys", headers=recovered).json()["total"] == 1
    assert service.post("/api/v1/auth/login", json={"email": customer["email"], "password": PASSWORD}).status_code == 401
    service.put(f"/api/v1/operator/customers/{customer['id']}", headers=OPERATOR, json={"enabled": False}).raise_for_status()
    assert service.get("/api/v1/auth/check", headers=recovered).status_code == 401
    assert service.get("/api/v1/surveys", headers={"X-API-Key": key}).status_code == 401
    token = data["public_path"].split("/")[-1]
    assert service.get(f"/api/v1/public/surveys/{token}").status_code == 404
    assert service.post(f"/api/v1/public/surveys/{token}/responses", json={"answers": {}}).status_code == 404
    service.put(f"/api/v1/operator/customers/{customer['id']}", headers=OPERATOR, json={"enabled": True}).raise_for_status()
    assert service.get("/api/v1/auth/check", headers=recovered).status_code == 401
    assert service.get("/api/v1/surveys", headers={"X-API-Key": key}).status_code == 200


def test_invitation_email_and_duplicate_accounts(service):
    customer = invite(service)
    duplicate = service.post("/api/v1/operator/customers", headers=OPERATOR, json={"name": "Duplicate", "email": customer["email"].upper()})
    assert duplicate.status_code == 409
    wrong = service.post("/api/v1/auth/activate", json={"token": customer["activation_path"].split("/")[-1], "email": "wrong@example.com", "password": PASSWORD})
    assert wrong.status_code == 400
    reset = service.post(f"/api/v1/operator/customers/{customer['id']}/reset", headers=OPERATOR).json()
    old = service.post("/api/v1/auth/activate", json={"token": customer["activation_path"].split("/")[-1], "email": customer["email"], "password": PASSWORD})
    assert old.status_code == 400
    activate(service, reset)
    listing = service.get("/api/v1/operator/customers", headers=OPERATOR).json()
    assert listing["total"] == 1
    assert set(listing["items"][0]) == {"id", "name", "email", "enabled", "created_at", "status"}


def test_login_rejects_cross_origin_and_limits_attempts(service):
    data = {"email": "unknown@example.com", "password": PASSWORD}
    assert service.post("/api/v1/auth/login", json=data, headers={"Origin": "https://consumer.example"}).status_code == 403
    assert service.post("/api/v1/auth/login", json=data, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    for _ in range(10):
        assert service.post("/api/v1/auth/login", json=data).status_code == 401
    limited = service.post("/api/v1/auth/login", json=data)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
