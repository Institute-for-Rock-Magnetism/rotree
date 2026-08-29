"""Cladogram rendering of a rotation tree with matplotlib."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import matplotlib

matplotlib.use("Agg") if not matplotlib.get_backend() else None
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .parser import RotationModel, parse_rot
from .tree import PlateNode, build_tree

# one hue per depth level, cycled; muted so labels stay the focus
_DEPTH_COLORS = [
    "#31547E",
    "#3D7A6C",
    "#8A6B2F",
    "#7A4B6E",
    "#4B6E8A",
    "#6E5E3D",
]
_ORPHAN_COLOR = "#9A5B4F"
_LABEL_COLOR = "#26313B"
_MUTED_COLOR = "#7C8894"


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


def _branch_color(node: PlateNode, depth: int) -> str:
    if node.plate_id < 0:
        return _ORPHAN_COLOR
    return _DEPTH_COLORS[depth % len(_DEPTH_COLORS)]


def plot_cladogram(
    source: Union[str, Path, RotationModel],
    time: float = 0.0,
    ax: Optional[plt.Axes] = None,
    show_names: bool = True,
    highlight: Optional[set[int]] = None,
    anchor: int = 0,
    label_fontsize: float = 7.0,
    color: Optional[str] = None,
    highlight_color: str = "#C1441E",
    name_maxlen: int = 28,
    mark_crossovers: bool = True,
    annotations=None,
):
    """Draw the plate-hierarchy cladogram of a .rot model at ``time`` Ma.

    Parameters
    ----------
    source : path to a .rot file, .rot text, or a parsed RotationModel
    time : reconstruction age (Ma) at which the hierarchy is evaluated
    highlight : plate IDs whose labels are emphasized
    color : single branch color; default colors branches by depth
    mark_crossovers : ring the plates that re-parent elsewhere in time
    annotations : sidecar annotations (path/JSON/list, see
        :mod:`rotree.annotations`); plates with an event active at
        ``time`` are drawn as diamonds

    Returns the matplotlib Axes.
    """
    from .annotations import load_annotations

    model = source if isinstance(source, RotationModel) else parse_rot(source)
    root = build_tree(model, time=time, anchor=anchor)
    positions = _layout(root)
    n_leaves = root.n_leaves

    if ax is None:
        height = max(3.0, 0.17 * n_leaves + 0.8)
        _, ax = plt.subplots(figsize=(9.5, height))
    fig = ax.figure
    fig.set_facecolor("white")
    ax.set_facecolor("#FBFCFD")

    crossover_plates = (
        {p for p in model.moving_plates if model.crossovers(p)}
        if mark_crossovers
        else set()
    )
    events = load_annotations(annotations)
    active_plates = {p for e in events if e.active_at(time) for p in e.plates}

    # subtle bands behind alternating leaf rows keep long labels traceable
    for row in range(0, n_leaves, 2):
        ax.axhspan(row - 0.5, row + 0.5, color="#F0F3F6", zorder=0, lw=0)

    highlight = highlight or set()
    depth_of = {id(root): 0}
    for node in root.walk():
        x, y = positions[id(node)]
        depth = depth_of[id(node)]
        for child in node.children:
            depth_of[id(child)] = depth + 1
            cx, cy = positions[id(child)]
            branch = color or _branch_color(child, depth + 1)
            style = ":" if child.plate_id < 0 else "-"
            ax.plot(
                [x, x, cx],
                [y, cy, cy],
                lw=1.0,
                ls=style,
                color=branch,
                solid_capstyle="round",
                zorder=1,
            )
        is_leaf = not node.children
        if node.plate_id < 0:
            label = "orphans"
        else:
            label = str(node.plate_id)
            if show_names and node.name:
                # keep internal-node labels short so chains don't collide
                maxlen = name_maxlen if is_leaf else min(name_maxlen, 14)
                name = node.name
                if len(name) > maxlen:
                    name = name[: maxlen - 1] + "…"
                label += f"  {name}"
        emphasized = node.plate_id in highlight
        node_color = color or _branch_color(node, depth)
        ax.text(
            x + (0.07 if is_leaf else -0.04),
            y,
            label,
            fontsize=(label_fontsize if is_leaf else label_fontsize - 0.8)
            + (1.5 if emphasized else 0.0),
            va="center" if is_leaf else "bottom",
            ha="left" if is_leaf else "right",
            color=highlight_color
            if emphasized
            else (_MUTED_COLOR if node.plate_id < 0 else _LABEL_COLOR),
            fontweight="bold" if emphasized else "normal",
            fontstyle="italic" if node.plate_id < 0 else "normal",
            zorder=3,
        )
        marker = "D" if node.plate_id in active_plates else "o"
        ax.plot(
            [x],
            [y],
            marker,
            ms=3.4 if marker == "D" else 2.6,
            color=node_color,
            zorder=2,
        )
        if node.plate_id in crossover_plates:
            ax.plot(
                [x],
                [y],
                "o",
                ms=6.5,
                mfc="none",
                mec=highlight_color,
                mew=0.9,
                zorder=2,
            )

    title_path = model.path.name if model.path else "rotation model"
    ax.set_title(
        f"{title_path} — plate hierarchy at {time:g} Ma",
        fontsize=11,
        color=_LABEL_COLOR,
        pad=10,
    )
    ax.set_xlabel("levels from anchor plate", fontsize=8.5, color=_MUTED_COLOR)
    ax.set_yticks([])
    ax.tick_params(axis="x", labelsize=7.5, colors=_MUTED_COLOR)
    ax.set_xlim(-0.5, root.depth + 1.5)
    ax.set_ylim(-0.8, n_leaves - 0.2)
    ax.invert_yaxis()
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(_MUTED_COLOR)

    legend_handles = []
    if crossover_plates:
        legend_handles.append(
            Line2D(
                [],
                [],
                marker="o",
                ls="none",
                mfc="none",
                mec=highlight_color,
                mew=0.9,
                ms=6.5,
                label="plate re-parents at another age (crossover)",
            )
        )
    if active_plates:
        legend_handles.append(
            Line2D(
                [],
                [],
                marker="D",
                ls="none",
                color=_LABEL_COLOR,
                ms=4.5,
                label="annotated event active at this age",
            )
        )
    if legend_handles:
        ax.legend(
            handles=legend_handles,
            loc="lower right",
            frameon=False,
            fontsize=7,
            labelcolor=_MUTED_COLOR,
        )
    fig.tight_layout()
    return ax


def save_cladogram(source, out: Union[str, Path], time: float = 0.0, **kwargs) -> Path:
    ax = plot_cladogram(source, time=time, **kwargs)
    out = Path(out)
    ax.figure.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(ax.figure)
    return out
