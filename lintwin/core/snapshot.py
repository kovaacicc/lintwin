import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from .constants import SNAPSHOT_FILE


@dataclass
class FileEntry:
    size: int
    modified: str


@dataclass
class RemoteSnapshot:
    timestamp: str
    files: dict[str, FileEntry] = field(default_factory=dict)


@dataclass
class Snapshot:
    machine: str
    remotes: dict[str, RemoteSnapshot] = field(default_factory=dict)


def load_snapshot(path: Path = SNAPSHOT_FILE) -> Snapshot | None:
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    remotes = {
        name: RemoteSnapshot(
            timestamp=r["timestamp"],
            files={k: FileEntry(**v) for k, v in r.get("files", {}).items()},
        )
        for name, r in data.get("remotes", {}).items()
    }
    return Snapshot(machine=data["machine"], remotes=remotes)


def save_snapshot(snapshot: Snapshot, path: Path = SNAPSHOT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "machine": snapshot.machine,
        "remotes": {
            name: {
                "timestamp": r.timestamp,
                "files": {k: {"size": v.size, "modified": v.modified} for k, v in r.files.items()},
            }
            for name, r in snapshot.remotes.items()
        },
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_file_snapshot(paths: list[str]) -> dict[str, FileEntry]:
    entries: dict[str, FileEntry] = {}
    for path_str in paths:
        root = Path(path_str).expanduser()
        if root.is_file():
            _add_entry(entries, root)
        elif root.is_dir():
            for f in root.rglob("*"):
                if f.is_file():
                    _add_entry(entries, f)
    return entries


def _add_entry(entries: dict[str, FileEntry], path: Path) -> None:
    stat = path.stat()
    entries[str(path)] = FileEntry(
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )


def update_snapshot(
    machine_name: str,
    remote_name: str,
    rsync_paths: list[str],
    path: Path | None = None,
) -> None:
    if path is None:
        path = SNAPSHOT_FILE
    snap = load_snapshot(path)
    if snap is None:
        snap = Snapshot(machine=machine_name)
    snap.remotes[remote_name] = RemoteSnapshot(
        timestamp=now_iso(),
        files=build_file_snapshot(rsync_paths),
    )
    save_snapshot(snap, path)
