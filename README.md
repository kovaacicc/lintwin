# lintwin

Keep your Linux machines in sync — dotfiles, configs, packages, and large files.

## How it works

Two sync strategies:

- **Git** (bare repo): text files, dotfiles, configs — tracked explicitly, committed and pushed to a private GitHub repo. Works offline; syncs whenever both machines are online.
- **rsync**: large files, Downloads, Pictures, Documents — direct machine-to-machine transfer over LAN or Tailscale. Requires both machines to be reachable.

## Prerequisites

- Python 3.11+
- `git`, `rsync` — `sudo pacman -S git rsync`
- `gh` (GitHub CLI) — `sudo pacman -S github-cli`, then authenticate: `gh auth login`
- SSH key-based auth to your other machines (no password prompts during sync)

## Install

On Arch Linux, avoid installing into the system Python. Use a virtualenv:

```bash
git clone https://github.com/you/archsync
cd archsync
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

To use `lintwin` without activating the venv each time, add an alias to your `.bashrc`:

```bash
alias lintwin='/path/to/archsync/.venv/bin/lintwin'
```

## Setup

### First machine

```bash
lintwin init
# or with a name upfront (skips the prompt):
lintwin init --name desktop
```

The wizard will:
1. Check `git`, `rsync`, `gh` are installed
2. Ask for a machine name — use something descriptive like `desktop`, `laptop`, `work-pc`
3. Create a private GitHub repo (or use an existing one)
4. Show your dotfiles — you choose which to track with git
5. Show your home directories — you choose which to sync with rsync
6. Initialize the bare repo, commit and push `shared.toml`

At the end it prints the `--join` command to run on your other machines.

### Every other machine

```bash
lintwin init --join git@github.com:you/lintwin-dots.git
# or with a name:
lintwin init --join git@github.com:you/lintwin-dots.git --name work-laptop
```

This pulls your existing tracked paths from the repo and walks you through entering each remote machine's IP/hostname.

## Daily use

```bash
lintwin status          # what's changed since last sync, which remotes are reachable
lintwin sync            # git + rsync: shows preview, asks to confirm
lintwin sync --dry-run  # preview only — no changes applied
lintwin pull            # pull only (no push)
```

When you have more than one remote configured, pass `--to`:

```bash
lintwin sync --to desktop
lintwin pull --to laptop
```

## Managing tracked paths

```bash
lintwin track ~/.config/nvim --via git      # track with git (must be inside $HOME)
lintwin track ~/Documents --via rsync        # track with rsync
lintwin untrack ~/.config/nvim               # stop tracking
```

## Package management

```bash
lintwin packages export             # snapshot installed packages (pacman, AUR, pip, npm)
lintwin packages diff --to desktop  # show what's missing between this machine and desktop
lintwin packages install            # install packages that are on remote but missing locally
```

Package lists live in `~/.local/share/lintwin/packages/` and are committed to your git repo so they stay in sync.

## CLI reference

```
lintwin init                                first-run wizard
lintwin init --name <name>                  skip the machine name prompt
lintwin init --join <url>                   join existing setup on a new machine
lintwin init --join <url> --name <name>     join with a specific machine name

lintwin sync                                full sync: git + rsync
lintwin sync --to <remote>                  required when 2+ remotes are configured
lintwin sync --dry-run                      preview only, no changes applied

lintwin pull                                pull only (no push)
lintwin pull --to <remote>

lintwin status                              git changes + dirty repos + remote reachability
lintwin diff                                git diff + rsync diff vs remote
lintwin diff --to <remote>

lintwin track <path> --via git              add to git-tracked paths
lintwin track <path> --via rsync            add to rsync paths
lintwin untrack <path>                      remove from sync

lintwin packages export                     snapshot installed packages
lintwin packages diff --to <remote>         show packages missing between machines
lintwin packages install                    install packages missing locally
```

## Config files

| File | Purpose |
|------|---------|
| `~/.config/lintwin/config.toml` | Local machine config (name, remote hosts). **Never committed.** |
| `~/.config/lintwin/shared.toml` | Shared config (tracked paths). Committed and synced. |
| `~/.local/share/lintwin/repo/` | Bare git repo |
| `~/.local/share/lintwin/packages/` | Exported package lists |
| `~/.local/share/lintwin/last_sync.json` | rsync snapshot for conflict detection |

### `~/.config/lintwin/config.toml` (local only, never committed)

```toml
[machine]
name = "laptop"

[remotes.desktop]
host = "192.168.1.10"
ssh_user = "karlo"
tailscale_hostname = "desktop"   # optional — tried first if set
```

### `~/.config/lintwin/shared.toml` (committed, synced across machines)

```toml
[git_paths]
paths = [
  "~/.config",
  "~/.bashrc",
  "~/.gitconfig",
  "~/.local/bin",
]

[rsync_paths]
paths = [
  "~/Downloads",
  "~/Pictures",
  "~/Documents",
]

[never_sync]
patterns = [
  "~/.ssh/id_*",
  "~/.cache",
  "*.gpg",
  "~/.gnupg",
]
```

## What gets synced

**Git:** dotfiles and config dirs listed in `[git_paths]`. Committed to your private GitHub repo and synced via push/pull. Works across any network; syncs even when machines are not online at the same time.

**rsync:** directories listed in `[rsync_paths]`. Transferred directly over SSH — requires both machines to be reachable (LAN or Tailscale).

**Never synced:** SSH private keys (`~/.ssh/id_*`), caches, GPG keys, and anything matching `[never_sync]` patterns.

**Project repos** (`~/projects/`): lintwin does not touch their contents. It scans for uncommitted or unpushed changes and warns you before sync so you don't lose work.

## What lintwin is not

- Not a daemon — everything is manually triggered
- Not Ansible — it does not provision software beyond installing from your package snapshots
- Not cross-platform — Arch-first; other distros can be added via a new `PackageManager` implementation
- Not a replacement for your project git repos — it warns about dirty ones, never modifies them

## Troubleshooting

**`lintwin status` (or sync/pull) shows "Not initialized"**
Run `lintwin init` first. All commands except `init` require the bare repo and config to exist.

**`git status` error: path is outside repository**
Git-tracked paths must be inside `$HOME`. Remove the offending path:
```bash
lintwin untrack /etc/something
# if you still want it synced:
lintwin track /etc/something --via rsync
```

**rsync skipped with "Cannot reach..."**
The remote is offline or not on the same network. Run `lintwin pull --to <remote>` to pull git-only changes, or wait until both machines are on the same network / Tailscale.

**Conflict detected on sync**
lintwin prompts you: keep local, keep remote, skip, or show diff (text files only). Conflicts only appear when the same file was modified on both machines since the last sync.

**`lintwin packages diff` shows everything as missing**
Run `lintwin packages export` on both machines first to generate the package snapshots.
