"""Include Survey Machine in an existing FastAPI process without another server."""

from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI

from .application import create_app
from .config import Settings


def mount_api(parent: FastAPI, settings: Settings | None = None, *, path: str = "/surveys") -> FastAPI:
    if not path.startswith("/") or path == "/" or path.endswith("/") or any(c in path for c in "{}?#"):
        raise ValueError("Use a mount path such as /surveys, without a trailing slash.")
    service = create_app(replace(settings or Settings.from_environment(), serve_ui=False))
    parent_lifespan = parent.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        # FastAPI does not automatically run a mounted application's lifespan.
        # Open before the parent's startup, close after its shutdown hooks.
        async with service.router.lifespan_context(service):
            async with parent_lifespan(app) as state:
                yield state

    parent.mount(path, service, name="survey-machine")
    parent.router.lifespan_context = lifespan
    return service
