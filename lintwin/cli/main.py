import click
from rich.console import Console
from lintwin.cli.track import track_cmd, untrack_cmd
from lintwin.cli.init import init_cmd
from lintwin.cli.sync import sync_cmd
from lintwin.cli.status import status_cmd
from lintwin.cli.pull import pull_cmd
from lintwin.cli.diff import diff_cmd

console = Console()


@click.group()
@click.version_option()
def cli() -> None:
    """lintwin — keep your Linux machines in sync."""


cli.add_command(track_cmd)
cli.add_command(untrack_cmd)
cli.add_command(init_cmd)
cli.add_command(sync_cmd)
cli.add_command(status_cmd)
cli.add_command(pull_cmd)
cli.add_command(diff_cmd)
