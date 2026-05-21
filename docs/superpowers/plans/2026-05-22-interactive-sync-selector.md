# Interactive Sync Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `Confirm.ask` checklist in `lintwin init` with an arrow-key interactive selector that shows file sizes, supports subfolder drilling, and displays live git/rsync totals.

**Architecture:** A new `lintwin/cli/selector.py` module owns the entire feature — data model, scanning, rendering, and key handling. `init.py` calls a single `run_selector(home)` function. `rich.Live` redraws the display on every keypress; `readchar` captures raw key events.

**Tech Stack:** Python 3.11+, `rich` (already a dep), `readchar` (new dep, ~10KB), `pytest`, `click.testing`

---

## File Map

| File | Change | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add `readchar` dependency |
| `lintwin/cli/selector.py` | Create | `SelectorNode`, scanning, path derivation, mode logic, rendering, key loop |
| `lintwin/cli/init.py` | Modify | Replace checklist functions with `run_selector` call |
| `tests/test_selector.py` | Create | Unit tests for scanning, derivation, mode logic |
| `tests/test_cli_init.py` | Modify | Remove tests for deleted functions |

---

## Task 1: Data model, scanning, and `readchar` dependency

**Goal:** Scaffold `selector.py` with `SelectorNode`, size scanning, and lazy child loading; add `readchar` to deps.

**Files:**
- Modify: `pyproject.toml`
- Create: `lintwin/cli/selector.py`
- Create: `tests/test_selector.py`

**Acceptance Criteria:**
- [ ] `readchar` is in `pyproject.toml` dependencies and installs cleanly
- [ ] `SelectorNode` can be constructed with defaults
- [ ] `_scan_home(tmp_path)` returns one node per non-noise item, with correct default modes
- [ ] `_load_children(node)` populates `node.children` and sets `children_loaded = True`
- [ ] Children inherit parent mode on first load
- [ ] `pytest tests/test_selector.py -v` passes

**Verify:** `.venv/bin/python -m pytest tests/test_selector.py -v` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/test_selector.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_selector.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `selector.py` doesn't exist yet.

- [ ] **Step 3: Add `readchar` to `pyproject.toml`**

In `pyproject.toml`, change:

```toml
dependencies = [
    "click>=8.1",
    "rich>=13.0",
    "tomli-w>=1.0",
]
```

To:

```toml
dependencies = [
    "click>=8.1",
    "rich>=13.0",
    "tomli-w>=1.0",
    "readchar>=4.0",
]
```

Then reinstall: `.venv/bin/pip install -e .`

- [ ] **Step 4: Create `lintwin/cli/selector.py` with data model and scanning**

```python
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lintwin.core.constants import DEFAULT_GIT_PATHS, DEFAULT_RSYNC_PATHS, NOISE_DOTFILES

Mode = Literal["skip", "git", "rsync"]
DisplayMode = Literal["skip", "git", "rsync", "mixed"]


@dataclass
class SelectorNode:
    path: Path
    mode: Mode = "skip"
    size: int = 0
    children: list[SelectorNode] = field(default_factory=list)
    expanded: bool = False
    children_loaded: bool = False


def _get_size(path: Path) -> int:
    if path.is_file() or (path.is_symlink() and not path.is_dir()):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    if path.is_dir():
        try:
            result = subprocess.run(
                ["du", "-sb", str(path)],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return int(result.stdout.split()[0])
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
    return 0


def _default_mode(path: Path) -> Mode:
    name = path.name
    for p in DEFAULT_GIT_PATHS:
        if Path(p).expanduser().name == name:
            return "git"
    for p in DEFAULT_RSYNC_PATHS:
        if Path(p).expanduser().name == name:
            return "rsync"
    return "skip"


def _scan_home(home: Path) -> list[SelectorNode]:
    nodes = []
    for item in sorted(home.iterdir()):
        if item.name in NOISE_DOTFILES:
            continue
        mode = _default_mode(item)
        size = _get_size(item)
        nodes.append(SelectorNode(path=item, mode=mode, size=size))
    return nodes


def _load_children(node: SelectorNode) -> None:
    if node.children_loaded:
        return
    try:
        children_paths = sorted(node.path.iterdir())
    except PermissionError:
        node.children_loaded = True
        return
    for item in children_paths:
        size = _get_size(item)
        node.children.append(SelectorNode(path=item, mode=node.mode, size=size))
    node.children_loaded = True


def run_selector(home: Path) -> tuple[list[str], list[str]]:
    raise NotImplementedError("implemented in task 3")
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_selector.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml lintwin/cli/selector.py tests/test_selector.py
git commit -m "feat: add SelectorNode data model, scanning, and readchar dep"
```

