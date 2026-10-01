"""Time-axis cladogram: which plate each plate is fixed to, and why it changes.

The tree view (:mod:`rotree.plot`) shows the hierarchy at one age. This
view lays the hierarchy out along geological time instead, in the manner
of a hand-drawn Neoproterozoic cladogram:

- time runs left to right, older on the left;
- each plate is a line over the span the file defines it, coloured by the
  plate it is fixed to over each interval, and drawn in one of three
  weights (a proxy for its size: how many plates it carries);
- at every handoff a connector joins the plate to its new parent and a
  *stop* box, spanning the evidence's own age uncertainty, is drawn in
  the colour of the event that caused it — rifting, collision, suture,
  ophiolite obduction, a paleomagnetic constraint…;
- a handoff with no evidence is drawn as a hollow dashed ``?`` stop and
  listed as a gap, never hidden;
- numbered stops refer to an evidence table under the figure (static
  output) or to hover cards (HTML).

Evidence comes from the ``<stem>.handoff_evidence.csv`` sidecar
(:mod:`rotree.evidence`); without one the same figure is the plain tree
through time, with every handoff marked as a gap.
"""

from __future__ import annotations

import colorsys
import html as _html
import json
import math
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Union

from .evidence import (
    EVENT_COLORS,
    EVENT_TYPES,
    GAP_COLOR,
    AnnotatedHandoff,
    EvidenceReport,
    in_window,
    load_model_and_evidence,
)
from .parser import RotationModel
from .timescale import periods_between

LINE_WIDTHS = {"major": 3.0, "intermediate": 1.8, "minor": 1.0}
_INK = "#1D2A33"
_MUTED = "#6F7C84"
_RULE = "#C9D0D4"
_GOLD = "#B9853A"  # the cursor; the flyover design's gold, darkened for paper


def plate_color(plate: Optional[int]) -> str:
    """One stable colour per plate ID — the same golden-ratio hue step
    GPlates Studio uses, so a parent reads the same in both."""
    if plate is None:
        return "#B8BEC2"
    hue = math.fmod(plate * 137.508, 360.0) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.42, 0.52)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


@dataclass
class Interval:
    older: float
    younger: float
    parent: Optional[int]  # None: the file leaves the plate undefined here


@dataclass
class Row:
    plate: int
    name: str
    intervals: list[Interval]
    line_class: str = "minor"
    group: int = 0
    index: int = 0
    home_parent: Optional[int] = None


@dataclass
class Stop:
    """One numbered handoff drawn on the timeline."""

    number: int
    item: AnnotatedHandoff
    row: Row
    to_row: Optional[Row]
    from_row: Optional[Row]


@dataclass
class TimelineLayout:
    oldest: float
    youngest: float
    rows: list[Row]
    stops: list[Stop]
    report: EvidenceReport
    names: dict[int, str]
    title: str = ""
    omitted: int = 0
    groups: list[tuple[int, int]] = field(default_factory=list)  # (first, last) row index

    def row_of(self, plate: Optional[int]) -> Optional[Row]:
        return next((r for r in self.rows if r.plate == plate), None)


def plate_intervals(model: RotationModel, plate: int, oldest: float, youngest: float) -> list[Interval]:
    """Constant-parent spans of ``plate`` clipped to the window, oldest first."""
    rows = model.lines_for(plate)
    spans: list[Interval] = []
    for younger, older in zip(rows, rows[1:]):
        if older.time - younger.time <= 1e-9:
            continue
        parent = younger.fixed_plate if younger.fixed_plate == older.fixed_plate else None
        o, y = min(older.time, oldest), max(younger.time, youngest)
        if o - y > 1e-9:
            spans.append(Interval(o, y, parent))
    spans.sort(key=lambda s: -s.older)
    merged: list[Interval] = []
    for span in spans:
        if merged and merged[-1].parent == span.parent and abs(merged[-1].younger - span.older) < 1e-9:
            merged[-1].younger = span.younger
        else:
            merged.append(span)
    return merged


def _parent_near(intervals: list[Interval], age: float) -> Optional[int]:
    for span in intervals:
        if span.younger - 1e-9 <= age <= span.older + 1e-9 and span.parent is not None:
            return span.parent
    return None


