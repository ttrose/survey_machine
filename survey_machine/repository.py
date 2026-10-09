from datetime import datetime, timezone
import hashlib
import json
import secrets
from uuid import uuid4

from .database import Database
from .models import KeyCreate, Submission, SurveyCreate, SurveyUpdate


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def survey_record(row):
    if row is None:
        return None
    result = dict(row)
    result["questions"] = json.loads(result["questions"])
    result["public_path"] = "/s/" + result.pop("share_token")
    result.setdefault("response_count", 0)
    return result


def response_record(row):
    result = {k: row[k] for k in ("id", "submitted_at", "respondent_name")}
    result["answers"] = json.loads(row["answers"])
    if result["respondent_name"] is None:
        result.pop("respondent_name")
    return result


class Repository:
    def __init__(self, database: Database):
        self.database = database

    async def get_survey(self, survey_id: str):
        row = await self.database.fetch_one(
            "SELECT s.*, (SELECT COUNT(*) FROM responses r WHERE r.survey_id = s.id) AS response_count FROM surveys s WHERE s.id = ?",
            (survey_id,),
        )
        return survey_record(row)

    async def list_surveys(self, limit=50, offset=0, status=None, search=None):
        clauses, params = [], []
        if status:
            clauses.append("s.status = ?")
            params.append(status)
        if search:
            clauses.append("LOWER(s.title) LIKE ? ESCAPE '\\'")
            escaped = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append("%" + escaped + "%")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        count = await self.database.fetch_one("SELECT COUNT(*) AS total FROM surveys s" + where, tuple(params))
        rows = await self.database.fetch_all(
            "SELECT s.*, (SELECT COUNT(*) FROM responses r WHERE r.survey_id = s.id) AS response_count FROM surveys s" + where +
            " ORDER BY s.updated_at DESC, s.id DESC LIMIT ? OFFSET ?", tuple(params + [limit, offset]),
        )
        return {"items": [survey_record(row) for row in rows], "total": count["total"], "limit": limit, "offset": offset}

    async def create_survey(self, survey: SurveyCreate):
        survey_id, token, timestamp = str(uuid4()), secrets.token_urlsafe(24), now()
        await self.database.execute(
            "INSERT INTO surveys(id, share_token, title, description, respondent_mode, questions, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (survey_id, token, survey.title, survey.description, survey.respondent_mode,
             encode([q.model_dump(mode="json") for q in survey.questions]), timestamp, timestamp),
        )
        return await self.get_survey(survey_id)

    async def update_survey(self, survey_id: str, survey: SurveyUpdate):
        changed = await self.database.execute(
            "UPDATE surveys SET title = ?, description = ?, respondent_mode = ?, questions = ?, updated_at = ?, revision = revision + 1 WHERE id = ? AND status = 'draft' AND revision = ?",
            (survey.title, survey.description, survey.respondent_mode, encode([q.model_dump(mode="json") for q in survey.questions]), now(), survey_id, survey.revision),
        )
        return await self.get_survey(survey_id) if changed else None

    async def change_status(self, survey_id: str, status: str, revision: int):
        timestamp = now()
        changed = await self.database.execute(
            "UPDATE surveys SET status = ?, updated_at = ?, published_at = COALESCE(published_at, ?), revision = revision + 1 WHERE id = ? AND revision = ?",
            (status, timestamp, timestamp, survey_id, revision),
        )
        return await self.get_survey(survey_id) if changed else None

    async def delete_survey(self, survey_id: str):
        return await self.database.execute("DELETE FROM surveys WHERE id = ?", (survey_id,))

    async def get_public_survey(self, token: str):
        return survey_record(await self.database.fetch_one("SELECT * FROM surveys WHERE share_token = ?", (token,)))

    async def add_response(self, survey: dict, submission: Submission, answers: dict):
        response_id, timestamp = str(uuid4()), now()
        # The status/revision check and insert happen in one SQL statement. A close
        # or publish racing this request cannot accept a stale form definition.
        await self.database.execute(
            "INSERT INTO responses(id, survey_id, submission_id, respondent_name, answers, submitted_at) "
            "SELECT ?, ?, ?, ?, ?, ? FROM surveys WHERE id = ? AND status = 'published' AND revision = ? "
            "ON CONFLICT(survey_id, submission_id) DO NOTHING",
            (response_id, survey["id"], str(submission.submission_id), submission.respondent_name, encode(answers), timestamp, survey["id"], survey["revision"]),
        )
        row = await self.database.fetch_one("SELECT * FROM responses WHERE survey_id = ? AND submission_id = ?", (survey["id"], str(submission.submission_id)))
        if not row:
            return None
        if json.loads(row["answers"]) != answers or row["respondent_name"] != submission.respondent_name:
            raise ValueError("This submission ID was already used for different answers.")
        return {"id": row["id"], "submitted_at": row["submitted_at"]}

    async def list_responses(self, survey_id: str, limit=50, offset=0):
        count = await self.database.fetch_one("SELECT COUNT(*) AS total FROM responses WHERE survey_id = ?", (survey_id,))
        rows = await self.database.fetch_all(
            "SELECT * FROM responses WHERE survey_id = ? ORDER BY submitted_at DESC, id DESC LIMIT ? OFFSET ?", (survey_id, limit, offset),
        )
        return {"items": [response_record(row) for row in rows], "total": count["total"], "limit": limit, "offset": offset}

    async def iter_responses(self, survey_id: str, cutoff: str):
        timestamp, response_id = "", ""
        while True:
            rows = await self.database.fetch_all(
                "SELECT * FROM responses WHERE survey_id = ? AND submitted_at <= ? AND "
                "(submitted_at > ? OR (submitted_at = ? AND id > ?)) ORDER BY submitted_at, id LIMIT 250",
                (survey_id, cutoff, timestamp, timestamp, response_id),
            )
            if not rows:
                break
            for row in rows:
                yield response_record(row)
            timestamp, response_id = rows[-1]["submitted_at"], rows[-1]["id"]

    async def delete_response(self, survey_id: str, response_id: str):
        return await self.database.execute("DELETE FROM responses WHERE survey_id = ? AND id = ?", (survey_id, response_id))

    async def create_key(self, data: KeyCreate):
        key = "sm_" + secrets.token_urlsafe(32)
        result = {"id": str(uuid4()), "name": data.name, "prefix": key[:11], "scopes": data.scopes, "created_at": now()}
        await self.database.execute(
            "INSERT INTO api_keys(id, name, prefix, key_digest, scopes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (result["id"], data.name, result["prefix"], hashlib.sha256(key.encode()).hexdigest(), encode(data.scopes), result["created_at"]),
        )
        return {**result, "key": key}

    async def list_keys(self):
        rows = await self.database.fetch_all("SELECT id, name, prefix, scopes, created_at FROM api_keys ORDER BY created_at DESC")
        return [{**row, "scopes": json.loads(row["scopes"])} for row in rows]

    async def find_key(self, key: str):
        row = await self.database.fetch_one("SELECT id, scopes FROM api_keys WHERE key_digest = ?", (hashlib.sha256(key.encode()).hexdigest(),))
        return {**row, "scopes": set(json.loads(row["scopes"]))} if row else None

    async def delete_key(self, key_id: str):
        return await self.database.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
