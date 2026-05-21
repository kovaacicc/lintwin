from pathlib import Path
from lintwin.cli.selector import SelectorNode, _scan_home, _load_children, _get_size


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
