import json
import subprocess
import tempfile
from dataclasses import dataclass
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
    ssh_cmd += [f"{remote.ssh_user}@{host}", f"cat {remote_path}"]
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


def _is_binary(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def build_excludes_file(patterns: list[str]) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".excludes", delete=False) as f:
        for pattern in patterns:
            f.write(f"{pattern}\n")
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
    remote_path = f"{remote.ssh_user}@{host}:{expanded}/"
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
