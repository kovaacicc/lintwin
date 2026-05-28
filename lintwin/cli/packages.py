import json
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from lintwin.core.config import load_local_config
from lintwin.core.packages.arch import get_available_managers
from lintwin.core.constants import PACKAGES_DIR

console = Console()


@click.group("packages")
def packages_cmd() -> None:
    """Manage and compare installed packages across machines."""


@packages_cmd.command("export")
def export_cmd() -> None:
    """Snapshot currently installed packages to files."""
    local = load_local_config()
    machine_dir = PACKAGES_DIR / local.machine_name
    machine_dir.mkdir(parents=True, exist_ok=True)
    for mgr in get_available_managers():
        data = mgr.export()
        out = machine_dir / f"{mgr.name()}.json"
        out.write_text(json.dumps(data, indent=2))
        console.print(f"[green]Exported[/green] {mgr.name()} → {out}")
    console.print("[dim]Run `lintwin sync` to share your package list with other machines.[/dim]")


@packages_cmd.command("diff")
@click.option("--to", "remote_name", required=True, help="Remote machine name")
def diff_cmd(remote_name: str) -> None:
    """Compare installed packages with a remote machine (reads from local git copy)."""
    local = load_local_config()
    if remote_name not in local.remotes:
        console.print(f"[red]Unknown remote:[/red] {remote_name}")
        raise SystemExit(1)

    for mgr in get_available_managers():
        remote_file = PACKAGES_DIR / remote_name / f"{mgr.name()}.json"
        if not remote_file.exists():
            console.print(
                f"[yellow]No package data for {remote_name}[/yellow] — "
                f"run `lintwin packages export` on {remote_name} then sync."
            )
            continue
        other = json.loads(remote_file.read_text())
        diff = mgr.diff(other)
        if diff["missing"] or diff["extra"]:
            table = Table(title=f"{mgr.name()} diff vs {remote_name}")
            table.add_column("Status")
            table.add_column("Package")
            for pkg in diff["missing"]:
                table.add_row("[red]missing[/red]", pkg)
            for pkg in diff["extra"]:
                table.add_row("[yellow]extra[/yellow]", pkg)
            console.print(table)
        else:
            console.print(f"[green]{mgr.name()}:[/green] in sync with {remote_name}")


@packages_cmd.command("install")
@click.option("--from", "from_machine", default=None, metavar="MACHINE",
              help="Install packages from this machine's export (defaults to local machine).")
def install_cmd(from_machine: str | None) -> None:
    """Install packages listed in exported files that are missing locally."""
    local = load_local_config()
    source = from_machine or local.machine_name
    source_dir = PACKAGES_DIR / source
    if not source_dir.exists():
        console.print(
            f"[red]No exported package files for {source}.[/red] "
            "Run `lintwin packages export` first."
        )
        raise SystemExit(1)

    managers_by_name = {mgr.name(): mgr for mgr in get_available_managers()}

    for pkg_file in source_dir.glob("*.json"):
        mgr_name = pkg_file.stem
        if mgr_name not in managers_by_name:
            console.print(f"[dim]Skipping {mgr_name} (not available on this machine)[/dim]")
            continue
        mgr = managers_by_name[mgr_name]
        other = json.loads(pkg_file.read_text())
        diff = mgr.diff(other)
        if diff["missing"]:
            console.print(f"Installing {len(diff['missing'])} missing {mgr_name} package(s)...")
            mgr.install(diff["missing"])
        else:
            console.print(f"[green]{mgr_name}:[/green] nothing to install")
