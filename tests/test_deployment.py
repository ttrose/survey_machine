import importlib.util
import json
from pathlib import Path
import stat
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy_cloudflare", ROOT / "scripts/deploy_cloudflare.py")
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)
TEST_DATABASE_ID = "00000000-0000-4000-8000-000000000001"


@pytest.fixture
def deployment_root(tmp_path, monkeypatch):
    (tmp_path / "wrangler.jsonc").write_bytes((ROOT / "wrangler.jsonc").read_bytes())
    monkeypatch.setattr(deployment, "ROOT", tmp_path)
    monkeypatch.setenv("D1_DATABASE_ID", TEST_DATABASE_ID)
    return tmp_path


@pytest.mark.parametrize("value", [None, "", "not-a-uuid", "REPLACE_WITH_YOUR_D1_DATABASE_ID"])
def test_invalid_database_id_stops_before_any_command(deployment_root, monkeypatch, value):
    monkeypatch.delenv("D1_DATABASE_ID", raising=False)
    if value is not None:
        monkeypatch.setenv("D1_DATABASE_ID", value)
    monkeypatch.setattr(deployment.subprocess, "run", lambda *a, **k: pytest.fail("Command must not run"))
    with pytest.raises(ValueError, match="Set D1_DATABASE_ID"):
        deployment.deploy()
    assert not list(deployment_root.glob("wrangler.deploy-*.jsonc"))


def test_config_is_private_preserves_template_and_cleans_up_on_failure(deployment_root):
    template = deployment_root / "wrangler.jsonc"
    original = template.read_bytes()
    with pytest.raises(RuntimeError):
        with deployment.deployment_config() as config:
            rendered = json.loads(config.read_text())
            expected = json.loads(original)
            expected["d1_databases"][0]["database_id"] = TEST_DATABASE_ID
            assert rendered == expected
            assert config.parent == template.parent
            assert stat.S_IMODE(config.stat().st_mode) == 0o600
            assert template.read_bytes() == original
            raise RuntimeError("Deployment interrupted")
    assert not config.exists()
    assert template.read_bytes() == original


def test_missing_placeholder_does_not_fall_back_to_another_database(deployment_root):
    config = deployment_root / "wrangler.jsonc"
    config.write_text(config.read_text().replace(deployment.PLACEHOLDER, TEST_DATABASE_ID))
    with pytest.raises(ValueError, match="exactly one"):
        with deployment.deployment_config():
            pytest.fail("Must reject a config with no placeholder")


@pytest.mark.parametrize("dry_run", [True, False])
def test_dry_run_stays_local_and_deploy_uses_same_database(deployment_root, monkeypatch, dry_run):
    commands = []
    configs = []

    def record(command, **kwargs):
        assert kwargs == {"cwd": deployment_root, "check": True}
        commands.append(command)
        if "--config" in command:
            config = Path(command[command.index("--config") + 1])
            assert json.loads(config.read_text())["d1_databases"][0]["database_id"] == TEST_DATABASE_ID
            configs.append(config)

    monkeypatch.setattr(deployment.subprocess, "run", record)
    deployment.deploy(dry_run=dry_run)
    assert "scripts/stage_worker.py" in commands[0]
    assert "--dry-run" in commands[1]
    if dry_run:
        assert len(commands) == 2
        assert all("--remote" not in command for command in commands)
    else:
        assert len(commands) == 4
        assert commands[2][3:8] == ["d1", "migrations", "apply", "DB", "--remote"]
        assert "deploy" in commands[3] and "--dry-run" not in commands[3]
    assert len(set(configs)) == 1
    assert not configs[0].exists()


@pytest.mark.parametrize("failure_step", [1, 2])
def test_bundle_or_migration_failure_prevents_deployment(deployment_root, monkeypatch, failure_step):
    commands = []

    def fail(command, **kwargs):
        commands.append(command)
        if len(commands) - 1 == failure_step:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(deployment.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        deployment.deploy()
    assert len(commands) == failure_step + 1
    assert not list(deployment_root.glob("wrangler.deploy-*.jsonc"))
