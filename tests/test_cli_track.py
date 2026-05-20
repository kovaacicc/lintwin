import pytest
import tomli_w
from pathlib import Path
from click.testing import CliRunner
from lintwin.cli.main import cli


def _write_shared(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "git_paths": {"paths": ["~/.bashrc"]},
        "rsync_paths": {"paths": ["~/Downloads"]},
        "never_sync": {"patterns": []},
    }
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def test_track_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared)
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["track", "~/mydir", "--via", "git"])
    assert result.exit_code == 0
    assert "~/mydir" in result.output

    import tomllib
    with open(shared, "rb") as f:
        data = tomllib.load(f)
    assert "~/mydir" in data["git_paths"]["paths"]


def test_track_rsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared)
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["track", "~/mydir", "--via", "rsync"])
    assert result.exit_code == 0

    import tomllib
    with open(shared, "rb") as f:
        data = tomllib.load(f)
    assert "~/mydir" in data["rsync_paths"]["paths"]


def test_untrack_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared)
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["untrack", "~/.bashrc"])
    assert result.exit_code == 0
    assert "Removed" in result.output


def test_untrack_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared)
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["untrack", "~/nottracked"])
    assert result.exit_code != 0
    assert "not tracked" in result.output.lower()
