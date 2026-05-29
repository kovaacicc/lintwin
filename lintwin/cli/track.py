import fnmatch
import click
from pathlib import Path
from rich.console import Console
from lintwin.core.config import track_path, untrack_path, load_shared_config
from lintwin.core.constants import SHARED_CONFIG_PATH
from lintwin.core import git as git_core

console = Console()
err_console = Console(stderr=True)


def _matches_never_sync(path: str, patterns: list[str]) -> bool:
    abs_str = str(Path(path).expanduser().resolve())
    for pattern in patterns:
        exp_pattern = str(Path(pattern).expanduser())
        if fnmatch.fnmatch(abs_str, exp_pattern):
            return True
    return False


@click.command("track")
@click.argument("path")
@click.option("--via", type=click.Choice(["git", "rsync"]), required=True,
              help="Sync method: git (text/configs) or rsync (large files)")
def track_cmd(path: str, via: str) -> None:
    """Add PATH to the sync list."""
    if via == "git":
        expanded = Path(path).expanduser().resolve()
        if not str(expanded).startswith(str(Path.home().resolve())):
            err_console.print(f"[red]Error:[/red] Git-tracked paths must be inside $HOME. Use --via rsync for paths outside $HOME.")
            raise SystemExit(1)
    shared = load_shared_config(SHARED_CONFIG_PATH)
    if _matches_never_sync(path, shared.never_sync):
        err_console.print(
            f"[red]Error:[/red] {path} matches a never-sync pattern and cannot be tracked. "
            "Edit the [never_sync] section in shared.toml to override."
        )
        raise SystemExit(1)
    track_path(path, via, SHARED_CONFIG_PATH)
    console.print(f"[green]Tracking[/green] {path} via {via}")


@click.command("untrack")
@click.argument("path")
def untrack_cmd(path: str) -> None:
    """Remove PATH from the sync list."""
    via = untrack_path(path, SHARED_CONFIG_PATH)
    if not via:
        err_console.print(f"[red]Error:[/red] {path} is not tracked")
        raise SystemExit(1)
    console.print(f"[green]Removed[/green] {path} from sync list")
    if via == "git" and git_core.is_initialized():
        git_core.git_rm_cached(path)
        git_core.commit(f"lintwin: untrack {path}")
        if click.confirm("Push now?", default=False):
            git_core.push()
