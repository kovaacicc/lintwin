import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from lintwin.core.config import (
    LocalConfig, RemoteConfig, SharedConfig,
    load_local_config, load_shared_config, save_shared_config,
)
from lintwin.core.scanner import scan_for_dirty_repos, DirtyRepo
from lintwin.core.rsync import check_connectivity, fetch_remote_snapshot, detect_conflicts, build_excludes_file, rsync_path, rsync_file, Resolution, Conflict
from lintwin.core.snapshot import load_snapshot, now_iso, update_snapshot, Snapshot
from lintwin.core import git as git_core
from lintwin.core.constants import BARE_REPO, SNAPSHOT_FILE
from lintwin.core.sizeguard import scan_oversized, FlaggedItem
from lintwin.cli.format import fmt_size

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


def apply_size_resolution(shared: SharedConfig, item: FlaggedItem, choice: str) -> None:
    """Mutate shared config for one guard resolution. 'g' and any unrecognized choice are no-ops."""
    if choice == "r":
        if item.path not in shared.git_excludes:
            shared.git_excludes.append(item.path)
        if item.path not in shared.rsync_paths:
            shared.rsync_paths.append(item.path)
    elif choice == "n":
        if item.path not in shared.never_sync:
            shared.never_sync.append(item.path)


def _run_size_guard(shared: SharedConfig, dry_run: bool) -> bool:
    """Scan git paths for oversized new items. Returns False if the user aborts."""
    threshold = shared.max_git_file_mb * 1024 * 1024
    flagged = scan_oversized(
        shared.git_paths,
        shared.never_sync + shared.git_excludes,
        threshold,
        BARE_REPO,
        Path.home(),
    )
    if not flagged:
        return True
    console.print(
        f"\n[yellow]⚠ Large items would be committed to git "
        f"(limit {shared.max_git_file_mb} MB):[/yellow]"
    )
    if dry_run:
        for item in flagged:
            kind = "dir " if item.is_dir else "file"
            console.print(f"  [{kind}] {item.path}  {fmt_size(item.size)}")
        console.print("[dim]--dry-run: no prompts, no changes.[/dim]")
        return True
    changed = False
    for item in flagged:
        console.print(f"\n  [cyan]{item.path}[/cyan]  {fmt_size(item.size)}")
        choice = click.prompt(
            "  [r] offload to rsync  [n] never-sync  [g] commit to git anyway  [a] abort sync",
            default="r",
        ).strip().lower()
        if choice == "a":
            console.print("Aborted.")
            return False  # abort discards any partial resolutions — nothing is persisted
        if choice in ("r", "n"):
            apply_size_resolution(shared, item, choice)
            changed = True
    if changed:
        save_shared_config(shared)
    return True


@click.command("sync")
@click.option("--to", "remote_name", default=None, help="Target remote (required when 2+ remotes configured)")
@click.option("--dry-run", is_flag=True, help="Preview only, no changes applied")
def sync_cmd(remote_name: str | None, dry_run: bool) -> None:
    """Sync this machine with a remote (git + rsync)."""
    try:
        local = load_local_config()
    except FileNotFoundError:
        console.print("[red]Not initialized.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    if not git_core.is_initialized():
        console.print("[red]Bare repo not found.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    shared = load_shared_config()
    remote_name_resolved, remote = _select_remote(local, remote_name)
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

    if not _run_size_guard(shared, dry_run):
        return

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
        git_core.stage_paths(
            shared.git_paths, BARE_REPO,
            excludes=shared.never_sync + shared.git_excludes,
        )
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
    console.print("[dim]ℹ  sync pushes from this machine — run from the machine with the newer content.[/dim]")
    local_snap = load_snapshot(SNAPSHOT_FILE)
    remote_snap = fetch_remote_snapshot(remote)

    if local_snap and not _check_remote_freshness(local_snap, remote_snap, remote_name, local.machine_name):
        return

    resolutions: dict[str, Resolution] = {}
    if local_snap and remote_snap:
        conflicts = detect_conflicts(local_snap, remote_snap, remote_name, shared.rsync_paths)
        for conflict in conflicts:
            resolutions[conflict.path] = _resolve_conflict(conflict, remote, remote_name)

    excluded_from_push = {p for p, r in resolutions.items() if r in (Resolution.KEEP_REMOTE, Resolution.SKIP)}
    keep_remote_paths = [p for p, r in resolutions.items() if r == Resolution.KEEP_REMOTE]

    for path in shared.rsync_paths:
        if any(path.startswith(skip) or str(path) == skip for skip in skip_paths):
            console.print(f"  [dim]Skipping {path} (dirty repo)[/dim]")
            continue
        excludes = build_excludes_file(shared.never_sync + list(excluded_from_push), path)
        result = rsync_path(path, remote, direction="push", excludes_file=excludes)
        if result.returncode == 0:
            console.print(f"  [green]✓[/green] {path}")
        else:
            console.print(f"  [red]✗[/red] {path}: {result.stderr[:80]}")

    for file_path in keep_remote_paths:
        result = rsync_file(file_path, remote, direction="pull")
        if result.returncode == 0:
            console.print(f"  [green]✓[/green] (kept remote) {file_path}")
        else:
            console.print(f"  [red]✗[/red] (keep remote failed) {file_path}: {result.stderr[:80]}")

    update_snapshot(local.machine_name, remote_name, shared.rsync_paths)


def _check_remote_freshness(
    local_snap: Snapshot,
    remote_snap: Snapshot | None,
    remote_name: str,
    machine_name: str,
) -> bool:
    if remote_snap is None:
        return True
    local_entry = local_snap.remotes.get(remote_name)
    if not local_entry:
        return True
    remote_entry = remote_snap.remotes.get(machine_name)
    if not remote_entry:
        return True
    if remote_entry.timestamp > local_entry.timestamp:
        console.print(f"\n[yellow]⚠  '{remote_name}' last synced at {remote_entry.timestamp[:19]} — after your last sync at {local_entry.timestamp[:19]}.[/yellow]")
        console.print("   It may have content newer than yours. Run [cyan]lintwin pull[/cyan] first if unsure.")
        if not click.confirm("   Proceed with sync anyway?", default=False):
            console.print("Aborted.")
            return False
    return True


def _resolve_conflict(conflict: Conflict, remote: RemoteConfig, remote_name: str) -> Resolution:
    console.print(f"\n[yellow]⚠ CONFLICT:[/yellow] {conflict.path}")
    console.print(f"  local:  modified {conflict.local_modified}")
    console.print(f"  {remote_name}: modified {conflict.remote_modified}")
    choices = "[1] Keep local  [2] Keep remote  [3] Skip"
    if not conflict.is_binary:
        choices += "  [4] Show diff"
    choice = click.prompt(f"  {choices}", default="3")
    if choice == "4" and not conflict.is_binary:
        import subprocess as _sp
        _sp.run(["diff", "--color", conflict.path, f"{remote.ssh_user}@{remote.host}:{conflict.path}"])
        choice = click.prompt("  [1] Keep local  [2] Keep remote  [3] Skip", default="3")
    return {"1": Resolution.KEEP_LOCAL, "2": Resolution.KEEP_REMOTE, "3": Resolution.SKIP}.get(choice, Resolution.SKIP)


