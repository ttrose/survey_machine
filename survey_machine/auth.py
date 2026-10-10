"""One deployment, isolated customer accounts, scoped keys and browser sessions."""

import hashlib
import hmac
import secrets
import time
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import APIKeyCookie, APIKeyHeader
from pydantic import ConfigDict, Field, StrictBool, field_validator

from . import __version__
from .config import Settings
from .database import D1Database
from .models import ALL_SCOPES, Model
from .repository import Repository, now

COOKIE = "sm_session"
SESSION_SECONDS = 12 * 60 * 60
INVITE_SECONDS = 7 * 24 * 60 * 60
ITERATIONS = 600_000
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
session_cookie = APIKeyCookie(name=COOKIE, auto_error=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token, settings):
    return hmac.new(settings.admin_api_key.encode(), token.encode(), "sha256").hexdigest()


async def get_settings(request: Request):
    if "env" in request.scope:
        env = request.scope["env"]
        try:
            return Settings(admin_api_key=str(env.ADMIN_API_KEY),
                            secure_cookies=str(getattr(env, "SECURE_COOKIES", "true")).lower() == "true")
        except (AttributeError, ValueError):
            raise HTTPException(503, "The operator has not configured the service.")
    return request.app.state.settings


async def get_database(request: Request):
    if "env" in request.scope:
        if not hasattr(request.state, "database"):
            request.state.database = D1Database(request.scope["env"].DB)
        return request.state.database
    return request.app.state.database


DB = Annotated[object, Depends(get_database)]
Config = Annotated[Settings, Depends(get_settings)]


async def authenticate(request: Request, database: DB, settings: Config,
                       key: Annotated[str | None, Depends(api_key_header)],
                       token: Annotated[str | None, Depends(session_cookie)]):
    if key is not None:
        if len(key) <= 256 and secrets.compare_digest(key.encode(), settings.admin_api_key.encode()):
            return {"owner": True, "operator": True, "scopes": ALL_SCOPES,
                    "workspace_id": "default", "workspace": "Operator workspace"}
        principal = await Repository(database).find_key(key) if len(key) <= 256 else None
        if principal:
            return {**principal, "owner": False, "operator": False}
    elif token and len(token) == 43:
        principal = await database.fetch_one(
            "SELECT w.id AS workspace_id, w.name AS workspace, w.email FROM sessions s "
            "JOIN workspaces w ON w.id = s.workspace_id WHERE s.digest = ? AND s.expires_at > ? "
            "AND w.enabled = 1 AND s.session_version = w.session_version", (digest(token), int(time.time())),
        )
        if principal:
            csrf = csrf_token(token, settings)
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                supplied = request.headers.get("X-CSRF-Token", "")
                if not secrets.compare_digest(supplied.encode(), csrf.encode()):
                    raise HTTPException(403, "Refresh the page before trying again.")
            return {**principal, "owner": True, "operator": False, "scopes": ALL_SCOPES, "csrf_token": csrf}
    raise HTTPException(401, "Sign in or provide a valid X-API-Key header.")


Principal = Annotated[dict, Depends(authenticate)]


def require_scope(scope):
    async def check(principal: Principal):
        if scope not in principal["scopes"]:
            raise HTTPException(403, f"This API key requires the {scope} permission.")
        return principal
    return check


async def require_owner(principal: Principal):
    if not principal["owner"]:
        raise HTTPException(403, "Sign in as the workspace owner to perform this operation.")
    return principal


async def require_operator(principal: Principal):
    if not principal["operator"]:
        raise HTTPException(403, "This operation requires the service operator.")
    return principal


