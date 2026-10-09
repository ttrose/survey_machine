"""Cloudflare entry point: the same FastAPI routes, using D1 bindings."""

from workers import asgi

from survey_machine.application import create_app

app = create_app(worker=True)
Default = asgi.entrypoint(app)
