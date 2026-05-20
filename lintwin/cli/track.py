import click
from rich.console import Console
from lintwin.core.config import track_path, untrack_path
from lintwin.core.constants import SHARED_CONFIG_PATH

console = Console()
err_console = Console(stderr=True)


@click.command("track")
@click.argument("path")
@click.option("--via", type=click.Choice(["git", "rsync"]), required=True,
              help="Sync method: git (text/configs) or rsync (large files)")
def track_cmd(path: str, via: str) -> None:
    """Add PATH to the sync list."""
    track_path(path, via, SHARED_CONFIG_PATH)
    console.print(f"[green]Tracking[/green] {path} via {via}")


@click.command("untrack")
@click.argument("path")
def untrack_cmd(path: str) -> None:
    """Remove PATH from the sync list."""
    removed = untrack_path(path, SHARED_CONFIG_PATH)
    if not removed:
        err_console.print(f"[red]Error:[/red] {path} is not tracked")
        raise SystemExit(1)
    console.print(f"[green]Removed[/green] {path} from sync list")
