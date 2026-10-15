# Survey Machine

A survey service you can use on its own, embed in another application, or call over a REST API. One deployment serves multiple customer accounts, each with private surveys, responses and integration keys. The primary deployment target is Python on Cloudflare Workers with D1; PostgreSQL is available for conventional hosting.

## What works

- Operator invitations, customer sign-in, persistent browser sessions, recovery links and account access management.
- Survey templates and a visual editor with text, email, number, date, choice and rating questions.
- Anonymous or named responses, public share links and iframe embeds.
- Drafts, publication, closing/reopening, duplication and stale-edit protection.
- Results summaries, individual responses, deletion, and CSV/JSON export.
- Workspace-scoped integration keys and a versioned HTTP/JSON API usable from any language.
- Local SQLite, local Cloudflare/D1, optional Docker/PostgreSQL and automated tests.

## Start locally

Install Node.js 22+ and uv 0.12.3+, then run:

```sh
uv sync --frozen --extra local --extra dev --group workers
npm ci
npm run setup
npm run dev
```

Open **http://127.0.0.1:8000**. Choose **Operator sign-in**, read `ADMIN_API_KEY` from the ignored `.env` file, then open **Customers → Invite customer**. Share the generated link privately. The customer chooses a password and can immediately start building surveys. Invitations and recovery links are delivered manually in this release.

For Cloudflare's local runtime instead:

```sh
npm run db:migrate:local
npm run dev:cloudflare
```

Open **http://127.0.0.1:8787** and use the operator key from `.dev.vars`. This runs against local D1 and needs no Cloudflare account. The two development modes use separate databases and keys.

## Verify and prepare for deployment

```sh
npm run check
npm test
npx playwright install --with-deps chromium
npm run test:browser
SM_TEST_D1=1 npm run test:browser
npm run build:cloudflare
```

The final command is a **dry-run**. Setup, tests, local build commands and GitHub Actions checks do not publish the application or create Cloudflare resources. Browser tests create disposable local databases. A Docker alternative for browser testing is documented for Linux systems without Chromium's libraries.

For a conventional PostgreSQL deployment, `docker compose up --build -d --wait` starts the app at **http://127.0.0.1:8080** with persistent database storage.

For Cloudflare, keep the database ID placeholder in `wrangler.jsonc`. Supply the production ID through the `D1_DATABASE_ID` build variable and use `npm run deploy:cloudflare` when ready to migrate and publish. The [UI deployment guide](docs/deployment.md#cloudflare-and-github-ui-setup) covers the Cloudflare and GitHub settings.

- [Setup, testing, backups and deployment](docs/deployment.md)
- [API and client-language examples](docs/api.md)
- [Self-host the API or mount it inside your own application](docs/self-hosting.md)
- [Architecture and release boundaries](docs/architecture.md)
- [Recorded local verification](docs/verification.md)
- [Security and privacy](SECURITY.md)

The current release has one owner per customer workspace. Team memberships, automated email, billing, MFA, uploads and conditional survey branching are future features. Public share links permit multiple responses; anonymous mode does not guarantee that free-text answers contain no personal information.

License and usage
This project is proprietary and is not licensed for public use.

You may view the source code, but you must receive written permission before using, copying, modifying, distributing, hosting, deploying, sublicensing, or selling the software.

To request permission, contact
Thomas Rose
Thomas.trose@outlook.com

See the LICENSE file for the complete terms.
