import subprocess
import click
from rich.console import Console
from lintwin.core.config import load_local_config, load_shared_config
from lintwin.core.rsync import check_connectivity, build_excludes_file
from lintwin.core import git as git_core
from lintwin.core.constants import BARE_REPO
from lintwin.cli.sync import _select_remote
from pathlib import Path

console = Console()


@click.command("diff")
@click.option("--to", "remote_name", default=None, help="Target remote (required when 2+ remotes configured)")
def diff_cmd(remote_name: str | None) -> None:
    """Show file-level differences between this machine and a remote."""
    local = load_local_config()
    shared = load_shared_config()
    remote_name_resolved, remote = _select_remote(local, remote_name)

    console.print("[bold]Git uncommitted changes:[/bold]")
    changes = git_core.status_short(shared.git_paths, BARE_REPO)
    if changes:
        for code, path in changes:
            console.print(f"  [{code}] {path}")
    else:
        console.print("  (none)")

    if not check_connectivity(remote):
        console.print(f"\n[yellow]Cannot reach '{remote_name_resolved}' — rsync diff unavailable.[/yellow]")
        return

    console.print(f"\n[bold]Rsync diff vs {remote_name_resolved}:[/bold]")
    for path in shared.rsync_paths:
        excludes = build_excludes_file(shared.never_sync, path)
        expanded = str(Path(path).expanduser())
        remote_path = f"{remote.ssh_user}@{remote.host}:{expanded}/"
        result = subprocess.run(
            ["rsync", "-avz", "--dry-run", "--delete",
             f"--exclude-from={excludes}", f"{expanded}/", remote_path],
            capture_output=True, text=True,
        )
        lines = [l for l in result.stdout.splitlines() if l.strip() and not l.startswith("sending")]
        if lines:
            console.print(f"  [bold]{path}:[/bold]")
            for line in lines:
                console.print(f"    {line}")
