import asyncio
import csv
from io import StringIO
import json
from uuid import uuid4

import pytest

from survey_machine.config import Settings
from survey_machine.models import Question, Submission, SurveyCreate, validate_answers, AnswerError
from survey_machine.repository import Repository


def public_url(survey):
    return "/api/v1/public/surveys/" + survey["public_path"].split("/")[-1]


def submit(client, survey, text="A thoughtful answer", **extra):
    return client.post(public_url(survey) + "/responses", json={"answers": {survey["questions"][0]["id"]: text}, **extra})


def test_health_and_openapi(client):
    assert client.get("/health").json()["status"] == "ok"
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-API-Key"
    assert "security" not in schema["paths"]["/api/v1/public/surveys/{token}"]["get"]
    assert client.get("/api/does-not-exist").status_code == 404


def test_private_endpoints_require_key(client, make_survey):
    survey = make_survey()
    client.headers.pop("X-API-Key")
    assert client.get("/api/v1/surveys").status_code == 401
    assert client.get(f"/api/v1/surveys/{survey['id']}/responses").status_code == 401
    assert client.get(f"/api/v1/surveys/{survey['id']}/export").status_code == 401
    assert client.post("/api/v1/surveys", json={"title": "No access"}).status_code == 401
    assert client.get(public_url(survey)).status_code == 200


def test_draft_publish_close_reopen_and_definition_lock(client, make_survey):
    survey = make_survey(publish=False)
    assert client.get(public_url(survey)).status_code == 404
    assert submit(client, survey).status_code == 404
    payload = {k: survey[k] for k in ("title", "description", "respondent_mode", "questions", "revision")}
    payload["description"] = "A better description"
    updated = client.put(f"/api/v1/surveys/{survey['id']}", json=payload)
    assert updated.status_code == 200
    assert client.put(f"/api/v1/surveys/{survey['id']}", json=payload).status_code == 409
    assert client.post(f"/api/v1/surveys/{survey['id']}/publish").status_code == 200
    assert client.put(f"/api/v1/surveys/{survey['id']}", json=updated.json() | {}).status_code == 422
    payload["revision"] = updated.json()["revision"] + 1
    assert client.put(f"/api/v1/surveys/{survey['id']}", json=payload).status_code == 409
    assert submit(client, survey).status_code == 201
    assert client.post(f"/api/v1/surveys/{survey['id']}/close").status_code == 200
    assert client.get(public_url(survey)).status_code == 410
    assert submit(client, survey).status_code == 410
    assert client.post(f"/api/v1/surveys/{survey['id']}/publish").status_code == 200
    assert submit(client, survey).status_code == 201


def test_cannot_publish_empty_survey(client, make_survey):
    survey = make_survey(publish=False, questions=[])
    assert client.post(f"/api/v1/surveys/{survey['id']}/publish").status_code == 422


def test_anonymous_responses_have_no_identifiers(client, make_survey):
    survey = make_survey()
    assert submit(client, survey, respondent_name="Not allowed").status_code == 422
    assert submit(client, survey, metadata={"ip": "127.0.0.1"}).status_code == 422
    client.headers.pop("X-API-Key")
    assert submit(client, survey).status_code == 201
    from conftest import ADMIN_KEY
    records = client.get(f"/api/v1/surveys/{survey['id']}/responses", headers={"X-API-Key": ADMIN_KEY}).json()["items"]
    assert len(records) == 1
    assert set(records[0]) == {"id", "submitted_at", "answers"}
    public = client.get(public_url(survey)).json()
    assert set(public) == {"title", "description", "respondent_mode", "questions"}


def test_named_responses_require_a_name(client, make_survey):
    survey = make_survey(named=True)
    assert submit(client, survey).status_code == 422
    assert submit(client, survey, respondent_name="  ").status_code == 422
    assert submit(client, survey, respondent_name="  Taylor  ").status_code == 201
    result = client.get(f"/api/v1/surveys/{survey['id']}/responses").json()
    assert result["items"][0]["respondent_name"] == "Taylor"


def test_idempotency_and_payload_conflict(client, make_survey):
    survey = make_survey()
    submission_id = str(uuid4())
    first = submit(client, survey, submission_id=submission_id)
    second = submit(client, survey, submission_id=submission_id)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert submit(client, survey, text="Different answer", submission_id=submission_id).status_code == 409
    assert client.get(f"/api/v1/surveys/{survey['id']}/responses").json()["total"] == 1


def test_required_unknown_and_invalid_answers(client, make_survey):
    survey = make_survey()
    assert client.post(public_url(survey) + "/responses", json={"answers": {}}).status_code == 422
    assert client.post(public_url(survey) + "/responses", json={"answers": {"unknown": "Bad"}}).status_code == 422
    assert submit(client, survey, text=True).status_code == 422
    response = submit(client, survey, text="x" * 1001)
    assert response.status_code == 422
    assert "x" * 1001 not in response.text


@pytest.mark.parametrize("kind,options,bad,good", [
    ("email", [], "not an email", "hello@example.com"),
    ("number", [], True, 0),
    ("number", [], "4", -3.5),
    ("rating", [], 2.5, 5),
    ("rating", [], 6, 1),
    ("date", [], "2026-02-30", "2026-10-09"),
    ("date", [], "20261009", "2026-10-09"),
    ("single_choice", ["A", "B"], "C", "A"),
    ("multiple_choice", ["A", "B"], ["A", "A"], ["A", "B"]),
    ("multiple_choice", ["A", "B"], [1], ["B"]),
])
def test_question_validation(kind, options, bad, good):
    question = Question(type=kind, title="Question", required=True, options=options)
    survey = SurveyCreate(title="Survey", questions=[question])
    with pytest.raises(AnswerError):
        validate_answers(survey, Submission(answers={str(question.id): bad}))
    assert validate_answers(survey, Submission(answers={str(question.id): good}))[str(question.id)] == good


