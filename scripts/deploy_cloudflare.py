"""Deploy using D1_DATABASE_ID without changing the tracked Wrangler config."""

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "REPLACE_WITH_YOUR_D1_DATABASE_ID"


@contextmanager
def deployment_config():
    value = os.environ.get("D1_DATABASE_ID", "").strip()
    try:
        database_id = str(UUID(value))
    except ValueError:
        raise ValueError(
            "Set D1_DATABASE_ID to your database UUID in Cloudflare's build settings "
            "or your shell environment. Keep the placeholder in wrangler.jsonc."
        ) from None

    template = (ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError("wrangler.jsonc must contain exactly one D1 database ID placeholder.")

    # Keep the config beside the template so entrypoint, asset and migration paths
    # resolve identically. Git and Docker ignore these owner-only temporary files.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=ROOT, prefix="wrangler.deploy-",
        suffix=".jsonc", delete_on_close=False,
    ) as config:
        config.write(template.replace(PLACEHOLDER, database_id))
        config.close()
        yield Path(config.name)


def deploy(*, dry_run=False):
    with deployment_config() as config:
        # Workers Builds does not use Wrangler's custom build settings.
        subprocess.run([sys.executable, "scripts/stage_worker.py"], cwd=ROOT, check=True)
        command = [
            "uv", "run", "--frozen", "--group", "workers", "pywrangler", "deploy",
            "--config", str(config),
        ]
        # Catch bundling errors before changing the remote schema.
        subprocess.run(
            [*command, "--dry-run", "--outdir", "dist/cloudflare"], cwd=ROOT, check=True,
        )
        if dry_run:
            return
        subprocess.run(
            ["npx", "--no-install", "wrangler", "d1", "migrations", "apply", "DB",
             "--remote", "--config", str(config)],
            cwd=ROOT, check=True,
        )
        subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate and bundle locally; do not apply remote migrations or deploy.",
    )
    args = parser.parse_args()
    try:
        deploy(dry_run=args.dry_run)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
