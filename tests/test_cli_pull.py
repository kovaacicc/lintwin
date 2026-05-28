from unittest.mock import MagicMock
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import LocalConfig, RemoteConfig, SharedConfig
from lintwin.core.snapshot import (
    Snapshot, RemoteSnapshot, FileEntry, load_snapshot, now_iso,
)
from lintwin.core.rsync import detect_conflicts


MOCK_LOCAL = LocalConfig(
    machine_name="laptop",
    remotes={"desktop": RemoteConfig(host="100.1.1.1", ssh_user="karlo")},
)
MOCK_SHARED = SharedConfig(git_paths=["~/.bashrc"], rsync_paths=["~/Downloads"])


def _patch_pull(monkeypatch, tmp_path, *, connectivity=True):
    snap_file = tmp_path / "last_sync.json"
    monkeypatch.setattr("lintwin.cli.pull.load_local_config", lambda: MOCK_LOCAL)
    monkeypatch.setattr("lintwin.cli.pull.load_shared_config", lambda: MOCK_SHARED)
    monkeypatch.setattr("lintwin.cli.pull.git_core.is_initialized", lambda: True)
    monkeypatch.setattr("lintwin.cli.pull.git_core.fetch", lambda repo: None)
    monkeypatch.setattr("lintwin.cli.pull.git_core.divergence_info", lambda branch, repo: (0, 0))
    monkeypatch.setattr("lintwin.cli.pull.check_connectivity", lambda r: connectivity)
    monkeypatch.setattr("lintwin.cli.pull.load_snapshot", lambda path: None)
    monkeypatch.setattr("lintwin.cli.pull.fetch_remote_snapshot", lambda r: None)
    monkeypatch.setattr("lintwin.cli.pull.build_excludes_file",
                        lambda ns, path: tmp_path / "excl")
    monkeypatch.setattr("lintwin.cli.pull.rsync_path",
                        lambda path, remote, direction, excludes_file: MagicMock(returncode=0))
    monkeypatch.setattr("lintwin.cli.pull.SNAPSHOT_FILE", snap_file)
    monkeypatch.setattr("lintwin.core.snapshot.build_file_snapshot", lambda paths: {})
    return snap_file


def test_pull_updates_snapshot_after_rsync(monkeypatch, tmp_path) -> None:
    snap_file = _patch_pull(monkeypatch, tmp_path)

    result = CliRunner().invoke(cli, ["pull", "--to", "desktop"])

    assert result.exit_code == 0
    assert snap_file.exists(), "pull must write snapshot after rsync completes"
    snap = load_snapshot(snap_file)
    assert snap is not None
    assert snap.machine == "laptop"
    assert "desktop" in snap.remotes


def test_pull_skips_snapshot_when_remote_unreachable(monkeypatch, tmp_path) -> None:
    snap_file = _patch_pull(monkeypatch, tmp_path, connectivity=False)

    result = CliRunner().invoke(cli, ["pull", "--to", "desktop"])

    assert result.exit_code == 0
    assert not snap_file.exists(), "snapshot must not be written when rsync is skipped"


def test_no_spurious_conflicts_when_snapshot_is_current() -> None:
    """When last_sync_ts is recent, files with older mtimes are not flagged as conflicts."""
    file_path = "/home/user/notes.txt"
    file_mtime = "2023-06-01T12:00:00+00:00"
    current_ts = now_iso()

    local_snap = Snapshot(
        machine="laptop",
        remotes={"desktop": RemoteSnapshot(
            timestamp=current_ts,
            files={file_path: FileEntry(size=100, modified=file_mtime)},
        )},
    )
    remote_snap = Snapshot(
        machine="desktop",
        remotes={"laptop": RemoteSnapshot(
            timestamp=current_ts,
            files={file_path: FileEntry(size=100, modified=file_mtime)},
        )},
    )

    conflicts = detect_conflicts(local_snap, remote_snap, "desktop", [file_path])
    assert conflicts == []