def test_api_key_permissions_revocation_and_secret_storage(client, make_survey):
    survey = make_survey()
    key = client.post("/api/v1/api-keys", json={"name": "Read only", "scopes": ["surveys:read"]}).json()
    assert key["key"].startswith("sm_")
    listed = client.get("/api/v1/api-keys").json()
    assert "key" not in listed[0] and "key_digest" not in listed[0]
    headers = {"X-API-Key": key["key"]}
    assert client.get("/api/v1/surveys", headers=headers).status_code == 200
    assert client.post("/api/v1/surveys", headers=headers, json={"title": "Denied"}).status_code == 403
    assert client.get(f"/api/v1/surveys/{survey['id']}/responses", headers=headers).status_code == 403
    assert client.post("/api/v1/api-keys", headers=headers, json={"name": "Escalation"}).status_code == 403
    assert client.get("/api/v1/auth/check", headers=headers).status_code == 403
    assert client.delete(f"/api/v1/api-keys/{key['id']}").status_code == 204
    assert client.get("/api/v1/surveys", headers=headers).status_code == 401


def test_write_key_cannot_delete_response_data(client, make_survey):
    survey = make_survey()
    key = client.post("/api/v1/api-keys", json={"name": "Creator", "scopes": ["surveys:write"]}).json()
    assert client.delete(f"/api/v1/surveys/{survey['id']}", headers={"X-API-Key": key["key"]}).status_code == 403


def test_summary_and_safe_csv_json_exports(client, make_survey):
    survey = make_survey(named=True, questions=[
        {"title": "=Dangerous header", "type": "short_text", "required": True},
        {"title": "Rating", "type": "rating", "required": True},
        {"title": "Choices", "type": "multiple_choice", "options": ["A", "B"]},
    ])
    ids = [q["id"] for q in survey["questions"]]
    for rating in (1, 5):
        response = client.post(public_url(survey) + "/responses", json={"respondent_name": "=HYPERLINK(\"bad\")",
            "answers": {ids[0]: "  =2+2", ids[1]: rating, ids[2]: ["A", "B"]}})
        assert response.status_code == 201
    summary = client.get(f"/api/v1/surveys/{survey['id']}/summary").json()
    assert summary["total"] == 2
    assert summary["questions"][1]["average"] == 3
    assert summary["questions"][2]["counts"] == {"A": 2, "B": 2}
    csv_response = client.get(f"/api/v1/surveys/{survey['id']}/export?format=csv")
    rows = list(csv.reader(StringIO(csv_response.text.lstrip("\ufeff"))))
    assert len(rows) == 3
    assert rows[0][3].startswith("'=")
    assert rows[1][2].startswith("'=") and rows[1][3] == "'=2+2"
    assert "attachment" in csv_response.headers["content-disposition"]
    raw = client.get(f"/api/v1/surveys/{survey['id']}/export?format=json").json()
    assert raw[0]["answers"][ids[0]] == "=2+2"
    assert len(raw) == 2


def test_pagination_search_duplication_and_cascade_delete(client, make_survey):
    survey = make_survey()
    receipt = submit(client, survey).json()
    cloned = client.post(f"/api/v1/surveys/{survey['id']}/duplicate").json()
    assert cloned["status"] == "draft" and cloned["response_count"] == 0
    assert cloned["public_path"] != survey["public_path"]
    assert cloned["questions"][0]["id"] != survey["questions"][0]["id"]
    page = client.get("/api/v1/surveys?limit=1&offset=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get("/api/v1/surveys?search=%25").json()["total"] == 0
    assert client.delete(f"/api/v1/surveys/{survey['id']}/responses/{receipt['id']}").status_code == 204
    assert client.get(f"/api/v1/surveys/{survey['id']}/responses").json()["total"] == 0
    assert submit(client, survey).status_code == 201
    assert client.delete(f"/api/v1/surveys/{survey['id']}").status_code == 204
    assert client.get(public_url(survey)).status_code == 404
    assert client.get("/api/v1/stats").json()["responses"] == 0


def test_close_race_prevents_stale_response_insert(client, make_survey):
    survey = make_survey()
    assert client.post(f"/api/v1/surveys/{survey['id']}/close").status_code == 200
    repository = Repository(client.app.state.database)
    submission = Submission(answers={survey["questions"][0]["id"]: "Late answer"})
    result = client.portal.call(repository.add_response, survey, submission, submission.answers)
    assert result is None
    assert client.get(f"/api/v1/surveys/{survey['id']}/responses").json()["total"] == 0


def test_body_limit_and_cors_policy(client):
    large = client.post("/api/v1/surveys", content=b"x" * (512 * 1024 + 1))
    assert large.status_code == 413
    allowed = client.options("/api/v1/surveys", headers={"Origin": "https://consumer.example", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-api-key"})
    assert allowed.status_code == 204 and allowed.headers["access-control-allow-origin"] == "https://consumer.example"
    denied = client.options("/api/v1/surveys", headers={"Origin": "https://consumer.example.evil", "Access-Control-Request-Method": "GET"})
    assert denied.status_code == 403
    assert "access-control-allow-origin" not in denied.headers
    assert "frame-ancestors 'self'" in client.get("/").headers["content-security-policy"]
    assert "frame-ancestors *" in client.get("/s/test").headers["content-security-policy"]


def test_no_insecure_default_key():
    for key in ("", "short", "replace-with-a-random-secret-at-least-32-characters"):
        with pytest.raises(ValueError):
            Settings(admin_api_key=key)
