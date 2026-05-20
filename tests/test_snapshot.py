import json
from pathlib import Path
from datetime import datetime, timezone
from lintwin.core.snapshot import (
    Snapshot, RemoteSnapshot, FileEntry,
    load_snapshot, save_snapshot, now_iso, build_file_snapshot,
)


def test_load_returns_none_when_missing(tmp_path: Path) -> None:
    result = load_snapshot(tmp_path / "missing.json")
    assert result is None


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "last_sync.json"
    snap = Snapshot(
        machine="laptop",
        remotes={
            "desktop": RemoteSnapshot(
                timestamp="2026-05-20T10:00:00+00:00",
                files={"/home/k/foo.txt": FileEntry(size=42, modified="2026-05-20T09:00:00+00:00")}
            )
        }
    )
    save_snapshot(snap, path)
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.machine == "laptop"
    assert "desktop" in loaded.remotes
    assert loaded.remotes["desktop"].files["/home/k/foo.txt"].size == 42


def test_now_iso_is_utc() -> None:
    ts = now_iso()
    dt = datetime.fromisoformat(ts)
    assert dt.tzinfo is not None


def test_build_file_snapshot(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    entries = build_file_snapshot([str(tmp_path)])
    assert str(f) in entries
    assert entries[str(f)].size == 5
