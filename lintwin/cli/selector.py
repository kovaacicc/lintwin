from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lintwin.core.constants import DEFAULT_GIT_PATHS, DEFAULT_RSYNC_PATHS, NOISE_DOTFILES

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


def _compute_totals(nodes: list[SelectorNode]) -> tuple[int, int]:
    # nodes must be the top-level list only — never a recursive walk
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
                _cycle_mode(node)

            elif key == readchar.key.RIGHT:
                node, depth, _last = flat[cursor]
                if depth == 0 and node.path.is_dir():
                    _load_children(node)
                    node.expanded = True
                    flat = _flatten(nodes)

            elif key == readchar.key.LEFT:
                node, depth, _last = flat[cursor]
                if depth == 1:
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
                return _derive_paths(nodes, home)

            elif key in ("q", "Q"):
                console.print("[yellow]Init cancelled.[/yellow]")
                raise SystemExit(0)

            cursor = min(cursor, len(flat) - 1)
            live.update(_render(flat, cursor, nodes))
