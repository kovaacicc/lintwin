from pathlib import Path
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.cli.init import check_prerequisites, discover_dotfiles, discover_rsync_dirs


def test_check_prerequisites_returns_list() -> None:
    missing = check_prerequisites()
    assert isinstance(missing, list)


def test_discover_dotfiles_finds_dotfiles(tmp_path: Path) -> None:
    (tmp_path / ".bashrc").write_text("")
    (tmp_path / ".vimrc").write_text("")
    (tmp_path / ".cache").mkdir()
    (tmp_path / "Documents").mkdir()
    found = discover_dotfiles(tmp_path)
    names = [p.name for p in found]
    assert ".bashrc" in names
    assert ".vimrc" in names
    assert ".cache" not in names


def test_discover_rsync_dirs_finds_non_hidden_dirs(tmp_path: Path) -> None:
    (tmp_path / "Projects").mkdir()
    (tmp_path / "Games").mkdir()
    (tmp_path / ".config").mkdir()
    found = discover_rsync_dirs(tmp_path)
    names = [p.name for p in found]
    assert "Projects" in names
    assert "Games" in names
    assert ".config" not in names


def test_init_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_init_shows_join_option() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0
    assert "--join" in result.output
