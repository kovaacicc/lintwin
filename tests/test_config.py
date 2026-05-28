import pytest
import tomli_w
from pathlib import Path
from lintwin.core.config import (
    LocalConfig, RemoteConfig, SharedConfig,
    load_local_config, save_local_config,
    load_shared_config, save_shared_config,
    track_path, untrack_path,
    add_machine_exclude, remove_machine_exclude,
)


def _write_local(path: Path, machine: str, remotes: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"machine": {"name": machine}, "remotes": remotes}
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def _write_shared(path: Path, git_paths: list, rsync_paths: list, never: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "git_paths": {"paths": git_paths},
        "rsync_paths": {"paths": rsync_paths},
        "never_sync": {"patterns": never},
    }
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def test_load_local_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    _write_local(cfg_path, "laptop", {
        "desktop": {"host": "100.1.1.1", "ssh_user": "karlo"}
    })
    cfg = load_local_config(cfg_path)
    assert cfg.machine_name == "laptop"
    assert "desktop" in cfg.remotes
    assert cfg.remotes["desktop"].host == "100.1.1.1"
    assert cfg.remotes["desktop"].tailscale_hostname is None


def test_save_and_reload_local_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg = LocalConfig(
        machine_name="laptop",
        remotes={"desktop": RemoteConfig(host="100.1.1.1", ssh_user="karlo", tailscale_hostname="desktop")}
    )
    save_local_config(cfg, cfg_path)
    loaded = load_local_config(cfg_path)
    assert loaded.machine_name == "laptop"
    assert loaded.remotes["desktop"].tailscale_hostname == "desktop"


def test_load_shared_config(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, ["~/.bashrc"], ["~/Downloads"], ["~/.cache"])
    cfg = load_shared_config(cfg_path)
    assert "~/.bashrc" in cfg.git_paths
    assert "~/Downloads" in cfg.rsync_paths
    assert "~/.cache" in cfg.never_sync


def test_track_path_git(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, ["~/.bashrc"], [], [])
    track_path("~/.vimrc", "git", cfg_path)
    cfg = load_shared_config(cfg_path)
    assert "~/.vimrc" in cfg.git_paths


def test_track_path_rsync(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, [], ["~/Downloads"], [])
    track_path("~/Projects", "rsync", cfg_path)
    cfg = load_shared_config(cfg_path)
    assert "~/Projects" in cfg.rsync_paths


def test_track_path_no_duplicate(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, ["~/.bashrc"], [], [])
    track_path("~/.bashrc", "git", cfg_path)
    cfg = load_shared_config(cfg_path)
    assert cfg.git_paths.count("~/.bashrc") == 1


def test_untrack_path_found(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, ["~/.bashrc"], ["~/Downloads"], [])
    result = untrack_path("~/.bashrc", cfg_path)
    assert result is True
    cfg = load_shared_config(cfg_path)
    assert "~/.bashrc" not in cfg.git_paths


def test_untrack_path_not_found(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, [], [], [])
    result = untrack_path("~/.vimrc", cfg_path)
    assert result is False


def test_shared_config_roundtrips_size_guard_fields(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    cfg = SharedConfig(
        git_paths=["~/.bashrc"],
        git_excludes=["~/.config/big.bin"],
        max_git_file_mb=50,
    )
    save_shared_config(cfg, cfg_path)
    loaded = load_shared_config(cfg_path)
    assert loaded.git_excludes == ["~/.config/big.bin"]
    assert loaded.max_git_file_mb == 50


def test_shared_config_defaults_when_size_guard_sections_absent(tmp_path: Path) -> None:
    cfg_path = tmp_path / "shared.toml"
    _write_shared(cfg_path, ["~/.bashrc"], ["~/Downloads"], ["~/.cache"])
    loaded = load_shared_config(cfg_path)
    assert loaded.git_excludes == []
    assert loaded.max_git_file_mb == 25


# --- per_machine tests ---

def test_load_shared_config_with_per_machine(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    cfg_file.write_text(
        '[per_machine.laptop]\nexcludes = ["~/.config/kwinrc", "~/.config/monitors.xml"]\n'
        '[per_machine.desktop]\nexcludes = ["~/.config/monitors.xml"]\n'
    )
    cfg = load_shared_config(cfg_file)
    assert cfg.per_machine == {
        "laptop": ["~/.config/kwinrc", "~/.config/monitors.xml"],
        "desktop": ["~/.config/monitors.xml"],
    }


def test_load_shared_config_per_machine_missing(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    cfg_file.write_text("")
    cfg = load_shared_config(cfg_file)
    assert cfg.per_machine == {}


def test_save_shared_config_round_trips_per_machine(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    original = SharedConfig(
        per_machine={"laptop": ["~/.config/kwinrc"], "desktop": ["~/.config/monitors.xml"]}
    )
    save_shared_config(original, cfg_file)
    loaded = load_shared_config(cfg_file)
    assert loaded.per_machine == original.per_machine


def test_add_machine_exclude(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    cfg_file.write_text("")
    add_machine_exclude("laptop", "~/.config/kwinrc", cfg_file)
    cfg = load_shared_config(cfg_file)
    assert "~/.config/kwinrc" in cfg.per_machine["laptop"]


def test_add_machine_exclude_no_duplicate(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    cfg_file.write_text("")
    add_machine_exclude("laptop", "~/.config/kwinrc", cfg_file)
    add_machine_exclude("laptop", "~/.config/kwinrc", cfg_file)
    cfg = load_shared_config(cfg_file)
    assert cfg.per_machine["laptop"].count("~/.config/kwinrc") == 1


def test_remove_machine_exclude_found(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    cfg_file.write_text("")
    add_machine_exclude("laptop", "~/.config/kwinrc", cfg_file)
    result = remove_machine_exclude("laptop", "~/.config/kwinrc", cfg_file)
    assert result is True
    cfg = load_shared_config(cfg_file)
    assert "~/.config/kwinrc" not in cfg.per_machine.get("laptop", [])


def test_remove_machine_exclude_not_found(tmp_path):
    cfg_file = tmp_path / "shared.toml"
    cfg_file.write_text("")
    result = remove_machine_exclude("laptop", "~/.config/kwinrc", cfg_file)
    assert result is False
