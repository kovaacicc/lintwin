import click
from rich.console import Console
from lintwin.core.config import load_local_config, load_shared_config
from lintwin.core.rsync import check_connectivity, fetch_remote_snapshot, detect_conflicts, build_excludes_file, rsync_path
from lintwin.core.snapshot import load_snapshot
from lintwin.core import git as git_core
from lintwin.core.constants import BARE_REPO, SNAPSHOT_FILE
from lintwin.cli.sync import _select_remote

console = Console()


@click.command("pull")
@click.option("--to", "remote_name", default=None, help="Target remote")
def pull_cmd(remote_name: str | None) -> None:
    """Pull changes from remote without pushing."""
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

    console.print("[bold]Git pull...[/bold]")
    git_core.fetch(BARE_REPO)
    _, behind = git_core.divergence_info("main", BARE_REPO)
    if behind > 0:
        git_core.pull_fast_forward("main", BARE_REPO)
        console.print(f"  Pulled {behind} commit(s).")
    else:
        console.print("  Already up to date.")

    if not check_connectivity(remote):
        console.print(f"[yellow]Cannot reach '{remote_name_resolved}' — skipping rsync pull.[/yellow]")
        return

    local_snap = load_snapshot(SNAPSHOT_FILE)
    remote_snap = fetch_remote_snapshot(remote)
    if local_snap and remote_snap:
        conflicts = detect_conflicts(local_snap, remote_snap, remote_name_resolved, shared.rsync_paths)
        if conflicts:
            console.print(f"\n[yellow]⚠ {len(conflicts)} conflict(s) detected — run `lintwin sync` to resolve.[/yellow]")
            for c in conflicts:
                console.print(f"  {c.path}")
            return

    for path in shared.rsync_paths:
        excludes = build_excludes_file(shared.never_sync, path)
        rsync_path(path, remote, direction="pull", excludes_file=excludes)
    console.print("[green]Pull complete.[/green]")
