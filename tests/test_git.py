import subprocess
from pathlib import Path
import pytest
from lintwin.core.git import (
    init_bare_repo, _git, set_remote,
    divergence_info, stage_paths, commit,
    status_short, log_oneline,
)


@pytest.fixture
def bare_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    work = tmp_path / "work"
    work.mkdir()
    init_bare_repo(repo)
    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    set_remote(f"file://{origin}", bare_repo=repo)
    (work / "hello.txt").write_text("hello")
    subprocess.run(
        ["git", f"--git-dir={repo}", f"--work-tree={work}", "add", str(work / "hello.txt")],
        check=True
    )
    subprocess.run(
        ["git", f"--git-dir={repo}", f"--work-tree={work}", "-c", "user.email=test@test.com",
         "-c", "user.name=Test", "commit", "-m", "init"],
        check=True
    )
    subprocess.run(
        ["git", f"--git-dir={repo}", f"--work-tree={work}", "push", "-u", "origin", "main"],
        check=True
    )
    return repo, work


def test_init_bare_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    init_bare_repo(repo)
    assert (repo / "HEAD").exists()


def test_divergence_in_sync(bare_repo) -> None:
    repo, work = bare_repo
    ahead, behind = divergence_info(bare_repo=repo, branch="main")
    assert ahead == 0
    assert behind == 0


def test_commit_returns_false_nothing_to_commit(bare_repo) -> None:
    repo, work = bare_repo
    result = commit("test msg", bare_repo=repo, work_tree=work)
    assert result is False


def test_commit_returns_true_when_staged(bare_repo) -> None:
    repo, work = bare_repo
    (work / "newfile.txt").write_text("new")
    stage_paths([str(work / "newfile.txt")], bare_repo=repo, work_tree=work)
    result = commit("add newfile", bare_repo=repo, work_tree=work)
    assert result is True


def test_status_short_returns_modified(bare_repo) -> None:
    repo, work = bare_repo
    (work / "hello.txt").write_text("changed")
    changes = status_short([str(work / "hello.txt")], bare_repo=repo, work_tree=work)
    assert any("hello.txt" in path for _, path in changes)
