import subprocess
from pathlib import Path
from .constants import BARE_REPO


def _git(*args: str, bare_repo: Path = BARE_REPO, work_tree: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    if work_tree is None:
        work_tree = Path.home()
    return subprocess.run(
        ["git", f"--git-dir={bare_repo}", f"--work-tree={work_tree}", *args],
        capture_output=True, text=True, check=check,
    )


def init_bare_repo(bare_repo: Path = BARE_REPO) -> None:
    bare_repo.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare_repo)], check=True, capture_output=True)
    # suppress untracked files in status — essential for home-dir work-tree
    subprocess.run(
        ["git", f"--git-dir={bare_repo}", "config", "status.showUntrackedFiles", "no"],
        check=True, capture_output=True,
    )


def set_remote(url: str, bare_repo: Path = BARE_REPO) -> None:
    result = subprocess.run(
        ["git", f"--git-dir={bare_repo}", "remote", "get-url", "origin"],
        capture_output=True,
    )
    if result.returncode == 0:
        subprocess.run(
            ["git", f"--git-dir={bare_repo}", "remote", "set-url", "origin", url],
            check=True, capture_output=True,
        )
    else:
        subprocess.run(
            ["git", f"--git-dir={bare_repo}", "remote", "add", "origin", url],
            check=True, capture_output=True,
        )


def fetch(bare_repo: Path = BARE_REPO) -> None:
    _git("fetch", "origin", bare_repo=bare_repo)


def local_head(bare_repo: Path = BARE_REPO) -> str:
    return _git("rev-parse", "HEAD", bare_repo=bare_repo).stdout.strip()


def remote_head(branch: str = "main", bare_repo: Path = BARE_REPO) -> str:
    return _git("rev-parse", f"origin/{branch}", bare_repo=bare_repo).stdout.strip()


def is_initialized(bare_repo: Path = BARE_REPO) -> bool:
    return bare_repo.is_dir() and (bare_repo / "HEAD").exists()


def divergence_info(branch: str = "main", bare_repo: Path = BARE_REPO) -> tuple[int, int]:
    result = _git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}", bare_repo=bare_repo, check=False)
    if result.returncode != 0:
        # origin/main doesn't exist yet (before first push) — count local commits as ahead
        head = _git("rev-list", "--count", "HEAD", bare_repo=bare_repo, check=False)
        if head.returncode == 0:
            return int(head.stdout.strip()), 0
        return 0, 0
    parts = result.stdout.strip().split()
    return int(parts[0]), int(parts[1])


def list_tracked_files(bare_repo: Path = BARE_REPO, work_tree: Path | None = None) -> set[str]:
    if work_tree is None:
        work_tree = Path.home()
    result = _git("ls-files", "--full-name", bare_repo=bare_repo, work_tree=work_tree, check=False)
    if result.returncode != 0:
        return set()
    return {str(work_tree / line) for line in result.stdout.splitlines() if line}


def stage_paths(
    paths: list[str],
    bare_repo: Path = BARE_REPO,
    work_tree: Path | None = None,
    excludes: list[str] | None = None,
) -> None:
    existing = [str(Path(p).expanduser()) for p in paths if Path(p).expanduser().exists()]
    if not existing:
        return
    wt = work_tree if work_tree is not None else Path.home()
    pathspecs = list(existing)
    for entry in excludes or []:
        resolved = Path(entry).expanduser()
        try:
            rel = resolved.relative_to(wt)
        except ValueError:
            continue  # not under the work tree (e.g. a bare glob) — git can't exclude it here
        pathspecs.append(f":(exclude){rel}")
    _git("add", "--", *pathspecs, bare_repo=bare_repo, work_tree=work_tree)


def commit(message: str, bare_repo: Path = BARE_REPO, work_tree: Path | None = None) -> bool:
    result = _git("diff", "--cached", "--quiet", bare_repo=bare_repo, work_tree=work_tree, check=False)
    if result.returncode == 0:
        return False
    _git("commit", "-m", message, bare_repo=bare_repo, work_tree=work_tree)
    return True


def push(branch: str = "main", bare_repo: Path = BARE_REPO) -> None:
    _git("push", "origin", branch, bare_repo=bare_repo)


def pull_fast_forward(branch: str = "main", bare_repo: Path = BARE_REPO) -> None:
    _git("pull", "--ff-only", "origin", branch, bare_repo=bare_repo)


def rebase(branch: str = "main", bare_repo: Path = BARE_REPO) -> None:
    _git("rebase", f"origin/{branch}", bare_repo=bare_repo)


def log_oneline(ref: str, n: int = 10, bare_repo: Path = BARE_REPO) -> list[str]:
    result = _git("log", "--oneline", f"-{n}", ref, bare_repo=bare_repo)
    return result.stdout.strip().splitlines()


def status_short(paths: list[str], bare_repo: Path = BARE_REPO, work_tree: Path | None = None) -> list[tuple[str, str]]:
    specs = [str(Path(p).expanduser()) for p in paths]
    result = _git("status", "--porcelain", "--", *specs, bare_repo=bare_repo, work_tree=work_tree)
    lines = []
    for line in result.stdout.splitlines():
        if len(line) > 3:
            code = line[:2].strip()
            path = line[3:]
            lines.append((code, path))
    return lines
