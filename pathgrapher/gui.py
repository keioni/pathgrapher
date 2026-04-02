"""tkinter GUI — draws proportional directory blocks on a Canvas."""

import os
import queue
import time
import tkinter as tk
from tkinter import font as tkfont

from .scanner import DirNode, start_scan

MAX_DEPTH = 6       # maximum number of columns to render
PATH_COL_WIDTH = 200  # width of the leftmost path column in pixels


def _fmt_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _tree_depth(node: DirNode, limit: int = MAX_DEPTH, min_pct: float = 0.0) -> int:
    """Return the depth of the subtree, capped at *limit*."""
    visible = [
        child for child in node.children
        if node.size == 0 or (child.size / node.size * 100) >= min_pct
    ]
    if not visible or limit == 0:
        return 0
    return 1 + max(_tree_depth(child, limit - 1, min_pct) for child in visible)


def _draw_tree(
    canvas: tk.Canvas,
    node: DirNode,
    x: int,
    y: int,
    width: int,
    height: int,
    levels: int,
    item_to_path: dict[int, str],
    min_font_size: int = 8,
    first_col: bool = True,
    min_pct: float = 0.0,
) -> None:
    """Draw node's children as a column, then recurse into the next column.

    Each child occupies a vertical slice proportional to its size within
    (y, y+height). If the child itself has children, they are drawn in the
    next column at the same vertical range.
    """
    if not node.children or levels == 0 or width < 2 or height < 2:
        return

    col_width = width // levels

    if first_col:
        min_block_height = tkfont.Font(
            family="Helvetica", size=min_font_size
        ).metrics("linespace") + 4
    else:
        min_block_height = 1

    # filter out children below the minimum percentage threshold
    visible_children = [
        child for child in node.children
        if node.size == 0 or (child.size / node.size * 100) >= min_pct
    ]
    if not visible_children:
        return

    # re-normalize to fit exactly within height
    total_size = sum(child.size for child in visible_children)
    if total_size == 0:
        return

    # first pass: compute raw heights and enforce min_block_height
    raw_heights = []
    for child in reversed(visible_children):  # largest at bottom
        ratio = child.size / total_size
        raw_heights.append(max(min_block_height, int(height * ratio)))

    # scale to fit exactly within height (up or down)
    total_raw = sum(raw_heights)
    if total_raw != height:
        scale = height / total_raw
        raw_heights = [max(1, int(h * scale)) for h in raw_heights]
        # distribute rounding remainder to the largest block (first in list = bottom)
        diff = height - sum(raw_heights)
        raw_heights[0] += diff

    cursor_y = y
    for child, block_height in zip(reversed(visible_children), raw_heights):
        block_y = cursor_y
        cursor_y += block_height

        item_id = canvas.create_rectangle(
            x, block_y, x + col_width, block_y + block_height,
            fill="#4a90d9", outline="white",
        )
        item_to_path[item_id] = child.path
        _draw_label(
            canvas, child, node.size,
            x, block_y, col_width, block_height,
            min_font_size,
        )

        if child.children and levels > 1:
            _draw_tree(
                canvas, child,
                x + col_width, block_y,
                width - col_width, block_height,
                levels - 1,
                item_to_path,
                min_font_size,
                first_col=False,
                min_pct=min_pct,
            )


def _draw_label(
    canvas: tk.Canvas,
    node: DirNode,
    parent_size: int,
    x: int,
    y: int,
    width: int,
    height: int,
    min_font_size: int = 8,
) -> None:
    pct = node.size / parent_size * 100 if parent_size else 0
    size_str = _fmt_size(node.size)
    pct_str = f"{pct:.1f}%"
    label_2 = f"{node.name}\n{size_str} ({pct_str})"
    label_1 = f"{node.name} {size_str} ({pct_str})"

    rotate = height > width  # rotate 90° when taller than wide
    avail_width, avail_height = (height, width) if rotate else (width, height)

    # try each label variant from most to least detailed
    # 3-line and 2-line respect min_font_size; 1-line falls back to smaller sizes
    font = None
    label = None
    all_sizes = (14, 12, 10, 8, 6)
    sized_sizes = [s for s in all_sizes if s >= min_font_size] or [min_font_size]

    fallback_sizes = (14, 12, 10, 8, 6)

    for candidate_label, font_sizes in (
        (label_2, sized_sizes),       # 2-line: respect min_font_size
        (label_1, [min_font_size]),   # 1-line: fixed min_font_size
        (label_1, fallback_sizes),    # 1-line: try smaller fonts
    ):
        for font_size in font_sizes:
            f = tkfont.Font(family="Helvetica", size=font_size)
            lines = candidate_label.split("\n")
            text_width = max(f.measure(line) for line in lines)
            text_height = f.metrics("linespace") * len(lines)
            if text_width <= avail_width - 4 and text_height <= avail_height - 4:
                font = f
                label = candidate_label
                break
        if font is not None:
            break

    if font is None or label is None:
        # last resort: truncate label_1 at smallest font
        f = tkfont.Font(family="Helvetica", size=fallback_sizes[-1])
        if f.metrics("linespace") > avail_height - 4:
            return  # truly too small
        truncated = label_1
        while truncated and f.measure(truncated) > avail_width - 4:
            truncated = truncated[:-1]
        if not truncated:
            return
        if truncated != label_1:
            truncated = truncated[:-1] + "…"
        font = f
        label = truncated

    cx, cy = x + width // 2, y + height // 2
    angle = 90 if rotate else 0
    canvas.create_text(
        cx, cy,
        text=label,
        font=font,
        fill="white",
        angle=angle,
        justify="center",
    )


