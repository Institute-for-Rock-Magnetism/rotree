"""Parser for PLATES4/GPlates rotation (.rot) files.

A .rot file is a plain-text table of total reconstruction poles::

    moving_plate  time_Ma  pole_lat  pole_lon  angle_deg  fixed_plate  !comment

``rotree`` needs only the plate hierarchy, so the parser keeps the pole
values but is tolerant of formatting details (commented-out lines beginning
with ``999`` conventions vary between models and are kept, flagged, so the
tree can optionally ignore them).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Union


@dataclass(frozen=True)
class RotationLine:
    """One finite-rotation line of a .rot file."""

    moving_plate: int
    time: float
    pole_lat: float
    pole_lon: float
    angle: float
    fixed_plate: int
    comment: str = ""
    line_number: int = 0

    @property
    def is_disabled(self) -> bool:
        """GPlates convention: a commented-out pole keeps plate id 999."""
        return self.moving_plate == 999


@dataclass
class RotationModel:
    """All rotation lines of one .rot file, indexed by moving plate."""

    lines: list[RotationLine] = field(default_factory=list)
    path: Optional[Path] = None

    @property
    def moving_plates(self) -> list[int]:
        return sorted({l.moving_plate for l in self.lines})

    def lines_for(self, moving_plate: int) -> list[RotationLine]:
        rows = [l for l in self.lines if l.moving_plate == moving_plate]
        return sorted(rows, key=lambda l: l.time)

    def plate_names(self) -> dict[int, str]:
        """Best-effort plate names harvested from trailing comments."""
        names: dict[int, str] = {}
        for line in self.lines:
            text = _clean_comment(line.comment)
            if text and line.moving_plate not in names:
                names[line.moving_plate] = text
        return names

    def parent_of(self, moving_plate: int, time: float) -> Optional[int]:
        """Fixed plate of ``moving_plate`` at ``time`` (Ma).

        Uses the fixed plate of the rotation interval that encloses ``time``.
        Returns None when the plate is not defined at that time.
        """
        rows = self.lines_for(moving_plate)
        if not rows:
            return None
        if time < rows[0].time - 1e-9 or time > rows[-1].time + 1e-9:
            return None
        chosen = rows[0]
        for row in rows:
            if row.time <= time + 1e-9:
                chosen = row
            else:
                break
        return chosen.fixed_plate

    def crossovers(self, moving_plate: int) -> list[tuple[float, int, int]]:
        """(time, old_fixed, new_fixed) wherever the fixed plate changes."""
        rows = self.lines_for(moving_plate)
        out: list[tuple[float, int, int]] = []
        for a, b in zip(rows, rows[1:]):
            if a.fixed_plate != b.fixed_plate:
                out.append((b.time, a.fixed_plate, b.fixed_plate))
        return out


_LINE_RE = re.compile(
    r"^\s*(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s*(.*)$"
)


def _clean_comment(comment: str) -> str:
    text = comment.lstrip("!").strip()
    text = re.sub(r"^[A-Z]{2,4}[-_]", "", text)  # strip leading model tags like GTS-
    text = text.split("!")[0].strip()
    return text


def parse_rot(source: Union[str, Path]) -> RotationModel:
    """Parse a .rot file (path or text content) into a RotationModel."""
    if isinstance(source, Path) or (
        isinstance(source, str) and "\n" not in source and Path(source).exists()
    ):
        path: Optional[Path] = Path(source)
        text = path.read_text(errors="replace")
    else:
        path = None
        text = str(source)

    model = RotationModel(path=path)
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "!", "//")):
            continue
        match = _LINE_RE.match(stripped)
        if not match:
            continue
        moving, time, lat, lon, angle, fixed, comment = match.groups()
        model.lines.append(
            RotationLine(
                moving_plate=int(moving),
                time=float(time),
                pole_lat=float(lat),
                pole_lon=float(lon),
                angle=float(angle),
                fixed_plate=int(fixed),
                comment=comment.strip(),
                line_number=number,
            )
        )
    return model
