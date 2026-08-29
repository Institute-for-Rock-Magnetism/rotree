"""Build the README demo GIF: a Mollweide global reconstruction playing
forward through the Phanerozoic, side by side with the rotree cladogram
of the same rotation model at the same age.

Left panel: continental polygons reconstructed with pygplates and colored
by each plate's depth in the rotation tree (levels from the anchor) —
the same palette the cladogram uses, so the two panels read together.
Right panel: the rotree cladogram skeleton, re-built at every age, with
hand-offs (crossovers) that fire between frames flagged in the banner.

Requires: pygplates, cartopy, shapely, pillow (none are rotree deps —
this is a docs-only script). Paths below point at local copies of the
Torsvik/Doubrovine 2012-2016 hybrid frame (CEED) and the CEED6 land
polygons; adjust to your own copies to regenerate.

Usage::

    python docs/make_reconstruction_gif.py [ROT_FILE] [POLYGONS] [OUT_GIF]
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import pygplates
from matplotlib.patches import Polygon as MplPolygon
from PIL import Image

from rotree import build_tree, parse_rot
from rotree.plot import _DEPTH_COLORS, _MUTED_COLOR, plot_cladogram

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

TIMES = list(range(540, -1, -20))  # 540 Ma -> today
FRAME_MS = 500
END_HOLD_MS = 2500
ORPHAN_GREY = "#B9C2CA"


def plate_depths(root) -> dict[int, int]:
    """plate id -> levels from the anchor, at one age."""
    depths: dict[int, int] = {}

    def walk(node, depth):
        if node.plate_id >= 0:
            depths[node.plate_id] = depth
        for child in node.children:
            walk(child, depth + (0 if node.plate_id < 0 else 1))

    walk(root, 0)
    return depths


def draw_map(ax, features, rotation_model, wrapper, time, depths):
    """Fill reconstructed land polygons, colored by rotation-tree depth.

    Rings are dateline-wrapped and pole-closed by pygplates, then their
    vertices are projected directly to Mollweide coordinates and drawn as
    plain patches — sidestepping map-library polygon cutting, which can
    invert thin slivers into globe-covering fills.
    """
    ax.set_global()
    ax.set_facecolor("#E9F1F6")
    moll, geo = ax.projection, ccrs.PlateCarree()
    reconstructed = []
    pygplates.reconstruct(features, rotation_model, reconstructed, time)
    for rec in reconstructed:
        pid = rec.get_feature().get_reconstruction_plate_id()
        depth = depths.get(pid)
        color = (
            ORPHAN_GREY
            if depth is None
            else _DEPTH_COLORS[depth % len(_DEPTH_COLORS)]
        )
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


def main() -> None:
    model = parse_rot(ROT)
    features = pygplates.FeatureCollection(str(POLY))
    rotation_model = pygplates.RotationModel(str(ROT))
    wrapper = pygplates.DateLineWrapper(0.0)

    frames = []
    for i, time in enumerate(TIMES):
        root = build_tree(model, time=time)
        depths = plate_depths(root)

        fig = plt.figure(figsize=(13.2, 5.6), dpi=100)
        ax_map = fig.add_axes(
            [0.015, 0.06, 0.56, 0.82], projection=ccrs.Mollweide()
        )
        ax_tree = fig.add_axes([0.615, 0.06, 0.37, 0.82])

        draw_map(ax_map, features, rotation_model, wrapper, time, depths)
        ax_map.set_title(
            f"{time} Ma — Torsvik/Doubrovine 2012–2016 hybrid frame (CEED6 land)",
            fontsize=11,
        )

        plot_cladogram(
            model,
            time=time,
            ax=ax_tree,
            show_labels=False,
            mark_crossovers=False,
        )
        ax_tree.set_title(
            f"rotree: plate hierarchy at {time} Ma "
            f"({root.n_leaves} leaves, depth {root.depth})",
            fontsize=11,
        )
        ax_tree.set_xlim(-0.5, 17)  # fixed frame so the tree doesn't jump
        ax_tree.set_xlabel("")  # the banner below explains the x-axis

        # hand-offs firing since the previous frame -> banner text
        prev = TIMES[i - 1] if i else None
        fired = [
            (p, t, old, new)
            for p in model.moving_plates
            for (t, old, new) in model.crossovers(p)
            if prev is not None and time <= t < prev
        ]
        if fired:
            shown = ", ".join(
                f"{p}: {old}→{new}" for p, t, old, new in fired[:6]
            )
            more = f"  (+{len(fired) - 6} more)" if len(fired) > 6 else ""
            banner = f"reference-frame hand-offs this step — {shown}{more}"
        else:
            banner = "no reference-frame hand-offs this step"
        fig.text(
            0.5,
            0.015,
            banner
            + "   |   map colors = levels from anchor plate (cladogram x-axis)",
            ha="center",
            fontsize=9,
            color=_MUTED_COLOR,
        )

        fig.canvas.draw()
        frames.append(Image.frombuffer(
            "RGBA",
            fig.canvas.get_width_height(),
            fig.canvas.buffer_rgba(),
        ).convert("P", palette=Image.ADAPTIVE, colors=128))
        plt.close(fig)
        print(f"frame {i + 1}/{len(TIMES)}: {time} Ma", flush=True)

    durations = [FRAME_MS] * len(frames)
    durations[-1] = END_HOLD_MS
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
