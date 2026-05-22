from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.cli.init import check_prerequisites


def test_check_prerequisites_returns_list() -> None:
    missing = check_prerequisites()
    assert isinstance(missing, list)


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
