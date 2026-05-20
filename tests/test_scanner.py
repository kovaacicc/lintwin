import subprocess
from pathlib import Path
import pytest
from lintwin.core.scanner import find_git_repos, check_dirty, scan_for_dirty_repos, DirtyRepo


def _make_clean_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", str(path)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], capture_output=True, check=True)
    (path / "file.txt").write_text("hello")
    subprocess.run(["git", "-C", str(path), "add", "."], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], capture_output=True, check=True)


def _make_dirty_repo(path: Path) -> None:
    _make_clean_repo(path)
    (path / "new.txt").write_text("uncommitted")


def test_find_git_repos(tmp_path: Path) -> None:
    repo1 = tmp_path / "proj1"
    repo2 = tmp_path / "proj2"
    _make_clean_repo(repo1)
    _make_clean_repo(repo2)
    found = find_git_repos([str(tmp_path)])
    assert repo1 in found
    assert repo2 in found


def test_check_dirty_clean_repo(tmp_path: Path) -> None:
    repo = tmp_path / "clean"
    _make_clean_repo(repo)
    result = check_dirty(repo)
    assert result is None


def test_check_dirty_uncommitted(tmp_path: Path) -> None:
    repo = tmp_path / "dirty"
    _make_dirty_repo(repo)
    result = check_dirty(repo)
    assert result is not None
    assert isinstance(result, DirtyRepo)
    assert result.uncommitted > 0


def test_scan_mixed(tmp_path: Path) -> None:
    clean = tmp_path / "clean"
    dirty = tmp_path / "dirty"
    _make_clean_repo(clean)
    _make_dirty_repo(dirty)
    results = scan_for_dirty_repos([str(tmp_path)])
    paths = [r.path for r in results]
    assert dirty in paths
    assert clean not in paths
