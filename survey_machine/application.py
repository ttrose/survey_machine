from contextlib import asynccontextmanager
import csv
from decimal import Decimal
from io import StringIO
import secrets
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import APIKeyHeader

from . import __version__
from .config import Settings
from .database import D1Database, open_database
from .middleware import SecurityMiddleware
from .models import (
    ALL_SCOPES, AnswerError, KeyCreate, KeyCreated, KeyOut, PublicSurvey, QuestionSummary,
    QuestionType, Receipt, ResponsePage, ResultsSummary, Submission, SurveyCreate,
    SurveyOut, SurveyPage, SurveyUpdate, validate_answers,
)
from .repository import Repository, encode, now


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_settings(request: Request):
    if "env" in request.scope:
        try:
            return Settings(admin_api_key=str(request.scope["env"].ADMIN_API_KEY))
        except (AttributeError, ValueError):
            raise HTTPException(503, "The workspace administrator has not configured the service.")
    return request.app.state.settings


async def get_repository(request: Request):
    if "env" in request.scope:
        if not hasattr(request.state, "repository"):
            request.state.repository = Repository(D1Database(request.scope["env"].DB))
        return request.state.repository
    return Repository(request.app.state.database)


Repo = Annotated[Repository, Depends(get_repository)]


async def authenticate(
    key: Annotated[str | None, Depends(api_key_header)],
    repository: Repo,
    settings: Annotated[Settings, Depends(get_settings)],
):
    if not key or len(key) > 256:
        raise HTTPException(401, "Provide a valid X-API-Key header.")
    if secrets.compare_digest(key.encode(), settings.admin_api_key.encode()):
        return {"owner": True, "scopes": ALL_SCOPES}
    principal = await repository.find_key(key)
    if principal is None:
        raise HTTPException(401, "Provide a valid X-API-Key header.")
    return {**principal, "owner": False}


def require_scope(scope):
    async def check(principal: Annotated[dict, Depends(authenticate)]):
        if scope not in principal["scopes"]:
            raise HTTPException(403, f"This API key requires the {scope} permission.")
        return principal
    return check


async def require_owner(principal: Annotated[dict, Depends(authenticate)]):
    if not principal["owner"]:
        raise HTTPException(403, "This operation requires the workspace administrator key.")
    return principal


async def must_get_survey(repository, survey_id):
    result = await repository.get_survey(str(survey_id))
    if result is None:
        raise HTTPException(404, "Survey not found.")
    return result


async def must_get_public(repository, token):
    result = await repository.get_public_survey(token)
    if result is None or result["status"] == "draft":
        raise HTTPException(404, "Survey not found.")
    if result["status"] == "closed":
        raise HTTPException(410, "This survey has closed and is no longer accepting responses.")
    return result


