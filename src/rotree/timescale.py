"""Periods of the geologic time scale, for the axis under a timeline.

Boundary ages are the Geologic Time Scale 2020; colours are the ICS/CGMW
chart. Transcribed from the same table GPlates Studio draws under its tree
history, so a figure and the workbench agree about where the Cryogenian
starts. Only periods are listed (and the Archean eras, which have none).
"""

from __future__ import annotations

from typing import NamedTuple


class Period(NamedTuple):
    name: str
    older: float
    younger: float
    color: str


PERIODS = (
    Period("Siderian", 2500.0, 2300.0, "#F68D67"),
    Period("Rhyacian", 2300.0, 2050.0, "#F79B71"),
    Period("Orosirian", 2050.0, 1800.0, "#F7A976"),
    Period("Statherian", 1800.0, 1600.0, "#F8B77D"),
    Period("Calymmian", 1600.0, 1400.0, "#FDC07F"),
    Period("Ectasian", 1400.0, 1200.0, "#FECC8C"),
    Period("Stenian", 1200.0, 1000.0, "#FED99A"),
    Period("Tonian", 1000.0, 720.0, "#FEB342"),
    Period("Cryogenian", 720.0, 635.0, "#FEBF4E"),
    Period("Ediacaran", 635.0, 538.8, "#FED379"),
    Period("Cambrian", 538.8, 486.85, "#7FA056"),
    Period("Ordovician", 486.85, 443.1, "#009270"),
    Period("Silurian", 443.1, 419.62, "#B3E1B6"),
    Period("Devonian", 419.62, 358.86, "#CB8C37"),
    Period("Carboniferous", 358.86, 298.9, "#67A599"),
    Period("Permian", 298.9, 251.902, "#F04028"),
    Period("Triassic", 251.902, 201.4, "#812B92"),
    Period("Jurassic", 201.4, 143.1, "#34B2C9"),
    Period("Cretaceous", 143.1, 66.0, "#7FC64E"),
    Period("Paleogene", 66.0, 23.04, "#FD9A52"),
    Period("Neogene", 23.04, 2.58, "#FFE619"),
    Period("Quaternary", 2.58, 0.0, "#F9F97F"),
)


def periods_between(oldest: float, youngest: float) -> list[Period]:
    """Periods overlapping [youngest, oldest], clipped to it."""
    out = []
    for p in PERIODS:
        older, younger = min(p.older, oldest), max(p.younger, youngest)
        if older > younger:
            out.append(Period(p.name, older, younger, p.color))
    return out


def period_at(age: float) -> str:
    for p in PERIODS:
        if p.younger <= age <= p.older:
            return p.name
    return ""
