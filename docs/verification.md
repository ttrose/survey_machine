# Local release checks

Checked on Linux on 2026-10-09 for version 0.1.0. These are local results; no
Cloudflare or AWS deployment was performed.

| Check | Result |
| --- | --- |
| Python API suite with SQLite | 35 passed |
| Python API suite with a disposable PostgreSQL server | 35 passed |
| Chromium browser suite with SQLite/Uvicorn | 6 passed |
| Chromium browser suite with local Python Workers/D1 | 6 passed |
| JavaScript syntax and dependency lock checks | Passed |
| Python wheel installed outside the checkout | Passed: migrations, API, packaged assets, mounted lifespan |
| Docker Compose application with PostgreSQL | Built and healthy |
| API-only Docker image plus the example HTTP client | Passed: create key, create/publish survey, submit, read summary |
| Cloudflare deployment dry-run | Passed; 2,361.89 KiB compressed bundle |

The browser suite covers operator invitations, customer activation/session refresh,
account isolation, survey publication, anonymous and named responses, all eight
question types, CSV export, closing/reopening, embedding, key revocation, mobile
editing/sign-out, and edits made during a slow save. Chromium ran in the documented
Playwright container because the Linux host lacks its browser system libraries.

The API tests also check migration of populated first-release data, key permissions,
CSRF/origin handling, password recovery, disabling accounts, request validation,
idempotency, stale edits, safe CSV output and database readiness. The test client
currently emits an upstream Starlette deprecation warning for its httpx integration;
the tests pass.

Prepared GitHub Actions checks have not been observed running remotely. Real
Cloudflare account configuration, permissions, HTTPS routing, performance under
load and plan/runtime limits still need validation at deployment. Conventional
database migrations should run in one application instance before scaling out.

See [deployment](deployment.md) for commands to repeat the checks and the remaining
account-specific deployment steps, and [self-hosting](self-hosting.md) for the
independent-service and embedded-Python options.
