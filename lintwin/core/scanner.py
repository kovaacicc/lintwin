import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DirtyRepo:
    path: Path
    uncommitted: int
    unpushed: int


def find_git_repos(paths: list[str]) -> list[Path]:
    repos: list[Path] = []
    for path_str in paths:
        root = Path(path_str).expanduser()
        if not root.exists():
            continue
        for git_dir in root.rglob(".git"):
            if git_dir.is_dir():
                repos.append(git_dir.parent)
    return repos


def check_dirty(repo: Path) -> DirtyRepo | None:
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    uncommitted = len([l for l in status.stdout.splitlines() if l.strip()])

    cherry = subprocess.run(
        ["git", "-C", str(repo), "cherry", "-v"],
        capture_output=True, text=True,
    )
    unpushed = len([l for l in cherry.stdout.splitlines() if l.strip()])

    if uncommitted > 0 or unpushed > 0:
        return DirtyRepo(path=repo, uncommitted=uncommitted, unpushed=unpushed)
    return None


def scan_for_dirty_repos(paths: list[str]) -> list[DirtyRepo]:
    return [r for repo in find_git_repos(paths) if (r := check_dirty(repo)) is not None]
