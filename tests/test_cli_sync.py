from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from lintwin.cli.main import cli
from lintwin.core.config import LocalConfig, RemoteConfig, SharedConfig
from lintwin.core.rsync import Conflict, Resolution
from lintwin.core.snapshot import Snapshot, RemoteSnapshot
from lintwin.core.scanner import DirtyRepo
from pathlib import Path


MOCK_LOCAL = LocalConfig(
    machine_name="laptop",
    remotes={"desktop": RemoteConfig(host="100.1.1.1", ssh_user="karlo")},
)
MOCK_SHARED = SharedConfig(git_paths=["~/.bashrc"], rsync_paths=["~/Downloads"])


def _patch_configs(monkeypatch):
    monkeypatch.setattr("lintwin.cli.sync.load_local_config", lambda: MOCK_LOCAL)
    monkeypatch.setattr("lintwin.cli.sync.load_shared_config", lambda: MOCK_SHARED)
    monkeypatch.setattr("lintwin.cli.sync.git_core.is_initialized", lambda: True)


def test_sync_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output


def test_sync_dry_run_no_changes(monkeypatch) -> None:
    _patch_configs(monkeypatch)
    monkeypatch.setattr("lintwin.cli.sync.scan_for_dirty_repos", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.git_status_short", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.check_connectivity", lambda r: False)

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--dry-run"])
    assert result.exit_code == 0
    assert "dry" in result.output.lower() or "preview" in result.output.lower() or "nothing" in result.output.lower()


