from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import load_shared_config


def _write_local_config(tmp_path, machine_name="laptop"):
    local = tmp_path / "config.toml"
    local.write_text(f'[machine]\nname = "{machine_name}"\n[remotes]\n')
    return local


def _write_shared_config(tmp_path):
    shared = tmp_path / "shared.toml"
    shared.write_text("")
    return shared


def test_exclude_add(tmp_path, monkeypatch):
    local = _write_local_config(tmp_path)
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    result = runner.invoke(cli, ["exclude", "add", "~/.config/kwinrc"])
    assert result.exit_code == 0
    cfg = load_shared_config(shared)
    assert "~/.config/kwinrc" in cfg.per_machine.get("laptop", [])


def test_exclude_add_idempotent(tmp_path, monkeypatch):
    local = _write_local_config(tmp_path)
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    runner.invoke(cli, ["exclude", "add", "~/.config/kwinrc"])
    runner.invoke(cli, ["exclude", "add", "~/.config/kwinrc"])
    cfg = load_shared_config(shared)
    assert cfg.per_machine.get("laptop", []).count("~/.config/kwinrc") == 1


def test_exclude_remove(tmp_path, monkeypatch):
    local = _write_local_config(tmp_path)
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    runner.invoke(cli, ["exclude", "add", "~/.config/kwinrc"])
    result = runner.invoke(cli, ["exclude", "remove", "~/.config/kwinrc"])
    assert result.exit_code == 0
    assert "Removed" in result.output
    cfg = load_shared_config(shared)
    assert "~/.config/kwinrc" not in cfg.per_machine.get("laptop", [])


def test_exclude_remove_not_found(tmp_path, monkeypatch):
    local = _write_local_config(tmp_path)
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    result = runner.invoke(cli, ["exclude", "remove", "~/.config/kwinrc"])
    assert result.exit_code != 0
    assert "not in the exclude list" in result.output


def test_exclude_list(tmp_path, monkeypatch):
    local = _write_local_config(tmp_path)
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    runner.invoke(cli, ["exclude", "add", "~/.config/kwinrc"])
    result = runner.invoke(cli, ["exclude", "list"])
    assert result.exit_code == 0
    assert "~/.config/kwinrc" in result.output


def test_exclude_list_empty(tmp_path, monkeypatch):
    local = _write_local_config(tmp_path)
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", local)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    result = runner.invoke(cli, ["exclude", "list"])
    assert result.exit_code == 0
    assert "No per-machine excludes" in result.output


def test_exclude_not_initialized(tmp_path, monkeypatch):
    missing = tmp_path / "config.toml"
    shared = _write_shared_config(tmp_path)
    monkeypatch.setattr("lintwin.cli.exclude.LOCAL_CONFIG_PATH", missing)
    monkeypatch.setattr("lintwin.cli.exclude.SHARED_CONFIG_PATH", shared)
    runner = CliRunner()
    for args in (
        ["exclude", "add", "~/.config/kwinrc"],
        ["exclude", "remove", "~/.config/kwinrc"],
        ["exclude", "list"],
    ):
        result = runner.invoke(cli, args)
        assert result.exit_code != 0
