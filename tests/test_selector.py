from pathlib import Path

from lintwin.cli.selector import (
    SelectorNode,
    _compute_totals,
    _cycle_mode,
    _derive_paths,
    _flatten,
    _get_size,
    _load_children,
    _node_display_mode,
    _scan_home,
)
from lintwin.cli.format import fmt_size


# ── SelectorNode / scanning ───────────────────────────────────────────────────

def test_selector_node_defaults() -> None:
    node = SelectorNode(path=Path("/tmp/x"))
    assert node.mode == "skip"
    assert node.size == 0
    assert node.children == []
    assert node.expanded is False
    assert node.children_loaded is False


def test_scan_home_finds_dotfiles_and_dirs(tmp_path: Path) -> None:
    (tmp_path / ".bashrc").write_text("export PATH=$PATH")
    (tmp_path / ".gitconfig").write_text("[user]")
    (tmp_path / ".cache").mkdir()        # NOISE — excluded
    (tmp_path / "Documents").mkdir()
    nodes = _scan_home(tmp_path)
    names = [n.path.name for n in nodes]
    assert ".bashrc" in names
    assert ".gitconfig" in names
    assert "Documents" in names
    assert ".cache" not in names


def test_scan_home_default_modes(tmp_path: Path) -> None:
    (tmp_path / ".bashrc").write_text("")
    (tmp_path / "Documents").mkdir()
    (tmp_path / ".otherstuff").write_text("")
    nodes = _scan_home(tmp_path)
    by_name = {n.path.name: n for n in nodes}
    assert by_name[".bashrc"].mode == "git"
    assert by_name["Documents"].mode == "rsync"
    assert by_name[".otherstuff"].mode == "skip"


def test_scan_home_computes_file_size(tmp_path: Path) -> None:
    f = tmp_path / ".bashrc"
    f.write_text("x" * 100)
    nodes = _scan_home(tmp_path)
    node = next(n for n in nodes if n.path.name == ".bashrc")
    assert node.size == 100


def test_load_children_inherits_parent_mode(tmp_path: Path) -> None:
    parent_dir = tmp_path / ".config"
    parent_dir.mkdir()
    (parent_dir / "nvim").mkdir()
    (parent_dir / "fish").mkdir()
    node = SelectorNode(path=parent_dir, mode="git", size=0)
    _load_children(node)
    assert node.children_loaded is True
    assert len(node.children) == 2
    assert all(c.mode == "git" for c in node.children)


def test_load_children_idempotent(tmp_path: Path) -> None:
    d = tmp_path / ".config"
    d.mkdir()
    (d / "nvim").mkdir()
    node = SelectorNode(path=d, mode="skip", size=0)
    _load_children(node)
    _load_children(node)  # second call must not double-add children
    assert len(node.children) == 1


# ── _node_display_mode ────────────────────────────────────────────────────────

def test_display_mode_no_children() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="git")
    assert _node_display_mode(node) == "git"


def test_display_mode_loaded_empty_children() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="git")
    node.children_loaded = True  # loaded but empty
    assert _node_display_mode(node) == "git"


def test_display_mode_all_same() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git"),
        SelectorNode(path=Path("/tmp/x/b"), mode="git"),
    ]
    parent.children_loaded = True
    assert _node_display_mode(parent) == "git"


def test_display_mode_mixed() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git"),
        SelectorNode(path=Path("/tmp/x/b"), mode="rsync"),
    ]
    parent.children_loaded = True
    assert _node_display_mode(parent) == "mixed"


# ── _cycle_mode ───────────────────────────────────────────────────────────────

def test_cycle_mode_skip_to_git() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="skip")
    _cycle_mode(node)
    assert node.mode == "git"


def test_cycle_mode_rsync_to_skip() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="rsync")
    _cycle_mode(node)
    assert node.mode == "skip"


def test_cycle_mode_mixed_to_git() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git"),
        SelectorNode(path=Path("/tmp/x/b"), mode="rsync"),
    ]
    parent.children_loaded = True
    _cycle_mode(parent)
    assert parent.mode == "git"
    assert all(c.mode == "git" for c in parent.children)


def test_cycle_mode_propagates_to_loaded_children() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="skip"),
        SelectorNode(path=Path("/tmp/x/b"), mode="skip"),
    ]
    parent.children_loaded = True
    _cycle_mode(parent)
    assert parent.mode == "git"
    assert all(c.mode == "git" for c in parent.children)


# ── _compute_totals ───────────────────────────────────────────────────────────

