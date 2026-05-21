# Interactive Sync Selector — Design Spec

**Date:** 2026-05-22
**Status:** Approved

## Overview

Replace the current per-item `Confirm.ask` loop in `lintwin init` with a full interactive terminal selector. Users navigate their home folder with arrow keys, assign each item to `git`, `rsync`, or `skip`, drill into subfolders to select specific children, and see running size totals update live. Built on `rich.Live` + `readchar`.

---

## Module Structure

One new file: `lintwin/cli/selector.py`

Owns: data model, size scanning, rendering, key handling.

Public interface:

```python
def run_selector(home: Path) -> tuple[list[str], list[str]]:
    """Returns (git_paths, rsync_paths) as lists of ~/... strings."""
```

`init.py` calls `run_selector(home)` and uses the result directly. The functions `discover_dotfiles`, `discover_rsync_dirs`, and `_interactive_checklist` are removed from `init.py`.

New dependency added to `pyproject.toml`: `readchar`.

---

## Data Model

```python
@dataclass
class SelectorNode:
    path: Path
    mode: Literal["skip", "git", "rsync"] = "skip"
    size: int = 0                # bytes, computed once
    children: list[SelectorNode] = field(default_factory=list)
    expanded: bool = False
    children_loaded: bool = False  # lazy — only scanned on first expand
```

---

## Scanning

**Startup scan:** All top-level items in `~` are scanned before the UI opens. Sizes are computed via `du -sb` (dirs) and `os.path.getsize` (files). A `Scanning...` spinner is shown during this phase. Items in `NOISE_DOTFILES` are excluded.

**Default modes:** Items matching `DEFAULT_GIT_PATHS` start as `git`. Items matching `DEFAULT_RSYNC_PATHS` start as `rsync`. Everything else starts as `skip`.

**Lazy child scan:** Children are only loaded when the user presses `→` on a folder for the first time. Sizes for children are computed at that point. This avoids scanning large directories like `Documents/` upfront.

---

## Display Layout

```
── git 12.4 MB  ·  rsync 2.1 GB  ──────────────────────────
  [git  ]  .bashrc                              4 KB
  [git  ]  .gitconfig                           2 KB
▶ [mixed]  .config/                            48 MB
  ├ [git  ]  nvim/                              2 MB
  ├ [git  ]  fish/                             80 KB
  ├ [skip ]  chromium/                         44 MB
  └ [skip ]  discord/                           1 MB
  [rsync]  Documents/                          14 GB
  [skip ]  Downloads/                           5 GB
────────────────────────────────────────────────────────────
  ↑↓ navigate  ·  space cycle mode  ·  → expand  ·  ← collapse  ·  enter confirm  ·  q cancel
```

The totals bar at the top updates on every keypress.

---

## Key Bindings

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move cursor |
| `space` | Cycle mode on current item (see below) |
| `→` | Expand folder, load children if first time |
| `←` | Collapse folder |
| `enter` | Confirm and return selections |
| `q` | Cancel — exits `lintwin init` entirely with a friendly message, no changes written |

---

## Mode Cycling & Parent/Child Behaviour

**On a regular item:** cycles `skip → git → rsync → skip`.

**On a folder (expanded or collapsed):**
- Cycles the parent mode through `skip → git → rsync → skip`
- Propagates the new mode to **all loaded children** immediately
- Children not yet loaded inherit the parent mode when first scanned; if the parent is `[mixed]` at scan time, children default to `skip`

**`[mixed]` state:** Shown on a parent when children have differing modes. Pressing `space` on `[mixed]` advances to `git` (start of cycle) and applies to all children.

---

## Running Totals

Totals count bytes at the **leaf level** to avoid double-counting:

- If a node has `children_loaded = True`: its own size is **never** counted — only its children contribute
- If a node has `children_loaded = False`: its own size is counted directly

This means:
- Expand `.config/`, mark `nvim/` as git, collapse → total still reflects `nvim/` size only (10 MB), not the full `.config/` (100 MB)
- Children stay in memory after collapse; totals remain accurate

---

## Tracked Path Derivation

When the user presses `enter`, the tree is walked once to produce the final path lists:

| Condition | Result |
|-----------|--------|
| `children_loaded = False`, mode = git/rsync | Add parent path (e.g. `~/.config`) |
| `children_loaded = True`, all children same mode (git/rsync) | **Collapse back to parent path** — new subdirs auto-included in future syncs |
| `children_loaded = True`, all children skip | Omit |
| `children_loaded = True`, mixed child modes | Track each non-skip child individually (e.g. `~/.config/nvim`, `~/.config/fish`) |

**Why collapse back when all children share a mode:** tracking the parent path means any new subfolder created after init is automatically included in future syncs without requiring `lintwin track`. Tracking children individually would silently miss new additions.

**Structure is always preserved:** a child path always includes its parent in the tracked path. Selecting `nvim/` inside `.config/` produces `~/.config/nvim`, never a bare `nvim`.

---

## `init.py` Changes

In `_run_init`, replace:

```python
dotfiles = discover_dotfiles(home)
default_names = {Path(p).expanduser().name for p in DEFAULT_GIT_PATHS}
git_paths = _interactive_checklist("Git-tracked dotfiles", dotfiles, default_names)

rsync_dirs = discover_rsync_dirs(home)
extra_rsync = _interactive_checklist("Rsync directories", rsync_dirs, set())
rsync_paths = list(DEFAULT_RSYNC_PATHS) + extra_rsync
```

With:

```python
git_paths, rsync_paths = run_selector(home)
```

Remove `discover_dotfiles`, `discover_rsync_dirs`, `_interactive_checklist` from `init.py`. `_run_join` is untouched.

---

## Out of Scope (Future)

- **Pre-sync size guard:** before each `lintwin sync`, scan git-tracked paths for files/dirs over 25 MB that have appeared since last sync. Warn and offer to move to rsync or never_sync. Tracked as a separate spec.
