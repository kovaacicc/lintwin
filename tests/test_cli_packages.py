import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from lintwin.cli.main import cli


def test_packages_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "--help"])
    assert result.exit_code == 0
    assert "export" in result.output
    assert "diff" in result.output
    assert "install" in result.output


def test_packages_export_writes_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("lintwin.cli.packages.PACKAGES_DIR", tmp_path)

    mock_mgr = MagicMock()
    mock_mgr.name.return_value = "pacman"
    mock_mgr.export.return_value = {"explicit": ["nvim", "git"], "aur": []}
    monkeypatch.setattr("lintwin.cli.packages.get_available_managers", lambda: [mock_mgr])

    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "export"])
    assert result.exit_code == 0
    out_file = tmp_path / "pacman.json"
    assert out_file.exists()
    data = json.loads(out_file.read_text())
    assert data["explicit"] == ["nvim", "git"]


def test_packages_export_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "export", "--help"])
    assert result.exit_code == 0


def test_packages_install_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["packages", "install", "--help"])
    assert result.exit_code == 0
