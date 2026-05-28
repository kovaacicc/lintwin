import json
from unittest.mock import patch, MagicMock
from lintwin.core.packages.base import PackageManager
from lintwin.core.packages.arch import PacmanManager, PipManager, NpmManager, get_available_managers


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
    assert issubclass(PipManager, PackageManager)


def test_pip_export_strips_versions() -> None:
    mgr = PipManager()
    pip_json = '[{"name": "requests", "version": "2.31.0"}, {"name": "flask", "version": "3.0.0"}]'
    mock_result = MagicMock()
    mock_result.stdout = pip_json
    with patch("subprocess.run", return_value=mock_result):
        result = mgr.export()
    assert result["packages"] == ["requests", "flask"]
    assert not any("==" in p for p in result["packages"])


def test_pip_install_uses_break_system_packages() -> None:
    mgr = PipManager()
    with patch("subprocess.run") as mock_run:
        mgr.install(["requests", "flask"])
    cmd = mock_run.call_args[0][0]
    assert "--break-system-packages" in cmd


def test_npm_export_preserves_scoped_packages() -> None:
    mgr = NpmManager()
    npm_output = "/usr/lib/node_modules\n/usr/lib/node_modules/@vue/cli\n/usr/lib/node_modules/typescript\n"
    mock_result = MagicMock()
    mock_result.stdout = npm_output
    with patch("subprocess.run", return_value=mock_result):
        result = mgr.export()
    assert "@vue/cli" in result["packages"]
    assert "cli" not in result["packages"]
    assert "typescript" in result["packages"]


def test_npm_export_skips_root_dir() -> None:
    mgr = NpmManager()
    npm_output = "/usr/lib/node_modules\n/usr/lib/node_modules/npm\n"
    mock_result = MagicMock()
    mock_result.stdout = npm_output
    with patch("subprocess.run", return_value=mock_result):
        result = mgr.export()
    assert "node_modules" not in result["packages"]
    assert "npm" in result["packages"]


def test_get_available_managers_returns_list() -> None:
    managers = get_available_managers()
    assert isinstance(managers, list)
    for m in managers:
        assert isinstance(m, PackageManager)
