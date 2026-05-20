import pytest
from pathlib import Path


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake home directory for tests that write to ~/.config or ~/.local."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path
