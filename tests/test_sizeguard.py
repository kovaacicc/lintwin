from pathlib import Path
import pytest
from lintwin.core.git import init_bare_repo, stage_paths, commit
from lintwin.core.sizeguard import scan_oversized


@pytest.fixture
def repo_home(tmp_path: Path):
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    init_bare_repo(repo)
    cfg = home / ".config"
    cfg.mkdir()
    (cfg / "settings.txt").write_text("tracked")
    stage_paths([str(cfg / "settings.txt")], bare_repo=repo, work_tree=home)
    commit("init", bare_repo=repo, work_tree=home)
    return repo, home


def _make(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\0" * size)


def test_flags_large_untracked_file(repo_home) -> None:
    repo, home = repo_home
    _make(home / ".config" / "big.bin", 2048)
    (home / ".config" / "tiny.txt").write_text("x")
    flagged = scan_oversized([str(home / ".config")], [], 1024, repo, home)
    paths = {f.path for f in flagged}
    assert "~/.config/big.bin" in paths
    assert "~/.config/tiny.txt" not in paths
    assert all(not f.is_dir for f in flagged)


def test_flags_fully_new_directory_as_single_item(repo_home) -> None:
    repo, home = repo_home
    _make(home / ".config" / "newbig" / "a.bin", 700)
    _make(home / ".config" / "newbig" / "b.bin", 700)
    flagged = scan_oversized([str(home / ".config")], [], 1024, repo, home)
    dirs = [f for f in flagged if f.is_dir]
    assert len(dirs) == 1
    assert dirs[0].path == "~/.config/newbig"
    assert dirs[0].size == 1400
    assert not any(f.path.startswith("~/.config/newbig/") for f in flagged)


def test_excluded_item_not_flagged(repo_home) -> None:
    repo, home = repo_home
    _make(home / ".config" / "big.bin", 2048)
    flagged = scan_oversized(
        [str(home / ".config")],
        [str(home / ".config" / "big.bin")],
        1024, repo, home,
    )
    assert flagged == []


def test_results_sorted_largest_first(repo_home) -> None:
    repo, home = repo_home
    _make(home / ".config" / "small.bin", 1500)
    _make(home / ".config" / "large.bin", 4000)
    _make(home / ".config" / "medium.bin", 2500)
    flagged = scan_oversized([str(home / ".config")], [], 1024, repo, home)
    sizes = [f.size for f in flagged]
    assert sizes == sorted(sizes, reverse=True)
    assert flagged[0].path == "~/.config/large.bin"


def test_directory_with_tracked_file_not_flagged_as_dir(repo_home) -> None:
    repo, home = repo_home
    mixed = home / ".config" / "mixed"
    mixed.mkdir()
    (mixed / "tracked.txt").write_text("kept")
    stage_paths([str(mixed / "tracked.txt")], bare_repo=repo, work_tree=home)
    commit("add mixed tracked", bare_repo=repo, work_tree=home)
    _make(mixed / "big.bin", 2048)
    flagged = scan_oversized([str(home / ".config")], [], 1024, repo, home)
    assert not any(f.is_dir and f.path == "~/.config/mixed" for f in flagged)
    assert any(f.path == "~/.config/mixed/big.bin" for f in flagged)
