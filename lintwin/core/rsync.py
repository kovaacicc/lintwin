import json
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from .config import RemoteConfig
from .snapshot import Snapshot, RemoteSnapshot, FileEntry
from .constants import SNAPSHOT_FILE


@dataclass
class Conflict:
    path: str
    local_modified: str
    remote_modified: str
    is_binary: bool


class Resolution(Enum):
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"
    SKIP = "skip"


def check_connectivity(remote: RemoteConfig) -> bool:
    if remote.tailscale_hostname:
        result = subprocess.run(
            ["tailscale", "ping", "-c", "1", remote.tailscale_hostname],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return True
    result = subprocess.run(
        ["ping", "-c", "1", "-W", "2", remote.host],
        capture_output=True,
    )
    return result.returncode == 0


def fetch_remote_snapshot(remote: RemoteConfig, remote_path: Path = SNAPSHOT_FILE) -> Snapshot | None:
    host = remote.tailscale_hostname or remote.host
    ssh_cmd = ["ssh"]
    if remote.ssh_port:
        ssh_cmd += ["-p", str(remote.ssh_port)]
    ssh_cmd += [f"{remote.ssh_user}@{host}", f"cat {_to_remote_path(remote_path)}"]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    remotes = {
        name: RemoteSnapshot(
            timestamp=r["timestamp"],
            files={k: FileEntry(**v) for k, v in r.get("files", {}).items()},
        )
        for name, r in data.get("remotes", {}).items()
    }
    return Snapshot(machine=data["machine"], remotes=remotes)


def detect_conflicts(
    local_snapshot: Snapshot,
    remote_snapshot: Snapshot,
    remote_name: str,
    paths: list[str],
) -> list[Conflict]:
    local_remote = local_snapshot.remotes.get(remote_name)
    if not local_remote:
        return []
    last_sync_ts = local_remote.timestamp
    local_files = local_remote.files

    remote_local = remote_snapshot.remotes.get(local_snapshot.machine, RemoteSnapshot(timestamp=last_sync_ts))
    remote_files = remote_local.files

    conflicts = []
    for path, local_entry in local_files.items():
        remote_entry = remote_files.get(path)
        if remote_entry:
            if local_entry.modified > last_sync_ts and remote_entry.modified > last_sync_ts:
                conflicts.append(Conflict(
                    path=path,
                    local_modified=local_entry.modified,
                    remote_modified=remote_entry.modified,
                    is_binary=_is_binary(path),
                ))
    return conflicts


def _to_remote_path(local_path: str | Path) -> str:
    """Convert a local absolute or tilde path to ~/... for use as the remote side of rsync/SSH.

    Paths outside $HOME are returned unchanged (e.g. /opt/data stays as /opt/data).
    """
    abs_path = str(Path(local_path).expanduser())
    home = str(Path.home())
    if abs_path == home:
        return "~"
    if abs_path.startswith(home + "/"):
        return "~/" + abs_path[len(home) + 1:]
    return abs_path


def _is_binary(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def _translate_pattern(pattern: str, source_path: str) -> str | None:
    """
    Translate a never_sync pattern into an rsync exclude relative to source_path.

    Bare patterns (no '/') match anywhere in the tree and are returned unchanged.
    Path patterns are expanded from '~', checked against source_path, and rewritten
    as '/<relative>' so rsync anchors them to the transfer root. Patterns that don't
    fall under source_path are dropped (return None).
    """
    if "/" not in pattern:
        return pattern

    home = str(Path.home())
    abs_pattern = pattern.replace("~", home, 1) if pattern.startswith("~") else pattern
    abs_source = str(Path(source_path).expanduser())

    # Find the non-glob directory prefix to check containment
    glob_chars = set("*?[")
    first_glob = next((i for i, c in enumerate(abs_pattern) if c in glob_chars), len(abs_pattern))
    non_glob = abs_pattern[:first_glob]
    prefix_dir = str(Path(non_glob).parent)

    try:
        Path(prefix_dir).relative_to(abs_source)
    except ValueError:
        return None

    rel = abs_pattern[len(abs_source):].lstrip("/")
    return f"/{rel}"


def build_excludes_file(patterns: list[str], source_path: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".excludes", delete=False) as f:
        for pattern in patterns:
            translated = _translate_pattern(pattern, source_path)
            if translated is not None:
                f.write(f"{translated}\n")
        return f.name


def rsync_path(
    local_path: str,
    remote: RemoteConfig,
    direction: str = "push",
    dry_run: bool = False,
    excludes_file: str | None = None,
) -> subprocess.CompletedProcess:
    expanded = str(Path(local_path).expanduser())
    host = remote.tailscale_hostname or remote.host
    remote_path = f"{remote.ssh_user}@{host}:{_to_remote_path(local_path)}/"
    cmd = ["rsync", "-avz", "--delete"]
    if remote.ssh_port:
        cmd += ["-e", f"ssh -p {remote.ssh_port}"]
    if dry_run:
        cmd.append("--dry-run")
    if excludes_file:
        cmd.extend(["--exclude-from", excludes_file])
    if direction == "push":
        cmd.extend([f"{expanded}/", remote_path])
    else:
        cmd.extend([remote_path, f"{expanded}/"])
    return subprocess.run(cmd, capture_output=True, text=True)


def rsync_file(
    local_path: str,
    remote: RemoteConfig,
    direction: str = "pull",
) -> subprocess.CompletedProcess:
    expanded = str(Path(local_path).expanduser())
    host = remote.tailscale_hostname or remote.host
    remote_file = f"{remote.ssh_user}@{host}:{_to_remote_path(local_path)}"
    cmd = ["rsync", "-avz"]
    if remote.ssh_port:
        cmd += ["-e", f"ssh -p {remote.ssh_port}"]
    if direction == "pull":
        cmd.extend([remote_file, expanded])
    else:
        cmd.extend([expanded, remote_file])
    return subprocess.run(cmd, capture_output=True, text=True)
