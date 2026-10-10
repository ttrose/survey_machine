# Run and deploy

All normal development and test commands are local. No Cloudflare account is required
until you choose to create a remote database or deploy.

## Prerequisites and Linux setup

Install Node.js 22+, npm, and uv 0.12.3+ (tested with uv 0.12.5).
uv installs the Python version selected in .python-version; there is no need to replace
your distro's system Python. Cloudflare's compatibility date can select a newer Python
runtime for the Worker, managed separately by pywrangler.

From the repository root:

~~~sh
uv sync --frozen --extra local --extra dev --group workers
npm ci
npm run setup
npm run dev
~~~

Open http://127.0.0.1:8000. Choose **Operator sign-in** and read ADMIN_API_KEY from the
ignored .env file in your editor. Go to **Customers**, invite an owner, and share the
one-time link privately. The invited owner chooses a password and signs in to their
own workspace. Customer sessions survive page refresh; operator keys stay in memory.

setup never prints the generated values or replaces an existing configuration file.
It creates .env and .dev.vars with separate keys and owner-only file permissions.
Local SQLite data lives in data/survey-machine.sqlite3. Restarting preserves it.

## Local Cloudflare and D1

~~~sh
npm run db:migrate:local
npm run dev:cloudflare
~~~

Open http://127.0.0.1:8787. This instance uses the key in .dev.vars and its own database
under .wrangler/state, not the ordinary server's SQLite file. The placeholder D1 ID is
accepted for local use. .dev.vars sets SECURE_COOKIES=false for local HTTP only.

Use local migrations after adding migration files. Do not edit a migration that has
already been applied to a shared/production database; add another numbered migration.

The staging build copies only application modules into .worker. This prevents
Wrangler from bundling virtual environments, tests, or developer files. Dependencies
are pinned in uv.lock, package-lock.json and the Worker-specific pylock.toml.

## Verify before deployment

~~~sh
npm run check
npm test
npx playwright install --with-deps chromium
npm run test:browser
SM_TEST_D1=1 npm run test:browser
npm run build:cloudflare
~~~

The browser commands start disposable servers/databases on ports 8001 and 8788 and
exercise account setup, isolation, survey creation, named/anonymous responses,
results, CSV export, mobile layouts and key revocation. They do not use .env,
.dev.vars or your development database. Test credentials are deliberately public and
valid only in these disposable test servers. Never expose these servers to the internet.

On Linux, installing browser system libraries can require sudo. If that is unavailable,
run the browser in a container (terminal 1):

~~~sh
docker run --rm --name survey-machine-browser-test --network host \
  mcr.microsoft.com/playwright:v1.64.0-noble \
  npx --yes playwright@1.64.0 run-server --host 127.0.0.1 --port 31379
~~~

Then in terminal 2:

~~~sh
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:31379/ npm run test:browser
SM_TEST_D1=1 PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:31379/ npm run test:browser
~~~

The container alternative uses Linux host networking. Stop that container when finished.
GitHub Actions runs API tests with SQLite/PostgreSQL, both browser suites and a Worker
dry-run. It has no Cloudflare deployment credentials and performs no remote deployment.
The recorded local results and remaining deployment checks are in [verification.md](verification.md).

## Optional conventional server with PostgreSQL

~~~sh
npm run setup
docker compose up --build -d --wait
~~~

Open http://127.0.0.1:8080 and use the operator key from .env. PostgreSQL persists in
the survey-machine_postgres-data volume and is not exposed on a host port.
docker compose down stops/removes containers while preserving the volume.
Adding --volumes deletes the database; do not use that for routine shutdown.

For testing an existing disposable PostgreSQL server:

~~~sh
uv sync --frozen --extra local --extra dev --extra postgres
TEST_DATABASE_URL=postgresql://survey:TEST_PASSWORD@127.0.0.1:5432/survey_test \
  uv run --no-sync pytest -q
~~~

The test database name MUST end in _test; the suite clears its application records.
Never point this variable at development or production data.

For a conventional public host, terminate TLS with your reverse proxy, set
SECURE_COOKIES=true, set the correct trusted proxy addresses for Uvicorn, and limit
direct access to the app port. The provided Compose defaults bind to localhost.

## When you choose to deploy to Cloudflare

These are future manual steps, not performed by setup, tests, or CI.

1. Log in using npx wrangler login.
2. Create the one shared database using npx wrangler d1 create survey-machine.
3. Put its returned database_id in wrangler.jsonc. Keep the binding named DB.
4. Keep SECURE_COOKIES=true in wrangler.jsonc. Set CORS_ORIGINS only if a separate
   browser application needs direct API access, using comma-separated exact origins.
   Server-to-server calls and iframe embeds do not require CORS configuration.
5. Run the local verification commands above.
6. Back up existing remote data before migrations, then run
   npx wrangler d1 migrations apply DB --remote.
7. Set a fresh production operator key with npx wrangler secret put ADMIN_API_KEY.
   Enter it at the prompt; do not put it in wrangler.jsonc or source control.
8. Deploy with uv run --group workers pywrangler deploy.
9. Check /health, operator sign-in, a customer invitation, submission and export
   over the real HTTPS URL before inviting customers.

The first secret-put can offer to create the Worker if it does not yet exist.
These steps create resources or publish code and should be run only when you are ready.

Local checks do not establish Cloudflare account permissions, plan limits, production
CPU/startup budgets, custom-domain configuration or live routing. Evaluate those on
the chosen account before launch. Authentication hashing and large summaries/exports
need runtime headroom; choose an appropriate Workers plan and load-test expected usage.

## Operations and recovery

- Rotate the operator key using Cloudflare secrets (or the server environment), then
  restart the conventional server when applicable. Refresh customer pages afterward
  to renew their CSRF token. This does not delete surveys or integration keys.
- Use Customers → Reset password to issue a new recovery link. It expires in seven
  days and invalidates the owner's existing sessions when redeemed.
- Disable a customer to invalidate sessions and stop their API keys and public forms.
  Re-enabling restores keys/forms; the customer must sign in again.
- Export survey results for business use. For disaster recovery, back up the entire
  database: result exports do not include users, keys, survey definitions or sessions.
- For D1, use Cloudflare's database export and Time Travel facilities and rehearse
  restoration to a separate database. For PostgreSQL, use pg_dump/pg_restore.
- Worker rollback does not reverse a database migration. Future migrations should
  remain compatible with the previous application version during rollout.
- Anonymous responses omit name/IP/user-agent fields. Free-text answers can identify
  people, and hosting providers/reverse proxies can retain request logs independently.

References: [Python Workers](https://developers.cloudflare.com/workers/languages/python/),
[FastAPI on Workers](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/),
[D1 migrations](https://developers.cloudflare.com/d1/reference/migrations/),
[D1 backups](https://developers.cloudflare.com/d1/reference/time-travel/).
