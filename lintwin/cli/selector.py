from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lintwin.core.constants import DEFAULT_GIT_PATHS, DEFAULT_RSYNC_PATHS, NOISE_CHILDREN, NOISE_DOTFILES
from lintwin.cli.format import fmt_size

Mode = Literal["skip", "git", "rsync"]
DisplayMode = Literal["skip", "git", "rsync", "mixed"]  # used by _node_display_mode


@dataclass
class SelectorNode:
    path: Path
    mode: Mode = "skip"
    size: int = 0
    children: list[SelectorNode] = field(default_factory=list)
    expanded: bool = False
    children_loaded: bool = False
    parent: SelectorNode | None = None


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
    if not home.is_dir():
        return []
    nodes = []
    for item in sorted(home.iterdir()):
        if item.name in NOISE_DOTFILES:
            continue
        mode = _default_mode(item)
        size = _get_size(item)
        nodes.append(SelectorNode(path=item, mode=mode, size=size))
    return nodes


def _load_children(node: SelectorNode, home: Path | None = None) -> None:
    if node.children_loaded:
        return
    if home is None:
        home = Path.home()
    try:
        key = str(node.path.relative_to(home))
        noise = NOISE_CHILDREN.get(key, set())
    except ValueError:
        noise = set()
    try:
        children_paths = sorted(node.path.iterdir())
    except PermissionError:
        node.children_loaded = True
        return
    for item in children_paths:
        if item.name in noise:
            continue
        size = _get_size(item)
        child = SelectorNode(path=item, mode=node.mode, size=size, parent=node)
        node.children.append(child)
    node.children_loaded = True


def _node_display_mode(node: SelectorNode) -> DisplayMode:
    if not node.children_loaded or not node.children:
        return node.mode
    modes = {c.mode for c in node.children}
    if len(modes) == 1:
        return modes.pop()
    return "mixed"


_CYCLE_ORDER: list[Mode] = ["skip", "git", "rsync"]


def _cycle_mode(node: SelectorNode) -> None:
    display = _node_display_mode(node)
    if display == "mixed":
        next_mode: Mode = "git"
    else:
        idx = _CYCLE_ORDER.index(display)
        next_mode = _CYCLE_ORDER[(idx + 1) % len(_CYCLE_ORDER)]
    node.mode = next_mode
    if node.children_loaded:
        for child in node.children:
            child.mode = next_mode


def _leaf_bytes(node: SelectorNode) -> tuple[int, int]:
    if not node.children_loaded or not node.children:
        git = node.size if node.mode == "git" else 0
        rsync = node.size if node.mode == "rsync" else 0
        return git, rsync
    git, rsync = 0, 0
    for child in node.children:
        g, r = _leaf_bytes(child)
        git += g
        rsync += r
    return git, rsync


def _compute_totals(nodes: list[SelectorNode]) -> tuple[int, int]:
    git_bytes, rsync_bytes = 0, 0
    for node in nodes:
        g, r = _leaf_bytes(node)
        git_bytes += g
        rsync_bytes += r
    return git_bytes, rsync_bytes


def _collect_paths(
    node: SelectorNode,
    home: Path,
    git_paths: list[str],
    rsync_paths: list[str],
) -> None:
    rel = f"~/{node.path.relative_to(home)}"
    if not node.children_loaded or not node.children:
        if node.mode == "git":
            git_paths.append(rel)
        elif node.mode == "rsync":
            rsync_paths.append(rel)
        return
    # Collapse to parent only when every child is a leaf with the same mode.
    # If any child has loaded sub-children, we must recurse to get accurate paths.
    all_leaves = all(not c.children_loaded or not c.children for c in node.children)
    child_modes = {c.mode for c in node.children}
    if all_leaves and len(child_modes) <= 1:
        mode = child_modes.pop() if child_modes else "skip"
        if mode == "git":
            git_paths.append(rel)
        elif mode == "rsync":
            rsync_paths.append(rel)
    else:
        for child in node.children:
            _collect_paths(child, home, git_paths, rsync_paths)


def _derive_paths(
    nodes: list[SelectorNode], home: Path | None = None
) -> tuple[list[str], list[str]]:
    if home is None:
        home = Path.home()
    git_paths: list[str] = []
    rsync_paths: list[str] = []
    for node in nodes:
        _collect_paths(node, home, git_paths, rsync_paths)
    return git_paths, rsync_paths


