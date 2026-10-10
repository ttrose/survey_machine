"""Disposable local servers for browser tests. Never targets a remote database."""

import argparse
from pathlib import Path
import signal
import subprocess
import tempfile

from survey_machine.application import create_app
from survey_machine.config import Settings

TEST_KEY = "test-administrator-key-for-survey-machine-12345"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("sqlite", "d1"), default="sqlite")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="survey-machine-test-") as directory:
        root = Path(directory)
        if args.backend == "sqlite":
            import uvicorn

            app = create_app(Settings(admin_api_key=TEST_KEY, database_url=f"sqlite:///{root / 'test.sqlite3'}"))
            uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
        else:
            config = root / "test.env"
            config.write_text(f"ADMIN_API_KEY={TEST_KEY}\nSECURE_COOKIES=false\nCORS_ORIGINS=https://consumer.example\n")
            state = str(root / "state")
            subprocess.run(["npx", "wrangler", "d1", "migrations", "apply", "DB", "--local", "--persist-to", state], check=True)
            process = subprocess.Popen(["pywrangler", "dev", "--local", "--ip", "127.0.0.1", "--port", str(args.port),
                                        "--persist-to", state, "--env-file", str(config), "--show-interactive-dev-session=false"])
            def stop(*_):
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            try:
                raise SystemExit(process.wait())
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