class App(tk.Tk):
    def __init__(
        self,
        root_path: str,
        scan_queue: "queue.Queue[DirNode | None]",
        ignore_names: frozenset[str] = frozenset(),
        min_font_size: int = 8,
        cache_ttl: float = 300.0,
        min_pct: float = 0.0,
    ) -> None:
        super().__init__()
        self.title("Path Grapher")
        self.geometry("800x600")
        self._path = os.path.abspath(root_path)
        self._ignore_names = ignore_names
        self._min_font_size = min_font_size
        self._min_pct = min_pct
        self._cache_ttl = cache_ttl
        # cache: path -> (DirNode, timestamp)
        self._cache: dict[str, tuple[DirNode, float]] = {}
        self._queue = scan_queue
        self._done = False
        self._timed_out = False
        self._scan_start = time.monotonic()
        self._root_node: DirNode | None = None
        self._levels: int | None = None  # fixed after scan completes

        self._canvas = tk.Canvas(self, bg="#1e1e1e")
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Configure>", lambda _: self._redraw())
        self._canvas.bind("<Button-1>", self._on_left_click)
        self._canvas.bind("<Button-2>", self._go_up)  # macOS right-click
        # Windows/Linux right-click
        self._canvas.bind("<Button-3>", self._go_up)
        self._item_to_path: dict[int, str] = {}

        self._poll()

    def _on_left_click(self, event: tk.Event) -> None:
        items = self._canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item_id in reversed(items):  # topmost first
            path = self._item_to_path.get(item_id)
            if path:
                self._navigate(path)
                return

    def _go_up(self, _event: tk.Event) -> None:
        parent = os.path.dirname(self._path)
        if parent == self._path:
            return  # already at filesystem root
        self._navigate(parent)

    def _navigate(self, path: str) -> None:
        self._path = path
        self.title(f"Path Grapher — {self._path}")
        self._done = False
        self._timed_out = False
        self._levels = None
        self._scan_start = time.monotonic()

        cached = self._cache.get(path)
        if cached and (time.monotonic() - cached[1]) < self._cache_ttl:
            self._root_node = cached[0]
            self._done = True
            self._levels = min(_tree_depth(self._root_node, min_pct=self._min_pct), MAX_DEPTH)
            self._redraw()
            return

        self._root_node = None
        self._queue = start_scan(self._path, ignore_names=self._ignore_names)
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._done = True
                    if self._root_node is not None:
                        self._levels = min(
                            _tree_depth(self._root_node, min_pct=self._min_pct), MAX_DEPTH
                        )
                        self._cache[self._path] = (self._root_node, time.monotonic())
                    break
                self._root_node = item
                self._redraw()
        except queue.Empty:
            pass
        if not self._done:
            elapsed = time.monotonic() - self._scan_start
            if not self._timed_out and elapsed > 30:
                self._timed_out = True
                self._show_timeout()
            self.after(200, self._poll)

    def _show_timeout(self) -> None:
        canvas_width = self._canvas.winfo_width()
        canvas_height = self._canvas.winfo_height()
        self._canvas.create_rectangle(
            0, canvas_height - 32, canvas_width, canvas_height,
            fill="#c0392b", outline="",
        )
        self._canvas.create_text(
            canvas_width // 2, canvas_height - 16,
            text="スキャンに時間がかかっています (30秒超過)",
            fill="white",
            font=("Helvetica", 12),
        )

    def _draw_path_column(self, canvas_height: int) -> None:
        self._canvas.create_rectangle(
            0, 0, PATH_COL_WIDTH, canvas_height,
            fill="#2c2c2c", outline="#555555",
        )
        # path components, one per line
        parts = self._path.split(os.sep)
        parts = [p for p in parts if p]  # remove empty strings
        line_height = 20
        font = ("Helvetica", 11)
        y = 10
        for part in parts:
            self._canvas.create_text(
                PATH_COL_WIDTH // 2, y,
                text=part,
                fill="#cccccc",
                font=font,
                width=PATH_COL_WIDTH - 12,
                anchor="n",
            )
            # measure lines used (approximate)
            lines = max(1, len(part) * 7 // (PATH_COL_WIDTH - 12) + 1)
            y += line_height * lines + 4
            if y > canvas_height:
                break

    def _redraw(self) -> None:
        if self._root_node is None:
            return
        self._canvas.delete("all")
        canvas_width = self._canvas.winfo_width()
        canvas_height = self._canvas.winfo_height()
        self._draw_path_column(canvas_height)
        node = self._root_node
        levels = self._levels if self._levels is not None else min(
            _tree_depth(node, min_pct=self._min_pct), MAX_DEPTH
        )
        if levels == 0:
            return
        self._item_to_path = {}
        tree_x = PATH_COL_WIDTH
        tree_width = canvas_width - PATH_COL_WIDTH
        _draw_tree(
            self._canvas, node,
            tree_x, 0, tree_width, canvas_height,
            levels,
            self._item_to_path,
            self._min_font_size,
            min_pct=self._min_pct,
        )
