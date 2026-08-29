"""Sidecar annotations: attach curated knowledge to plates in a cladogram.

A .rot file records only the rotation tree; hand-drawn cladograms are
usually much richer — named orogenies, arcs, rifts and supergroups with
time spans, references, and notes. This module defines a small JSON
sidecar format for that knowledge so it can be layered onto rotree's
plots without touching the rotation file::

    {
      "title": "Neoproterozoic events",
      "events": [
        {
          "plates": [10100, 20100],
          "label": "Rigolet orogeny",
          "kind": "orogeny",
          "start": 1005,
          "end": 980,
          "ref": "Rivers (2008)",
          "note": "final Grenvillian collisional pulse"
        }
      ]
    }

Every event needs ``plates`` (one id or a list) and a ``label``; all other
fields are optional. ``start``/``end`` are ages in Ma (either order; a
single one makes a point event). ``kind`` is free text (orogeny, arc,
rift, supergroup, …), ``ref`` the citation, ``note`` free commentary, and
``color`` an optional CSS color for renderers that draw the event.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Union


@dataclass(frozen=True)
class PlateEvent:
    """One annotated event tied to one or more plates."""

    plates: tuple[int, ...]
    label: str
    start: Optional[float] = None  # older bound, Ma
    end: Optional[float] = None  # younger bound, Ma
    kind: str = ""
    ref: str = ""
    note: str = ""
    color: str = ""

    def involves(self, plate_id: int) -> bool:
        return plate_id in self.plates

    def active_at(self, time: float, tol: float = 1e-9) -> bool:
        """True when ``time`` (Ma) falls inside the event's span.

        A point event matches only its own age; an undated event never
        counts as active (it still shows up in listings).
        """
        if self.start is None and self.end is None:
            return False
        old = self.start if self.start is not None else self.end
        young = self.end if self.end is not None else self.start
        return young - tol <= time <= old + tol

    @property
    def span_text(self) -> str:
        if self.start is None and self.end is None:
            return "undated"
        if self.start is None or self.end is None or self.start == self.end:
            t = self.start if self.start is not None else self.end
            return f"{t:g} Ma"
        return f"{self.start:g}–{self.end:g} Ma"


def _coerce_event(raw: dict) -> PlateEvent:
    plates = raw.get("plates", raw.get("plate"))
    if plates is None:
        raise ValueError(f"annotation event needs 'plates': {raw!r}")
    if isinstance(plates, (int, float)):
        plates = [plates]
    label = raw.get("label")
    if not label:
        raise ValueError(f"annotation event needs a 'label': {raw!r}")
    start = raw.get("start")
    end = raw.get("end")
    if start is not None and end is not None and float(start) < float(end):
        start, end = end, start  # normalize: start is the older bound
    return PlateEvent(
        plates=tuple(int(p) for p in plates),
        label=str(label),
        start=None if start is None else float(start),
        end=None if end is None else float(end),
        kind=str(raw.get("kind", "")),
        ref=str(raw.get("ref", "")),
        note=str(raw.get("note", "")),
        color=str(raw.get("color", "")),
    )


def load_annotations(
    source: Union[str, Path, Iterable[Union[PlateEvent, dict]], None],
) -> list[PlateEvent]:
    """Normalize any accepted annotations input to a list of PlateEvent.

    Accepts None, a path to a sidecar JSON file, JSON text, or an iterable
    of PlateEvent / event dicts (handy from Python).
    """
    if source is None:
        return []
    if isinstance(source, (str, Path)):
        if isinstance(source, Path) or (
            "\n" not in source and "{" not in source and Path(source).exists()
        ):
            data = json.loads(Path(source).read_text())
        else:
            data = json.loads(str(source))
        events = data["events"] if isinstance(data, dict) else data
        return [_coerce_event(e) for e in events]
    return [
        e if isinstance(e, PlateEvent) else _coerce_event(e) for e in source
    ]


def events_for(
    events: Iterable[PlateEvent], plate_id: int
) -> list[PlateEvent]:
    """Events involving ``plate_id``, oldest first (undated last)."""
    mine = [e for e in events if e.involves(plate_id)]
    return sorted(
        mine,
        key=lambda e: -(e.start if e.start is not None
                        else e.end if e.end is not None else float("-inf")),
    )
