import subprocess
from pathlib import Path
import pytest
from lintwin.core.git import (
    init_bare_repo, _git, set_remote,
    divergence_info, stage_paths, commit,
    status_short, log_oneline, list_tracked_files,
    git_rm_cached,
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


def test_divergence_before_first_push(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    work = tmp_path / "work"
    work.mkdir()
    init_bare_repo(repo)
    origin = tmp_path / "origin"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    set_remote(f"file://{origin}", bare_repo=repo)
    (work / "hello.txt").write_text("hello")
    subprocess.run(["git", f"--git-dir={repo}", f"--work-tree={work}", "add", str(work / "hello.txt")], check=True)
    subprocess.run(
        ["git", f"--git-dir={repo}", f"--work-tree={work}", "-c", "user.email=test@test.com",
         "-c", "user.name=Test", "commit", "-m", "init"],
        check=True,
    )
    # origin/main does not exist yet — never pushed
    ahead, behind = divergence_info(bare_repo=repo, branch="main")
    assert ahead == 1
    assert behind == 0


def test_divergence_ahead(bare_repo) -> None:
    repo, work = bare_repo
    (work / "extra.txt").write_text("extra")
    stage_paths([str(work / "extra.txt")], bare_repo=repo, work_tree=work)
    commit("extra commit", bare_repo=repo, work_tree=work)
    ahead, behind = divergence_info(bare_repo=repo, branch="main")
    assert ahead == 1
    assert behind == 0


def test_divergence_behind(bare_repo, tmp_path: Path) -> None:
    repo, work = bare_repo
    # figure out origin URL from the bare repo's remote config
    result = subprocess.run(
        ["git", f"--git-dir={repo}", "remote", "get-url", "origin"],
        capture_output=True, text=True, check=True,
    )
    origin_url = result.stdout.strip()
    # push a new commit from a separate clone so origin/main advances
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", origin_url, str(clone)], check=True, capture_output=True)
    (clone / "extra.txt").write_text("extra")
    subprocess.run(["git", "-C", str(clone), "add", "extra.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(clone), "-c", "user.email=test@test.com", "-c", "user.name=Test",
         "commit", "-m", "remote extra"],
        check=True, capture_output=True,
    )
    subprocess.run(["git", "-C", str(clone), "push"], check=True, capture_output=True)
    # fetch so local tracking ref advances
    subprocess.run(["git", f"--git-dir={repo}", "fetch", "origin"], check=True, capture_output=True)
    ahead, behind = divergence_info(bare_repo=repo, branch="main")
    assert ahead == 0
    assert behind == 1


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


def test_list_tracked_files(bare_repo) -> None:
    repo, work = bare_repo
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(work / "hello.txt") in tracked


def test_stage_paths_honors_excludes(bare_repo) -> None:
    repo, work = bare_repo
    (work / "keep.txt").write_text("keep")
    (work / "skip.bin").write_text("skip")
    stage_paths(
        [str(work / "keep.txt"), str(work / "skip.bin")],
        bare_repo=repo, work_tree=work,
        excludes=[str(work / "skip.bin")],
    )
    commit("add keep", bare_repo=repo, work_tree=work)
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(work / "keep.txt") in tracked
    assert str(work / "skip.bin") not in tracked


def test_list_tracked_files_empty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    work = tmp_path / "work"
    work.mkdir()
    init_bare_repo(repo)
    assert list_tracked_files(bare_repo=repo, work_tree=work) == set()


def test_stage_paths_exclude_outside_work_tree_is_ignored(bare_repo, tmp_path: Path) -> None:
    repo, work = bare_repo
    (work / "inside.txt").write_text("inside")
    outside = tmp_path / "outside.bin"
    outside.write_text("outside")
    stage_paths(
        [str(work / "inside.txt")],
        bare_repo=repo, work_tree=work,
        excludes=[str(outside)],
    )
    commit("add inside", bare_repo=repo, work_tree=work)
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(work / "inside.txt") in tracked


def test_stage_paths_excludes_nested_config_toml(bare_repo) -> None:
    """config.toml (machine-local) is not staged when .config is tracked."""
    repo, work = bare_repo
    lintwin_dir = work / ".config" / "lintwin"
    lintwin_dir.mkdir(parents=True)
    (lintwin_dir / "config.toml").write_text("machine-local")
    (lintwin_dir / "shared.toml").write_text("shared")

    stage_paths(
        [str(work / ".config")],
        bare_repo=repo, work_tree=work,
        excludes=[str(lintwin_dir / "config.toml")],
    )
    commit("add dotconfig", bare_repo=repo, work_tree=work)
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(lintwin_dir / "shared.toml") in tracked
    assert str(lintwin_dir / "config.toml") not in tracked


def test_stage_paths_bare_glob_excludes_matching_files(bare_repo) -> None:
    """Bare glob like '*.gpg' excludes matching files anywhere in the tracked tree."""
    repo, work = bare_repo
    subdir = work / "keys"
    subdir.mkdir()
    (subdir / "secret.gpg").write_text("secret key material")
    (subdir / "pubkey.txt").write_text("public")

    stage_paths(
        [str(subdir)],
        bare_repo=repo, work_tree=work,
        excludes=["*.gpg"],
    )
    commit("add keys dir", bare_repo=repo, work_tree=work)
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(subdir / "pubkey.txt") in tracked
    assert str(subdir / "secret.gpg") not in tracked


def test_stage_paths_home_relative_glob_excludes_deep_matches(bare_repo) -> None:
    """A glob like '<wt>/.config/**/*.secret' excludes files at any depth."""
    repo, work = bare_repo
    app_dir = work / ".config" / "myapp"
    app_dir.mkdir(parents=True)
    (app_dir / "api.secret").write_text("secret token")
    (app_dir / "settings.conf").write_text("safe config")

    # Simulate how DEFAULT_NEVER_SYNC entries like "~/.config/**/*.secret" resolve
    # after expanduser() when the work tree is the home directory.
    glob_exclude = str(work / ".config" / "**" / "*.secret")
    stage_paths(
        [str(work / ".config")],
        bare_repo=repo, work_tree=work,
        excludes=[glob_exclude],
    )
    commit("add dotconfig", bare_repo=repo, work_tree=work)
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(app_dir / "settings.conf") in tracked
    assert str(app_dir / "api.secret") not in tracked


def test_stage_paths_gpg_files_not_committed_with_default_never_sync(bare_repo) -> None:
    """Integration: staging a dir containing .gpg files with DEFAULT_NEVER_SYNC excludes them."""
    from lintwin.core.constants import DEFAULT_NEVER_SYNC

    repo, work = bare_repo
    dot_local = work / ".local" / "share" / "app"
    dot_local.mkdir(parents=True)
    (dot_local / "keyring.gpg").write_text("encrypted data")
    (dot_local / "data.json").write_text("{}")

    stage_paths(
        [str(work / ".local")],
        bare_repo=repo, work_tree=work,
        excludes=DEFAULT_NEVER_SYNC,
    )
    commit("add local data", bare_repo=repo, work_tree=work)
    tracked = list_tracked_files(bare_repo=repo, work_tree=work)
    assert str(dot_local / "data.json") in tracked
    assert str(dot_local / "keyring.gpg") not in tracked


def test_git_rm_cached_removes_file_from_index(bare_repo) -> None:
    repo, work = bare_repo
    git_rm_cached("hello.txt", bare_repo=repo, work_tree=work)
    result = subprocess.run(
        ["git", f"--git-dir={repo}", f"--work-tree={work}", "ls-files", "hello.txt"],
        capture_output=True, text=True,
    )
    assert result.stdout.strip() == ""


def test_git_rm_cached_noop_for_untracked_file(bare_repo) -> None:
    repo, work = bare_repo
    git_rm_cached("nonexistent.txt", bare_repo=repo, work_tree=work)  # must not raise
