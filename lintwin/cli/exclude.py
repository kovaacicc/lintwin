import click
from rich.console import Console

from lintwin.core.config import (
    add_machine_exclude,
    load_local_config,
    load_shared_config,
    remove_machine_exclude,
)
from lintwin.core.constants import LOCAL_CONFIG_PATH, SHARED_CONFIG_PATH

console = Console()
err_console = Console(stderr=True)


@click.group("exclude")
def exclude_cmd() -> None:
    """Manage per-machine sync excludes."""


@exclude_cmd.command("add")
@click.argument("path")
def add_cmd(path: str) -> None:
    """Exclude PATH from sync on this machine only."""
    try:
        local = load_local_config(LOCAL_CONFIG_PATH)
    except FileNotFoundError:
        err_console.print("[red]Not initialized.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    add_machine_exclude(local.machine_name, path, SHARED_CONFIG_PATH)
    console.print(f"[green]Excluded[/green] {path} on {local.machine_name}")


@exclude_cmd.command("remove")
@click.argument("path")
def remove_cmd(path: str) -> None:
    """Remove PATH from this machine's excludes."""
    try:
        local = load_local_config(LOCAL_CONFIG_PATH)
    except FileNotFoundError:
        err_console.print("[red]Not initialized.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    removed = remove_machine_exclude(local.machine_name, path, SHARED_CONFIG_PATH)
    if not removed:
        err_console.print(
            f"[red]Error:[/red] {path} is not in the exclude list for {local.machine_name}"
        )
        raise SystemExit(1)
    console.print(f"[green]Removed[/green] {path} from {local.machine_name}'s excludes")


@exclude_cmd.command("list")
def list_cmd() -> None:
    """List this machine's per-machine excludes."""
    try:
        local = load_local_config(LOCAL_CONFIG_PATH)
    except FileNotFoundError:
        err_console.print("[red]Not initialized.[/red] Run `lintwin init` first.")
        raise SystemExit(1)
    shared = load_shared_config(SHARED_CONFIG_PATH)
    excludes = shared.per_machine.get(local.machine_name, [])
    if not excludes:
        console.print(f"No per-machine excludes for {local.machine_name}.")
    else:
        for p in excludes:
            console.print(p)
