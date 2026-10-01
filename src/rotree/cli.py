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

    def evidence_args(p):
        p.add_argument(
            "--evidence",
            type=Path,
            default=None,
            help="handoff-evidence CSV (default: <rot stem>.handoff_evidence.csv "
            "beside the .rot file, if present)",
        )
        p.add_argument("--no-evidence", action="store_true", help="ignore any sidecar")
        p.add_argument(
            "--window",
            type=float,
            nargs=2,
            default=[1100.0, 500.0],
            metavar=("OLDEST", "YOUNGEST"),
            help="age range in Ma (default 1100 500)",
        )
        p.add_argument("--tolerance", type=float, default=0.5,
                       help="Myr within which a sidecar age matches a handoff (default 0.5)")

    p_c = sub.add_parser(
        "cladogram",
        help="time-axis cladogram: which plate each plate is fixed to, when it "
        "hands off, and the evidence for each handoff (svg/pdf/png/html)",
    )
    p_c.add_argument("rot", type=Path)
    p_c.add_argument("-o", "--out", type=Path, default=None,
                     help="output .svg/.pdf/.png, or .html for the interactive page")
    evidence_args(p_c)
    p_c.add_argument("--plates", type=int, nargs="*", default=None,
                     help="rows to draw (plus the plates they hand off between)")
    p_c.add_argument("--circuit", type=int, default=None,
                     help="draw this plate, what it is fixed to, and everything fixed to it")
    p_c.add_argument("--time", type=float, default=None, help="draw a time cursor at this age")
    p_c.add_argument("--no-table", action="store_true", help="omit the evidence table (static output)")
    p_c.add_argument("--title", default=None)

    p_h = sub.add_parser(
        "handoffs",
        help="list every fixed-plate handoff with its evidence, or GAP where there "
        "is none, and report sidecar rows that match no handoff",
    )
    p_h.add_argument("rot", type=Path)
    evidence_args(p_h)
    p_h.add_argument("--template", type=Path, default=None,
                     help="write a sidecar skeleton (one row per handoff in the window) here")
    p_h.add_argument("--strict", action="store_true",
                     help="exit 1 if any sidecar row is unmatched or unreadable")

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
    elif args.command in ("cladogram", "handoffs"):
        from .evidence import format_report, load_model_and_evidence, write_template

        evidence = False if args.no_evidence else args.evidence
        oldest, youngest = max(args.window), min(args.window)
        if args.command == "cladogram":
            from .timeline import save_timeline

            out = args.out or args.rot.with_name(
                f"{args.rot.stem}_handoffs_{oldest:g}-{youngest:g}Ma.svg")
            path = save_timeline(
                args.rot, out, oldest=oldest, youngest=youngest, evidence=evidence,
                plates=args.plates, circuit=args.circuit, time=args.time,
                show_table=not args.no_table, tolerance=args.tolerance, title=args.title,
            )
            print(path)
        else:
            model, report = load_model_and_evidence(args.rot, evidence, args.tolerance)
            print(f"{args.rot.name} · evidence: "
                  f"{report.sidecar if report.sidecar else 'none'}")
            print(format_report(report, model.plate_names(), oldest, youngest))
            if args.template:
                print(write_template(model, args.template, oldest, youngest))
            if args.strict and (report.unmatched or report.issues):
                return 1
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
