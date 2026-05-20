import click
from rich.console import Console
from rich.table import Table
from lintwin.core.config import LocalConfig, RemoteConfig, SharedConfig, load_local_config, load_shared_config
from lintwin.core.scanner import scan_for_dirty_repos, DirtyRepo
from lintwin.core.rsync import check_connectivity, fetch_remote_snapshot, detect_conflicts, build_excludes_file, rsync_path
from lintwin.core.snapshot import load_snapshot, save_snapshot, build_file_snapshot, now_iso, RemoteSnapshot
from lintwin.core import git as git_core
from lintwin.core.constants import BARE_REPO, SNAPSHOT_FILE

git_status_short = git_core.status_short

console = Console()


def _select_remote(local: LocalConfig, to: str | None) -> tuple[str, RemoteConfig]:
    if to:
        if to not in local.remotes:
            console.print(f"[red]Unknown remote:[/red] {to}. Known: {list(local.remotes)}")
            raise SystemExit(1)
        return to, local.remotes[to]
    if len(local.remotes) == 1:
        name, remote = next(iter(local.remotes.items()))
        return name, remote
    console.print(f"[red]Multiple remotes configured. Use --to:[/red] {list(local.remotes)}")
    raise SystemExit(1)


def _show_dirty_repos(dirty: list[DirtyRepo]) -> str:
    console.print("\n[yellow]⚠ Dirty repos found:[/yellow]")
    for d in dirty:
        console.print(f"  {d.path}  — {d.uncommitted} uncommitted, {d.unpushed} unpushed")
    console.print("\n  [s] Skip all   [c] Copy anyway   [r] Decide per repo")
    choice = click.prompt("Choice", default="s")
    return choice.strip().lower()


def _show_git_preview(changes: list[tuple[str, str]]) -> None:
    if not changes:
        console.print("  (no git changes)")
        return
    for code, path in changes:
        console.print(f"  [cyan]{code}[/cyan]  {path}")


@click.command("sync")
@click.option("--to", "remote_name", default=None, help="Target remote (required when 2+ remotes configured)")
@click.option("--dry-run", is_flag=True, help="Preview only, no changes applied")
def sync_cmd(remote_name: str | None, dry_run: bool) -> None:
    """Sync this machine with a remote (git + rsync)."""
    local = load_local_config()
    shared = load_shared_config()
    all_paths = shared.git_paths + shared.rsync_paths

    dirty = scan_for_dirty_repos(all_paths)
    skip_dirty_paths: set[str] = set()
    if dirty:
        choice = _show_dirty_repos(dirty)
        if choice == "s":
            skip_dirty_paths = {str(d.path) for d in dirty}
        elif choice == "r":
            for d in dirty:
                if not click.confirm(f"  Copy {d.path} anyway?", default=False):
                    skip_dirty_paths.add(str(d.path))

    console.print("\n[bold]Preview (git):[/bold]")
    git_changes = git_status_short(shared.git_paths)
    _show_git_preview(git_changes)

    remote_name_resolved, remote = _select_remote(local, remote_name)
    reachable = check_connectivity(remote)

    if dry_run:
        console.print(f"\n[dim]--dry-run: no changes applied. Remote '{remote_name_resolved}' {'reachable' if reachable else 'unreachable'}.[/dim]")
        return

    if not click.confirm("\nProceed?", default=False):
        console.print("Aborted.")
        return

    _do_git_sync(shared, local.machine_name, remote_name_resolved)

    if reachable:
        _do_rsync_sync(shared, local, remote_name_resolved, remote, skip_dirty_paths)
    else:
        console.print(f"\n[yellow]Cannot reach '{remote_name_resolved}' — skipping rsync.[/yellow]")

    console.print("\n[green]Sync complete.[/green]")