---

## Task 2: Path derivation and mode logic

**Goal:** Implement `_derive_paths`, `_cycle_mode`, `_compute_totals`, `_flatten`, and helpers; all covered by unit tests.

**Files:**
- Modify: `lintwin/cli/selector.py`
- Modify: `tests/test_selector.py`

**Acceptance Criteria:**
- [ ] `_derive_paths` collapses to parent path when all children share a mode
- [ ] `_derive_paths` tracks children individually when modes are mixed
- [ ] `_derive_paths` uses parent path directly when `children_loaded = False`
- [ ] `_compute_totals` counts from children when loaded, parent size when not
- [ ] `_compute_totals` never double-counts parent + children
- [ ] `_cycle_mode` advances skip→git→rsync→skip; mixed→git
- [ ] `_cycle_mode` propagates to loaded children
- [ ] `_flatten` returns depth-0 entries for top-level, depth-1 for expanded children
- [ ] `pytest tests/test_selector.py -v` passes (all tests including new ones)

**Verify:** `.venv/bin/python -m pytest tests/test_selector.py -v` → all tests pass

**Steps:**

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_selector.py`:

```python
from lintwin.cli.selector import (
    _cycle_mode, _compute_totals, _derive_paths, _flatten, _node_display_mode,
)


# ── _node_display_mode ────────────────────────────────────────────────────────

def test_display_mode_no_children() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="git")
    assert _node_display_mode(node) == "git"


def test_display_mode_all_same() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git"),
        SelectorNode(path=Path("/tmp/x/b"), mode="git"),
    ]
    parent.children_loaded = True
    assert _node_display_mode(parent) == "git"


def test_display_mode_mixed() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git"),
        SelectorNode(path=Path("/tmp/x/b"), mode="rsync"),
    ]
    parent.children_loaded = True
    assert _node_display_mode(parent) == "mixed"


# ── _cycle_mode ───────────────────────────────────────────────────────────────

def test_cycle_mode_skip_to_git() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="skip")
    nodes = [node]
    _cycle_mode(node, nodes)
    assert node.mode == "git"


def test_cycle_mode_rsync_to_skip() -> None:
    node = SelectorNode(path=Path("/tmp/x"), mode="rsync")
    nodes = [node]
    _cycle_mode(node, nodes)
    assert node.mode == "skip"


def test_cycle_mode_mixed_to_git() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git"),
        SelectorNode(path=Path("/tmp/x/b"), mode="rsync"),
    ]
    parent.children_loaded = True
    nodes = [parent]
    _cycle_mode(parent, nodes)
    assert parent.mode == "git"
    assert all(c.mode == "git" for c in parent.children)


def test_cycle_mode_propagates_to_loaded_children() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="skip")
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="skip"),
        SelectorNode(path=Path("/tmp/x/b"), mode="skip"),
    ]
    parent.children_loaded = True
    nodes = [parent]
    _cycle_mode(parent, nodes)
    assert parent.mode == "git"
    assert all(c.mode == "git" for c in parent.children)


# ── _compute_totals ───────────────────────────────────────────────────────────

