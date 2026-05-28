import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import LocalConfig, RemoteConfig


def _make_local_config(machine_name="laptop", remotes=None):
    return LocalConfig(machine_name=machine_name, remotes=remotes or {})


def test_packages_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "--help"])
    assert result.exit_code == 0
    assert "export" in result.output
    assert "diff" in result.output
    assert "install" in result.output


def test_packages_export_writes_to_namespaced_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.export.return_value = {"explicit": ["nvim", "git"], "aur": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "export"])
    assert result.exit_code == 0
    out_file = tmp_path / "mylaptop" / "pacman.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["explicit"] == ["nvim", "git"]


def test_packages_export_prints_sync_hint(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.export.return_value = {"explicit": [], "aur": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "export"])
    assert result.exit_code == 0
    assert "lintwin sync" in result.output


def test_packages_diff_reads_local_file_not_ssh(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)

    remote_pkgs = {"explicit": ["htop", "nvim"], "aur": []}
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop" / "pacman.json").write_text(json.dumps(remote_pkgs))

    remotes = {"desktop": RemoteConfig(host="192.168.1.2", ssh_user="karlo")}
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(remotes=remotes),
    )

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.diff.return_value = {"missing": ["htop"], "extra": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "diff", "--to", "desktop"])
    assert result.exit_code == 0
    assert "htop" in result.output
    # No SSH subprocess should have been called
    mock_mgr.diff.assert_called_once_with(remote_pkgs)


def test_packages_diff_missing_remote_export(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)

    remotes = {"desktop": RemoteConfig(host="192.168.1.2", ssh_user="karlo")}
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(remotes=remotes),
    )

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "diff", "--to", "desktop"])
    assert result.exit_code == 0
    assert "desktop" in result.output
    assert "not yet exported" in result.output.lower() or "no package data" in result.output.lower()


def test_packages_install_reads_from_machine_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )

    (tmp_path / "mylaptop").mkdir()
    pkg_data = {"explicit": ["nvim", "htop"], "aur": []}
    (tmp_path / "mylaptop" / "pacman.json").write_text(json.dumps(pkg_data))

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.diff.return_value = {"missing": ["htop"], "extra": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "install"])
    assert result.exit_code == 0
    mock_mgr.install.assert_called_once_with(["htop"])


def test_packages_install_from_option(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )

    (tmp_path / "desktop").mkdir()
    pkg_data = {"explicit": ["steam", "nvim"], "aur": []}
    (tmp_path / "desktop" / "pacman.json").write_text(json.dumps(pkg_data))

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.diff.return_value = {"missing": ["steam"], "extra": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "install", "--from", "desktop"])
    assert result.exit_code == 0
    mock_mgr.install.assert_called_once_with(["steam"])


def test_packages_export_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "export", "--help"])
    assert result.exit_code == 0


def test_packages_install_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "install", "--help"])
    assert result.exit_code == 0


def test_packages_prune_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "prune", "--help"])
    assert result.exit_code == 0


def test_packages_prune_uninstalls_extra_on_confirm(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop" / "pacman.json").write_text(json.dumps({"explicit": ["nvim"], "aur": []}))

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.diff.return_value = {"missing": [], "extra": ["htop"]}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "prune", "--from", "desktop"], input="y\n")
    assert result.exit_code == 0
    mock_mgr.uninstall.assert_called_once_with(["htop"])


def test_packages_prune_aborts_on_no(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop" / "pacman.json").write_text(json.dumps({"explicit": ["nvim"], "aur": []}))

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.diff.return_value = {"missing": [], "extra": ["htop"]}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "prune", "--from", "desktop"], input="n\n")
    assert result.exit_code == 0
    mock_mgr.uninstall.assert_not_called()


def test_packages_prune_nothing_to_prune(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(
        "lintwin.cli.packages.load_local_config",
        lambda: _make_local_config(machine_name="mylaptop"),
    )
    (tmp_path / "desktop").mkdir()
    (tmp_path / "desktop" / "pacman.json").write_text(json.dumps({"explicit": ["nvim"], "aur": []}))

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.diff.return_value = {"missing": [], "extra": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "prune", "--from", "desktop"])
    assert result.exit_code == 0
    assert "nothing to prune" in result.output
    mock_mgr.uninstall.assert_not_called()