def _do_git_sync(shared: SharedConfig, machine_name: str, remote_name: str) -> None:
    console.print("\n[bold]Git sync...[/bold]")
    git_core.fetch(BARE_REPO)
    ahead, behind = git_core.divergence_info("main", BARE_REPO)

    if ahead == 0 and behind == 0:
        console.print("  Already up to date.")
    elif ahead > 0 and behind == 0:
        git_core.stage_paths(shared.git_paths, BARE_REPO)
        msg = f"lintwin: sync from {machine_name} @ {now_iso()}"
        git_core.commit(msg, BARE_REPO)
        git_core.push("main", BARE_REPO)
        console.print(f"  Pushed {ahead} commit(s).")
    elif behind > 0 and ahead == 0:
        git_core.pull_fast_forward("main", BARE_REPO)
        console.print(f"  Pulled {behind} commit(s).")
    else:
        console.print(f"  [yellow]Diverged:[/yellow] {ahead} ahead, {behind} behind.")
        local_log = git_core.log_oneline("HEAD", 5, BARE_REPO)
        remote_log = git_core.log_oneline("origin/main", 5, BARE_REPO)
        console.print("  Local:  " + " | ".join(local_log))
        console.print("  Remote: " + " | ".join(remote_log))
        choice = click.prompt("  [r]ebase / [m]erge / [a]bort", default="r")
        if choice == "r":
            git_core.rebase("main", BARE_REPO)
            git_core.push("main", BARE_REPO)
        elif choice == "m":
            git_core.pull_fast_forward("main", BARE_REPO)
        else:
            console.print("  Git sync aborted.")


def _do_rsync_sync(
    shared: SharedConfig,
    local: LocalConfig,
    remote_name: str,
    remote: RemoteConfig,
    skip_paths: set[str],
) -> None:
    console.print(f"\n[bold]Rsync sync → {remote_name}...[/bold]")
    local_snap = load_snapshot(SNAPSHOT_FILE)
    remote_snap = fetch_remote_snapshot(remote)

    if local_snap and remote_snap:
        conflicts = detect_conflicts(local_snap, remote_snap, remote_name, shared.rsync_paths)
        for conflict in conflicts:
            _resolve_conflict(conflict, remote, remote_name)

    excludes = build_excludes_file(shared.never_sync)
    for path in shared.rsync_paths:
        if any(path.startswith(skip) or str(path) == skip for skip in skip_paths):
            console.print(f"  [dim]Skipping {path} (dirty repo)[/dim]")
            continue
        result = rsync_path(path, remote, direction="push", excludes_file=excludes)
        if result.returncode == 0:
            console.print(f"  [green]✓[/green] {path}")
        else:
            console.print(f"  [red]✗[/red] {path}: {result.stderr[:80]}")

    _update_snapshot(local.machine_name, remote_name, shared.rsync_paths)


def _resolve_conflict(conflict, remote: RemoteConfig, remote_name: str) -> None:
    console.print(f"\n[yellow]⚠ CONFLICT:[/yellow] {conflict.path}")
    console.print(f"  local:  modified {conflict.local_modified}")
    console.print(f"  {remote_name}: modified {conflict.remote_modified}")
    choices = "[1] Keep local  [2] Keep remote  [3] Skip"
    if not conflict.is_binary:
        choices += "  [4] Show diff"
    choice = click.prompt(f"  {choices}", default="3")
    if choice == "4" and not conflict.is_binary:
        import subprocess
        subprocess.run(["diff", "--color", conflict.path,
                        f"{remote.ssh_user}@{remote.host}:{conflict.path}"])
        choice = click.prompt("  [1] Keep local  [2] Keep remote  [3] Skip", default="3")


def _update_snapshot(machine_name: str, remote_name: str, rsync_paths: list[str]) -> None:
    snap = load_snapshot(SNAPSHOT_FILE)
    if snap is None:
        from lintwin.core.snapshot import Snapshot
        snap = Snapshot(machine=machine_name)
    file_entries = build_file_snapshot(rsync_paths)
    snap.remotes[remote_name] = RemoteSnapshot(timestamp=now_iso(), files=file_entries)
    save_snapshot(snap, SNAPSHOT_FILE)