def test_compute_totals_no_children() -> None:
    nodes = [
        SelectorNode(path=Path("/tmp/a"), mode="git", size=100),
        SelectorNode(path=Path("/tmp/b"), mode="rsync", size=200),
        SelectorNode(path=Path("/tmp/c"), mode="skip", size=999),
    ]
    git_b, rsync_b = _compute_totals(nodes)
    assert git_b == 100
    assert rsync_b == 200


def test_compute_totals_counts_children_not_parent() -> None:
    parent = SelectorNode(path=Path("/tmp/x"), mode="git", size=1000)
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a"), mode="git", size=40),
        SelectorNode(path=Path("/tmp/x/b"), mode="skip", size=60),
    ]
    parent.children_loaded = True
    git_b, rsync_b = _compute_totals([parent])
    assert git_b == 40   # only child a, not parent's 1000
    assert rsync_b == 0


def test_compute_totals_still_correct_after_collapse(tmp_path: Path) -> None:
    # Expand, set nvim to git only, collapse — totals must reflect children
    parent_dir = tmp_path / ".config"
    parent_dir.mkdir()
    parent = SelectorNode(path=parent_dir, mode="skip", size=100)
    parent.children = [
        SelectorNode(path=parent_dir / "nvim", mode="git", size=10),
        SelectorNode(path=parent_dir / "chrome", mode="skip", size=90),
    ]
    parent.children_loaded = True
    parent.expanded = False  # collapsed, but children loaded
    git_b, _ = _compute_totals([parent])
    assert git_b == 10


# ── _derive_paths ─────────────────────────────────────────────────────────────

def test_derive_paths_unexpanded_uses_parent(tmp_path: Path) -> None:
    home = tmp_path
    f = home / ".bashrc"
    f.write_text("")
    node = SelectorNode(path=f, mode="git", size=0)
    git, rsync = _derive_paths([node], home)
    assert "~/.bashrc" in git
    assert rsync == []


def test_derive_paths_all_children_same_collapses(tmp_path: Path) -> None:
    home = tmp_path
    cfg = home / ".config"
    cfg.mkdir()
    node = SelectorNode(path=cfg, mode="git", size=0)
    node.children = [
        SelectorNode(path=cfg / "nvim", mode="git", size=0),
        SelectorNode(path=cfg / "fish", mode="git", size=0),
    ]
    node.children_loaded = True
    git, rsync = _derive_paths([node], home)
    assert git == ["~/.config"]


def test_derive_paths_mixed_children_tracks_individually(tmp_path: Path) -> None:
    home = tmp_path
    cfg = home / ".config"
    cfg.mkdir()
    node = SelectorNode(path=cfg, mode="skip", size=0)
    node.children = [
        SelectorNode(path=cfg / "nvim", mode="git", size=0),
        SelectorNode(path=cfg / "fish", mode="rsync", size=0),
        SelectorNode(path=cfg / "chrome", mode="skip", size=0),
    ]
    node.children_loaded = True
    git, rsync = _derive_paths([node], home)
    assert git == ["~/.config/nvim"]
    assert rsync == ["~/.config/fish"]


def test_derive_paths_all_skip_omitted(tmp_path: Path) -> None:
    home = tmp_path
    cfg = home / ".config"
    cfg.mkdir()
    node = SelectorNode(path=cfg, mode="skip", size=0)
    node.children = [SelectorNode(path=cfg / "x", mode="skip", size=0)]
    node.children_loaded = True
    git, rsync = _derive_paths([node], home)
    assert git == []
    assert rsync == []


# ── _flatten ──────────────────────────────────────────────────────────────────

def test_flatten_no_expansion() -> None:
    nodes = [
        SelectorNode(path=Path("/tmp/a")),
        SelectorNode(path=Path("/tmp/b")),
    ]
    flat = _flatten(nodes)
    assert len(flat) == 2
    assert all(depth == 0 for _, depth, _ in flat)


