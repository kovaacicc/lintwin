import json
import subprocess
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
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
    for mgr in get_available_managers():
        data = mgr.export()
        out = PACKAGES_DIR / f"{mgr.name()}.json"
        out.write_text(json.dumps(data, indent=2))
        console.print(f"[green]Exported[/green] {mgr.name()} → {out}")


@packages_cmd.command("diff")
@click.option("--to", "remote_name", required=True, help="Remote machine name")
def diff_cmd(remote_name: str) -> None:
    """Compare installed packages with a remote machine."""
    local = load_local_config()
    if remote_name not in local.remotes:
        console.print(f"[red]Unknown remote:[/red] {remote_name}")
        raise SystemExit(1)
    remote = local.remotes[remote_name]

    for mgr in get_available_managers():
        remote_file = PACKAGES_DIR / f"{mgr.name()}.json"
        result = subprocess.run(
            ["ssh", f"{remote.ssh_user}@{remote.host}", f"cat {remote_file}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            console.print(f"[yellow]Cannot fetch {mgr.name()} packages from {remote_name}[/yellow]")
            continue
        other = json.loads(result.stdout)
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
def install_cmd() -> None:
    """Install packages listed in exported files that are missing locally."""
    if not PACKAGES_DIR.exists():
        console.print("[red]No exported package files found. Run `lintwin packages export` first.[/red]")
        raise SystemExit(1)

    managers_by_name = {mgr.name(): mgr for mgr in get_available_managers()}

    for pkg_file in PACKAGES_DIR.glob("*.json"):
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
