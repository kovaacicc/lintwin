from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import LocalConfig, RemoteConfig, SharedConfig
from lintwin.core.scanner import DirtyRepo
from pathlib import Path


MOCK_LOCAL = LocalConfig(
    machine_name="laptop",
    remotes={"desktop": RemoteConfig(host="100.1.1.1", ssh_user="karlo")},
)
MOCK_SHARED = SharedConfig(git_paths=["~/.bashrc"], rsync_paths=["~/Downloads"])


def _patch_configs(monkeypatch):
    monkeypatch.setattr("lintwin.cli.sync.load_local_config", lambda: MOCK_LOCAL)
    monkeypatch.setattr("lintwin.cli.sync.load_shared_config", lambda: MOCK_SHARED)
    monkeypatch.setattr("lintwin.cli.sync.git_core.is_initialized", lambda: True)


def test_sync_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_sync_dry_run_no_changes(monkeypatch) -> None:
    _patch_configs(monkeypatch)
    monkeypatch.setattr("lintwin.cli.sync.scan_for_dirty_repos", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.git_status_short", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.check_connectivity", lambda r: False)

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--dry-run"])
    assert result.exit_code == 0
    assert "dry" in result.output.lower() or "preview" in result.output.lower() or "nothing" in result.output.lower()


def test_sync_aborts_on_connectivity_failure(monkeypatch) -> None:
    _patch_configs(monkeypatch)
    monkeypatch.setattr("lintwin.cli.sync.scan_for_dirty_repos", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.git_status_short", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.check_connectivity", lambda r: False)
    monkeypatch.setattr("lintwin.cli.sync._do_git_sync", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--to", "desktop"], input="y\n")
    assert "Cannot reach" in result.output


def test_sync_shows_dirty_repos(monkeypatch) -> None:
    _patch_configs(monkeypatch)
    dirty = DirtyRepo(path=Path("/home/k/projects/foo"), uncommitted=3, unpushed=1)
    monkeypatch.setattr("lintwin.cli.sync.scan_for_dirty_repos", lambda paths: [dirty])
    monkeypatch.setattr("lintwin.cli.sync.git_status_short", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.check_connectivity", lambda r: False)

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--dry-run"], input="s\n")
    assert "foo" in result.output or "dirty" in result.output.lower()
