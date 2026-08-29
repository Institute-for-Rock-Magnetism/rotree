"""Interactive (plotly) cladogram of a rotation tree.

Hovering any node — in particular the bifurcation points where branches
join a fixed plate — shows how that plate is positioned at the chosen age
and every reference-frame hand-off (crossover) it undergoes through time,
quoting the .rot file's own line annotations (typically the citation or
reasoning behind the frame choice) together with the source line numbers,
so every link in the tree can be traced back to the data it rests on.

Requires plotly: ``pip install rotree[interactive]``.
"""

from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Optional, Union

from .parser import RotationLine, RotationModel, parse_rot
from .plot import _layout
from .tree import PlateNode, build_tree

_ACCENT = "#C1441E"
_BRANCH = "#31547E"
_ORPHAN = "#9A5B4F"
_MUTED = "#7C8894"
_LABEL = "#26313B"


def _esc(text: str) -> str:
    return _html.escape(text, quote=False)


def _plate_ref(pid: int, names: dict[int, str]) -> str:
    name = names.get(pid, "")
    return f"{pid} ({_esc(name)})" if name else str(pid)


def _annotation(line: RotationLine) -> str:
    text = line.comment.lstrip("!").strip()
    if not text:
        return "<i>no annotation on this line</i>"
    return f"“{_esc(text)}”"


def _hover_text(
    node: PlateNode,
    model: RotationModel,
    names: dict[int, str],
    time: float,
) -> str:
    """HTML hover card: current frame, then the hand-off history with the
    file's own annotations as the citation / data basis for each choice."""
    if node.plate_id < 0:
        return (
            "<b>orphan branch</b><br>"
            "These plates are undefined at this age or their fixed-plate "
            "chain never reaches the anchor."
        )

    title = _plate_ref(node.plate_id, names)
    parts = [f"<b>plate {title}</b>"]

    segment = model.segment_at(node.plate_id, time)
    if segment is not None:
        rows = model.lines_for(node.plate_id)
        idx = rows.index(segment)
        span_end = rows[idx + 1].time if idx + 1 < len(rows) else segment.time
        parts.append(
            f"<br><b>frame at {time:g} Ma</b> — fixed to plate "
            f"{_plate_ref(segment.fixed_plate, names)}<br>"
            f"pole {segment.pole_lat:g}°, {segment.pole_lon:g}°, "
            f"angle {segment.angle:g}° "
            f"(segment {segment.time:g}–{span_end:g} Ma, "
            f".rot line {segment.line_number})<br>"
            f"basis: {_annotation(segment)}"
        )
    elif node.plate_id != 0:
        parts.append(f"<br><i>no rotation pole defined at {time:g} Ma</i>")

    crossovers = model.crossover_details(node.plate_id)
    if crossovers:
        parts.append("<br><br><b>reference-frame hand-offs</b>")
        for x in crossovers:
            parts.append(
                f"<br>• at {x.time:g} Ma: fixed "
                f"{_plate_ref(x.old_fixed, names)} → "
                f"{_plate_ref(x.new_fixed, names)}<br>"
                f"&nbsp;&nbsp;until then: {_annotation(x.before)} "
                f"(line {x.before.line_number})<br>"
                f"&nbsp;&nbsp;from then: {_annotation(x.after)} "
                f"(line {x.after.line_number})"
            )
    elif node.plate_id != 0:
        parts.append(
            "<br><br>no hand-offs: this plate keeps one fixed plate "
            "for its whole history"
        )

    children = [c for c in node.children if c.plate_id >= 0]
    if children:
        listed = ", ".join(_plate_ref(c.plate_id, names) for c in children[:8])
        more = f", … +{len(children) - 8} more" if len(children) > 8 else ""
        parts.append(
            f"<br><br><b>carries {len(children)} plate"
            f"{'s' if len(children) != 1 else ''} at this age</b><br>{listed}{more}"
        )
    return "".join(parts)


