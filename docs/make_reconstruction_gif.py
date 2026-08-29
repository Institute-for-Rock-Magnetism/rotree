"""Build the README demo GIF: a Mollweide global reconstruction playing
forward through the Phanerozoic above a time-axis cladogram that reveals
itself in step with the map.

Top row: continental polygons reconstructed with pygplates at the current
age, colored by major plate circuit — the nearest anchor plate (Laurentia,
Gondwana, Siberia, ...) up the rotation-tree parent chain at that age, so
a reference-frame hand-off (crossover) shows up as a color change.
Bottom row: every land-carrying plate as a lineage line against a shared
time axis, colored by the same circuit scheme through time. Lineages are
drawn only up to the current age, so the cladogram grows continuously as
the animation advances instead of re-laying-out each frame; orange ticks
mark hand-offs, and a cursor ties both rows to the same instant.

Requires: pygplates, cartopy, numpy, pillow (docs-only, not rotree deps).
Default paths point at local copies of the Torsvik/Doubrovine 2012-2016
hybrid frame (CEED) and the CEED6 land polygons.

Usage::

    python docs/make_reconstruction_gif.py [ROT_FILE] [POLYGONS] [OUT_GIF]
"""

from __future__ import annotations

import sys
from bisect import bisect_right
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import pygplates
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon as MplPolygon
from PIL import Image

from rotree import parse_rot

ROT = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/Users/yimingzhang/Github/Gallo_etal_2023_APWP_construction/data/"
    "Torsvik_Cocks_HybridRotationFile.rot"
)
POLY = Path(
    sys.argv[2]
    if len(sys.argv) > 2
    else "/Users/yimingzhang/Github/Rodinia_Model/Torsvik-extended/plates/"
    "CEED6_LAND.shp"
)
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else "docs/rotree_reconstruction.gif")

T_START, T_STEP = 540, 4  # Ma; forward toward the present
FRAME_MS = 90
END_HOLD_MS = 2500

# major plate circuits: nearest of these up the parent chain sets the color
CIRCUITS = {
    101: ("Laurentia", "#4E79A7"),
    201: ("S America", "#F28E2B"),
    301: ("Eurasia", "#59A14F"),
    302: ("Baltica", "#8CD17D"),
    401: ("Siberia", "#E15759"),
    501: ("India", "#B07AA1"),
    601: ("S China", "#EDC948"),
    701: ("Gondwana/Africa", "#9C755F"),
    801: ("Australia", "#FF9DA7"),
    802: ("Antarctica", "#76B7B2"),
    901: ("Pacific", "#A0CBE8"),
}
UNGROUPED = "#B9C2CA"
OCEAN = "#DCEAF2"
CURSOR = "#C1441E"
INK = "#26313B"
MUTED = "#7C8894"
ERAS = [(541, 252, "Paleozoic"), (252, 66, "Mesozoic"), (66, 0, "Cenozoic")]


class ParentIndex:
    """Fast parent-at-age lookups over a parsed rotation model."""

    def __init__(self, model):
        self.table = {}
        for pid in model.moving_plates:
            rows = model.lines_for(pid)
            self.table[pid] = (
                [r.time for r in rows],
                [r.fixed_plate for r in rows],
            )

    def parent(self, pid, t):
        entry = self.table.get(pid)
        if entry is None:
            return None
        times, fixed = entry
        if t < times[0] - 1e-9 or t > times[-1] + 1e-9:
            return None
        return fixed[max(0, bisect_right(times, t + 1e-9) - 1)]

    def circuit_color(self, pid, t):
        """Color of the nearest circuit anchor up the chain at age t."""
        seen = set()
        cur = pid
        while cur is not None and cur not in seen:
            if cur in CIRCUITS:
                return CIRCUITS[cur][1]
            seen.add(cur)
            cur = self.parent(cur, t)
        return UNGROUPED

    def span(self, pid):
        times = self.table[pid][0]
        return times[-1], times[0]  # oldest, youngest


def lineage_runs(index, pids, grid_step=2.0):
    """Per plate: contiguous same-color runs [(t_old, t_young, color)]."""
    runs = {}
    for pid in pids:
        oldest, youngest = index.span(pid)
        ts = np.arange(oldest, youngest - 1e-6, -grid_step).tolist() + [youngest]
        out = []
        for t in ts:
            c = index.circuit_color(pid, t)
            if out and out[-1][2] == c:
                out[-1][1] = t
            else:
                out.append([t, t, c])
        runs[pid] = [(a, b, c) for a, b, c in out]
    return runs


