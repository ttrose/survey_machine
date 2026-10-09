"""Create local configuration with a fresh secret, without printing it."""

from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
for name, content in (
    (".env", "DATABASE_URL=sqlite:///data/survey-machine.sqlite3\nCORS_ORIGINS=\n"),
    (".dev.vars", ""),
):
    target = root / name
    if target.exists():
        print(f"Keeping existing {name}.")
        continue
    target.write_text(f"ADMIN_API_KEY={secrets.token_urlsafe(32)}\n{content}", encoding="utf-8")
    print(f"Created {name}. Read ADMIN_API_KEY from this file to unlock your workspace.")
