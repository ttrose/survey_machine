# Architecture

Survey Machine is one application with a browser UI and a versioned HTTP/JSON API.
A single deployment serves many customer accounts. Customer separation is logical:
the same Worker and the same database hold all workspaces.

## Request paths

- Browser owner: sign in → HttpOnly session cookie → FastAPI → workspace-scoped repository.
- Integration server: X-API-Key → key's workspace and permissions → the same repository.
- Respondent: random public share token → published survey → validated response.
- Operator: operator key → customer invitations, recovery and access management.

The operator also has a default workspace. Existing surveys and integration keys from
the first version are migrated into it. The operator's survey API does not silently
switch to a customer's workspace. Infrastructure administrators still control the
underlying database; workspace isolation is an application authorization boundary.

## Components

| Component | Responsibility |
| --- | --- |
| survey_machine/application.py | Survey lifecycle, response validation, results, exports, frontend delivery |
| survey_machine/auth.py | Accounts, sessions, invitations, recovery, CSRF, login throttling |
| survey_machine/repository.py | Queries scoped by authenticated workspace |
| survey_machine/database.py | D1, SQLite and PostgreSQL adapters |
| survey_machine/models.py | Request/response models and eight question types |
| survey_machine/web/ | Buildless JavaScript UI, styles, public forms |
| worker.py | Cloudflare ASGI entry point |
| survey_machine/integration.py | API mounting and composed startup/shutdown for existing FastAPI apps |
| scripts/stage_worker.py | Copies only application Python modules into the Worker build |
| survey_machine/migrations/ | Shared SQL migrations |

The production Cloudflare path uses Python Workers, FastAPI, Workers Static Assets
and D1. The ordinary server uses Uvicorn and either SQLite for development or
PostgreSQL. Native database drivers never load in Workers. Password derivation uses
Web Crypto in Workers and Python's native implementation on conventional servers.

## Data model

- workspaces: one customer owner/login per workspace, activation/recovery state, access state.
- surveys: definitions stored as validated JSON, owning workspace, random share token,
  draft/published/closed status, optimistic revision.
- responses: survey, submission ID, answers, optional self-reported name and timestamp.
- api_keys: owning workspace, SHA-256 digest, display prefix and allowed operations.
- sessions: SHA-256 digest, expiry, workspace and session version.
- auth_attempts: short-lived rate-limit buckets for authentication.
- schema_migrations on conventional databases; d1_migrations on D1.

Every private survey lookup and mutation is scoped to the authenticated workspace.
Response and key operations carry the same scope. A caller cannot select a different
workspace by supplying a request field or header. The API returns 404 for a survey
owned by another account.

Public forms intentionally require no account. Possession of the share URL permits
reading the form and submitting answers while the survey and account are enabled.
It does not permit viewing results.

## Consistency

Draft changes use a revision number to reject stale edits. Once published, a survey's
questions and identity mode are locked; duplicate it for another round.

Submission IDs provide idempotency within a survey. Replaying the same ID with the
same answers returns the original receipt; conflicting answers return 409.
The response INSERT checks the current survey revision/status and account access in
one statement. D1 reads use a first-primary session for read-after-write consistency.

Exports use a timestamp cutoff and bounded batches of 250 records. They are streamed,
but concurrent deletions can affect an in-progress export. They are not a transactional
snapshot. Summaries scan the survey's responses and are suitable for an initial
release, not unbounded analytics workloads.

## Repository organization

Keep the app, API and deployment adapters together on main. Clients in Java, Python,
PHP, C and other languages use the same HTTP API. Language SDKs may be generated from
/openapi.json later; they do not require separate API implementations or permanent
language-specific branches.

The same package also runs with SERVE_UI=false or mounts inside an existing Python
application through mount_api. These installations use their own database and keys;
they do not contact the hosted application. See [self-hosting](self-hosting.md).

## Current release boundary

This is an invitation-based service with one owner per customer workspace. It includes
manual invitation/recovery links, API keys, survey editing, anonymous/named collection,
results and exports. It does not include team memberships, billing, automated email,
MFA, file uploads, conditional branching or scheduled campaigns. Self-reported names
are not verified identities. The database backend is selected per deployment; changing
backends does not automatically transfer data.