def row_order(index, model, pids, group_gap=3.0):
    """Stable row positions: grouped by circuit at youngest age (with a
    blank gap between circuits), cascading in by age of first appearance.
    Returns (pid -> y, group blocks [(name, color, y_lo, y_hi)], extent)."""

    palette = [(n, c) for n, c in CIRCUITS.values()] + [("other", UNGROUPED)]
    order = [c for _, c in palette]

    def key(pid):
        oldest, youngest = index.span(pid)
        color = index.circuit_color(pid, youngest)
        return (order.index(color), -oldest, pid)

    rows, blocks, y, prev_group = {}, [], 0.0, None
    for pid in sorted(pids, key=key):
        group = key(pid)[0]
        if prev_group is None or group != prev_group:
            if prev_group is not None:
                y += group_gap
            name, color = palette[group]
            blocks.append([name, color, y, y])
        rows[pid] = y
        blocks[-1][3] = y
        y += 1.0
        prev_group = group
    return rows, [tuple(b) for b in blocks], y


def draw_map(ax, reconstructed, wrapper, index, time):
    ax.set_global()
    ax.set_facecolor(OCEAN)
    moll, geo = ax.projection, ccrs.PlateCarree()
    for rec in reconstructed:
        pid = rec.get_feature().get_reconstruction_plate_id()
        color = index.circuit_color(pid, time)
        geom = rec.get_reconstructed_geometry()
        if not isinstance(geom, pygplates.PolygonOnSphere):
            continue
        for wrapped in wrapper.wrap(geom, 2.0):
            pts = np.array(
                [
                    (p.get_longitude(), p.get_latitude())
                    for p in wrapped.get_exterior_points()
                ]
            )
            if len(pts) < 3:
                continue
            xy = moll.transform_points(geo, pts[:, 0], pts[:, 1])[:, :2]
            if not np.isfinite(xy).all():
                continue
            ax.add_patch(
                MplPolygon(
                    xy,
                    closed=True,
                    facecolor=color,
                    edgecolor="white",
                    linewidth=0.15,
                    zorder=2,
                )
            )


def draw_timeline(ax, rows, blocks, runs, handoffs, time, extent, lw):
    ax.set_facecolor("#FBFCFD")
    headroom = extent * 1.08 + 2
    for old, young, label in ERAS:
        ax.axvspan(
            old,
            young,
            color="#F0F3F6" if label != "Mesozoic" else "#F6F3EC",
            zorder=0,
        )
        ax.text(
            (old + young) / 2,
            headroom,
            label,
            ha="center",
            va="top",
            fontsize=8,
            color=MUTED,
        )
    for name, color, y_lo, y_hi in blocks:
        ax.text(
            T_START + 4,
            (y_lo + y_hi) / 2,
            name,
            ha="left",
            va="center",
            fontsize=8,
            fontweight="bold",
            color=color,
            zorder=5,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=1.5),
        )
    segments, colors = [], []
    for pid, y in rows.items():
        for t_old, t_young, color in runs[pid]:
            if t_old <= time:
                continue
            segments.append([(t_old, y), (max(t_young, time), y)])
            colors.append(color)
    ax.add_collection(
        LineCollection(segments, colors=colors, linewidths=lw, zorder=2)
    )
    fired = [(t, rows[pid]) for pid, t in handoffs if t >= time and pid in rows]
    if fired:
        xs, ys = zip(*fired)
        ax.plot(xs, ys, "|", ms=5, mew=1.2, color=CURSOR, zorder=3, ls="none")
    ax.axvline(time, color=CURSOR, lw=1.0, zorder=4)
    ax.set_xlim(T_START + 8, -8)
    ax.set_ylim(-3, headroom + 1)
    ax.set_yticks([])
    ax.tick_params(axis="x", labelsize=8, colors=MUTED)
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)