def _flatten(
    nodes: list[SelectorNode],
    _depth: int = 0,
) -> list[tuple[SelectorNode, int, bool]]:
    flat: list[tuple[SelectorNode, int, bool]] = []
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        flat.append((node, _depth, is_last))
        if node.expanded and node.children_loaded:
            flat.extend(_flatten(node.children, _depth + 1))
    return flat


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
    scroll_offset: int = 0,
    max_visible: int | None = None,
) -> "Text":
    from rich.text import Text

    git_bytes, rsync_bytes = _compute_totals(nodes)
    lines: list[Text] = []

    totals = Text()
    totals.append("── git ", style="dim")
    totals.append(fmt_size(git_bytes), style="green bold")
    totals.append("  ·  rsync ", style="dim")
    totals.append(fmt_size(rsync_bytes), style="yellow bold")
    totals.append("  " + "─" * 38, style="dim")
    lines.append(totals)

    visible = flat[scroll_offset:scroll_offset + max_visible] if max_visible else flat
    for i, (node, depth, is_last) in enumerate(visible):
        actual_i = i + scroll_offset
        selected = actual_i == cursor
        line = Text()

        line.append("▶ " if selected else "  ", style="bold cyan" if selected else "")

        if depth == 0:
            pass
        else:
            line.append("  │ " * (depth - 1), style="dim")
            line.append("└ " if is_last else "├ ", style="dim")

        display = _node_display_mode(node)
        badge, badge_style = _MODE_BADGE[display]
        line.append(badge + "  ", style=badge_style)

        name = node.path.name + ("/" if node.path.is_dir() else "")
        line.append(f"{name:<32}", style="bold" if selected else "")
        line.append(fmt_size(node.size), style="dim")

        lines.append(line)

    # scroll position indicator
    if max_visible and len(flat) > max_visible:
        pct = int(100 * (scroll_offset + max_visible / 2) / len(flat))
        scroll_info = Text(f"  [{scroll_offset + 1}–{min(scroll_offset + max_visible, len(flat))}/{len(flat)}  {pct}%]", style="dim")
        lines.append(scroll_info)

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
    scroll_offset = 0
    flat = _flatten(nodes)

    # reserve lines for: totals header (1) + scroll indicator (1) + footer (2)
    OVERHEAD = 4

    def _clamp_scroll(cursor: int, scroll_offset: int, max_visible: int) -> int:
        if cursor < scroll_offset:
            return cursor
        if cursor >= scroll_offset + max_visible:
            return cursor - max_visible + 1
        return scroll_offset

    def _max_visible() -> int:
        return max(1, console.size.height - OVERHEAD)

    with Live(
        _render(flat, cursor, nodes, scroll_offset, _max_visible()),
        console=console,
        refresh_per_second=30,
        screen=False,
    ) as live:
        while True:
            key = readchar.readkey()
            mv = _max_visible()

            if key == readchar.key.UP:
                cursor = max(0, cursor - 1)

            elif key == readchar.key.DOWN:
                cursor = min(len(flat) - 1, cursor + 1)

            elif key == " ":
                node, _depth, _last = flat[cursor]
                _cycle_mode(node)

            elif key == readchar.key.RIGHT:
                node, _depth, _last = flat[cursor]
                if node.path.is_dir():
                    _load_children(node, home)
                    node.expanded = True
                    flat = _flatten(nodes)

            elif key == readchar.key.LEFT:
                node, depth, _last = flat[cursor]
                if node.expanded:
                    node.expanded = False
                    flat = _flatten(nodes)
                elif node.parent is not None:
                    node.parent.expanded = False
                    flat = _flatten(nodes)
                    cursor = next(i for i, (n, _, _) in enumerate(flat) if n is node.parent)

            elif key in (readchar.key.ENTER, "\r", "\n"):
                return _derive_paths(nodes, home)

            elif key in ("q", "Q"):
                console.print("[yellow]Init cancelled.[/yellow]")
                raise SystemExit(0)

            cursor = min(cursor, len(flat) - 1)
            scroll_offset = _clamp_scroll(cursor, scroll_offset, mv)
            live.update(_render(flat, cursor, nodes, scroll_offset, mv))
