"""Create local configuration with a fresh secret, without printing it."""

import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
for name, content in (
    (".env", "DATABASE_URL=sqlite:///data/survey-machine.sqlite3\nCORS_ORIGINS=\n"),
    (".dev.vars", "SECURE_COOKIES=false\n"),
):
    target = root / name
    if target.exists():
        print(f"Keeping existing {name}.")
        continue
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(f"ADMIN_API_KEY={secrets.token_urlsafe(32)}\n{content}")
    print(f"Created {name}. Read ADMIN_API_KEY from this file to unlock your workspace.")

# Docker Compose uses its own local PostgreSQL password. Preserve it on reruns.
config = root / ".env"
if not any(line.startswith("POSTGRES_PASSWORD=") for line in config.read_text(encoding="utf-8").splitlines()):
    with config.open("a", encoding="utf-8") as stream:
        stream.write(f"\nPOSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n")
    print("Added the local PostgreSQL password to .env.")
