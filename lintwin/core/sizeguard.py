import os
from dataclasses import dataclass
from pathlib import Path

from .git import list_tracked_files


@dataclass
class FlaggedItem:
    path: str        # ~/... display form
    size: int        # bytes
    is_dir: bool


def _tilde(path: Path, home: Path) -> str:
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


def _is_excluded(path: Path, excluded: set[str]) -> bool:
    s = str(path)
    return s in excluded or any(s.startswith(e + os.sep) for e in excluded)


def _dir_size(root: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).lstat().st_size
            except OSError:
                pass
    return total


def _dir_is_fully_new(directory: Path, tracked: set[str]) -> bool:
    prefix = str(directory) + os.sep
    return not any(t.startswith(prefix) for t in tracked)


def scan_oversized(
    git_paths: list[str],
    exclusions: list[str],
    threshold_bytes: int,
    bare_repo: Path,
    work_tree: Path,
) -> list[FlaggedItem]:
    """Oversized untracked files/dirs that this sync would newly commit to git."""
    tracked = list_tracked_files(bare_repo, work_tree)
    excluded = {str(Path(e).expanduser()) for e in exclusions}
    flagged: list[FlaggedItem] = []

    for raw in git_paths:
        root = Path(raw).expanduser()
        if not root.is_dir():
            continue  # file git_paths / missing paths: user-chosen, not scanned
        for dirpath, dirnames, filenames in os.walk(root):
            directory = Path(dirpath)
            if directory != root and _is_excluded(directory, excluded):
                dirnames[:] = []
                continue
            if directory != root and _dir_is_fully_new(directory, tracked):
                size = _dir_size(directory)
                if size >= threshold_bytes:
                    flagged.append(FlaggedItem(_tilde(directory, work_tree), size, True))
                dirnames[:] = []  # whole subtree resolved here
                continue
            for name in filenames:
                fp = directory / name
                if str(fp) in tracked or _is_excluded(fp, excluded):
                    continue
                try:
                    size = fp.lstat().st_size
                except OSError:
                    continue
                if size >= threshold_bytes:
                    flagged.append(FlaggedItem(_tilde(fp, work_tree), size, False))

    flagged.sort(key=lambda item: item.size, reverse=True)
    return flagged