def test_flatten_expanded_node_shows_children() -> None:
    parent = SelectorNode(path=Path("/tmp/x"))
    parent.children = [
        SelectorNode(path=Path("/tmp/x/a")),
        SelectorNode(path=Path("/tmp/x/b")),
    ]
    parent.children_loaded = True
    parent.expanded = True
    flat = _flatten([parent])
    assert len(flat) == 3
    assert flat[0][1] == 0   # parent depth 0
    assert flat[1][1] == 1   # child depth 1
    assert flat[2][2] is True   # last child


def test_flatten_collapsed_hides_children() -> None:
    parent = SelectorNode(path=Path("/tmp/x"))
    parent.children = [SelectorNode(path=Path("/tmp/x/a"))]
    parent.children_loaded = True
    parent.expanded = False
    flat = _flatten([parent])
    assert len(flat) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/python -m pytest tests/test_selector.py -v -k "display_mode or cycle or totals or derive or flatten"
```

Expected: `ImportError` or `AttributeError` — functions not yet defined.

- [ ] **Step 3: Implement the logic functions in `selector.py`**

Add after `_load_children` in `lintwin/cli/selector.py`:

```python
def _node_display_mode(node: SelectorNode) -> DisplayMode:
    if not node.children_loaded or not node.children:
        return node.mode
    modes = {c.mode for c in node.children}
    if len(modes) == 1:
        return modes.pop()
    return "mixed"


_CYCLE_ORDER: list[Mode] = ["skip", "git", "rsync"]


def _cycle_mode(node: SelectorNode, nodes: list[SelectorNode]) -> None:
    display = _node_display_mode(node)
    if display == "mixed":
        next_mode: Mode = "git"
    else:
        idx = _CYCLE_ORDER.index(display)
        next_mode = _CYCLE_ORDER[(idx + 1) % 3]
    node.mode = next_mode
    if node.children_loaded:
        for child in node.children:
            child.mode = next_mode


def _compute_totals(nodes: list[SelectorNode]) -> tuple[int, int]:
    git_bytes = 0
    rsync_bytes = 0
    for node in nodes:
        if node.children_loaded:
            for child in node.children:
                if child.mode == "git":
                    git_bytes += child.size
                elif child.mode == "rsync":
                    rsync_bytes += child.size
        else:
            if node.mode == "git":
                git_bytes += node.size
            elif node.mode == "rsync":
                rsync_bytes += node.size
    return git_bytes, rsync_bytes


def _derive_paths(
    nodes: list[SelectorNode], home: Path | None = None
) -> tuple[list[str], list[str]]:
    if home is None:
        home = Path.home()
    git_paths: list[str] = []
    rsync_paths: list[str] = []

    for node in nodes:
        rel = f"~/{node.path.relative_to(home)}"
        if not node.children_loaded:
            if node.mode == "git":
                git_paths.append(rel)
            elif node.mode == "rsync":
                rsync_paths.append(rel)
        else:
            child_modes = {c.mode for c in node.children}
            if len(child_modes) <= 1:
                mode = child_modes.pop() if child_modes else "skip"
                if mode == "git":
                    git_paths.append(rel)
                elif mode == "rsync":
                    rsync_paths.append(rel)
            else:
                for child in node.children:
                    child_rel = f"~/{child.path.relative_to(home)}"
                    if child.mode == "git":
                        git_paths.append(child_rel)
                    elif child.mode == "rsync":
                        rsync_paths.append(child_rel)

    return git_paths, rsync_paths


def _flatten(
    nodes: list[SelectorNode],
) -> list[tuple[SelectorNode, int, bool]]:
    flat: list[tuple[SelectorNode, int, bool]] = []
    for node in nodes:
        flat.append((node, 0, False))
        if node.expanded and node.children_loaded:
            for i, child in enumerate(node.children):
                is_last = i == len(node.children) - 1
                flat.append((child, 1, is_last))
    return flat


