import subprocess
from pathlib import Path
import click
from rich.console import Console
from rich.prompt import Prompt, Confirm
from lintwin.core.config import (
    LocalConfig, RemoteConfig, SharedConfig,
    save_local_config, save_shared_config, load_shared_config,
)
from lintwin.core.constants import (
    BARE_REPO, LOCAL_CONFIG_PATH, SHARED_CONFIG_PATH,
    DEFAULT_GIT_PATHS, DEFAULT_RSYNC_PATHS, NOISE_DOTFILES,
)
from lintwin.core import git as git_core

console = Console()

REQUIRED_TOOLS = ["git", "rsync", "gh"]


def check_prerequisites() -> list[str]:
    missing = []
    for tool in REQUIRED_TOOLS:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            missing.append(tool)
    return missing


def discover_dotfiles(home: Path) -> list[Path]:
    found = []
    for item in sorted(home.iterdir()):
        if item.name.startswith(".") and item.name not in NOISE_DOTFILES:
            found.append(item)
    return found


def discover_rsync_dirs(home: Path) -> list[Path]:
    defaults = {Path(p).expanduser().name for p in DEFAULT_RSYNC_PATHS}
    found = []
    for item in sorted(home.iterdir()):
        if item.is_dir() and not item.name.startswith(".") and item.name not in defaults:
            found.append(item)
    return found


def _interactive_checklist(title: str, items: list[Path], pre_checked: set[str]) -> list[str]:
    console.print(f"\n[bold]{title}[/bold]")
    selected = []
    for item in items:
        name = f"~/{item.relative_to(Path.home())}" if item.is_relative_to(Path.home()) else str(item)
        default = item.name in pre_checked
        if Confirm.ask(f"  Track {name}?", default=default):
            selected.append(name)
    return selected


def _create_github_repo(name: str) -> str:
    result = subprocess.run(
        ["gh", "repo", "create", name, "--private", "--confirm"],
        capture_output=True, text=True, check=True,
    )
    url = result.stdout.strip().splitlines()[-1]
    return url


@click.command("init")
@click.option("--join", "repo_url", default=None, metavar="REPO_URL",
              help="Join an existing lintwin setup from this git remote URL.")
@click.option("--name", "machine_name", default=None, metavar="NAME",
              help="Machine name (skips the interactive prompt).")
def init_cmd(repo_url: str | None, machine_name: str | None) -> None:
    """Set up lintwin on this machine."""
    missing = check_prerequisites()
    if missing:
        console.print(f"[red]Missing required tools:[/red] {', '.join(missing)}")
        console.print("Install them and run lintwin init again.")
        raise SystemExit(1)

    home = Path.home()

    if repo_url:
        _run_join(repo_url, home, machine_name)
    else:
        _run_init(home, machine_name)


def _run_init(home: Path, machine_name: str | None = None) -> None:
    if machine_name is None:
        machine_name = Prompt.ask("Name this machine", default="laptop")

    console.print("\n[bold]Git remote[/bold]")
    create_new = Confirm.ask("Create a new private GitHub repo?", default=True)
    if create_new:
        repo_name = Prompt.ask("Repo name", default="lintwin-dots")
        repo_url = _create_github_repo(repo_name)
        console.print(f"Created: {repo_url}")
    else:
        repo_url = Prompt.ask("SSH URL of existing repo")

    dotfiles = discover_dotfiles(home)
    default_names = {Path(p).expanduser().name for p in DEFAULT_GIT_PATHS}
    git_paths = _interactive_checklist("Git-tracked dotfiles", dotfiles, default_names)

    rsync_dirs = discover_rsync_dirs(home)
    extra_rsync = _interactive_checklist("Rsync directories", rsync_dirs, set())
    rsync_paths = list(DEFAULT_RSYNC_PATHS) + extra_rsync

    shared = SharedConfig(git_paths=git_paths, rsync_paths=rsync_paths)
    save_shared_config(shared, SHARED_CONFIG_PATH)

    local = LocalConfig(machine_name=machine_name, remotes={})
    save_local_config(local, LOCAL_CONFIG_PATH)

    git_core.init_bare_repo(BARE_REPO)
    git_core.set_remote(repo_url, BARE_REPO)
    git_core.stage_paths([str(SHARED_CONFIG_PATH)], BARE_REPO)
    git_core.commit(f"lintwin: init from {machine_name}", BARE_REPO)
    git_core.push("main", BARE_REPO)

    console.print("\n[green]Done![/green] On your other machine, run:")
    console.print(f"  lintwin init --join {repo_url}")


def _run_join(repo_url: str, home: Path, machine_name: str | None = None) -> None:
    if machine_name is None:
        machine_name = Prompt.ask("Name this machine", default="desktop")

    git_core.init_bare_repo(BARE_REPO)
    git_core.set_remote(repo_url, BARE_REPO)
    git_core.pull_fast_forward("main", BARE_REPO)

    shared = load_shared_config(SHARED_CONFIG_PATH)
    console.print(f"[green]Pulled config:[/green] {len(shared.git_paths)} git paths, {len(shared.rsync_paths)} rsync paths")

    remotes: dict[str, RemoteConfig] = {}
    while Confirm.ask("Add a remote machine?", default=True):
        name = Prompt.ask("Remote machine name")
        host = Prompt.ask("Host / IP")
        ssh_user = Prompt.ask("SSH user")
        ts_host = Prompt.ask("Tailscale hostname (leave blank to skip)", default="")
        remotes[name] = RemoteConfig(
            host=host,
            ssh_user=ssh_user,
            tailscale_hostname=ts_host if ts_host else None,
        )

    local = LocalConfig(machine_name=machine_name, remotes=remotes)
    save_local_config(local, LOCAL_CONFIG_PATH)
    console.print("[green]Done![/green] Run `lintwin sync` to sync.")
