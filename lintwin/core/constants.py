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
    "~/.config/lintwin/config.toml",
]

DEFAULT_MAX_GIT_FILE_MB: int = 25

NOISE_DOTFILES: set[str] = {
    ".cache", ".gnupg", ".thunderbird", ".dbus",
}

# Maps a parent directory name (or relative path segment) to child names that
# should be silently hidden when that directory is expanded in the selector.
# ".local/share" is keyed by two path components because its noise set differs
# from ".local" itself.
NOISE_CHILDREN: dict[str, set[str]] = {
    ".config": {"lintwin"},
    ".local": {"lib", "include"},
    ".local/share": {
        "baloo",
        "go",
        "Trash",
        "recently-used.xbel",
        "xorg",
        "flatpak",
        "lintwin",
    },
}