def build_layout(
    model: RotationModel,
    report: EvidenceReport,
    oldest: float = 1100.0,
    youngest: float = 500.0,
    plates: Optional[Iterable[int]] = None,
    circuit: Optional[int] = None,
    include_parents: bool = True,
    line_classes: Optional[dict[int, str]] = None,
    max_rows: int = 160,
    names: Optional[dict[int, str]] = None,
) -> TimelineLayout:
    """Choose, order and number what the timeline shows.

    Without ``plates`` or ``circuit`` the rows are every plate that hands
    off inside the window, plus the plates it hands off between. With
    ``circuit`` they are that plate, the plates it is fixed to, and every
    plate fixed to it (directly or not) at any age in the window.
    """
    if oldest < youngest:
        oldest, youngest = youngest, oldest
    names = dict(model.plate_names()) if names is None else dict(names)
    for item in report.handoffs:
        for row in item.evidence:
            if row.moving_plate_name and row.moving_plate_id not in names:
                names[row.moving_plate_id] = row.moving_plate_name
    moving = set(model.moving_plates) - {999}
    real = [h for h in report.handoffs if h.handoff.kind == "handoff" and in_window(h, oldest, youngest)]

    intervals = {p: plate_intervals(model, p, oldest, youngest) for p in moving}
    intervals = {p: s for p, s in intervals.items() if s}

    wanted: set[int] = set()
    if circuit is not None:
        wanted.add(circuit)
        changed = True
        while changed:  # everything whose parent is already wanted
            changed = False
            for p, spans in intervals.items():
                if p not in wanted and any(s.parent in wanted for s in spans):
                    wanted.add(p)
                    changed = True
        chain, cursor = set(), circuit  # and the chain above it
        while cursor in intervals and cursor not in chain:
            chain.add(cursor)
            cursor = next((s.parent for s in intervals[cursor] if s.parent is not None), None)
            if cursor is not None:
                wanted.add(cursor)
    if plates is not None:
        wanted |= set(plates)
    if plates is None and circuit is None:
        for item in real:
            wanted.add(item.handoff.moving_plate)
    if include_parents:
        for item in real:
            h = item.handoff
            if h.moving_plate in wanted:
                wanted |= {h.from_fixed, h.to_fixed}
    wanted.discard(None)

    rows: dict[int, Row] = {}
    for plate in wanted:
        spans = intervals.get(plate, [])
        rows[plate] = Row(plate=plate, name=names.get(plate, ""), intervals=spans,
                          home_parent=_parent_near(spans, youngest) if spans else None)
        if spans and rows[plate].home_parent is None:
            rows[plate].home_parent = next(
                (s.parent for s in reversed(spans) if s.parent is not None), None)

    # Depth-first from the roots of the tree at the young end of the window,
    # so a plate sits under the plate it ends up fixed to, like a cladogram.
    children: dict[Optional[int], list[int]] = {}
    for plate, row in rows.items():
        parent = row.home_parent if row.home_parent in rows and row.home_parent != plate else None
        children.setdefault(parent, []).append(plate)
    ordered: list[int] = []
    seen: set[int] = set()

    def visit(plate: int, group: int) -> None:
        if plate in seen:
            return
        seen.add(plate)
        rows[plate].group = group
        ordered.append(plate)
        for child in sorted(children.get(plate, [])):
            visit(child, group)

    for root in sorted(children.get(None, []), key=lambda p: (p != 0, p)):
        visit(root, root)
    for plate in sorted(rows):  # anything caught in a parent cycle
        visit(plate, plate)

    omitted = 0
    if len(ordered) > max_rows:
        omitted = len(ordered) - max_rows
        ordered = ordered[:max_rows]

    # Three weights of line, standing in for size: a plate that carries many
    # others is drawn heavier than a sliver that carries none.
    carried = {p: 0 for p in ordered}
    for plate in ordered:
        cursor, hops = rows[plate].home_parent, 0
        while cursor in carried and hops < 64:
            carried[cursor] += 1
            cursor, hops = rows[cursor].home_parent, hops + 1
    final: list[Row] = []
    for index, plate in enumerate(ordered):
        row = rows[plate]
        row.index = index
        if line_classes and plate in line_classes:
            row.line_class = line_classes[plate]
        elif carried[plate] >= 4 or plate == 0:
            row.line_class = "major"
        elif carried[plate] >= 1:
            row.line_class = "intermediate"
        else:
            row.line_class = "minor"
        final.append(row)

    groups: list[tuple[int, int]] = []
    for row in final:
        if groups and final[groups[-1][0]].group == row.group:
            groups[-1] = (groups[-1][0], row.index)
        else:
            groups.append((row.index, row.index))

    by_plate = {r.plate: r for r in final}
    stops: list[Stop] = []
    shown = [
        h for h in report.handoffs
        if in_window(h, oldest, youngest) and h.handoff.moving_plate in by_plate
        and (h.handoff.kind == "handoff" or h.evidence)
    ]
    shown.sort(key=lambda h: (-h.handoff.age, by_plate[h.handoff.moving_plate].index))
    for number, item in enumerate(shown, start=1):
        h = item.handoff
        stops.append(Stop(number, item, by_plate[h.moving_plate],
                          by_plate.get(h.to_fixed), by_plate.get(h.from_fixed)))

    title = model.path.name if model.path else "rotation model"
    return TimelineLayout(oldest, youngest, final, stops, report, names, title, omitted, groups)


def _plate_label(pid: Optional[int], names: dict[int, str], width: int = 26) -> str:
    if pid is None:
        return "—"
    name = " ".join(names.get(pid, "").split())
    if len(name) > width:
        name = name[: width - 1] + "…"
    return f"{pid} {name}".strip()


def _stop_span(stop: Stop, width: float) -> tuple[float, float]:
    """Older and younger x of a stop box: the evidence's own uncertainty
    when it has one, otherwise a fixed width centred on the handoff."""
    spans = [r.span() for r in stop.item.evidence if r.span() is not None]
    age = stop.item.handoff.age
    if spans:
        older = max(s[0] for s in spans)
        younger = min(s[1] for s in spans)
        if older - younger < width:
            mid = (older + younger) / 2
            older, younger = mid + width / 2, mid - width / 2
        return older, younger
    return age + width / 2, age - width / 2


