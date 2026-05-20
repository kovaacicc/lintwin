from unittest.mock import patch
from lintwin.core.packages.base import PackageManager
from lintwin.core.packages.arch import PacmanManager, PipManager, get_available_managers


def test_pacman_manager_is_subclass() -> None:
    assert issubclass(PacmanManager, PackageManager)


def test_pacman_diff_missing() -> None:
    mgr = PacmanManager()
    with patch.object(mgr, "export", return_value={"explicit": ["nvim", "git"], "aur": []}):
        result = mgr.diff({"explicit": ["nvim", "git", "htop"], "aur": []})
    assert "htop" in result["missing"]
    assert result["extra"] == []


def test_pacman_diff_extra() -> None:
    mgr = PacmanManager()
    with patch.object(mgr, "export", return_value={"explicit": ["nvim", "git", "htop"], "aur": []}):
        result = mgr.diff({"explicit": ["nvim", "git"], "aur": []})
    assert "htop" in result["extra"]
    assert result["missing"] == []


def test_pip_manager_is_subclass() -> None:
    from lintwin.core.packages.arch import PipManager
    assert issubclass(PipManager, PackageManager)


def test_get_available_managers_returns_list() -> None:
    managers = get_available_managers()
    assert isinstance(managers, list)
    for m in managers:
        assert isinstance(m, PackageManager)