def test_compute_totals_no_children() -> None:
    nodes = [
        SelectorNode(path=Path("/tmp/a"), mode="git", size=100),
        SelectorNode(path=Path("/tmp/b"), mode="rsync", size=200),
        SelectorNode(path=Path("/tmp/c"), mode="skip", size=999),
    ]
    git_b, rsync_b = _compute_totals(nodes)
    assert git_b == 100
    assert rsync_b == 200


def test_compute_totals_counts_children_not_parent() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="git", size=1000)
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git", size=40),
        SelectorNode(path=Path("/tmp/x/b"), mode="skip", size=60),
    ]
    parent.children_loaded = True
    git_b, rsync_b = _compute_totals([parent])
    assert git_b == 40   # only child a, not parent's 1000
    assert rsync_b == 0


def test_compute_totals_still_correct_after_collapse(tmp_path: Path) -> None:
    parent_dir = tmp_path / ".config"
    parent_dir.mkdir()
    parent = SelectorNode(path=parent_dir, mode="skip", size=100)
    parent.children = [
        SelectorNode(path=parent_dir / "nvim", mode="git", size=10),
        SelectorNode(path=parent_dir / "chrome", mode="skip", size=90),
    ]
    parent.children_loaded = True
    parent.expanded = False  # collapsed, but children loaded
    git_b, _ = _compute_totals([parent])
    assert git_b == 10


# ── _derive_paths ─────────────────────────────────────────────────────────────

def test_derive_paths_unexpanded_uses_parent(tmp_path: Path) -> None:
    home = tmp_path
    f = home / ".bashrc"
    f.write_text("")
    node = SelectorNode(path=f, mode="git", size=0)
    git, rsync = _derive_paths([node], home)
    assert "~/.bashrc" in git
    assert rsync == []


def test_derive_paths_all_children_same_collapses(tmp_path: Path) -> None:
    home = tmp_path
    cfg = home / ".config"
    cfg.mkdir()
    node = SelectorNode(path=cfg, mode="git", size=0)
    node.children = [
        SelectorNode(path=cfg / "nvim", mode="git", size=0),
        SelectorNode(path=cfg / "fish", mode="git", size=0),
    ]
    node.children_loaded = True
    git, rsync = _derive_paths([node], home)
    assert git == ["~/.config"]


def test_derive_paths_mixed_children_tracks_individually(tmp_path: Path) -> None:
    home = tmp_path
    cfg = home / ".config"
    cfg.mkdir()
    node = SelectorNode(path=cfg, mode="skip", size=0)
    node.children = [
        SelectorNode(path=cfg / "nvim", mode="git", size=0),
        SelectorNode(path=cfg / "fish", mode="rsync", size=0),
        SelectorNode(path=cfg / "chrome", mode="skip", size=0),
    ]
    node.children_loaded = True
    git, rsync = _derive_paths([node], home)
    assert git == ["~/.config/nvim"]
    assert rsync == ["~/.config/fish"]


def test_derive_paths_all_skip_omitted(tmp_path: Path) -> None:
    home = tmp_path
    cfg = home / ".config"
    cfg.mkdir()
    node = SelectorNode(path=cfg, mode="skip", size=0)
    node.children = [SelectorNode(path=cfg / "x", mode="skip", size=0)]
    node.children_loaded = True
    git, rsync = _derive_paths([node], home)
    assert git == []
    assert rsync == []


# ── _flatten ──────────────────────────────────────────────────────────────────

def test_flatten_no_expansion() -> None:
    nodes = [
        SelectorNode(path=Path("/tmp/a")),
        SelectorNode(path=Path("/tmp/b")),
    ]
    flat = _flatten(nodes)
    assert len(flat) == 2
    assert all(depth == 0 for _, depth, _ in flat)


def test_flatten_expanded_node_shows_children() -> None:
    parent = SelectorNode(path=Path("/tmp/x"))
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a")),
        SelectorNode(path=Path("/tmp/x/b")),
    ]
    parent.children_loaded = True
    parent.expanded = True
    flat = _flatten([parent])
    assert len(flat) == 3
    assert flat[0][1] == 0        # parent depth 0
    assert flat[1][1] == 1        # child depth 1
    assert flat[2][2] is True     # last child is_last=True


def test_flatten_collapsed_hides_children() -> None:
    parent = SelectorNode(path=Path("/tmp/x"))
    parent.children = [SelectorNode(path=Path("/tmp/x/a"))]
    parent.children_loaded = True
    parent.expanded = False
    flat = _flatten([parent])
    assert len(flat) == 1


