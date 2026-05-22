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
    BARE_REPO, LOCAL_CONFIG_PATH, SHARED_CONFIG_PATH, DEFAULT_MAX_GIT_FILE_MB,
)
from lintwin.core import git as git_core
from lintwin.cli.selector import run_selector

console = Console()

REQUIRED_TOOLS = ["git", "rsync", "gh"]


def check_prerequisites() -> list[str]:
    missing = []
    for tool in REQUIRED_TOOLS:
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            missing.append(tool)
    return missing


def _create_github_repo(name: str) -> str:
    subprocess.run(
        ["gh", "repo", "create", name, "--private"],
        capture_output=True, text=True, check=True,
    )
    result = subprocess.run(
        ["gh", "repo", "view", name, "--json", "sshUrl", "-q", ".sshUrl"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@click.command("init")
@click.option("--join", "repo_url", default=None, metavar="REPO_URL",
              help="Join an existing lintwin setup from this git remote URL.")
@click.option("--name", "machine_name", default=None, metavar="NAME",
              help="Machine name (skips the interactive prompt).")
@click.option("--max-git-file-mb", "max_git_file_mb", type=int,
              default=DEFAULT_MAX_GIT_FILE_MB, metavar="N", show_default=True,
              help="Flag git files/dirs larger than this many MB before sync. Fresh init only.")
def init_cmd(repo_url: str | None, machine_name: str | None, max_git_file_mb: int) -> None:
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
        _run_init(home, machine_name, max_git_file_mb)


def _run_init(home: Path, machine_name: str | None = None,
              max_git_file_mb: int = DEFAULT_MAX_GIT_FILE_MB) -> None:
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

    git_paths, rsync_paths = run_selector(home)

    shared = SharedConfig(
        git_paths=git_paths, rsync_paths=rsync_paths,
        max_git_file_mb=max_git_file_mb,
    )
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
        port_str = Prompt.ask("SSH port (leave blank for default 22)", default="")
        remotes[name] = RemoteConfig(
            host=host,
            ssh_user=ssh_user,
            tailscale_hostname=ts_host if ts_host else None,
            ssh_port=int(port_str) if port_str else None,
        )

    local = LocalConfig(machine_name=machine_name, remotes=remotes)
    save_local_config(local, LOCAL_CONFIG_PATH)
    console.print("[green]Done![/green] Run `lintwin sync` to sync.")