def csv_cell(value):
    if isinstance(value, list):
        value = encode(value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def create_app(settings: Settings | None = None, *, worker: bool = False):
    @asynccontextmanager
    async def lifespan(app):
        if worker:
            yield
            return
        app.state.settings = settings or Settings.from_environment()
        app.state.database = await open_database(app.state.settings.database_url)
        try:
            yield
        finally:
            await app.state.database.close()

    app = FastAPI(
        title="Survey Machine API", version=__version__, lifespan=lifespan,
        description="Create and publish surveys, collect anonymous or named responses, and review/export results. Administrative endpoints require a scoped X-API-Key. Public survey endpoints require only a share token.",
        redoc_url=None,
    )
    configured = settings if worker else (settings or Settings.from_environment())
    app.add_middleware(SecurityMiddleware, cors_origins=configured.cors_origins if configured else ())

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never echo input values: they can include names, answers or credentials.
        errors = [{"loc": error["loc"], "msg": error["msg"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/health", tags=["Service"])
    async def health(repository: Repo):
        await repository.database.fetch_one("SELECT 1 AS ready")
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/auth/check", tags=["Workspace"], dependencies=[Depends(require_owner)])
    async def auth_check():
        return {"workspace": "Survey Machine", "version": __version__}

    @app.get("/api/v1/stats", tags=["Workspace"], dependencies=[Depends(require_owner)])
    async def stats(repository: Repo):
        return await repository.database.fetch_one(
            "SELECT (SELECT COUNT(*) FROM surveys) AS surveys, (SELECT COUNT(*) FROM surveys WHERE status = 'published') AS published, (SELECT COUNT(*) FROM responses) AS responses"
        )

    @app.get("/api/v1/surveys", response_model=SurveyPage, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:read"))])
    async def list_surveys(repository: Repo, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                           offset: Annotated[int, Query(ge=0)] = 0,
                           status: Literal["draft", "published", "closed"] | None = None,
                           search: Annotated[str | None, Query(max_length=200)] = None):
        return await repository.list_surveys(limit, offset, status, search)

    @app.post("/api/v1/surveys", response_model=SurveyOut, status_code=201, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:write"))])
    async def create_survey(data: SurveyCreate, repository: Repo):
        return await repository.create_survey(data)

    @app.get("/api/v1/surveys/{survey_id}", response_model=SurveyOut, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:read"))])
    async def get_survey(survey_id: UUID, repository: Repo):
        return await must_get_survey(repository, survey_id)

    @app.put("/api/v1/surveys/{survey_id}", response_model=SurveyOut, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:write"))])
    async def update_survey(survey_id: UUID, data: SurveyUpdate, repository: Repo):
        await must_get_survey(repository, survey_id)
        result = await repository.update_survey(str(survey_id), data)
        if result is None:
            raise HTTPException(409, "The survey was changed in another session or has been published. Reload it; duplicate a published survey to edit its questions.")
        return result

    @app.post("/api/v1/surveys/{survey_id}/publish", response_model=SurveyOut, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:write"))])
    async def publish_survey(survey_id: UUID, repository: Repo):
        survey = await must_get_survey(repository, survey_id)
        if not survey["questions"]:
            raise HTTPException(422, "Add at least one question before publishing.")
        if survey["status"] == "published":
            return survey
        result = await repository.change_status(str(survey_id), "published", survey["revision"])
        if result is None:
            raise HTTPException(409, "The survey changed. Reload and try again.")
        return result

    @app.post("/api/v1/surveys/{survey_id}/close", response_model=SurveyOut, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:write"))])
    async def close_survey(survey_id: UUID, repository: Repo):
        survey = await must_get_survey(repository, survey_id)
        if survey["status"] == "draft":
            raise HTTPException(409, "Publish a draft before closing it.")
        if survey["status"] == "closed":
            return survey
        result = await repository.change_status(str(survey_id), "closed", survey["revision"])
        if result is None:
            raise HTTPException(409, "The survey changed. Reload and try again.")
        return result

    @app.post("/api/v1/surveys/{survey_id}/duplicate", response_model=SurveyOut, status_code=201, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:write"))])
    async def duplicate_survey(survey_id: UUID, repository: Repo):
        survey = await must_get_survey(repository, survey_id)
        data = SurveyCreate(title=(survey["title"][:193] + " (copy)"), description=survey["description"],
                            respondent_mode=survey["respondent_mode"], questions=survey["questions"])
        for question in data.questions:
            from uuid import uuid4
            question.id = uuid4()
        return await repository.create_survey(data)

    @app.delete("/api/v1/surveys/{survey_id}", status_code=204, tags=["Surveys"], dependencies=[Depends(require_scope("surveys:write")), Depends(require_scope("responses:delete"))])
    async def delete_survey(survey_id: UUID, repository: Repo):
        if not await repository.delete_survey(str(survey_id)):
            raise HTTPException(404, "Survey not found.")
        return Response(status_code=204)

    @app.get("/api/v1/public/surveys/{token}", response_model=PublicSurvey, tags=["Public surveys"])
    async def public_survey(token: str, repository: Repo):
        survey = await must_get_public(repository, token)
        return {field: survey[field] for field in ("title", "description", "respondent_mode", "questions")}

    @app.post("/api/v1/public/surveys/{token}/responses", response_model=Receipt, status_code=201, tags=["Public surveys"])
    async def submit_response(token: str, data: Submission, repository: Repo):
        survey = await must_get_public(repository, token)
        definition = SurveyCreate(**{field: survey[field] for field in ("title", "description", "respondent_mode", "questions")})
        try:
            answers = validate_answers(definition, data)
        except AnswerError as error:
            raise HTTPException(422, {"message": str(error), "fields": error.errors})
        try:
            receipt = await repository.add_response(survey, data, answers)
        except ValueError as error:
            raise HTTPException(409, str(error))
        if receipt is None:
            raise HTTPException(409, "The survey changed or closed before this response was accepted.")
        return receipt

    @app.get("/api/v1/surveys/{survey_id}/responses", response_model=ResponsePage, response_model_exclude_none=True, tags=["Responses"], dependencies=[Depends(require_scope("responses:read"))])
    async def list_responses(survey_id: UUID, repository: Repo, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                             offset: Annotated[int, Query(ge=0)] = 0):
        await must_get_survey(repository, survey_id)
        return await repository.list_responses(str(survey_id), limit, offset)

    @app.get("/api/v1/surveys/{survey_id}/summary", response_model=ResultsSummary, tags=["Responses"], dependencies=[Depends(require_scope("responses:read"))])
    async def results_summary(survey_id: UUID, repository: Repo):
        survey = await must_get_survey(repository, survey_id)
        summaries, sums, total = [], {}, 0
        for question in survey["questions"]:
            counts = {option: 0 for option in question["options"]}
            if question["type"] == "rating":
                counts = {str(i): 0 for i in range(1, int(question["max_value"]) + 1)}
            summaries.append(QuestionSummary(question_id=question["id"], title=question["title"], type=question["type"], answered=0, counts=counts))
            sums[question["id"]] = Decimal(0)
        async for response in repository.iter_responses(str(survey_id), now()):
            total += 1
            for summary in summaries:
                key = str(summary.question_id)
                if key not in response["answers"]:
                    continue
                value = response["answers"][key]
                summary.answered += 1
                if summary.type in (QuestionType.NUMBER, QuestionType.RATING):
                    sums[key] += Decimal(str(value))
                if summary.type == QuestionType.RATING:
                    summary.counts[str(int(value))] += 1
                elif summary.type == QuestionType.SINGLE_CHOICE:
                    summary.counts[value] += 1
                elif summary.type == QuestionType.MULTIPLE_CHOICE:
                    for option in value:
                        summary.counts[option] += 1
        for summary in summaries:
            if summary.answered and summary.type in (QuestionType.NUMBER, QuestionType.RATING):
                summary.average = round(float(sums[str(summary.question_id)] / summary.answered), 2)
        return ResultsSummary(total=total, questions=summaries)

    @app.delete("/api/v1/surveys/{survey_id}/responses/{response_id}", status_code=204, tags=["Responses"], dependencies=[Depends(require_scope("responses:delete"))])
    async def delete_response(survey_id: UUID, response_id: UUID, repository: Repo):
        if not await repository.delete_response(str(survey_id), str(response_id)):
            raise HTTPException(404, "Response not found.")
        return Response(status_code=204)

    @app.get("/api/v1/surveys/{survey_id}/export", tags=["Responses"], dependencies=[Depends(require_scope("responses:read"))],
             responses={200: {"description": "Download all responses as CSV or JSON", "content": {"text/csv": {}, "application/json": {}}}})
    async def export_responses(survey_id: UUID, repository: Repo, format: Literal["csv", "json"] = "csv"):
        survey = await must_get_survey(repository, survey_id)
        cutoff = now()

        async def rows():
            if format == "json":
                yield "["
                first = True
                async for response in repository.iter_responses(str(survey_id), cutoff):
                    yield ("" if first else ",") + encode(response)
                    first = False
                yield "]"
                return
            buffer = StringIO()
            writer = csv.writer(buffer)

            def line(cells):
                buffer.seek(0)
                buffer.truncate()
                writer.writerow([csv_cell(cell) for cell in cells])
                return buffer.getvalue()

            header = ["response_id", "submitted_at"]
            if survey["respondent_mode"] == "named":
                header.append("respondent_name")
            header.extend(q["title"] + " [" + q["id"] + "]" for q in survey["questions"])
            yield "\ufeff" + line(header)
            async for response in repository.iter_responses(str(survey_id), cutoff):
                cells = [response["id"], response["submitted_at"]]
                if survey["respondent_mode"] == "named":
                    cells.append(response.get("respondent_name", ""))
                cells.extend(response["answers"].get(q["id"], "") for q in survey["questions"])
                yield line(cells)

        return StreamingResponse(rows(), media_type="text/csv" if format == "csv" else "application/json",
                                 headers={"Content-Disposition": f'attachment; filename="survey-{survey_id}.{format}"'})

    @app.get("/api/v1/api-keys", response_model=list[KeyOut], tags=["API keys"], dependencies=[Depends(require_owner)])
    async def list_keys(repository: Repo):
        return await repository.list_keys()

    @app.post("/api/v1/api-keys", response_model=KeyCreated, status_code=201, tags=["API keys"], dependencies=[Depends(require_owner)])
    async def create_key(data: KeyCreate, repository: Repo):
        return await repository.create_key(data)

    @app.delete("/api/v1/api-keys/{key_id}", status_code=204, tags=["API keys"], dependencies=[Depends(require_owner)])
    async def revoke_key(key_id: UUID, repository: Repo):
        if not await repository.delete_key(str(key_id)):
            raise HTTPException(404, "API key not found.")
        return Response(status_code=204)

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str, request: Request):
        if not path or (path.startswith("s/") and len(path.split("/")) == 2):
            asset = "index.html"
        elif path in {"index.html", "styles.css", "app.js", "api.js", "forms.js", "mark.svg"}:
            asset = path
        else:
            raise HTTPException(404, "Not found.")
        if worker:
            upstream = await request.scope["env"].ASSETS.fetch("https://assets.local/" + asset)
            body = await upstream.bytes()
            return Response(content=bytes(body), status_code=upstream.status,
                            headers={"Content-Type": upstream.headers.get("Content-Type") or "application/octet-stream"})
        from pathlib import Path
        from fastapi.responses import FileResponse
        return FileResponse(Path(__file__).parent / "web" / asset)

    return app