async def password_bits(password, salt, *, worker=False):
    if worker:
        from js import Object, TextEncoder, Uint8Array, crypto
        from pyodide.ffi import to_js

        algorithm = to_js({"name": "PBKDF2", "salt": Uint8Array.new(list(salt)),
                           "iterations": ITERATIONS, "hash": "SHA-256"}, dict_converter=Object.fromEntries)
        key = await crypto.subtle.importKey("raw", TextEncoder.new().encode(password), "PBKDF2", False,
                                           to_js(["deriveBits"]))
        bits = await crypto.subtle.deriveBits(algorithm, key, 256)
        return bytes(Uint8Array.new(bits).to_py())
    import asyncio

    return await asyncio.to_thread(hashlib.pbkdf2_hmac, "sha256", password.encode(), salt, ITERATIONS)


async def hash_password(password, *, worker=False):
    salt = secrets.token_bytes(16)
    bits = await password_bits(password, salt, worker=worker)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${bits.hex()}"


async def verify_password(password, encoded, *, worker=False):
    # Do the same expensive work for unknown accounts to avoid account discovery.
    encoded = encoded or f"pbkdf2_sha256${ITERATIONS}${'00' * 16}${'00' * 32}"
    _, _, salt, expected = encoded.split("$")
    actual = await password_bits(password, bytes.fromhex(salt), worker=worker)
    return secrets.compare_digest(actual.hex(), expected)


Email = Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]


class Credentials(Model):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    email: Email
    password: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def valid_password(cls, value):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Use valid Unicode characters in your password.")
        return value


class Activate(Credentials):
    token: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]


class CustomerCreate(Model):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    email: Email

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class CustomerStatus(Model):
    enabled: StrictBool


async def throttle(request, database, identity=""):
    current = int(time.time())
    # Only authentication is rate limited here. Survey respondents' IPs are never stored.
    address = request.client.host if request.client else "unknown"
    if "env" in request.scope:
        address = request.headers.get("CF-Connecting-IP", address)
    await database.execute("DELETE FROM auth_attempts WHERE expires_at <= ?", (current,))
    for kind, value, limit in [("address", address, 30), ("account", identity, 10)]:
        if not value:
            continue
        bucket = f"{kind}:{digest(value)}:{current // 300}"
        row = await database.fetch_one(
            "INSERT INTO auth_attempts(bucket, attempts, expires_at) VALUES (?, 1, ?) "
            "ON CONFLICT(bucket) DO UPDATE SET attempts = auth_attempts.attempts + 1 RETURNING attempts",
            (bucket, (current // 300 + 1) * 300),
        )
        if row["attempts"] > limit:
            raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.",
                                headers={"Retry-After": str(300 - current % 300)})


def account_info(principal):
    return {key: principal[key] for key in ("workspace", "workspace_id", "operator", "email", "csrf_token") if key in principal} | {"version": __version__}


async def start_session(row, request, response, database, settings):
    token = secrets.token_urlsafe(32)
    current = int(time.time())
    await database.execute("DELETE FROM sessions WHERE expires_at <= ?", (current,))
    await database.execute("INSERT INTO sessions(digest, workspace_id, session_version, expires_at) VALUES (?, ?, ?, ?)",
                           (digest(token), row["id"], row["session_version"], current + SESSION_SECONDS))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="lax",
                        path=request.scope.get("root_path", "") or "/",
                        secure=settings.secure_cookies or request.url.scheme == "https")
    return account_info({"workspace": row["name"], "workspace_id": row["id"], "email": row["email"],
                         "operator": False, "csrf_token": csrf_token(token, settings)})


router = APIRouter(prefix="/api/v1", tags=["Accounts"])


@router.get("/auth/check")
async def auth_check(principal: Annotated[dict, Depends(require_owner)]):
    return account_info(principal)


@router.post("/auth/login")
async def login(data: Credentials, request: Request, response: Response, database: DB, settings: Config):
    await throttle(request, database, data.email)
    row = await database.fetch_one("SELECT * FROM workspaces WHERE email = ?", (data.email,))
    valid = await verify_password(data.password, row["password_hash"] if row else None, worker="env" in request.scope)
    if not valid or not row or not row["enabled"]:
        raise HTTPException(401, "The email or password is incorrect, or this account is unavailable.")
    return await start_session(row, request, response, database, settings)


