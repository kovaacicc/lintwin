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


def _patch_init(monkeypatch):
    import lintwin.cli.init as init_mod
    captured = {}
    monkeypatch.setattr(init_mod, "save_shared_config",
                        lambda config, *a, **k: captured.__setitem__("shared", config))
    monkeypatch.setattr(init_mod, "save_local_config", lambda *a, **k: None)
    monkeypatch.setattr(init_mod, "run_selector",
                        lambda home: (["~/.bashrc"], ["~/Downloads"]))
    monkeypatch.setattr(init_mod, "check_prerequisites", lambda: [])
    monkeypatch.setattr(init_mod.Confirm, "ask", lambda *a, **k: False)
    monkeypatch.setattr(init_mod.Prompt, "ask",
                        lambda *a, **k: "git@example.com:me/dots.git")
    monkeypatch.setattr(init_mod.git_core, "init_bare_repo", lambda *a, **k: None)
    monkeypatch.setattr(init_mod.git_core, "set_remote", lambda *a, **k: None)
    monkeypatch.setattr(init_mod.git_core, "stage_paths", lambda *a, **k: None)
    monkeypatch.setattr(init_mod.git_core, "commit", lambda *a, **k: True)
    monkeypatch.setattr(init_mod.git_core, "push", lambda *a, **k: None)
    return captured


def test_init_max_git_file_mb_flag(monkeypatch) -> None:
    captured = _patch_init(monkeypatch)
    result = CliRunner().invoke(cli, ["init", "--name", "laptop", "--max-git-file-mb", "50"])
    assert result.exit_code == 0, result.output
    assert captured["shared"].max_git_file_mb == 50


def test_init_max_git_file_mb_defaults_to_25(monkeypatch) -> None:
    captured = _patch_init(monkeypatch)
    result = CliRunner().invoke(cli, ["init", "--name", "laptop"])
    assert result.exit_code == 0, result.output
    assert captured["shared"].max_git_file_mb == 25


def test_init_join_warns_when_max_git_file_mb_passed(monkeypatch) -> None:
    import lintwin.cli.init as init_mod
    monkeypatch.setattr(init_mod, "check_prerequisites", lambda: [])
    monkeypatch.setattr(init_mod, "save_local_config", lambda *a, **k: None)
    monkeypatch.setattr(init_mod, "load_shared_config",
                        lambda *a, **k: init_mod.SharedConfig())
    monkeypatch.setattr(init_mod.git_core, "init_bare_repo", lambda *a, **k: None)
    monkeypatch.setattr(init_mod.git_core, "set_remote", lambda *a, **k: None)
    monkeypatch.setattr(init_mod.git_core, "pull_fast_forward", lambda *a, **k: None)
    monkeypatch.setattr(init_mod.Confirm, "ask", lambda *a, **k: False)
    result = CliRunner().invoke(cli, [
        "init", "--join", "git@example.com:me/dots.git",
        "--name", "desktop", "--max-git-file-mb", "50",
    ])
    assert result.exit_code == 0, result.output
    assert "ignored with --join" in result.output
