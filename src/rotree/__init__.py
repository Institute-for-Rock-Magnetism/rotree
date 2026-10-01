"""rotree: cladogram visualization of GPlates .rot plate hierarchies."""

from .annotations import PlateEvent, load_annotations
from .evidence import (
    EvidenceReport,
    EvidenceRow,
    Handoff,
    annotate,
    detect_handoffs,
    find_sidecar,
    load_evidence,
    sidecar_path,
)
from .interactive import plot_interactive, save_interactive
from .parser import Crossover, RotationLine, RotationModel, parse_rot
from .plot import plot_cladogram, save_cladogram
from .timeline import plot_timeline, save_timeline, save_timeline_html
from .tree import PlateNode, all_crossovers, build_tree

__version__ = "0.2.0"

__all__ = [
    "Crossover",
    "RotationLine",
    "RotationModel",
    "parse_rot",
    "PlateNode",
    "build_tree",
    "all_crossovers",
    "plot_cladogram",
    "save_cladogram",
    "plot_interactive",
    "save_interactive",
    "Handoff",
    "EvidenceRow",
    "EvidenceReport",
    "detect_handoffs",
    "load_evidence",
    "annotate",
    "sidecar_path",
    "find_sidecar",
    "plot_timeline",
    "save_timeline",
    "save_timeline_html",
    "PlateEvent",
    "load_annotations",
    "__version__",
]
