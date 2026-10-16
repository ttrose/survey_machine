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

Keep `REPLACE_WITH_YOUR_D1_DATABASE_ID` in the committed `wrangler.jsonc`. Production
uses the `D1_DATABASE_ID` environment variable supplied by Cloudflare's build settings.
`npm run deploy:cloudflare` validates it, stages the Python application, checks the
bundle, applies remote migrations, and deploys. A failed build or migration stops
deployment. Both migration and deployment use the same temporary configuration.
That file is ignored by Git and Docker and removed when the command exits, including
on failure. The tracked configuration is never rewritten.

These are manual setup steps. The GitHub Actions checks remain local; connecting
**Cloudflare Workers Builds** enables actual deployments on future pushes to `main`.

### Cloudflare and GitHub UI setup

1. In GitHub, make sure `main` includes `scripts/deploy_cloudflare.py` and the
   `deploy:cloudflare` script in `package.json`. Do not paste the production ID into
   GitHub's file editor, a commit message, or an issue.
2. In Cloudflare, open **Storage & databases → D1**, create `survey-machine` if it
   does not already exist, and copy its database ID. Use one shared database for
   this deployment. Leave the binding name `DB` in the repository configuration.
3. Under **Workers & Pages → Create application**, start with the Hello World
   Worker named `survey-machine`. This creates a placeholder so settings can be
   configured before publishing the application. If that Worker exists, open it.
4. Under the Worker's **Settings → Variables and Secrets**, add `ADMIN_API_KEY`
   as a runtime **Secret**, using a fresh production operator key. Keep it in your
   password manager; never copy it into GitHub or the build command.
5. Connect the GitHub repository under **Settings → Builds**. Select `main` and
   use the following settings. Before the application build runs, make sure its
   deployment API token has **Account → D1 → Edit** for the target account, in
   addition to its Workers deployment permissions. Cloudflare may already include D1 permissions.
   Verify that the build token has Account → D1 → Edit for the target account..

| Build setting | Value |
| --- | --- |
| Worker name | `survey-machine` |
| Root directory | Repository root |
| Build command | `python -m pip install uv==0.12.5 && npm ci && uv sync --frozen --group workers` |
| Deploy command | `npm run deploy:cloudflare` |
| Preview builds | Disabled for this initial production setup |

Add these under **Build variables and secrets**, separate from runtime variables:

| Name | Value |
| --- | --- |
| `D1_DATABASE_ID` | The database ID copied from D1; store it here only |
| `SKIP_DEPENDENCY_INSTALL` | `true` (the build command installs pinned dependencies) |
| `NODE_VERSION` | `22` |

6. Save the settings and start the build (or retry if an initial build started
   before configuration was complete). On later releases, back up existing data
   before applying new migrations. The deploy command handles Wrangler migration
   tracking; do not paste the SQL files into the D1 console manually.
7. After a successful deployment, visit the Worker's HTTPS URL and `/health`.
   Test operator sign-in, a customer invitation, survey publication, submission
   and export before inviting customers.

Build variables are only available during the build. The generated config attaches
D1 to the Worker as `DB`; the application does not need `D1_DATABASE_ID` as a runtime
variable. Keep `SECURE_COOKIES=true`. Set `CORS_ORIGINS` in `wrangler.jsonc` only for
separate browser applications that need direct API access, using exact origins.

The deploy helper explicitly stages Python modules because Workers Builds does not
honor Wrangler's custom build settings. It uses `pywrangler` to package Python
dependencies. Do not replace the deploy command with plain `npx wrangler deploy`.

### Optional terminal deployment

After installing dependencies, authenticate with `npx wrangler login`, create the
database if needed with `npx wrangler d1 create survey-machine`, and set the runtime
operator key through the dashboard or `npx wrangler secret put ADMIN_API_KEY`.
Supply the database ID without putting it in a command saved in shell history:

~~~sh
read -r -p "D1 database ID: " D1_DATABASE_ID
export D1_DATABASE_ID
npm run deploy:cloudflare -- --dry-run
~~~

The dry-run bundles locally and does not run remote migrations or publish anything.
When ready, run `npm run deploy:cloudflare` to migrate and publish, then
`unset D1_DATABASE_ID`. Ordinary local development and `npm run build:cloudflare`
continue to work with the placeholder and need no production ID.

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
[Workers Builds settings](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/),
[Workers build image](https://developers.cloudflare.com/workers/ci-cd/builds/build-image/),
[D1 migrations](https://developers.cloudflare.com/d1/reference/migrations/),
[D1 backups](https://developers.cloudflare.com/d1/reference/time-travel/).
