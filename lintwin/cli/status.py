import click
from rich.console import Console
from lintwin.core.config import load_local_config, load_shared_config
from lintwin.core.scanner import scan_for_dirty_repos
from lintwin.core.rsync import check_connectivity
from lintwin.core import git as git_core
from lintwin.core.constants import BARE_REPO

git_status_short = git_core.status_short
console = Console()


@click.command("status")
def status_cmd() -> None:
    """Show what has changed since the last sync."""
    try:
        local = load_local_config()
    except FileNotFoundError:
        console.print("[red]Not initialized.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    if not git_core.is_initialized():
        console.print("[red]Bare repo not found.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    shared = load_shared_config()
    all_paths = shared.git_paths + shared.rsync_paths

    console.print(f"[bold]Machine:[/bold] {local.machine_name}")

    console.print("\n[bold]Git changes:[/bold]")
    changes = git_status_short(shared.git_paths)
    if changes:
        for code, path in changes:
            console.print(f"  [{code}] {path}")
    else:
        console.print("  (none)")

    dirty = scan_for_dirty_repos(all_paths)
    if dirty:
        console.print("\n[yellow]Dirty repos:[/yellow]")
        for d in dirty:
            console.print(f"  {d.path}  — {d.uncommitted} uncommitted, {d.unpushed} unpushed")

    console.print("\n[bold]Remotes:[/bold]")
    for name, remote in local.remotes.items():
        reachable = check_connectivity(remote)
        status = "[green]reachable[/green]" if reachable else "[red]unreachable[/red]"
        console.print(f"  {name}: {status}")