def _stop_color(stop: Stop) -> str:
    if not stop.item.evidence:
        return GAP_COLOR
    return stop.item.evidence[0].color


def _evidence_lines(stop: Stop, names: dict[int, str]) -> list[str]:
    h = stop.item.handoff
    if h.kind == "appearance":
        head = f"[{stop.number}] {h.age:g} Ma · {_plate_label(h.moving_plate, names)} appears on {h.to_fixed}"
    else:
        head = (f"[{stop.number}] {h.age:g} Ma · {_plate_label(h.moving_plate, names)}: "
                f"{h.from_fixed} → {h.to_fixed}")
    if not stop.item.evidence:
        return [head + " · GAP — no evidence recorded"]
    out = [head]
    for row in stop.item.evidence:
        bits = [f"{row.title} ({row.event_type.replace('_', ' ')})"]
        if row.age_text:
            bits.append(row.age_text)
        if row.evidence:
            bits.append(row.evidence)
        bits.append(f"ref: {row.reference or 'none given'}")
        bits.append(f"confidence {row.confidence}")
        out.append("      " + " · ".join(bits))
    return out


def plot_timeline(
    source: Union[str, Path, RotationModel],
    oldest: float = 1100.0,
    youngest: float = 500.0,
    evidence=None,
    plates: Optional[Iterable[int]] = None,
    circuit: Optional[int] = None,
    time: Optional[float] = None,
    show_table: bool = True,
    show_labels: bool = True,
    line_classes: Optional[dict[int, str]] = None,
    tolerance: float = 0.5,
    title: Optional[str] = None,
    width: float = 15.0,
):
    """Draw the time-axis cladogram with matplotlib; returns the Figure.

    ``evidence`` is a sidecar path, CSV text or list of dicts; ``None``
    looks for ``<stem>.handoff_evidence.csv`` beside the rotation file and
    ``False`` ignores any sidecar. ``time`` draws a cursor at that age.
    """
    import matplotlib

    if not matplotlib.get_backend():
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyBboxPatch, Patch

    model, report = load_model_and_evidence(source, evidence, tolerance)
    layout = build_layout(model, report, oldest, youngest, plates, circuit,
                          line_classes=line_classes)
    oldest, youngest = layout.oldest, layout.youngest
    span = oldest - youngest
    n = max(1, len(layout.rows))

    table: list[str] = []
    if show_table:
        for stop in layout.stops:
            for line in _evidence_lines(stop, layout.names):
                table.extend(textwrap.wrap(line, 175, subsequent_indent="        ") or [""])
        if report.unmatched:
            table.append("")
            table.append("Sidecar rows that match no handoff in the rotation file:")
            for row, reason in report.unmatched:
                table.extend(textwrap.wrap(f"  row {row.row_number}: {row.title} — {reason}", 175,
                                           subsequent_indent="        "))
    # Everything is placed in inches from the top, so a tall model and a
    # short one keep the same margins: title, legend, top axis, rows, the
    # period scale, and then the evidence table.
    main_h = 0.24 * n + 0.3
    head_h = 1.05
    table_h = 0.1 * len(table) + (0.3 if table else 0)
    total = head_h + main_h + 0.9 + table_h
    fig = plt.figure(figsize=(width, total))
    fig.set_facecolor("white")
    inch = lambda v: 1 - v / total  # noqa: E731
    ax = fig.add_axes([0.2, inch(head_h + main_h), 0.78, main_h / total])
    scale_ax = fig.add_axes([0.2, inch(head_h + main_h + 0.32), 0.78, 0.22 / total], sharex=ax)
    ax.set_xlim(oldest, youngest)
    ax.set_ylim(n - 0.4, -0.8)
    ax.set_facecolor("white")
    for spine in ("left", "right", "top", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(axis="x", labelsize=7.5, colors=_MUTED, top=True, labeltop=True,
                   bottom=False, labelbottom=False, length=3)
    ax.grid(axis="x", color="#EEF1F3", lw=0.6, zorder=0)

    # Row labels in the gutter, heavier for heavier lines.
    ax.set_yticks([r.index for r in layout.rows])
    ax.set_yticklabels([_plate_label(r.plate, layout.names, 30) for r in layout.rows], fontsize=7)
    for tick, row in zip(ax.get_yticklabels(), layout.rows):
        tick.set_fontweight("bold" if row.line_class == "major" else "normal")
        tick.set_color(_INK)
    ax.tick_params(axis="y", length=0, pad=6)

    for first, last in layout.groups[1:]:
        ax.axhline(first - 0.5, color=_RULE, lw=0.8, ls=(0, (6, 4)), zorder=1)

    for row in layout.rows:
        lw = LINE_WIDTHS[row.line_class]
        for s in row.intervals:
            if s.parent is None:
                ax.hlines(row.index, s.younger, s.older, color="#AEB6BB", lw=0.9, ls=":", zorder=2)
                continue
            ax.hlines(row.index, s.younger, s.older, color=plate_color(s.parent), lw=lw,
                      zorder=2, capstyle="butt")
            if show_labels and (s.older - s.younger) > span * 0.07:
                ax.text(s.older - span * 0.004, row.index - 0.16, f"on {s.parent}",
                        fontsize=5.2, color=_MUTED, ha="left", va="bottom", zorder=3)

    box_w = span * 0.012
    for stop in layout.stops:
        h = stop.item.handoff
        y = stop.row.index
        color = _stop_color(stop)
        if stop.to_row is not None and h.kind == "handoff":
            ax.vlines(h.age, min(y, stop.to_row.index), max(y, stop.to_row.index),
                      color=plate_color(h.to_fixed), lw=0.8, zorder=2.5)
        if stop.from_row is not None:
            ax.vlines(h.age, min(y, stop.from_row.index), max(y, stop.from_row.index),
                      color=plate_color(h.from_fixed), lw=0.6, ls=(0, (2, 2)), alpha=0.7, zorder=2.4)
        older, younger = _stop_span(stop, box_w)
        gap = stop.item.is_gap
        box = FancyBboxPatch(
            (younger, y - 0.3), older - younger, 0.6,
            boxstyle="round,pad=0,rounding_size=0.18",
            mutation_aspect=1 / max(1e-9, span / (n * 40)),
            facecolor="white" if gap else color, edgecolor=color,
            lw=0.9, ls=(0, (2, 1.5)) if gap else "-", alpha=1.0 if gap else 0.88, zorder=4)
        ax.add_patch(box)
        # The model's own handoff age, which the evidence box may not bracket.
        ax.vlines(h.age, y - 0.36, y + 0.36, color=_INK, lw=0.7, zorder=5)
        if show_labels:
            event = stop.item.evidence[0].title if not gap else ""
            if len(event) > 42:
                event = event[:41] + "…"
            label = f"{stop.number}?" if gap else f"{stop.number} {event}"
            # Near the young edge a label would run off the plot, so it goes on
            # the older side of its stop instead.
            late = younger - youngest < span * 0.22
            ax.text(older + span * 0.003 if late else younger - span * 0.003, y + 0.02, label,
                    fontsize=5.8, color=GAP_COLOR if gap else _INK,
                    ha="right" if late else "left", va="center", zorder=6,
                    fontstyle="italic" if gap else "normal",
                    bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none", alpha=0.75))
        if h.kind == "appearance":
            ax.plot([h.age], [y], "o", ms=3.2, mfc="white", mec=_INK, mew=0.7, zorder=6)

    for row in layout.rows:  # plates that begin inside the window
        first = row.intervals[0] if row.intervals else None
        if first and first.older < oldest - 1e-9:
            ax.plot([first.older], [row.index], "o", ms=3.0, mfc="white", mec=_MUTED, mew=0.7, zorder=5)

    if time is not None and youngest <= time <= oldest:
        for a in (ax, scale_ax):
            a.axvline(time, color=_GOLD, lw=1.4, zorder=7)
        ax.text(time, -0.75, f" {time:g} Ma", color=_GOLD, fontsize=7.5, va="bottom", ha="left")

    scale_ax.set_ylim(0, 1)
    scale_ax.axis("off")
    for p in periods_between(oldest, youngest):
        scale_ax.axvspan(p.younger, p.older, color=p.color, lw=0)
        scale_ax.axvline(p.older, color="white", lw=0.8)
        if (p.older - p.younger) > span * 0.05:
            scale_ax.text((p.older + p.younger) / 2, 0.5, p.name, ha="center", va="center",
                          fontsize=7, color=_INK)
    scale_ax.text(0.5, -0.9, "Age (Ma) · older → younger", transform=scale_ax.transAxes,
                  ha="center", va="top", fontsize=7.5, color=_MUTED)

    present = []
    for stop in layout.stops:
        for row in stop.item.evidence:
            if row.event_type not in present:
                present.append(row.event_type)
    handles = [Patch(facecolor=EVENT_COLORS[t], edgecolor="none", label=t.replace("_", " "))
               for t in EVENT_TYPES if t in present]
    if any(s.item.is_gap for s in layout.stops):
        handles.append(Patch(facecolor="white", edgecolor=GAP_COLOR, ls="--", label="gap: no evidence"))
    handles += [Line2D([], [], color=_MUTED, lw=w, label=f"{c} plate") for c, w in LINE_WIDTHS.items()]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.2, inch(0.5)),
               ncol=min(8, len(handles)), frameon=False, fontsize=7, handlelength=1.6,
               columnspacing=1.2)
    heading = title or f"{layout.title} — fixed-plate handoffs, {oldest:g}–{youngest:g} Ma"
    sidecar = report.sidecar.name if report.sidecar else "no evidence sidecar"
    fig.text(0.01, inch(0.1), heading, fontsize=11, color=_INK, va="top",
             family="serif")
    fig.text(0.01, inch(0.36), f"{sidecar} · {report.summary(oldest, youngest)}"
             + (f" · {layout.omitted} row(s) not drawn" if layout.omitted else ""),
             fontsize=6.8, color=_MUTED, va="top")

    if table:
        fig.text(0.02, inch(head_h + main_h + 0.95), "\n".join(table), fontsize=5.6, color=_INK,
                 va="top", ha="left", family="monospace", linespacing=1.25)
    fig.layout = layout
    return fig


