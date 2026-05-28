import pytest
import tomli_w
from pathlib import Path
from click.testing import CliRunner
from lintwin.cli.main import cli


def _write_shared(path: Path, never_sync: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "git_paths": {"paths": ["~/.bashrc"]},
        "rsync_paths": {"paths": ["~/Downloads"]},
        "never_sync": {"patterns": never_sync if never_sync is not None else []},
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


def test_track_blocked_by_exact_never_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared, never_sync=["~/.config/lintwin/config.toml"])
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["track", "~/.config/lintwin/config.toml", "--via", "git"])
    assert result.exit_code != 0
    assert "never-sync" in result.output.lower() or "never_sync" in result.output.lower()


def test_track_blocked_by_glob_never_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared, never_sync=["~/.ssh/id_*"])
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["track", "~/.ssh/id_ed25519", "--via", "git"])
    assert result.exit_code != 0
    assert "never-sync" in result.output.lower() or "never_sync" in result.output.lower()


def test_track_blocked_by_filename_glob_never_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared, never_sync=["*.gpg"])
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["track", "~/secrets.gpg", "--via", "git"])
    assert result.exit_code != 0
    assert "never-sync" in result.output.lower() or "never_sync" in result.output.lower()


def test_track_allowed_when_not_in_never_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = tmp_path / "shared.toml"
    _write_shared(shared, never_sync=["~/.config/lintwin/config.toml", "*.gpg"])
    monkeypatch.setattr("lintwin.core.config.SHARED_CONFIG_PATH", shared)
    monkeypatch.setattr("lintwin.cli.track.SHARED_CONFIG_PATH", shared)

    runner = CliRunner()
    result = runner.invoke(cli, ["track", "~/.config/nvim", "--via", "git"])
    assert result.exit_code == 0
