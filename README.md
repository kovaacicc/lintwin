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
- SSH key added to your GitHub account — lintwin uses SSH URLs for the git remote, so `git push` will fail without it. If you haven't done this: `cat ~/.ssh/id_ed25519.pub` (or `id_rsa.pub`) and add it at https://github.com/settings/keys
- SSH key-based auth to your other machines (no password prompts during sync)

## Install

On Arch Linux, avoid installing into the system Python. Use a virtualenv:

```bash
git clone https://github.com/kovaacicc/lintwin
cd lintwin
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

To use `lintwin` without activating the venv each time, add an alias to your `.bashrc`:

```bash
alias lintwin='/path/to/lintwin/.venv/bin/lintwin'
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

## Tailscale setup (optional, recommended)

Without Tailscale, rsync only works when both machines are on the same LAN. With Tailscale, lintwin can sync over any network — from a coffee shop, from work, from anywhere — without port forwarding or VPN configuration.

### Install and authenticate on each machine

```bash
sudo pacman -S tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up
```

`tailscale up` opens a browser to log in with your Tailscale account. Do this on every machine you want to sync.

### Find your machine names

```bash
tailscale status
```

This lists all your connected devices with their Tailscale hostnames (e.g. `desktop`, `laptop`) and IPs (e.g. `100.x.x.x`). Use these when lintwin asks for host/IP during `init`.

### Configure lintwin to use Tailscale

In `~/.config/lintwin/config.toml`, add `tailscale_hostname` to each remote:

```toml
[remotes.desktop]
host = "192.168.1.10"          # LAN IP — used as fallback
ssh_user = "user"
tailscale_hostname = "desktop" # Tailscale hostname — tried first
```

When `tailscale_hostname` is set, lintwin checks Tailscale reachability first (`tailscale ping <hostname>`). If the machine is reachable over Tailscale, it uses `tailscale_hostname` as the SSH target. If not (Tailscale offline or peer not connected), it falls back to `host`.

You can set `tailscale_hostname` without a LAN `host` if you only ever sync over Tailscale:

```toml
[remotes.desktop]
host = "100.64.0.2"            # Tailscale IP — works as both
ssh_user = "user"
tailscale_hostname = "desktop"
```

### SSH over Tailscale

Make sure your SSH key is authorized on the remote machine. Tailscale handles the network; SSH handles authentication. No extra config needed beyond what you'd do for LAN SSH:

```bash
ssh-copy-id user@desktop   # uses Tailscale hostname directly once tailscale is up
```

### Why not just use the Tailscale IP always?

Tailscale IPs (`100.x.x.x`) work even on LAN, but they route through Tailscale's relay if direct connection fails — which adds latency for large rsync transfers. Using the LAN IP as `host` and Tailscale as `tailscale_hostname` gives you fast local transfers when at home and seamless remote sync otherwise.

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
ssh_port = 2222                  # optional — omit if using default port 22
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

## Credits

This project was largely built with [Claude Code](https://claude.ai/code), Anthropic's AI coding assistant.

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
