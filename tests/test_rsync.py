from pathlib import Path
from unittest.mock import patch, MagicMock
from lintwin.core.config import RemoteConfig
from lintwin.core.snapshot import Snapshot, RemoteSnapshot, FileEntry
from lintwin.core.rsync import (
    check_connectivity, detect_conflicts, build_excludes_file, _is_binary, Conflict
)


REMOTE = RemoteConfig(host="10.0.0.1", ssh_user="karlo", tailscale_hostname="desktop")
REMOTE_NO_TS = RemoteConfig(host="10.0.0.1", ssh_user="karlo")


def test_check_connectivity_uses_tailscale_first() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = check_connectivity(REMOTE)
    assert result is True
    first_call_cmd = mock_run.call_args_list[0][0][0]
    assert "tailscale" in first_call_cmd


def test_check_connectivity_fallback_to_ping() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = check_connectivity(REMOTE_NO_TS)
    assert result is True
    first_call_cmd = mock_run.call_args_list[0][0][0]
    assert "ping" in first_call_cmd


def test_check_connectivity_returns_false_on_failure() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        result = check_connectivity(REMOTE_NO_TS)
    assert result is False


def _make_snapshot(machine: str, remote_name: str, sync_ts: str, files: dict) -> Snapshot:
    return Snapshot(
        machine=machine,
        remotes={
            remote_name: RemoteSnapshot(timestamp=sync_ts, files={
                k: FileEntry(size=100, modified=v) for k, v in files.items()
            })
        }
    )


def test_detect_conflicts_both_modified() -> None:
    last_sync = "2026-05-20T08:00:00+00:00"
    local = _make_snapshot("laptop", "desktop", last_sync, {
        "/home/k/doc.txt": "2026-05-20T10:00:00+00:00"
    })
    remote = _make_snapshot("desktop", "laptop", last_sync, {
        "/home/k/doc.txt": "2026-05-20T09:00:00+00:00"
    })
    conflicts = detect_conflicts(local, remote, "desktop", ["/home/k"])
    assert len(conflicts) == 1
    assert conflicts[0].path == "/home/k/doc.txt"


def test_detect_conflicts_one_side_only() -> None:
    last_sync = "2026-05-20T08:00:00+00:00"
    local = _make_snapshot("laptop", "desktop", last_sync, {
        "/home/k/doc.txt": "2026-05-20T10:00:00+00:00"
    })
    remote = _make_snapshot("desktop", "laptop", last_sync, {
        "/home/k/doc.txt": "2026-05-20T07:00:00+00:00"  # before last sync
    })
    conflicts = detect_conflicts(local, remote, "desktop", ["/home/k"])
    assert conflicts == []


def test_build_excludes_file_bare_glob_kept_for_any_source() -> None:
    """Patterns with no '/' (bare globs) match anywhere in the tree and are always kept."""
    excludes = build_excludes_file(["*.gpg"], "~/Documents")
    content = Path(excludes).read_text()
    assert "*.gpg" in content


def test_build_excludes_file_drops_path_outside_source() -> None:
    """Path patterns that don't live under the source root are dropped."""
    excludes = build_excludes_file(["~/.ssh/id_*"], "~/Documents")
    content = Path(excludes).read_text()
    assert content.strip() == ""


def test_build_excludes_file_translates_path_inside_home_root() -> None:
    """~/.cache syncing from ~ becomes /.cache (rsync-relative, no tilde)."""
    excludes = build_excludes_file(["~/.cache"], "~")
    content = Path(excludes).read_text()
    assert "/.cache" in content
    assert "~" not in content


def test_build_excludes_file_translates_glob_inside_home_root() -> None:
    """~/.ssh/id_* syncing from ~ becomes /.ssh/id_* (rsync-relative, no tilde)."""
    excludes = build_excludes_file(["~/.ssh/id_*"], "~")
    content = Path(excludes).read_text()
    assert "/.ssh/id_*" in content
    assert "~" not in content


def test_build_excludes_file_acceptance_documents_source() -> None:
    """
    Acceptance criterion: source=~/Documents keeps *.gpg but drops ~/.ssh/id_*.
    """
    excludes = build_excludes_file(["~/.ssh/id_*", "*.gpg"], "~/Documents")
    content = Path(excludes).read_text()
    assert "*.gpg" in content
    assert ".ssh" not in content


def test_build_excludes_file_acceptance_home_source() -> None:
    """
    Acceptance criterion: source=~ includes both patterns in rsync-understandable form.
    """
    excludes = build_excludes_file(["~/.ssh/id_*", "*.gpg"], "~")
    content = Path(excludes).read_text()
    assert "*.gpg" in content
    assert "/.ssh/id_*" in content
    assert "~" not in content


def test_is_binary_text_file(tmp_path: Path) -> None:
    f = tmp_path / "text.txt"
    f.write_text("hello world")
    assert _is_binary(str(f)) is False


def test_is_binary_binary_file(tmp_path: Path) -> None:
    f = tmp_path / "binary.bin"
    f.write_bytes(b"\x00\x01\x02")
    assert _is_binary(str(f)) is True
