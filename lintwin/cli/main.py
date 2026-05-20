import click
from rich.console import Console
from lintwin.cli.track import track_cmd, untrack_cmd

console = Console()


@click.group()
@click.version_option()
def cli() -> None:
    """lintwin — keep your Linux machines in sync."""


cli.add_command(track_cmd)
cli.add_command(untrack_cmd)