def test_sync_aborts_on_connectivity_failure(monkeypatch) -> None:
    _patch_configs(monkeypatch)
    monkeypatch.setattr("lintwin.cli.sync.scan_for_dirty_repos", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.git_status_short", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.check_connectivity", lambda r: False)
    monkeypatch.setattr("lintwin.cli.sync._do_git_sync", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--to", "desktop"], input="y\n")
    assert "Cannot reach" in result.output


def test_sync_shows_dirty_repos(monkeypatch) -> None:
    _patch_configs(monkeypatch)
    dirty = DirtyRepo(path=Path("/home/k/projects/foo"), uncommitted=3, unpushed=1)
    monkeypatch.setattr("lintwin.cli.sync.scan_for_dirty_repos", lambda paths: [dirty])
    monkeypatch.setattr("lintwin.cli.sync.git_status_short", lambda paths: [])
    monkeypatch.setattr("lintwin.cli.sync.check_connectivity", lambda r: False)

    runner = CliRunner()
    result = runner.invoke(cli, ["sync", "--dry-run"], input="s\n")
    assert "foo" in result.output or "dirty" in result.output.lower()


def test_apply_size_resolution_offload_to_rsync() -> None:
    from lintwin.cli.sync import apply_size_resolution
    from lintwin.core.config import SharedConfig
    from lintwin.core.sizeguard import FlaggedItem
    shared = SharedConfig(git_paths=[], rsync_paths=[], never_sync=[])
    apply_size_resolution(shared, FlaggedItem("~/.config/big.bin", 99, False), "r")
    assert "~/.config/big.bin" in shared.git_excludes
    assert "~/.config/big.bin" in shared.rsync_paths
    assert "~/.config/big.bin" not in shared.never_sync


def test_apply_size_resolution_never_sync() -> None:
    from lintwin.cli.sync import apply_size_resolution
    from lintwin.core.config import SharedConfig
    from lintwin.core.sizeguard import FlaggedItem
    shared = SharedConfig(git_paths=[], rsync_paths=[], never_sync=[])
    apply_size_resolution(shared, FlaggedItem("~/.config/big.bin", 99, False), "n")
    assert "~/.config/big.bin" in shared.never_sync
    assert "~/.config/big.bin" not in shared.git_excludes
    assert "~/.config/big.bin" not in shared.rsync_paths


def test_apply_size_resolution_commit_anyway_is_noop() -> None:
    from lintwin.cli.sync import apply_size_resolution
    from lintwin.core.config import SharedConfig
    from lintwin.core.sizeguard import FlaggedItem
    shared = SharedConfig(git_paths=[], rsync_paths=[], never_sync=[])
    apply_size_resolution(shared, FlaggedItem("~/.config/big.bin", 99, False), "g")
    assert shared.git_excludes == []
    assert shared.never_sync == []
    assert shared.rsync_paths == []


def test_apply_size_resolution_is_idempotent() -> None:
    from lintwin.cli.sync import apply_size_resolution
    from lintwin.core.config import SharedConfig
    from lintwin.core.sizeguard import FlaggedItem
    shared = SharedConfig(git_paths=[], rsync_paths=[], never_sync=[])
    item = FlaggedItem("~/.config/big.bin", 99, False)
    apply_size_resolution(shared, item, "r")
    apply_size_resolution(shared, item, "r")
    assert shared.git_excludes == ["~/.config/big.bin"]
    assert shared.rsync_paths == ["~/.config/big.bin"]


_REMOTE = RemoteConfig(host="10.0.0.1", ssh_user="karlo")
_CONFLICT = Conflict(path="~/doc.txt", local_modified="2026-05-28T09:00:00", remote_modified="2026-05-28T10:00:00", is_binary=False)


def test_resolve_conflict_keep_local_returns_keep_local() -> None:
    from lintwin.cli.sync import _resolve_conflict
    with patch("lintwin.cli.sync.click.prompt", return_value="1"):
        result = _resolve_conflict(_CONFLICT, _REMOTE, "desktop")
    assert result == Resolution.KEEP_LOCAL


def test_resolve_conflict_keep_remote_returns_keep_remote() -> None:
    from lintwin.cli.sync import _resolve_conflict
    with patch("lintwin.cli.sync.click.prompt", return_value="2"):
        result = _resolve_conflict(_CONFLICT, _REMOTE, "desktop")
    assert result == Resolution.KEEP_REMOTE


def test_resolve_conflict_skip_returns_skip() -> None:
    from lintwin.cli.sync import _resolve_conflict
    with patch("lintwin.cli.sync.click.prompt", return_value="3"):
        result = _resolve_conflict(_CONFLICT, _REMOTE, "desktop")
    assert result == Resolution.SKIP


def test_resolve_conflict_show_diff_then_keep_local() -> None:
    from lintwin.cli.sync import _resolve_conflict
    with patch("lintwin.cli.sync.click.prompt", side_effect=["4", "1"]):
        with patch("subprocess.run"):
            result = _resolve_conflict(_CONFLICT, _REMOTE, "desktop")
    assert result == Resolution.KEEP_LOCAL


def test_freshness_check_silent_when_remote_snap_is_none() -> None:
    from lintwin.cli.sync import _check_remote_freshness
    local = Snapshot(machine="laptop", remotes={"desktop": RemoteSnapshot(timestamp="2026-05-28T09:00:00", files={})})
    assert _check_remote_freshness(local, None, "desktop", "laptop") is True


def test_freshness_check_silent_when_no_local_entry() -> None:
    from lintwin.cli.sync import _check_remote_freshness
    local = Snapshot(machine="laptop", remotes={})
    remote = Snapshot(machine="desktop", remotes={"laptop": RemoteSnapshot(timestamp="2026-05-28T10:00:00", files={})})
    assert _check_remote_freshness(local, remote, "desktop", "laptop") is True


def test_freshness_check_silent_when_no_remote_entry() -> None:
    from lintwin.cli.sync import _check_remote_freshness
    local = Snapshot(machine="laptop", remotes={"desktop": RemoteSnapshot(timestamp="2026-05-28T09:00:00", files={})})
    remote = Snapshot(machine="desktop", remotes={})
    assert _check_remote_freshness(local, remote, "desktop", "laptop") is True


def test_freshness_check_warns_when_remote_newer() -> None:
    from lintwin.cli.sync import _check_remote_freshness
    local = Snapshot(machine="laptop", remotes={"desktop": RemoteSnapshot(timestamp="2026-05-28T09:00:00", files={})})
    remote = Snapshot(machine="desktop", remotes={"laptop": RemoteSnapshot(timestamp="2026-05-28T14:00:00", files={})})
    with patch("click.confirm", return_value=True):
        with patch("lintwin.cli.sync.console.print"):
            result = _check_remote_freshness(local, remote, "desktop", "laptop")
    assert result is True


def test_freshness_check_silent_when_local_newer() -> None:
    from lintwin.cli.sync import _check_remote_freshness
    local = Snapshot(machine="laptop", remotes={"desktop": RemoteSnapshot(timestamp="2026-05-28T14:00:00", files={})})
    remote = Snapshot(machine="desktop", remotes={"laptop": RemoteSnapshot(timestamp="2026-05-28T09:00:00", files={})})
    with patch("click.confirm") as mock_confirm:
        result = _check_remote_freshness(local, remote, "desktop", "laptop")
    assert result is True
    mock_confirm.assert_not_called()


from contextlib import ExitStack

_SNAP = Snapshot(machine="laptop", remotes={"desktop": RemoteSnapshot(timestamp="2026-05-28T08:00:00", files={})})
_SYNC_CONFLICT = Conflict(path="~/doc.txt", local_modified="2026-05-28T09:00:00", remote_modified="2026-05-28T10:00:00", is_binary=False)


def _setup_do_rsync(stack, resolution, conflicts=None):
    if conflicts is None:
        conflicts = [_SYNC_CONFLICT]
    stack.enter_context(patch("lintwin.cli.sync.load_snapshot", return_value=_SNAP))
    stack.enter_context(patch("lintwin.cli.sync.fetch_remote_snapshot", return_value=_SNAP))
    stack.enter_context(patch("lintwin.cli.sync._check_remote_freshness", return_value=True))
    stack.enter_context(patch("lintwin.cli.sync.detect_conflicts", return_value=conflicts))
    if resolution is not None:
        stack.enter_context(patch("lintwin.cli.sync._resolve_conflict", return_value=resolution))
    stack.enter_context(patch("lintwin.cli.sync.update_snapshot"))
    mock_bef = stack.enter_context(patch("lintwin.cli.sync.build_excludes_file", return_value="/tmp/ex"))
    return mock_bef


def test_do_rsync_sync_keep_remote_excluded_from_push_and_rsync_file_called() -> None:
    from lintwin.cli.sync import _do_rsync_sync
    with ExitStack() as stack:
        mock_bef = _setup_do_rsync(stack, Resolution.KEEP_REMOTE)
        stack.enter_context(patch("lintwin.cli.sync.rsync_path", return_value=MagicMock(returncode=0, stderr="")))
        mock_rf = stack.enter_context(patch("lintwin.cli.sync.rsync_file", return_value=MagicMock(returncode=0, stderr="")))
        _do_rsync_sync(MOCK_SHARED, MOCK_LOCAL, "desktop", _REMOTE, set())
    assert "~/doc.txt" in mock_bef.call_args[0][0]
    mock_rf.assert_called_once()
    assert mock_rf.call_args.kwargs.get("direction") == "pull"


def test_do_rsync_sync_skip_excluded_from_push_no_rsync_file() -> None:
    from lintwin.cli.sync import _do_rsync_sync
    with ExitStack() as stack:
        mock_bef = _setup_do_rsync(stack, Resolution.SKIP)
        stack.enter_context(patch("lintwin.cli.sync.rsync_path", return_value=MagicMock(returncode=0, stderr="")))
        mock_rf = stack.enter_context(patch("lintwin.cli.sync.rsync_file"))
        _do_rsync_sync(MOCK_SHARED, MOCK_LOCAL, "desktop", _REMOTE, set())
    assert "~/doc.txt" in mock_bef.call_args[0][0]
    mock_rf.assert_not_called()


def test_do_rsync_sync_keep_local_included_in_push_no_rsync_file() -> None:
    from lintwin.cli.sync import _do_rsync_sync
    with ExitStack() as stack:
        mock_bef = _setup_do_rsync(stack, Resolution.KEEP_LOCAL)
        stack.enter_context(patch("lintwin.cli.sync.rsync_path", return_value=MagicMock(returncode=0, stderr="")))
        mock_rf = stack.enter_context(patch("lintwin.cli.sync.rsync_file"))
        _do_rsync_sync(MOCK_SHARED, MOCK_LOCAL, "desktop", _REMOTE, set())
    assert "~/doc.txt" not in mock_bef.call_args[0][0]
    mock_rf.assert_not_called()


def test_do_rsync_sync_no_conflicts_standard_push() -> None:
    from lintwin.cli.sync import _do_rsync_sync
    with ExitStack() as stack:
        _setup_do_rsync(stack, resolution=None, conflicts=[])
        mock_rp = stack.enter_context(patch("lintwin.cli.sync.rsync_path", return_value=MagicMock(returncode=0, stderr="")))
        mock_rf = stack.enter_context(patch("lintwin.cli.sync.rsync_file"))
        _do_rsync_sync(MOCK_SHARED, MOCK_LOCAL, "desktop", _REMOTE, set())
    mock_rp.assert_called_once()
    assert mock_rp.call_args.kwargs.get("direction", "push") == "push"
    mock_rf.assert_not_called()
