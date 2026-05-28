from pathlib import Path
from unittest.mock import patch, MagicMock
from lintwin.core.config import RemoteConfig
from lintwin.core.snapshot import Snapshot, RemoteSnapshot, FileEntry
from lintwin.core.rsync import (
    check_connectivity, detect_conflicts, build_excludes_file, _is_binary, Conflict,
    rsync_path, rsync_file, fetch_remote_snapshot, Resolution,
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


def test_rsync_path_push_uses_tilde_for_remote() -> None:
    """Remote path must use ~/... so rsync expands ~ relative to remote user's home, not local."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rsync_path("~/Documents", REMOTE)
    cmd = mock_run.call_args[0][0]
    remote_arg = next(a for a in cmd if "@" in a and ":" in a)
    assert ":~/" in remote_arg, f"Expected tilde in remote path, got: {remote_arg}"
    assert ":/home/" not in remote_arg, f"Local home leaked into remote path: {remote_arg}"


def test_rsync_path_pull_uses_tilde_for_remote() -> None:
    """Pull direction must also use ~/... on the remote side."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rsync_path("~/Documents", REMOTE, direction="pull")
    cmd = mock_run.call_args[0][0]
    remote_arg = next(a for a in cmd if "@" in a and ":" in a)
    assert ":~/" in remote_arg, f"Expected tilde in remote path, got: {remote_arg}"
    assert ":/home/" not in remote_arg, f"Local home leaked into remote path: {remote_arg}"


def test_fetch_remote_snapshot_uses_tilde_path_in_ssh_command() -> None:
    """SSH cat command must use ~/... so it resolves against the remote user's home."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        fetch_remote_snapshot(REMOTE)
    ssh_cmd = mock_run.call_args[0][0]
    cat_arg = ssh_cmd[-1]
    assert cat_arg.startswith("cat ~/"), f"Expected tilde path in cat command, got: {cat_arg}"
    assert "/home/" not in cat_arg, f"Local home leaked into SSH snapshot path: {cat_arg}"


def test_is_binary_text_file(tmp_path: Path) -> None:
    f = tmp_path / "text.txt"
    f.write_text("hello world")
    assert _is_binary(str(f)) is False


def test_is_binary_binary_file(tmp_path: Path) -> None:
    f = tmp_path / "binary.bin"
    f.write_bytes(b"\x00\x01\x02")
    assert _is_binary(str(f)) is True


def test_resolution_enum_values() -> None:
    assert Resolution.KEEP_LOCAL.value == "keep_local"
    assert Resolution.KEEP_REMOTE.value == "keep_remote"
    assert Resolution.SKIP.value == "skip"


def test_rsync_file_pull_uses_tilde_for_remote() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rsync_file("~/Documents/notes.txt", REMOTE, direction="pull")
    cmd = mock_run.call_args[0][0]
    remote_arg = next(a for a in cmd if "@" in a and ":" in a)
    assert ":~/" in remote_arg, f"Expected tilde in remote path, got: {remote_arg}"
    assert ":/home/" not in remote_arg


def test_rsync_file_push_uses_tilde_for_remote() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rsync_file("~/Documents/notes.txt", REMOTE, direction="push")
    cmd = mock_run.call_args[0][0]
    remote_arg = next(a for a in cmd if "@" in a and ":" in a)
    assert ":~/" in remote_arg, f"Expected tilde in remote path, got: {remote_arg}"
    assert ":/home/" not in remote_arg


def test_rsync_file_respects_ssh_port() -> None:
    remote_with_port = RemoteConfig(host="10.0.0.1", ssh_user="karlo", ssh_port=2222)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        rsync_file("~/Documents/notes.txt", remote_with_port, direction="pull")
    cmd = mock_run.call_args[0][0]
    assert "-e" in cmd
    assert "2222" in cmd[cmd.index("-e") + 1]
