import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option()
def cli() -> None:
    """lintwin — keep your Linux machines in sync."""
