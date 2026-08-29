"""Cladogram rendering of a rotation tree with matplotlib."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import matplotlib

matplotlib.use("Agg") if not matplotlib.get_backend() else None
import matplotlib.pyplot as plt

from .parser import RotationModel, parse_rot
from .tree import PlateNode, build_tree


def _layout(root: PlateNode) -> dict[int, tuple[float, float]]:
    """x = depth from root, y = leaf-ordered position; keyed by id(node)."""
    positions: dict[int, tuple[float, float]] = {}
    next_y = [0.0]

    def place(node: PlateNode, depth: int) -> float:
        if not node.children:
            y = next_y[0]
            next_y[0] += 1.0
        else:
            ys = [place(child, depth + 1) for child in node.children]
            y = sum(ys) / len(ys)
        positions[id(node)] = (float(depth), y)
        return y

    place(root, 0)
    return positions


def plot_cladogram(
    source: Union[str, Path, RotationModel],
    time: float = 0.0,
    ax: Optional[plt.Axes] = None,
    show_names: bool = True,
    highlight: Optional[set[int]] = None,
    anchor: int = 0,
    label_fontsize: float = 7.0,
    color: str = "#355F8C",
    highlight_color: str = "#C1441E",
    name_maxlen: int = 28,
):
    """Draw the plate-hierarchy cladogram of a .rot model at ``time`` Ma.

    Parameters
    ----------
    source : path to a .rot file, .rot text, or a parsed RotationModel
    time : reconstruction age (Ma) at which the hierarchy is evaluated
    highlight : plate IDs whose labels are emphasized

    Returns the matplotlib Axes.
    """
    model = source if isinstance(source, RotationModel) else parse_rot(source)
    root = build_tree(model, time=time, anchor=anchor)
    positions = _layout(root)
    n_leaves = root.n_leaves

    if ax is None:
        height = max(3.0, 0.16 * n_leaves)
        _, ax = plt.subplots(figsize=(9, height))

    highlight = highlight or set()
    for node in root.walk():
        x, y = positions[id(node)]
        for child in node.children:
            cx, cy = positions[id(child)]
            ax.plot([x, x, cx], [y, cy, cy], lw=0.8, color=color, zorder=1)
        is_leaf = not node.children
        if node.plate_id < 0:
            label = node.name or "orphans"
        else:
            label = str(node.plate_id)
            if show_names and node.name:
                name = node.name
                if len(name) > name_maxlen:
                    name = name[: name_maxlen - 1] + "\u2026"
                label += f" {name}"
        emphasized = node.plate_id in highlight
        ax.text(
            x + 0.05,
            y,
            label,
            fontsize=label_fontsize + (1.5 if emphasized else 0.0),
            va="center" if is_leaf else "bottom",
            ha="left" if is_leaf else "right",
            color=highlight_color if emphasized else "0.15",
            fontweight="bold" if emphasized else "normal",
            zorder=2,
        )
        ax.plot([x], [y], "o", ms=2.2, color=color, zorder=2)

    title_path = model.path.name if model.path else "rotation model"
    ax.set_title(f"{title_path} — plate hierarchy at {time:g} Ma", fontsize=10)
    ax.set_xlabel("levels from anchor plate")
    ax.set_yticks([])
    ax.set_xlim(-0.5, root.depth + 1.5)
    ax.invert_yaxis()
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.figure.tight_layout()
    return ax


def save_cladogram(source, out: Union[str, Path], time: float = 0.0, **kwargs) -> Path:
    ax = plot_cladogram(source, time=time, **kwargs)
    out = Path(out)
    ax.figure.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(ax.figure)
    return out
