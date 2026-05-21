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


def run_selector(home: Path) -> tuple[list[str], list[str]]:
    raise NotImplementedError("implemented in task 3")