def build(
    out: Path,
    circuit_filter=None,
    t_step=T_STEP,
    frame_ms=FRAME_MS,
    slot_in=0.10,
    lw=1.6,
) -> None:
    """Render one GIF. ``circuit_filter``: anchor plate ids whose circuits
    the timeline shows (None = all); the map always stays global.
    ``slot_in`` is the vertical space (inches) per lineage row."""
    model = parse_rot(ROT)
    index = ParentIndex(model)
    features = pygplates.FeatureCollection(str(POLY))
    rotation_model = pygplates.RotationModel(str(ROT))
    wrapper = pygplates.DateLineWrapper(0.0)

    land_pids = sorted(
        {
            f.get_reconstruction_plate_id()
            for f in features
            if f.get_reconstruction_plate_id() in index.table
        }
    )
    if circuit_filter is not None:
        wanted = {CIRCUITS[a][1] for a in circuit_filter}
        land_pids = [
            pid
            for pid in land_pids
            if index.circuit_color(pid, index.span(pid)[1]) in wanted
        ]
    rows, blocks, extent = row_order(index, model, land_pids)
    runs = lineage_runs(index, land_pids)
    handoffs = [
        (pid, x.time) for pid in land_pids for x in model.crossover_details(pid)
    ]

    # size the figure so every lineage row gets slot_in inches
    width = 10.8
    map_h, legend_h, tl_h = 4.4, 0.5, max(2.2, extent * slot_in)
    margin_top, margin_bot = 0.4, 0.55
    height = margin_top + map_h + legend_h + tl_h + margin_bot
    tl_frac = tl_h / height
    map_y0 = (margin_bot + tl_h + legend_h) / height
    legend_y = (margin_bot + tl_h + 0.08) / height

    times = list(np.arange(T_START, -1e-9, -t_step)) + [0.0]
    times = sorted(set(round(t, 3) for t in times), reverse=True)

    frames = []
    for i, time in enumerate(times):
        fig = plt.figure(figsize=(width, height), dpi=88)
        ax_map = fig.add_axes(
            [0.10, map_y0, 0.80, map_h / height], projection=ccrs.Mollweide()
        )
        ax_tl = fig.add_axes([0.06, margin_bot / height, 0.88, tl_frac])

        reconstructed = []
        pygplates.reconstruct(features, rotation_model, reconstructed, time)
        draw_map(ax_map, reconstructed, wrapper, index, time)
        ax_map.set_title(
            f"{time:g} Ma — Torsvik/Doubrovine 2012–2016 hybrid frame, "
            "colored by plate circuit",
            fontsize=11,
            color=INK,
        )
        draw_timeline(ax_tl, rows, blocks, runs, handoffs, time, extent, lw)
        fig.legend(
            handles=[
                plt.Line2D([], [], color=c, lw=4, label=n)
                for n, c in CIRCUITS.values()
            ],
            loc="lower center",
            bbox_to_anchor=(0.5, legend_y),
            ncol=6,
            frameon=False,
            fontsize=7,
            handlelength=1.2,
            columnspacing=1.2,
            labelcolor=MUTED,
        )
        caption = (
            "age in Ma, time flowing toward the present · each line = one "
            "land-carrying plate · color = nearest circuit anchor in the "
            "rotation tree\norange ticks = reference-frame hand-offs "
            "(crossovers)"
        )
        if circuit_filter is not None:
            shown = " and ".join(CIRCUITS[a][0] for a in sorted(circuit_filter))
            caption += f" · timeline shows the {shown} circuits as examples"
        fig.text(
            0.5,
            0.10 / height,
            caption,
            ha="center",
            va="bottom",
            fontsize=8,
            color=MUTED,
        )

        fig.canvas.draw()
        frames.append(
            Image.frombuffer(
                "RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba()
            ).convert("P", palette=Image.ADAPTIVE, colors=128)
        )
        plt.close(fig)
        if i % 20 == 0 or time == 0:
            print(f"frame {i + 1}/{len(times)}: {time:g} Ma", flush=True)

    durations = [frame_ms] * len(frames)
    durations[-1] = END_HOLD_MS
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    # README GIF: two example circuits, roomy rows, smooth 4 Ma steps
    build(OUT, circuit_filter={101, 701}, slot_in=0.10, lw=1.6)
    # companion: every circuit, spaced for legibility, coarser steps
    full = OUT.with_name(OUT.stem + "_full" + OUT.suffix)
    build(full, circuit_filter=None, t_step=8, frame_ms=170, slot_in=0.055, lw=1.1)


if __name__ == "__main__":
    main()
