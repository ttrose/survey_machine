"""Run: uv run --extra local uvicorn examples.embedded_app:create_app --factory

Reads the ignored .env for local convenience. A deployed host should supply its
configuration through the environment and protect private API calls on its server.
"""

from dotenv import load_dotenv
from fastapi import FastAPI

from survey_machine import Settings, mount_api


def create_app():
    load_dotenv()
    app = FastAPI(title="Your existing application")

    @app.get("/")
    async def home():
        return {"application": "Your app", "surveys": "/surveys/docs"}

    mount_api(app, Settings.from_environment(), path="/surveys")
    return app
