"""Command-line interface: ``rotree plot model.rot --time 600 -o tree.png``."""

from __future__ import annotations

import argparse
from pathlib import Path

from .parser import parse_rot
from .tree import all_crossovers, build_tree


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="rotree",
        description="Cladogram visualization of GPlates .rot plate hierarchies",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plot = sub.add_parser("plot", help="render the cladogram to an image")
    p_plot.add_argument("rot", type=Path, help="path to the .rot file")
    p_plot.add_argument("--time", type=float, default=0.0, help="age in Ma (default 0)")
    p_plot.add_argument("-o", "--out", type=Path, default=None, help="output image (png/pdf/svg)")
    p_plot.add_argument("--anchor", type=int, default=0, help="anchor plate id (default 0)")
    p_plot.add_argument("--no-names", action="store_true", help="hide plate names")
    p_plot.add_argument("--highlight", type=int, nargs="*", default=[], help="plate ids to emphasize")
    p_plot.add_argument(
        "--annotations",
        type=Path,
        default=None,
        help="sidecar JSON of curated plate events (orogenies, arcs, refs); "
        "plates with an event active at --time are drawn as diamonds",
    )

    p_html = sub.add_parser(
        "html",
        help="render an interactive cladogram (hover nodes for hand-off "
        "details and the .rot annotations behind them; needs plotly)",
    )
    p_html.add_argument("rot", type=Path, help="path to the .rot file")
    p_html.add_argument("--time", type=float, default=0.0, help="age in Ma (default 0)")
    p_html.add_argument("-o", "--out", type=Path, default=None, help="output .html file")
    p_html.add_argument("--anchor", type=int, default=0, help="anchor plate id (default 0)")
    p_html.add_argument("--no-names", action="store_true", help="hide plate names")
    p_html.add_argument("--highlight", type=int, nargs="*", default=[], help="plate ids to emphasize")
    p_html.add_argument(
        "--annotations",
        type=Path,
        default=None,
        help="sidecar JSON of curated plate events; events appear in the "
        "hover cards and active plates are drawn as diamonds",
    )
    p_html.add_argument(
        "--cdn",
        action="store_true",
        help="load plotly.js from the CDN (small file, needs internet) "
        "instead of embedding it",
    )

    p_x = sub.add_parser("crossovers", help="list fixed-plate changes (reparenting) through time")
    p_x.add_argument("rot", type=Path)

    p_ls = sub.add_parser("tree", help="print the hierarchy as indented text")
    p_ls.add_argument("rot", type=Path)
    p_ls.add_argument("--time", type=float, default=0.0)
    p_ls.add_argument("--anchor", type=int, default=0)

    args = parser.parse_args(argv)
    if args.command == "plot":
        from .plot import save_cladogram

        out = args.out or args.rot.with_suffix("").with_name(
            f"{args.rot.stem}_cladogram_{args.time:g}Ma.png"
        )
        path = save_cladogram(
            args.rot,
            out,
            time=args.time,
            anchor=args.anchor,
            show_names=not args.no_names,
            highlight=set(args.highlight),
            annotations=args.annotations,
        )
        print(path)
    elif args.command == "html":
        from .interactive import save_interactive

        out = args.out or args.rot.with_suffix("").with_name(
            f"{args.rot.stem}_cladogram_{args.time:g}Ma.html"
        )
        path = save_interactive(
            args.rot,
            out,
            time=args.time,
            anchor=args.anchor,
            show_names=not args.no_names,
            highlight=set(args.highlight),
            annotations=args.annotations,
            include_plotlyjs="cdn" if args.cdn else True,
        )
        print(path)
    elif args.command == "crossovers":
        model = parse_rot(args.rot)
        rows = all_crossovers(model)
        if not rows:
            print("no crossovers: every plate keeps one fixed plate")
        for plate, time, old, new in rows:
            print(f"{plate:>7d}  at {time:>8.2f} Ma  fixed {old} -> {new}")
    elif args.command == "tree":
        model = parse_rot(args.rot)
        root = build_tree(model, time=args.time, anchor=args.anchor)

        def emit(node, indent=0):
            label = str(node.plate_id) if node.plate_id >= 0 else "orphans"
            name = f"  {node.name}" if node.name else ""
            print("  " * indent + label + name)
            for child in node.children:
                emit(child, indent + 1)

        emit(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