def save_timeline(source, out: Union[str, Path], **kwargs) -> Path:
    """Write the cladogram to ``out``: ``.html`` is interactive, anything
    else (``.svg``, ``.pdf``, ``.png``) is a static matplotlib figure."""
    out = Path(out)
    if out.suffix.lower() in (".html", ".htm"):
        return save_timeline_html(source, out, **kwargs)
    import matplotlib.pyplot as plt

    # Editable text in vector output: a figure is usually finished by hand.
    with plt.rc_context({"svg.fonttype": "none", "pdf.fonttype": 42}):
        fig = plot_timeline(source, **kwargs)
        fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)
    return out


# --------------------------------------------------------------------------
# Interactive HTML: a hand-built SVG with hover cards, a time cursor that
# can be scrubbed, and click-a-stop-to-jump. No plotly: the page is one
# self-contained file with nothing to fetch.

def _esc(text) -> str:
    return _html.escape(str(text), quote=True)


def timeline_html(
    source: Union[str, Path, RotationModel],
    oldest: float = 1100.0,
    youngest: float = 500.0,
    evidence=None,
    plates: Optional[Iterable[int]] = None,
    circuit: Optional[int] = None,
    time: Optional[float] = None,
    line_classes: Optional[dict[int, str]] = None,
    tolerance: float = 0.5,
    title: Optional[str] = None,
    **_ignored,
) -> str:
    model, report = load_model_and_evidence(source, evidence, tolerance)
    layout = build_layout(model, report, oldest, youngest, plates, circuit, line_classes=line_classes)
    oldest, youngest = layout.oldest, layout.youngest
    span = oldest - youngest
    gutter, right, top, row_h = 280, 30, 44, 22
    width = 1400
    plot_w = width - gutter - right
    n = max(1, len(layout.rows))
    height = top + n * row_h + 58

    def x(age: float) -> float:
        return gutter + (oldest - age) / span * plot_w

    def y(index: int) -> float:
        return top + index * row_h + row_h / 2

    parts = [f'<svg id="chart" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Fixed-plate handoffs through time">']
    step = 50 if span > 300 else 20 if span > 100 else 10
    age = math.floor(oldest / step) * step
    while age >= youngest - 1e-9:
        parts.append(f'<line class="grid" x1="{x(age):.1f}" x2="{x(age):.1f}" y1="{top - 6}" '
                     f'y2="{top + n * row_h}"/><text class="tick" x="{x(age):.1f}" y="{top - 12}">'
                     f'{age:g}</text>')
        age -= step
    for first, _ in layout.groups[1:]:
        yy = top + first * row_h
        parts.append(f'<line class="group" x1="8" x2="{width - right}" y1="{yy}" y2="{yy}"/>')

    rows_json = []
    for row in layout.rows:
        yy = y(row.index)
        parts.append(f'<g class="row" data-plate="{row.plate}">'
                     f'<rect class="rowhit" x="0" y="{yy - row_h / 2}" width="{width}" height="{row_h}"/>'
                     f'<text class="label {row.line_class}" x="12" y="{yy + 4}">'
                     f'{_esc(_plate_label(row.plate, layout.names, 30))}</text>'
                     f'<text class="parentnow" data-plate="{row.plate}" x="{gutter - 8}" y="{yy + 4}"></text>')
        for s in row.intervals:
            if s.parent is None:
                parts.append(f'<line class="undefined" x1="{x(s.older):.1f}" x2="{x(s.younger):.1f}" '
                             f'y1="{yy}" y2="{yy}"/>')
            else:
                parts.append(f'<line class="seg" stroke="{plate_color(s.parent)}" '
                             f'stroke-width="{LINE_WIDTHS[row.line_class] * 1.3:.1f}" '
                             f'x1="{x(s.older):.1f}" x2="{x(s.younger):.1f}" y1="{yy}" y2="{yy}">'
                             f'<title>{row.plate} fixed to {s.parent} '
                             f'({_esc(layout.names.get(s.parent, ""))}), {s.older:g}–{s.younger:g} Ma</title></line>')
        parts.append("</g>")
        rows_json.append({"plate": row.plate, "spans": [[s.older, s.younger, s.parent] for s in row.intervals]})

    stops_json = []
    box_w = span * 0.012
    for stop in layout.stops:
        h = stop.item.handoff
        yy = y(stop.row.index)
        color = _stop_color(stop)
        older, younger = _stop_span(stop, box_w)
        g = [f'<g class="stop{" gap" if stop.item.is_gap else ""}" data-i="{stop.number - 1}" '
             f'tabindex="0" role="button" aria-label="Handoff {stop.number} at {h.age:g} Ma">']
        if stop.to_row is not None and h.kind == "handoff":
            g.append(f'<line class="join" stroke="{plate_color(h.to_fixed)}" x1="{x(h.age):.1f}" '
                     f'x2="{x(h.age):.1f}" y1="{yy}" y2="{y(stop.to_row.index)}"/>')
        if stop.from_row is not None:
            g.append(f'<line class="split" stroke="{plate_color(h.from_fixed)}" x1="{x(h.age):.1f}" '
                     f'x2="{x(h.age):.1f}" y1="{yy}" y2="{y(stop.from_row.index)}"/>')
        g.append(f'<rect class="box" x="{x(older):.1f}" y="{yy - 7}" width="{max(6, x(younger) - x(older)):.1f}" '
                 f'height="14" rx="4" fill="{color if not stop.item.is_gap else "none"}" stroke="{color}"/>')
        g.append(f'<line class="age" x1="{x(h.age):.1f}" x2="{x(h.age):.1f}" y1="{yy - 9}" y2="{yy + 9}"/>')
        label = f"{stop.number}?" if stop.item.is_gap else f"{stop.number} {stop.item.evidence[0].title}"
        if len(label) > 46:
            label = label[:45] + "…"
        if younger - youngest < span * 0.22:  # keep late labels inside the chart
            g.append(f'<text class="stoplabel" text-anchor="end" x="{x(older) - 4:.1f}" y="{yy + 4}">{_esc(label)}</text>')
        else:
            g.append(f'<text class="stoplabel" x="{max(x(younger), x(older) + 6) + 4:.1f}" y="{yy + 4}">{_esc(label)}</text>')
        g.append("</g>")
        parts.extend(g)
        stops_json.append({
            "n": stop.number, "age": h.age, "kind": h.kind, "plate": h.moving_plate,
            "plateLabel": _plate_label(h.moving_plate, layout.names, 40),
            "from": h.from_fixed, "fromLabel": _plate_label(h.from_fixed, layout.names, 40) if h.from_fixed is not None else "",
            "to": h.to_fixed, "toLabel": _plate_label(h.to_fixed, layout.names, 40),
            "gap": stop.item.is_gap,
            "lines": [l.line_number for l in (h.older_line, h.younger_line) if l is not None],
            "evidence": [{
                "type": r.event_type, "label": r.title, "evidence": r.evidence, "age": r.age_text,
                "reference": r.reference, "confidence": r.confidence, "color": r.color,
            } for r in stop.item.evidence],
        })

    ys = top + n * row_h + 8
    for p in periods_between(oldest, youngest):
        parts.append(f'<rect class="period" x="{x(p.older):.1f}" y="{ys}" width="{x(p.younger) - x(p.older):.1f}" '
                     f'height="18" fill="{p.color}"><title>{p.name} {p.older:g}–{p.younger:g} Ma</title></rect>')
        if x(p.younger) - x(p.older) > 60:
            parts.append(f'<text class="periodname" x="{(x(p.older) + x(p.younger)) / 2:.1f}" y="{ys + 13}">{p.name}</text>')
    parts.append(f'<text class="axisname" x="{gutter + plot_w / 2}" y="{ys + 40}">Age (Ma) · older → younger</text>')
    parts.append(f'<line id="cursor" x1="0" x2="0" y1="{top - 6}" y2="{ys + 18}"/>')
    parts.append("</svg>")

    present = [t for t in EVENT_TYPES if any(r.event_type == t for s in layout.stops for r in s.item.evidence)]
    legend = "".join(f'<span><i style="background:{EVENT_COLORS[t]}"></i>{t.replace("_", " ")}</span>' for t in present)
    if any(s.item.is_gap for s in layout.stops):
        legend += f'<span><i class="gapkey" style="border-color:{GAP_COLOR}"></i>gap · no evidence</span>'
    heading = title or f"{layout.title}"
    sidecar = report.sidecar.name if report.sidecar else "no evidence sidecar"
    unmatched = "".join(
        f"<li>row {row.row_number}: <b>{_esc(row.title)}</b> — {_esc(reason)}</li>"
        for row, reason in report.unmatched)
    warnings = "".join(f"<li>{_esc(w)}</li>" for w in report.warnings + report.issues)
    data = json.dumps({"oldest": oldest, "youngest": youngest, "gutter": gutter, "plotW": plot_w,
                       "rows": rows_json, "stops": stops_json,
                       "time": time if time is not None else oldest})
    return _PAGE.format(
        title=_esc(heading), oldest=f"{oldest:g}", youngest=f"{youngest:g}", svg="".join(parts),
        legend=legend, sidecar=_esc(sidecar), summary=_esc(report.summary(oldest, youngest)),
        unmatched=f"<h2>Rows that match no handoff</h2><ul>{unmatched}</ul>" if unmatched else "",
        warnings=f"<h2>Warnings</h2><ul>{warnings}</ul>" if warnings else "",
        data=data.replace("</", "<\\/"),
    )


