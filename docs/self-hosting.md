# Add Survey Machine to your own application

The same code can run independently of the hosted Survey Machine application.
There is no callback to a central service, Cloudflare account requirement, or
mandatory hosted customer account for conventional installations. Your installation
owns its database and keys. Distribution and use remain subject to [LICENSE](../LICENSE).

| Your application | Integration |
| --- | --- |
| Java, PHP, C, Node, Python or any HTTP client | Run the container as an internal service; call its JSON API from your backend |
| An existing Python/FastAPI application | Install the package and mount its API in your process |
| You want the survey builder and ready-made respondent forms | Keep the complete service UI; link to surveys or use iframe embeds |
| You already have a frontend | Set SERVE_UI=false and render questions from the public API |

All modes use the same versioned API, validation, database migrations, account
isolation and result export. Keep them in the same repository and release; API
consumers do not need a separate branch for each language.

## 1. An independent service for any language

With this repository, Docker and Python 3 installed (Python is only needed for this
one-time configuration step):

```sh
python3 scripts/setup_dev.py
SERVE_UI=false docker compose up --build -d --wait
```

This starts an API-only service at http://127.0.0.1:8080 and a persistent PostgreSQL
database. Visit /docs for the interactive API reference. The homepage, built-in
builder, and /s/... respondent pages return 404 in this mode. The public JSON
endpoints remain available. Remove SERVE_UI=false to include the complete UI.

For an existing Docker Compose application, add a service built from this repository's
[Dockerfile](../Dockerfile). Configure ADMIN_API_KEY, DATABASE_URL and SERVE_UI=false.
Your backend can call http://survey-machine:8000/api/v1 on a shared Docker network.
Use your own PostgreSQL server/database instead of the example postgres service when
appropriate. Give Survey Machine a **dedicated database** to avoid table-name conflicts
with your application. It creates its own tables when it starts.

To package the image without starting anything:

```sh
docker build -t survey-machine:0.1.0 .
```

The image includes Python, the API, database adapters, migrations and optional UI.
Node, Wrangler and Cloudflare credentials are not required to run it. Persistent
production data should live in PostgreSQL, not in the container's writable layer.

### Bootstrap an integration without the management UI

Use the installation's operator key once, from a trusted server/terminal, to create
a scoped key in the default workspace. Read the operator key from your local ignored
.env or your deployment's configuration into ADMIN_API_KEY; keep it out of source.

```sh
curl "$SURVEY_MACHINE_URL/api/v1/api-keys" \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"name":"My application","scopes":["surveys:read","surveys:write","responses:read"]}'
```

Save the returned key in your backend's secret configuration as SURVEY_MACHINE_KEY.
It is shown only once. Your normal integration then uses that key instead of the
operator key. Add responses:delete only if your application needs deletion.

One workspace is sufficient when the integrating backend owns all surveys. If that
backend serves different customers, a shared key grants access to all surveys in
that workspace: the backend must enforce its own per-customer authorization. For
Survey Machine's account isolation, provision separate customer workspaces and keys
using the documented invitation/activation API. Do not accept a key or workspace ID
chosen by an untrusted browser as evidence of permission.

### Run the complete example

