from unittest.mock import patch
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import LocalConfig, RemoteConfig, SharedConfig


MOCK_LOCAL = LocalConfig(
    machine_name="laptop",
    remotes={"desktop": RemoteConfig(host="100.1.1.1", ssh_user="karlo")},
)
MOCK_SHARED = SharedConfig(git_paths=["~/.bashrc"], rsync_paths=["~/Downloads"])


def test_status_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["status", "--help"])
    assert result.exit_code == 0


def test_pull_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["pull", "--help"])
    assert result.exit_code == 0


def test_diff_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["diff", "--help"])
    assert result.exit_code == 0


def test_status_shows_machine_name(monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.status.load_local_config", lambda: MOCK_LOCAL)
    monkeypatch.setattr("lintwin.cli.status.load_shared_config", lambda: MOCK_SHARED)
    monkeypatch.setattr("lintwin.cli.status.git_status_short", lambda paths: [("M", "~/.bashrc")])
    monkeypatch.setattr("lintwin.cli.status.scan_for_dirty_repos", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.status.check_connectivity", lambda r: False)

    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "laptop" in result.output
