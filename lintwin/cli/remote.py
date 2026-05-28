import click
from rich.console import Console
from rich.table import Table
from lintwin.core.config import (
    RemoteConfig, load_local_config, save_local_config,
)
from lintwin.core.constants import LOCAL_CONFIG_PATH

console = Console()


def _load_or_exit():
    try:
        return load_local_config(LOCAL_CONFIG_PATH)
    except FileNotFoundError:
        console.print("[red]Not initialized.[/red] Run `lintwin init` first.")
        raise SystemExit(1)


@click.group("remote")
def remote_cmd() -> None:
    """Manage remote machines."""


@remote_cmd.command("add")
@click.argument("name")
@click.option("--host", required=True, help="Host / IP address.")
@click.option("--ssh-user", required=True, help="SSH username.")
@click.option("--tailscale-hostname", default=None, help="Tailscale hostname.")
@click.option("--ssh-port", type=int, default=None, help="SSH port (default 22).")
def remote_add(name: str, host: str, ssh_user: str,
               tailscale_hostname: str | None, ssh_port: int | None) -> None:
    """Add a remote machine."""
    config = _load_or_exit()
    if name in config.remotes:
        console.print(
            f"[red]Remote '{name}' already exists.[/red] "
            f"Use `lintwin remote edit {name}` to update it."
        )
        raise SystemExit(1)
    config.remotes[name] = RemoteConfig(
        host=host, ssh_user=ssh_user,
        tailscale_hostname=tailscale_hostname, ssh_port=ssh_port,
    )
    save_local_config(config, LOCAL_CONFIG_PATH)
    console.print(f"[green]Added remote '{name}'.[/green]")


@remote_cmd.command("list")
def remote_list() -> None:
    """List all remote machines."""
    config = _load_or_exit()
    if not config.remotes:
        console.print("No remotes configured. Use `lintwin remote add` to add one.")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Host")
    table.add_column("User")
    table.add_column("Tailscale")
    table.add_column("Port")
    for rname, r in config.remotes.items():
        table.add_row(
            rname, r.host, r.ssh_user,
            r.tailscale_hostname or "",
            str(r.ssh_port) if r.ssh_port else "",
        )
    console.print(table)


@remote_cmd.command("remove")
@click.argument("name")
def remote_remove(name: str) -> None:
    """Remove a remote machine."""
    config = _load_or_exit()
    if name not in config.remotes:
        console.print(f"[red]Remote '{name}' not found.[/red]")
        raise SystemExit(1)
    del config.remotes[name]
    save_local_config(config, LOCAL_CONFIG_PATH)
    console.print(f"[green]Removed remote '{name}'.[/green]")


@remote_cmd.command("edit")
@click.argument("name")
@click.option("--host", default=None, help="New host / IP address.")
@click.option("--ssh-user", default=None, help="New SSH username.")
@click.option("--tailscale-hostname", default=None, help="New Tailscale hostname.")
@click.option("--no-tailscale", is_flag=True, default=False, help="Remove the Tailscale hostname.")
@click.option("--ssh-port", type=int, default=None, help="New SSH port.")
def remote_edit(name: str, host: str | None, ssh_user: str | None,
                tailscale_hostname: str | None, no_tailscale: bool,
                ssh_port: int | None) -> None:
    """Edit a remote machine's settings."""
    config = _load_or_exit()
    if name not in config.remotes:
        console.print(f"[red]Remote '{name}' not found.[/red]")
        raise SystemExit(1)
    r = config.remotes[name]
    if host is not None:
        r.host = host
    if ssh_user is not None:
        r.ssh_user = ssh_user
    if no_tailscale:
        r.tailscale_hostname = None
    elif tailscale_hostname is not None:
        r.tailscale_hostname = tailscale_hostname
    if ssh_port is not None:
        r.ssh_port = ssh_port
    save_local_config(config, LOCAL_CONFIG_PATH)
    console.print(f"[green]Updated remote '{name}'.[/green]")
