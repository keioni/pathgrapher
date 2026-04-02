"""Filesystem scanner — uses `du -xkd` per subdirectory for fast traversal."""

import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field

MAX_DEPTH = 5  # total depth from root (including root's children)


@dataclass
class DirNode:
    name: str
    path: str
    size: int = 0
    children: list["DirNode"] = field(default_factory=list)


def _parse_du_tree(
    lines: list[str],
    root: str,
    ignore_names: frozenset[str],
) -> dict[str, DirNode]:
    """Parse `du -xkd N` output into a dict of path -> DirNode."""
    nodes: dict[str, DirNode] = {}
    for line in lines:
        parts = line.rstrip("\n").split("\t", 1)
        if len(parts) != 2:
            continue
        try:
            size_bytes = int(parts[0]) * 1024
        except ValueError:
            continue
        path = os.path.normpath(parts[1])
        name = os.path.basename(path) or path

        # skip any path that contains an ignored component below root
        rel = os.path.relpath(path, root)
        if any(part in ignore_names for part in rel.split(os.sep)):
            continue

        nodes[path] = DirNode(name=name, path=path, size=size_bytes)

    # wire up parent-child relationships
    for path, node in nodes.items():
        if path == root:
            continue
        parent_path = os.path.dirname(path)
        if parent_path in nodes:
            nodes[parent_path].children.append(node)

    for node in nodes.values():
        node.children.sort(key=lambda n: n.size)

    return nodes


def _scan_subtree(
    path: str, depth: int, ignore_names: frozenset[str]
) -> DirNode:
    """Run `du -xkd {depth}` on *path* and return a DirNode tree."""
    fallback = DirNode(name=os.path.basename(path) or path, path=path)
    try:
        result = subprocess.run(
            ["du", f"-xkd{depth}", path],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return fallback

    nodes = _parse_du_tree(result.stdout.splitlines(), path, ignore_names)
    return nodes.get(path, fallback)


def _scan(
    root: str,
    out: "queue.Queue[DirNode | None]",
    interval: float = 0.5,
    ignore_names: frozenset[str] = frozenset(),
) -> None:
    root = os.path.abspath(root)
    root_node = DirNode(name=os.path.basename(root) or root, path=root)
    last_send = time.monotonic()

    try:
        entries = list(os.scandir(root))
    except OSError:
        out.put(root_node)
        out.put(None)
        return

    for entry in entries:
        if entry.is_symlink():
            continue
        if not entry.is_dir(follow_symlinks=False):
            try:
                root_node.size += entry.stat(follow_symlinks=False).st_size
            except OSError:
                pass
            continue

        if entry.name in ignore_names:
            continue

        # scan up to (MAX_DEPTH - 1) more levels inside this child
        child = _scan_subtree(entry.path, MAX_DEPTH - 1, ignore_names)
        root_node.size += child.size
        root_node.children.append(child)
        root_node.children.sort(key=lambda n: n.size)

        now = time.monotonic()
        if now - last_send >= interval:
            out.put(root_node)
            last_send = now

    out.put(root_node)
    out.put(None)


def start_scan(
    root: str,
    interval: float = 0.5,
    ignore_names: frozenset[str] = frozenset(),
) -> "queue.Queue[DirNode | None]":
    q: queue.Queue[DirNode | None] = queue.Queue()
    t = threading.Thread(
        target=_scan, args=(root, q, interval, ignore_names), daemon=True
    )
    t.start()
    return q
