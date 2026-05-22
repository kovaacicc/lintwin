# lintwin — Project Context for Claude

## What this is
lintwin ("linux twin") is a personal CLI tool for keeping multiple Arch Linux machines in sync.
Two strategies: **git** (bare repo, text/configs) and **rsync** (large files, LAN/Tailscale).
Built in Python, lives at `~/.config/lintwin/` (config) and `~/.local/share/lintwin/` (data).

## Project structure
```
lintwin/
  cli/          main.py, init.py, sync.py, status.py, pull.py, diff.py, track.py, packages.py, selector.py, format.py
  core/         git.py, rsync.py, scanner.py, snapshot.py, config.py, constants.py, sizeguard.py
  core/packages/  base.py (ABC), arch.py (pacman/AUR/pip/npm)
tests/          99 unit tests, all passing
README.md       full user docs including Tailscale setup
pyproject.toml  entry point: lintwin.cli.main:cli
.venv/          virtualenv — use .venv/bin/python and .venv/bin/lintwin
```

## Running
```bash
.venv/bin/python -m pytest tests/ -q   # run tests
.venv/bin/lintwin --help               # CLI
```

## Key data paths (runtime, not in repo)
- `~/.config/lintwin/config.toml`    — local machine name + remotes (never committed)
- `~/.config/lintwin/shared.toml`    — tracked paths (committed to git remote)
- `~/.local/share/lintwin/repo/`     — bare git repo
- `~/.local/share/lintwin/packages/` — exported package lists
- `~/.local/share/lintwin/last_sync.json` — rsync snapshot for conflict detection

## Implementation status
All planned tasks complete. 99/99 tests passing.
Commands: init, sync, status, pull, diff, track, untrack, packages (export/diff/install)
`lintwin init` uses an interactive arrow-key selector (`cli/selector.py`, built on `rich.Live`
+ `readchar`) to assign home-directory items to git/rsync/skip with live size totals.
Before each `lintwin sync`, `core/sizeguard.py` scans git-tracked paths for oversized new
files/dirs and prompts the user to offload them to rsync, add them to never-sync, or commit
anyway. The threshold defaults to 25 MB and can be set at init time with `--max-git-file-mb N`
(written into `shared.toml`).

## Known gaps (not yet implemented)
- No `lintwin remote add` command — remotes added only during `init` wizard or by hand-editing config.toml
- PackageManager only has Arch implementation — adding Debian/Ubuntu means writing `debian.py` implementing the ABC
- `lintwin init --join` does not auto-detect existing machines from the repo; user enters each remote manually

## Design decisions
- Bare git repo (not yadm) for dotfile tracking
- `config.toml` is local-only, never committed; `shared.toml` is committed and synced across machines
- rsync conflict detection via snapshot timestamps in `last_sync.json`
- PackageManager is an ABC — adding other distros is a single new file
- Tailscale: `tailscale ping <hostname>` checked first if `tailscale_hostname` set in config, falls back to `host`

## Recent bug fixes (2026-05-20)
- stage_paths was passed `[]` instead of `shared.git_paths` in sync — dotfiles never staged
- `divergence_info` crashed before first push (no origin/main yet) — now graceful
- `status`/`sync`/`pull` gave raw traceback when run before `lintwin init` — now friendly error
- git-tracked paths outside `$HOME` silently broke all git ops — now caught at `track` time
- Remote selection in `sync` now happens before git preview (was after)
