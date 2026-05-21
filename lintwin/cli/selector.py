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


def run_selector(home: Path) -> tuple[list[str], list[str]]:
    raise NotImplementedError("implemented in task 3")