def save_timeline_html(source, out: Union[str, Path], **kwargs) -> Path:
    out = Path(out)
    out.write_text(timeline_html(source, **kwargs), encoding="utf-8")
    return out


_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — handoffs through time</title>
<style>
:root{{--bg:#091117;--panel:#101c23;--ink:#f2eee4;--muted:#a5afb1;--faint:#526068;--gold:#e7c393;
--rule:rgba(255,255,255,.14);--grid:rgba(255,255,255,.06);--card:#06131de6;color-scheme:dark}}
@media (prefers-color-scheme: light){{:root{{--bg:#f4f1ea;--panel:#fbfaf6;--ink:#13212a;--muted:#5d6a70;
--faint:#9aa4a8;--gold:#9a6b2f;--rule:rgba(9,17,23,.16);--grid:rgba(9,17,23,.06);--card:#fbfaf6f2;color-scheme:light}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:13px/1.5 Arial,Helvetica,sans-serif}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;padding:26px 32px 12px;flex-wrap:wrap}}
.wordmark{{font:22px Georgia,serif;letter-spacing:.2em;text-transform:uppercase}}
.wordmark span{{display:block;font:9px Arial;letter-spacing:.26em;margin-top:8px;color:var(--muted)}}
.era{{font:30px Georgia,serif;text-align:center;font-variant-numeric:tabular-nums}}
.era span{{display:block;font:8px Arial;letter-spacing:.22em;margin-top:4px;color:var(--muted)}}
.context{{padding:0 32px;font-size:9px;letter-spacing:.15em;color:var(--muted);text-transform:uppercase}}
.context b{{color:var(--ink);font-weight:normal}}.dot{{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--gold);margin-right:7px}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;padding:12px 32px;font-size:11px;color:var(--muted)}}
.legend i{{display:inline-block;width:14px;height:9px;border-radius:2px;margin-right:6px;vertical-align:-1px}}
.legend .gapkey{{border:1px dashed;background:none}}
.transport{{display:flex;align-items:center;gap:16px;padding:6px 32px 10px;border-bottom:1px solid var(--rule)}}
.transport button{{border:1px solid var(--rule);background:transparent;color:var(--ink);border-radius:3px;padding:6px 10px;font-size:11px;cursor:pointer}}
.transport button:focus-visible,.stop:focus-visible{{outline:2px solid var(--gold);outline-offset:3px}}
.transport input{{flex:1;accent-color:var(--gold)}}.time{{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}}
main{{padding:8px 16px 0}}svg{{width:100%;height:auto;display:block}}
.grid{{stroke:var(--grid)}}.tick{{fill:var(--muted);font-size:10px;text-anchor:middle}}
.group{{stroke:var(--rule);stroke-dasharray:6 4}}.rowhit{{fill:transparent}}.row:hover .rowhit{{fill:var(--grid)}}
.label{{fill:var(--ink);font-size:11px}}.label.major{{font-weight:bold}}.label.minor{{fill:var(--muted)}}
.parentnow{{fill:var(--gold);font-size:10px;text-anchor:end}}
.seg{{stroke-linecap:butt}}.undefined{{stroke:var(--faint);stroke-dasharray:2 3}}
.join{{stroke-width:1.2}}.split{{stroke-width:1;stroke-dasharray:3 3;opacity:.6}}
.box{{stroke-width:1.2;opacity:.9}}.gap .box{{stroke-dasharray:3 2}}.age{{stroke:var(--ink);stroke-width:1}}
.stop{{cursor:pointer}}.stop:hover .box,.stop.on .box{{stroke:var(--gold);stroke-width:2.4;opacity:1}}
.stoplabel{{fill:var(--ink);font-size:10px}}.gap .stoplabel{{fill:#e0705f;font-style:italic}}
.period{{opacity:.9}}.periodname{{fill:#13212a;font-size:10px;text-anchor:middle}}
.axisname{{fill:var(--muted);font-size:11px;text-anchor:middle}}#cursor{{stroke:var(--gold);stroke-width:1.6}}
#card{{position:fixed;pointer-events:none;max-width:420px;background:var(--card);border:1px solid var(--rule);
border-radius:3px;padding:12px 14px;font-size:12px;box-shadow:0 8px 30px rgba(0,0,0,.35);display:none;z-index:5}}
#card h3{{font:17px Georgia,serif;color:var(--gold);margin:0 0 4px}}#card .over{{font-size:9px;letter-spacing:.2em;color:var(--muted);text-transform:uppercase}}
#card .ev{{border-top:1px solid var(--rule);margin-top:8px;padding-top:8px}}#card small{{display:block;color:var(--muted)}}
#card .gapnote{{color:#e0705f}}
section.notes{{padding:10px 32px 40px;max-width:1100px;color:var(--muted)}}section.notes h2{{font:18px Georgia,serif;color:var(--gold);margin:22px 0 8px}}
</style></head><body>
<header><div class="wordmark">rotree<span>handoffs through time</span></div>
<div class="era"><span id="age">{oldest}</span><span>MILLION YEARS AGO · <b id="period"></b></span></div>
<div class="time">{oldest}–{youngest} Ma</div></header>
<div class="context"><span class="dot"></span><b>{title}</b> · {sidecar} · {summary}</div>
<div class="legend">{legend}</div>
<div class="transport"><button id="prev" aria-label="Previous handoff">◀ Previous</button>
<button id="next" aria-label="Next handoff">Next ▶</button><span class="time">{oldest} Ma</span>
<input id="scrub" type="range" min="{youngest}" max="{oldest}" step="0.5" aria-label="Geological time, older on the left">
<span class="time">{youngest} Ma</span></div>
<main>{svg}</main>
<div id="card" role="tooltip"></div>
<section class="notes">{unmatched}{warnings}
<p>Click a stop to move the time cursor to its handoff; hover it for the evidence. Stops span the evidence's
own age uncertainty; the thin vertical tick is the age at which the rotation file changes the fixed plate.
A hollow dashed stop is a handoff with no evidence recorded: a gap, not an absence of a handoff.</p></section>
<script>
const D={data};
const PERIODS=[["Stenian",1200,1000],["Tonian",1000,720],["Cryogenian",720,635],["Ediacaran",635,538.8],["Cambrian",538.8,486.85],["Ordovician",486.85,443.1],["Silurian",443.1,419.62],["Devonian",419.62,358.86],["Carboniferous",358.86,298.9],["Permian",298.9,251.902],["Triassic",251.902,201.4],["Jurassic",201.4,143.1],["Cretaceous",143.1,66],["Paleogene",66,23.04],["Neogene",23.04,2.58],["Quaternary",2.58,0]];
const scrub=document.getElementById('scrub'),cursor=document.getElementById('cursor'),card=document.getElementById('card');
const svg=document.getElementById('chart'),vb=svg.viewBox.baseVal;
const X=a=>D.gutter+(D.oldest-a)/(D.oldest-D.youngest)*D.plotW;
function esc(s){{return String(s??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
function setTime(a){{a=Math.max(D.youngest,Math.min(D.oldest,a));scrub.value=a;cursor.setAttribute('x1',X(a));cursor.setAttribute('x2',X(a));
document.getElementById('age').textContent=Math.round(a).toLocaleString();
const p=PERIODS.find(p=>a<=p[1]&&a>=p[2]);document.getElementById('period').textContent=p?p[0].toUpperCase():'';
for(const r of D.rows){{const s=r.spans.find(s=>a<=s[0]+1e-9&&a>=s[1]-1e-9);const el=document.querySelector('.parentnow[data-plate="'+r.plate+'"]');
if(el)el.textContent=s?(s[2]===null?'undefined':'on '+s[2]):''}}
document.querySelectorAll('.stop').forEach(g=>g.classList.toggle('on',Math.abs(D.stops[+g.dataset.i].age-a)<1e-6))}}
function show(i,ev){{const s=D.stops[i];let h='<div class="over">Handoff '+s.n+' · '+s.age+' Ma'+(s.lines.length?' · .rot line '+s.lines.join(', '):'')+'</div>';
h+='<h3>'+esc(s.plateLabel)+'</h3>';h+=s.kind==='appearance'?'<small>first defined, fixed to '+esc(s.toLabel)+'</small>':'<small>fixed to '+esc(s.fromLabel)+' → '+esc(s.toLabel)+' (older → younger)</small>';
if(s.gap)h+='<div class="ev gapnote">No evidence recorded for this handoff. It is a gap in the evidence, not in the model.</div>';
for(const e of s.evidence)h+='<div class="ev"><b style="color:'+e.color+'">'+esc(e.label)+'</b> <small>'+esc(e.type.replace(/_/g,' '))+(e.age?' · '+esc(e.age):'')+' · confidence '+esc(e.confidence)+'</small>'+(e.evidence?'<div>'+esc(e.evidence)+'</div>':'')+'<small>'+(e.reference?esc(e.reference):'no reference given')+'</small></div>';
card.innerHTML=h;card.style.display='block';move(ev)}}
function move(ev){{if(!ev||ev.clientX===undefined)return;const w=card.offsetWidth,hh=card.offsetHeight;let x=ev.clientX+16,y=ev.clientY+16;
if(x+w>innerWidth-8)x=ev.clientX-w-16;if(y+hh>innerHeight-8)y=Math.max(8,ev.clientY-hh-16);card.style.left=x+'px';card.style.top=y+'px'}}
document.querySelectorAll('.stop').forEach(g=>{{const i=+g.dataset.i;g.addEventListener('mouseenter',e=>show(i,e));g.addEventListener('mousemove',move);
g.addEventListener('mouseleave',()=>card.style.display='none');g.addEventListener('click',()=>setTime(D.stops[i].age));
g.addEventListener('focus',()=>{{const r=g.getBoundingClientRect();show(i,{{clientX:r.right,clientY:r.top}})}});g.addEventListener('blur',()=>card.style.display='none');
g.addEventListener('keydown',e=>{{if(e.key==='Enter'||e.key===' '){{e.preventDefault();setTime(D.stops[i].age)}}}})}});
scrub.addEventListener('input',()=>setTime(+scrub.value));
function jump(dir){{const a=+scrub.value;const ages=[...new Set(D.stops.map(s=>s.age))].sort((p,q)=>q-p);
const t=dir>0?ages.find(x=>x<a-1e-6):[...ages].reverse().find(x=>x>a+1e-6);if(t!==undefined)setTime(t)}}
document.getElementById('next').onclick=()=>jump(1);document.getElementById('prev').onclick=()=>jump(-1);
setTime(D.time);
</script></body></html>
"""