@router.post("/auth/activate")
async def activate(data: Activate, request: Request, response: Response, database: DB, settings: Config):
    await throttle(request, database)
    token_digest = digest(data.token)
    params = (token_digest, data.email, int(time.time()))
    clause = " WHERE onboarding_digest = ? AND email = ? AND onboarding_expires > ? AND enabled = 1"
    if not await database.fetch_one("SELECT id FROM workspaces" + clause, params):
        raise HTTPException(400, "This invitation or reset link is invalid, expired, or already used.")
    encoded = await hash_password(data.password, worker="env" in request.scope)
    row = await database.fetch_one(
        "UPDATE workspaces SET password_hash = ?, onboarding_digest = NULL, onboarding_expires = NULL, "
        "session_version = session_version + 1" + clause + " RETURNING id, name, email, session_version",
        (encoded, token_digest, data.email, int(time.time())),
    )
    if row is None:
        raise HTTPException(400, "This invitation or reset link is invalid, expired, or already used.")
    return await start_session(row, request, response, database, settings)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, response: Response, database: DB, principal: Principal):
    if token := request.cookies.get(COOKIE):
        await database.execute("DELETE FROM sessions WHERE digest = ?", (digest(token),))
    response.delete_cookie(COOKIE, path=request.scope.get("root_path", "") or "/", httponly=True, samesite="lax")


@router.get("/operator/customers", dependencies=[Depends(require_operator)])
async def customers(database: DB, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                    offset: Annotated[int, Query(ge=0)] = 0):
    rows = await database.fetch_all(
        "SELECT id, name, email, enabled, created_at, CASE WHEN password_hash IS NULL THEN 'invited' ELSE 'active' END AS status "
        "FROM workspaces WHERE id <> 'default' ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", (limit, offset))
    total = await database.fetch_one("SELECT COUNT(*) AS total FROM workspaces WHERE id <> 'default'")
    return {"items": rows, "total": total["total"], "limit": limit, "offset": offset}


@router.post("/operator/customers", status_code=201, dependencies=[Depends(require_operator)])
async def create_customer(data: CustomerCreate, database: DB):
    token, workspace_id, current = secrets.token_urlsafe(32), str(uuid4()), int(time.time())
    changed = await database.execute(
        "INSERT INTO workspaces(id, name, email, onboarding_digest, onboarding_expires, created_at) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(email) DO NOTHING", (workspace_id, data.name, data.email, digest(token), current + INVITE_SECONDS, now()))
    if not changed:
        raise HTTPException(409, "An account with that email already exists.")
    return {"id": workspace_id, "name": data.name, "email": data.email, "activation_path": f"/#/activate/{token}",
            "expires_in": INVITE_SECONDS}


@router.post("/operator/customers/{workspace_id}/reset", dependencies=[Depends(require_operator)])
async def reset_customer(workspace_id: UUID, database: DB):
    token = secrets.token_urlsafe(32)
    row = await database.fetch_one(
        "UPDATE workspaces SET onboarding_digest = ?, onboarding_expires = ? WHERE id = ? "
        "RETURNING id, name, email", (digest(token), int(time.time()) + INVITE_SECONDS, str(workspace_id)))
    if row is None:
        raise HTTPException(404, "Customer not found.")
    return {**row, "activation_path": f"/#/activate/{token}", "expires_in": INVITE_SECONDS}


@router.put("/operator/customers/{workspace_id}", dependencies=[Depends(require_operator)])
async def customer_status(workspace_id: UUID, data: CustomerStatus, database: DB):
    changed = await database.execute("UPDATE workspaces SET enabled = ?, session_version = session_version + 1 WHERE id = ?",
                                     (int(data.enabled), str(workspace_id)))
    if not changed:
        raise HTTPException(404, "Customer not found.")
    return {"id": str(workspace_id), "enabled": data.enabled}
