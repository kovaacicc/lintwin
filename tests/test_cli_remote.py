from pathlib import Path
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import LocalConfig, RemoteConfig, save_local_config, load_local_config


def _make_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    save_local_config(LocalConfig(machine_name="this-machine"), cfg)
    return cfg


def _with_remote(tmp_path: Path, name: str, host: str = "1.2.3.4", user: str = "me") -> Path:
    cfg = _make_config(tmp_path)
    config = load_local_config(cfg)
    config.remotes[name] = RemoteConfig(host=host, ssh_user=user)
    save_local_config(config, cfg)
    return cfg


def _patch(monkeypatch, cfg: Path):
    import lintwin.cli.remote as m
    monkeypatch.setattr(m, "LOCAL_CONFIG_PATH", cfg)


# --- remote add ---

def test_remote_add_writes_entry(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config(tmp_path)
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, [
        "remote", "add", "laptop", "--host", "10.0.0.5", "--ssh-user", "karlo",
    ])
    assert result.exit_code == 0, result.output

    loaded = load_local_config(cfg)
    assert "laptop" in loaded.remotes
    assert loaded.remotes["laptop"].host == "10.0.0.5"
    assert loaded.remotes["laptop"].ssh_user == "karlo"


def test_remote_add_with_optional_flags(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config(tmp_path)
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, [
        "remote", "add", "server",
        "--host", "10.0.0.10", "--ssh-user", "root",
        "--tailscale-hostname", "server.tail",
        "--ssh-port", "2222",
    ])
    assert result.exit_code == 0, result.output

    r = load_local_config(cfg).remotes["server"]
    assert r.tailscale_hostname == "server.tail"
    assert r.ssh_port == 2222


def test_remote_add_fails_if_already_exists(tmp_path: Path, monkeypatch) -> None:
    cfg = _with_remote(tmp_path, "laptop")
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, [
        "remote", "add", "laptop", "--host", "10.0.0.5", "--ssh-user", "karlo",
    ])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_remote_add_fails_if_not_initialized(tmp_path: Path, monkeypatch) -> None:
    _patch(monkeypatch, tmp_path / "config.toml")  # does not exist

    result = CliRunner().invoke(cli, [
        "remote", "add", "laptop", "--host", "10.0.0.5", "--ssh-user", "karlo",
    ])
    assert result.exit_code != 0
    assert "lintwin init" in result.output


# --- remote list ---

def test_remote_list_shows_remotes(tmp_path: Path, monkeypatch) -> None:
    cfg = _with_remote(tmp_path, "laptop", host="10.0.0.5", user="karlo")
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, ["remote", "list"])
    assert result.exit_code == 0, result.output
    assert "laptop" in result.output
    assert "10.0.0.5" in result.output
    assert "karlo" in result.output


def test_remote_list_no_remotes(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config(tmp_path)
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, ["remote", "list"])
    assert result.exit_code == 0, result.output
    assert "no remotes" in result.output.lower()


def test_remote_list_fails_if_not_initialized(tmp_path: Path, monkeypatch) -> None:
    _patch(monkeypatch, tmp_path / "config.toml")

    result = CliRunner().invoke(cli, ["remote", "list"])
    assert result.exit_code != 0
    assert "lintwin init" in result.output


# --- remote remove ---

def test_remote_remove_deletes_entry(tmp_path: Path, monkeypatch) -> None:
    cfg = _with_remote(tmp_path, "laptop")
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, ["remote", "remove", "laptop"])
    assert result.exit_code == 0, result.output
    assert "laptop" not in load_local_config(cfg).remotes


def test_remote_remove_fails_if_not_found(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config(tmp_path)
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, ["remote", "remove", "ghost"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# --- remote edit ---

def test_remote_edit_updates_host(tmp_path: Path, monkeypatch) -> None:
    cfg = _with_remote(tmp_path, "laptop", host="10.0.0.5", user="karlo")
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, [
        "remote", "edit", "laptop", "--host", "192.168.1.50",
    ])
    assert result.exit_code == 0, result.output

    r = load_local_config(cfg).remotes["laptop"]
    assert r.host == "192.168.1.50"
    assert r.ssh_user == "karlo"  # unchanged


def test_remote_edit_clears_tailscale_hostname(tmp_path: Path, monkeypatch) -> None:
    from lintwin.core.config import RemoteConfig
    cfg = _make_config(tmp_path)
    config = load_local_config(cfg)
    config.remotes["laptop"] = RemoteConfig(host="10.0.0.5", ssh_user="karlo", tailscale_hostname="laptop.tail")
    save_local_config(config, cfg)
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, ["remote", "edit", "laptop", "--no-tailscale"])
    assert result.exit_code == 0, result.output
    assert load_local_config(cfg).remotes["laptop"].tailscale_hostname is None


def test_remote_edit_fails_if_not_found(tmp_path: Path, monkeypatch) -> None:
    cfg = _make_config(tmp_path)
    _patch(monkeypatch, cfg)

    result = CliRunner().invoke(cli, [
        "remote", "edit", "ghost", "--host", "1.2.3.4",
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