# ── fmt_size ──────────────────────────────────────────────────────────────────

def test_fmt_size_bytes() -> None:
    assert fmt_size(0) == "0 B"
    assert fmt_size(500) == "500 B"
    assert fmt_size(1023) == "1023 B"


def test_fmt_size_kilobytes() -> None:
    assert fmt_size(1024) == "1.0 KB"
    assert fmt_size(2048) == "2.0 KB"


def test_fmt_size_megabytes() -> None:
    assert fmt_size(1024 ** 2) == "1.0 MB"


def test_fmt_size_gigabytes() -> None:
    assert fmt_size(1024 ** 3) == "1.0 GB"


# ── Unlimited depth / parent / NOISE_CHILDREN ────────────────────────────────

def test_selector_node_has_parent_field() -> None:
    node = SelectorNode(path=Path("/tmp/x"))
    assert node.parent is None


def test_load_children_sets_parent_refs(tmp_path: Path) -> None:
    parent_dir = tmp_path / ".config"
    parent_dir.mkdir()
    (parent_dir / "nvim").mkdir()
    node = SelectorNode(path=parent_dir, mode="git", size=0)
    _load_children(node, home=tmp_path)
    assert len(node.children) == 1
    assert node.children[0].parent is node


def test_load_children_filters_noise_children(tmp_path: Path) -> None:
    local_dir = tmp_path / ".local"
    local_dir.mkdir()
    (local_dir / "bin").mkdir()
    (local_dir / "lib").mkdir()      # NOISE_CHILDREN[".local"]
    (local_dir / "include").mkdir()  # NOISE_CHILDREN[".local"]
    node = SelectorNode(path=local_dir, mode="skip", size=0)
    _load_children(node, home=tmp_path)
    names = [c.path.name for c in node.children]
    assert "bin" in names
    assert "lib" not in names
    assert "include" not in names


def test_load_children_filters_noise_children_share(tmp_path: Path) -> None:
    share_dir = tmp_path / ".local" / "share"
    share_dir.mkdir(parents=True)
    (share_dir / "nvim").mkdir()
    (share_dir / "baloo").mkdir()  # NOISE_CHILDREN[".local/share"]
    (share_dir / "go").mkdir()     # NOISE_CHILDREN[".local/share"]
    node = SelectorNode(path=share_dir, mode="skip", size=0)
    _load_children(node, home=tmp_path)
    names = [c.path.name for c in node.children]
    assert "nvim" in names
    assert "baloo" not in names
    assert "go" not in names


def test_flatten_recurses_to_depth_2() -> None:
    grandchild = SelectorNode(path=Path("/tmp/x/a/1"))
    child = SelectorNode(path=Path("/tmp/x/a"))
    child.children = [grandchild]
    child.children_loaded = True
    child.expanded = True

    parent = SelectorNode(path=Path("/tmp/x"))
    parent.children = [child]
    parent.children_loaded = True
    parent.expanded = True

    flat = _flatten([parent])
    assert len(flat) == 3
    depths = [d for _, d, _ in flat]
    assert depths == [0, 1, 2]


def test_compute_totals_recurses_grandchildren() -> None:
    grandchild = SelectorNode(path=Path("/tmp/x/a/1"), mode="git", size=50)
    child = SelectorNode(path=Path("/tmp/x/a"), mode="git", size=200)
    child.children = [grandchild]
    child.children_loaded = True

    parent = SelectorNode(path=Path("/tmp/x"), mode="git", size=1000)
    parent.children = [child]
    parent.children_loaded = True

    git_b, rsync_b = _compute_totals([parent])
    assert git_b == 50  # only grandchild leaf, not child (200) or parent (1000)
    assert rsync_b == 0


def test_derive_paths_recurses_grandchildren(tmp_path: Path) -> None:
    home = tmp_path
    local = home / ".local"
    share = local / "share"
    share.mkdir(parents=True)

    share_node = SelectorNode(path=share, mode="skip", size=0)
    share_node.children = [
        SelectorNode(path=share / "nvim", mode="git", size=0),
        SelectorNode(path=share / "icons", mode="rsync", size=0),
    ]
    share_node.children_loaded = True

    local_node = SelectorNode(path=local, mode="skip", size=0)
    local_node.children = [share_node]
    local_node.children_loaded = True

    git, rsync = _derive_paths([local_node], home)
    assert "~/.local/share/nvim" in git
    assert "~/.local/share/icons" in rsync