def plot_interactive(
    source: Union[str, Path, RotationModel],
    time: float = 0.0,
    highlight: Optional[set[int]] = None,
    anchor: int = 0,
    show_names: bool = True,
    name_maxlen: int = 24,
):
    """Interactive cladogram as a ``plotly.graph_objects.Figure``.

    Same tree as :func:`rotree.plot_cladogram`, but every node carries a
    hover card explaining the reference-frame hand-offs and quoting the
    .rot file's annotations (citations) with their line numbers.
    """
    try:
        import plotly.graph_objects as go
    except ImportError as err:  # pragma: no cover
        raise ImportError(
            "plotly is required for interactive output: "
            "pip install rotree[interactive]"
        ) from err

    model = source if isinstance(source, RotationModel) else parse_rot(source)
    root = build_tree(model, time=time, anchor=anchor)
    positions = _layout(root)
    names = model.plate_names()
    highlight = highlight or set()
    crossover_plates = {p for p in model.moving_plates if model.crossovers(p)}

    edge_x: list[Optional[float]] = []
    edge_y: list[Optional[float]] = []
    orphan_edge_x: list[Optional[float]] = []
    orphan_edge_y: list[Optional[float]] = []
    for node in root.walk():
        x, y = positions[id(node)]
        for child in node.children:
            cx, cy = positions[id(child)]
            xs, ys = (orphan_edge_x, orphan_edge_y) if child.plate_id < 0 else (edge_x, edge_y)
            xs.extend([x, x, cx, None])
            ys.extend([y, cy, cy, None])

    def node_trace(nodes: list[PlateNode], is_leaf: bool) -> "go.Scatter":
        xs, ys, labels, hovers, ring_w, txt_color = [], [], [], [], [], []
        for node in nodes:
            x, y = positions[id(node)]
            xs.append(x)
            ys.append(y)
            if node.plate_id < 0:
                label = "orphans"
            else:
                label = str(node.plate_id)
                if show_names and node.name:
                    maxlen = name_maxlen if is_leaf else min(name_maxlen, 14)
                    name = node.name
                    if len(name) > maxlen:
                        name = name[: maxlen - 1] + "…"
                    label += f"  {name}"
            labels.append(label)
            hovers.append(_hover_text(node, model, names, time))
            ring_w.append(1.6 if node.plate_id in crossover_plates else 0)
            txt_color.append(
                _ACCENT
                if node.plate_id in highlight
                else (_MUTED if node.plate_id < 0 else _LABEL)
            )
        return go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=labels,
            textposition="middle right" if is_leaf else "top left",
            textfont=dict(size=10, color=txt_color),
            marker=dict(
                size=7,
                color=[_ORPHAN if n.plate_id < 0 else _BRANCH for n in nodes],
                line=dict(width=ring_w, color=_ACCENT),
            ),
            hovertext=hovers,
            hoverinfo="text",
            hoverlabel=dict(
                bgcolor="white",
                bordercolor=_BRANCH,
                font=dict(size=11, color=_LABEL),
                align="left",
            ),
            showlegend=False,
        )

    leaves = [n for n in root.walk() if not n.children]
    internal = [n for n in root.walk() if n.children]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=edge_x, y=edge_y, mode="lines",
            line=dict(color=_BRANCH, width=1.2),
            hoverinfo="skip", showlegend=False,
        )
    )
    if orphan_edge_x:
        fig.add_trace(
            go.Scatter(
                x=orphan_edge_x, y=orphan_edge_y, mode="lines",
                line=dict(color=_ORPHAN, width=1.2, dash="dot"),
                hoverinfo="skip", showlegend=False,
            )
        )
    fig.add_trace(node_trace(internal, is_leaf=False))
    fig.add_trace(node_trace(leaves, is_leaf=True))

    title_path = model.path.name if model.path else "rotation model"
    n_leaves = root.n_leaves
    fig.update_layout(
        title=dict(
            text=(
                f"{title_path} — plate hierarchy at {time:g} Ma"
                "<br><sup>hover a node for its reference-frame hand-offs "
                "and the .rot annotations behind them; "
                "ringed nodes re-parent at another age</sup>"
            ),
            font=dict(size=15, color=_LABEL),
        ),
        template="plotly_white",
        xaxis=dict(
            title="levels from anchor plate",
            range=[-0.5, root.depth + 1.5],
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            visible=False,
            range=[n_leaves - 0.2, -0.8],  # inverted, root at top
        ),
        height=max(500, int(22 * n_leaves) + 160),
        margin=dict(l=40, r=40, t=90, b=50),
        plot_bgcolor="#FBFCFD",
    )
    return fig


def save_interactive(
    source,
    out: Union[str, Path],
    time: float = 0.0,
    include_plotlyjs: Union[bool, str] = True,
    **kwargs,
) -> Path:
    """Write the interactive cladogram to a standalone HTML file.

    ``include_plotlyjs=True`` embeds plotly.js (~3 MB, works offline);
    pass ``"cdn"`` for a small file that needs internet to open.
    """
    fig = plot_interactive(source, time=time, **kwargs)
    out = Path(out)
    fig.write_html(out, include_plotlyjs=include_plotlyjs)
    return out