Set SURVEY_MACHINE_URL (for example http://127.0.0.1:8080) and SURVEY_MACHINE_KEY in
your server environment, then run:

```sh
python examples/service_client.py
```

This creates a **demo** rating survey, publishes it, submits a sample answer through
the unauthenticated respondent API, and reads its summary. The sample data remains in
that installation. The client uses only Python's standard library; the same HTTP
requests work in [Java, PHP, C and other languages](api.md#client-examples).

For a real frontend, GET /api/v1/public/surveys/{token} supplies the question
definitions and POST /api/v1/public/surveys/{token}/responses accepts answers. The
token is the final segment of the survey's public_path. In API-only mode, public_path
is an identifier for the standard respondent page, **not an enabled web page**; your
application supplies that page. Similarly, invitation fragments must be handled by
your own activation screen, or use the complete service UI.

Expose the public API through your existing backend/proxy, or allowlist the exact
frontend origin with CORS_ORIGINS. Never put a private integration key in browser
code. Server-to-server HTTP calls do not need CORS.

## 2. Mount the API inside a Python application

Python 3.13 or newer is required. Build a wheel for private distribution:

```sh
uv build --out-dir dist/packages
uv run --no-sync python scripts/check_package.py dist/packages/survey_machine-0.1.0-py3-none-any.whl
```

In the receiving application's virtual environment:

```sh
uv pip install 'path/to/survey_machine-0.1.0-py3-none-any.whl[postgres]'
```

The wheel contains the API, migrations and optional web assets. It does not contain
local data, credentials, Wrangler or Node dependencies. This is a local/private
package workflow; nothing is published to PyPI.

The package check installs the wheel in a temporary virtual environment outside the
checkout and verifies migrations, assets, the API and embedded startup/shutdown.

Add these lines to the existing FastAPI application after creating it and defining
its lifespan:

```python
import os
from fastapi import FastAPI
from survey_machine import Settings, mount_api

app = FastAPI()  # Or your existing app, including its existing lifespan.
surveys = mount_api(app, Settings(
    admin_api_key=os.environ["ADMIN_API_KEY"],
    database_url=os.environ["SURVEY_DATABASE_URL"],
    secure_cookies=True,
), path="/surveys")
```

The API is now under /surveys/api/v1, health is /surveys/health, and the reference is
/surveys/docs. mount_api starts and closes Survey Machine's database alongside the
parent's existing lifespan, preserves its lifespan state, and disables the standalone
UI. Do not overwrite the parent's lifespan after mounting.

The helper deliberately composes lifespans because FastAPI does not automatically
start mounted applications. [FastAPI lifespan documentation](https://fastapi.tiangolo.com/advanced/events/#sub-applications)
and [mount documentation](https://fastapi.tiangolo.com/advanced/sub-applications/) explain
the underlying behavior.

Survey Machine retains its own API-key/session authorization. The host application's
login does not automatically authorize Survey Machine endpoints. Keep integration
keys server-side and use the existing app's backend to authorize user actions.
Use a dedicated database and the postgres extra for PostgreSQL. Native PostgreSQL
drivers are optional, so SQLite needs no additional database package.

Run the included example from this checkout:

```sh
uv run --extra local uvicorn examples.embedded_app:create_app --factory \
  --host 127.0.0.1 --port 8002
```

It reads the local .env, preserves the example app's / route, and mounts the API at
http://127.0.0.1:8002/surveys. Set SURVEY_MACHINE_URL to that mounted base URL when
using service_client.py. The example shares the database configured in .env.

## 3. Hosting alongside an AWS application

The built container can be run as an ECS Fargate service alongside your existing
application, with PostgreSQL supplied by a dedicated RDS database. This is a proposed
deployment mapping; AWS infrastructure has not been provisioned or tested here.
Fargate runs containers without a separately managed server fleet.
[AWS Fargate documentation](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)

Use your existing deployment pipeline to publish the image to ECR. Route service
traffic to container port 8000, use /health as the load balancer health check, and
terminate HTTPS at your application's ingress. Keep the database private; allow
database connections only from the service. Configure the runtime with DATABASE_URL,
ADMIN_API_KEY, SERVE_UI=false, and SECURE_COOKIES=true. Supply credentials through
your platform's secret injection, not through the image or source repository.

If an ALB serves Fargate tasks, its target group uses the ip target type. Configure
Uvicorn's trusted proxy addresses for that private ingress so HTTPS/origin handling
sees the original request scheme. Only trust forwarding headers from your ingress.
[Fargate service considerations](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html)

Run one application instance to apply a new conventional database migration before
scaling out; concurrent migration startups are not currently coordinated. Back up
the database before upgrades. This repository's Compose file is a local runnable
example, not an AWS infrastructure template. No Cloudflare services are involved in
this hosting mode.

If your existing backend is Python/FastAPI, you can instead install the wheel in its
existing image and use mount_api. Other languages run the provided service image
and call HTTP; they do not need to embed a Python interpreter.
