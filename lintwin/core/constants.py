from pathlib import Path

LINTWIN_DATA = Path.home() / ".local/share/lintwin"
LINTWIN_CONFIG_DIR = Path.home() / ".config/lintwin"
BARE_REPO = LINTWIN_DATA / "repo"
PACKAGES_DIR = LINTWIN_DATA / "packages"
SNAPSHOT_FILE = LINTWIN_DATA / "last_sync.json"
LOCAL_CONFIG_PATH = LINTWIN_CONFIG_DIR / "config.toml"
SHARED_CONFIG_PATH = LINTWIN_CONFIG_DIR / "shared.toml"

DEFAULT_GIT_PATHS: list[str] = [
    "~/.config",
    "~/.bashrc",
    "~/.zshrc",
    "~/.profile",
    "~/.gitconfig",
    "~/.tmux.conf",
    "~/.local/bin",
    "~/.ssh/config",
]

DEFAULT_RSYNC_PATHS: list[str] = [
    "~/Downloads",
    "~/Pictures",
    "~/Documents",
    "~/Desktop",
    "~/Music",
    "~/Videos",
]

DEFAULT_NEVER_SYNC: list[str] = [
    "~/.ssh/id_*",
    "~/.cache",
    "*.gpg",
    "~/.gnupg",
]

NOISE_DOTFILES: set[str] = {
    ".cache", ".gnupg", ".mozilla", ".thunderbird", ".dbus",
    ".local", ".var", ".pki",
}
