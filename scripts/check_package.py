"""Verify a wheel from outside the checkout, in a fresh disposable environment."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    wheel = Path(sys.argv[1]).resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise SystemExit("Pass the path to the built Survey Machine wheel.")
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    with tempfile.TemporaryDirectory(prefix="survey-package-") as directory:
        python = Path(directory) / "venv" / "bin" / "python"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(python.parent.parent)], check=True)
        subprocess.run(["uv", "pip", "install", "--python", str(python), f"{wheel}[local,dev]"], check=True)
        subprocess.run([str(python), "-c", '''
from pathlib import Path
import survey_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient

assert Path(survey_machine.__file__).resolve().is_relative_to(Path.cwd() / "venv")
settings = survey_machine.Settings(
    admin_api_key="test-only-package-check-key-123456789012345",
    database_url="sqlite:///:memory:",
)
with TestClient(survey_machine.create_app(settings)) as client:
    assert client.get("/health").status_code == 200
    assert "Survey Machine" in client.get("/").text
    assert client.get("/accounts.js").status_code == 200
    result = client.get("/api/v1/surveys", headers={"X-API-Key": settings.admin_api_key})
    assert result.status_code == 200 and result.json()["total"] == 0
parent = FastAPI()
survey_machine.mount_api(parent, settings)
with TestClient(parent) as client:
    assert client.get("/surveys/health").status_code == 200
    assert client.get("/surveys/").status_code == 404
print("Installed wheel verified: migrations, packaged UI, API and mounted lifespan.")
'''], cwd=directory, env=environment, check=True)


if __name__ == "__main__":
    main()
