"""Stage only application modules, never virtual environments or test data."""

from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
target = root / ".worker" / "survey_machine"
target.mkdir(parents=True, exist_ok=True)
sources = {path.name: path for path in (root / "survey_machine").glob("*.py") if path.name != "main.py"}
for path in target.glob("*.py"):
    if path.name not in sources:
        path.unlink()
for name, path in sources.items():
    shutil.copyfile(path, target / name)
shutil.copyfile(root / "worker.py", target.parent / "worker.py")
print(f"Staged {len(sources) + 1} application modules for Cloudflare.")