def _fmt_size(size: int) -> str:
    for unit, threshold in [("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)]:
        if size >= threshold:
            return f"{size / threshold:.1f} {unit}"
    return f"{size} B"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/python -m pytest tests/test_selector.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add lintwin/cli/selector.py tests/test_selector.py
git commit -m "feat: implement path derivation, mode cycling, totals, flatten"
```

---

## Task 3: Interactive UI — rendering and key event loop

**Goal:** Implement `run_selector` using `rich.Live` and `readchar`; the full interactive terminal UI.

**Files:**
- Modify: `lintwin/cli/selector.py` (replace `run_selector` stub)

**Acceptance Criteria:**
- [ ] `run_selector` returns `(git_paths, rsync_paths)` as lists of strings
- [ ] Pressing `q` raises `SystemExit(0)` with a cancel message printed
- [ ] The full test suite still passes (`pytest tests/ -q`)

**Verify:** `.venv/bin/python -m pytest tests/ -q` → 55+ tests pass, 0 failed

**Steps:**

- [ ] **Step 1: Add the rendering helper and replace `run_selector`**

Replace the `run_selector` stub at the bottom of `lintwin/cli/selector.py` with:

```python
_MODE_BADGE: dict[str, tuple[str, str]] = {
    "git":   ("[git  ]", "green"),
    "rsync": ("[rsync]", "yellow"),
    "skip":  ("[skip ]", "dim"),
    "mixed": ("[mixed]", "cyan"),
}


def _render(
    flat: list[tuple[SelectorNode, int, bool]],
    cursor: int,
    nodes: list[SelectorNode],
) -> "Text":
    from rich.text import Text

    git_bytes, rsync_bytes = _compute_totals(nodes)
    lines: list[Text] = []

    totals = Text()
    totals.append("── git ", style="dim")
    totals.append(_fmt_size(git_bytes), style="green bold")
    totals.append("  ·  rsync ", style="dim")
    totals.append(_fmt_size(rsync_bytes), style="yellow bold")
    totals.append("  " + "─" * 38, style="dim")
    lines.append(totals)

    for i, (node, depth, is_last) in enumerate(flat):
        selected = i == cursor
        line = Text()

        line.append("▶ " if selected else "  ", style="bold cyan" if selected else "")

        if depth == 1:
            line.append("└ " if is_last else "├ ", style="dim")

        display = _node_display_mode(node)
        badge, badge_style = _MODE_BADGE[display]
        line.append(badge + "  ", style=badge_style)

        name = node.path.name + ("/" if node.path.is_dir() else "")
        line.append(f"{name:<32}", style="bold" if selected else "")
        line.append(_fmt_size(node.size), style="dim")

        lines.append(line)

    footer = Text(
        "\n  ↑↓ navigate  ·  space cycle  ·  → expand  ·  ← collapse  ·  enter confirm  ·  q cancel",
        style="dim",
    )
    lines.append(footer)

    result = Text()
    for j, line in enumerate(lines):
        result.append_text(line)
        if j < len(lines) - 1:
            result.append("\n")
    return result


def run_selector(home: Path) -> tuple[list[str], list[str]]:
    import readchar
    from rich.console import Console
    from rich.live import Live

    console = Console()
    console.print("[dim]Scanning home directory...[/dim]")
    nodes = _scan_home(home)

    cursor = 0
    flat = _flatten(nodes)

    with Live(
        _render(flat, cursor, nodes),
        console=console,
        refresh_per_second=30,
        screen=False,
    ) as live:
        while True:
            key = readchar.readkey()

            if key == readchar.key.UP:
                cursor = max(0, cursor - 1)

            elif key == readchar.key.DOWN:
                cursor = min(len(flat) - 1, cursor + 1)

            elif key == " ":
                node, _depth, _last = flat[cursor]
                _cycle_mode(node, nodes)

            elif key == readchar.key.RIGHT:
                node, depth, _last = flat[cursor]
                if depth == 0 and node.path.is_dir():
                    _load_children(node)
                    node.expanded = True
                    flat = _flatten(nodes)

            elif key == readchar.key.LEFT:
                node, depth, _last = flat[cursor]
                if depth == 1:
                    # find the parent (nearest depth-0 above cursor)
                    parent_idx = next(
                        i for i in range(cursor - 1, -1, -1)
                        if flat[i][1] == 0
                    )
                    flat[parent_idx][0].expanded = False
                    flat = _flatten(nodes)
                    cursor = parent_idx
                elif node.expanded:
                    node.expanded = False
                    flat = _flatten(nodes)

            elif key in (readchar.key.ENTER, "\r", "\n"):
                return _derive_paths(nodes)

            elif key in ("q", "Q"):
                console.print("[yellow]Init cancelled.[/yellow]")
                raise SystemExit(0)

            cursor = min(cursor, len(flat) - 1)
            live.update(_render(flat, cursor, nodes))
```

- [ ] **Step 2: Run full test suite to confirm nothing broken**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: 55+ tests pass, 0 failed. (`run_selector` itself is not unit-tested here — it requires a live terminal; it is exercised in Task 4 via manual smoke test.)

- [ ] **Step 3: Commit**

```bash
git add lintwin/cli/selector.py
git commit -m "feat: implement interactive selector UI with rich.Live + readchar"
```

---

## Task 4: Wire into `init.py`, update tests, manual smoke test

**Goal:** Replace the old checklist functions in `init.py` with `run_selector`; clean up now-deleted function references in tests; verify the full `lintwin init` flow works end to end.

**Files:**
- Modify: `lintwin/cli/init.py`
- Modify: `tests/test_cli_init.py`

**Acceptance Criteria:**
- [ ] `_interactive_checklist`, `discover_dotfiles`, `discover_rsync_dirs` removed from `init.py`
- [ ] `_run_init` calls `run_selector(home)` and passes results to `SharedConfig`
- [ ] `test_cli_init.py` imports only symbols that still exist
- [ ] `pytest tests/ -q` → 50+ tests pass, 0 failed (3 tests removed for deleted functions)
- [ ] `lintwin init --help` still works

**Verify:** `.venv/bin/python -m pytest tests/ -q` → 0 failed

**Steps:**

- [ ] **Step 1: Update `init.py`**

Remove the functions `discover_dotfiles`, `discover_rsync_dirs`, and `_interactive_checklist` entirely.

Add the import at the top of `init.py` (with the other local imports):

```python
from lintwin.cli.selector import run_selector
```

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

Also remove the now-unused import `DEFAULT_GIT_PATHS` from the constants import line if it's no longer referenced elsewhere in `init.py`.

- [ ] **Step 2: Update `test_cli_init.py`**

Remove the three tests that reference deleted functions and fix the import line.

Change the import from:

```python
from lintwin.cli.init import check_prerequisites, discover_dotfiles, discover_rsync_dirs
```

To:

```python
from lintwin.cli.init import check_prerequisites
```

Delete these three test functions entirely:
- `test_discover_dotfiles_finds_dotfiles`
- `test_discover_rsync_dirs_finds_non_hidden_dirs`

(The scanning logic is now tested in `tests/test_selector.py`.)

- [ ] **Step 3: Run test suite**

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: 0 failed. Test count drops by 2 (the removed tests); selector tests add more than that, so total count will be higher than 55.

- [ ] **Step 4: Manual smoke test — confirm `lintwin init --help` works**

```bash
.venv/bin/lintwin init --help
```

Expected output includes `Usage: lintwin init` and `--join` option, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add lintwin/cli/init.py tests/test_cli_init.py
git commit -m "feat: wire interactive selector into lintwin init"
```

---

## Post-implementation

After all tasks complete, push to GitHub:

```bash
git push
```
