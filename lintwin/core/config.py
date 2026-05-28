import tomllib
import tomli_w
from dataclasses import dataclass, field
from pathlib import Path
from .constants import (
    LOCAL_CONFIG_PATH, SHARED_CONFIG_PATH,
    DEFAULT_GIT_PATHS, DEFAULT_RSYNC_PATHS, DEFAULT_NEVER_SYNC,
    DEFAULT_MAX_GIT_FILE_MB,
)


@dataclass
class RemoteConfig:
    host: str
    ssh_user: str
    tailscale_hostname: str | None = None
    ssh_port: int | None = None


@dataclass
class LocalConfig:
    machine_name: str
    remotes: dict[str, RemoteConfig] = field(default_factory=dict)


@dataclass
class SharedConfig:
    git_paths: list[str] = field(default_factory=lambda: list(DEFAULT_GIT_PATHS))
    rsync_paths: list[str] = field(default_factory=lambda: list(DEFAULT_RSYNC_PATHS))
    never_sync: list[str] = field(default_factory=lambda: list(DEFAULT_NEVER_SYNC))
    git_excludes: list[str] = field(default_factory=list)
    max_git_file_mb: int = DEFAULT_MAX_GIT_FILE_MB
    per_machine: dict[str, list[str]] = field(default_factory=dict)


def load_local_config(path: Path = LOCAL_CONFIG_PATH) -> LocalConfig:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    remotes = {
        name: RemoteConfig(
            host=cfg["host"],
            ssh_user=cfg["ssh_user"],
            tailscale_hostname=cfg.get("tailscale_hostname"),
            ssh_port=cfg.get("ssh_port"),
        )
        for name, cfg in data.get("remotes", {}).items()
    }
    return LocalConfig(machine_name=data["machine"]["name"], remotes=remotes)


def save_local_config(config: LocalConfig, path: Path = LOCAL_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"machine": {"name": config.machine_name}, "remotes": {}}
    for name, r in config.remotes.items():
        entry: dict = {"host": r.host, "ssh_user": r.ssh_user}
        if r.tailscale_hostname is not None:
            entry["tailscale_hostname"] = r.tailscale_hostname
        if r.ssh_port is not None:
            entry["ssh_port"] = r.ssh_port
        data["remotes"][name] = entry
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def load_shared_config(path: Path = SHARED_CONFIG_PATH) -> SharedConfig:
    if not path.exists():
        return SharedConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    per_machine_raw = data.get("per_machine", {})
    return SharedConfig(
        git_paths=data.get("git_paths", {}).get("paths", list(DEFAULT_GIT_PATHS)),
        rsync_paths=data.get("rsync_paths", {}).get("paths", list(DEFAULT_RSYNC_PATHS)),
        never_sync=data.get("never_sync", {}).get("patterns", list(DEFAULT_NEVER_SYNC)),
        git_excludes=data.get("git_excludes", {}).get("paths", []),
        max_git_file_mb=data.get("size_guard", {}).get("max_git_file_mb", DEFAULT_MAX_GIT_FILE_MB),
        per_machine={name: cfg.get("excludes", []) for name, cfg in per_machine_raw.items()},
    )


def save_shared_config(config: SharedConfig, path: Path = SHARED_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "git_paths": {"paths": config.git_paths},
        "rsync_paths": {"paths": config.rsync_paths},
        "never_sync": {"patterns": config.never_sync},
        "git_excludes": {"paths": config.git_excludes},
        # [size_guard] is a sub-table so future guard options can be added without new top-level keys.
        "size_guard": {"max_git_file_mb": config.max_git_file_mb},
    }
    if config.per_machine:
        data["per_machine"] = {
            name: {"excludes": excludes}
            for name, excludes in config.per_machine.items()
        }
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def track_path(path_str: str, via: str, shared_path: Path = SHARED_CONFIG_PATH) -> None:
    config = load_shared_config(shared_path)
    target = config.git_paths if via == "git" else config.rsync_paths
    if path_str not in target:
        target.append(path_str)
        save_shared_config(config, shared_path)


def untrack_path(path_str: str, shared_path: Path = SHARED_CONFIG_PATH) -> bool:
    config = load_shared_config(shared_path)
    for lst in (config.git_paths, config.rsync_paths):
        if path_str in lst:
            lst.remove(path_str)
            save_shared_config(config, shared_path)
            return True
    return False


def add_machine_exclude(machine_name: str, path_str: str, shared_path: Path = SHARED_CONFIG_PATH) -> None:
    config = load_shared_config(shared_path)
    excludes = config.per_machine.setdefault(machine_name, [])
    if path_str not in excludes:
        excludes.append(path_str)
        save_shared_config(config, shared_path)


def remove_machine_exclude(machine_name: str, path_str: str, shared_path: Path = SHARED_CONFIG_PATH) -> bool:
    config = load_shared_config(shared_path)
    excludes = config.per_machine.get(machine_name, [])
    if path_str not in excludes:
        return False
    excludes.remove(path_str)
    save_shared_config(config, shared_path)
    return True
