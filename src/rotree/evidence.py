"""Handoff evidence: why a plate changes the plate it is fixed to.

A rotation file says *that* a moving plate leaves one fixed plate for
another at some age; it rarely says *why*. The why is geology — a
collision or suture, a rift or breakup, an ophiolite obduction, a
paleomagnetic pole that forces the frame, or a terrane that only comes
into existence at that age. This module keeps that knowledge in a CSV
sidecar beside the rotation file, matches it against the handoffs rotree
detects in the file itself, and reports three things explicitly:

- handoffs that carry evidence;
- handoffs that carry none — **gaps**, drawn and listed as gaps rather
  than hidden;
- sidecar rows that do not correspond to any handoff in the file.

The sidecar for ``model.rot`` is ``model.handoff_evidence.csv`` in the
same directory, with the columns in :data:`SIDECAR_COLUMNS`.

Direction convention
--------------------
Handoffs are read forward in geological time. ``from_fixed_plate_id`` is
the fixed plate on the **older** side of ``handoff_age_ma`` and
``to_fixed_plate_id`` the fixed plate on the **younger** side: a terrane
that accretes to a craton at 780 Ma goes *from* whatever carried it
before *to* the craton. A row written the other way round still matches,
with a warning, so a reversed file is corrected rather than silently
dropped.

A row with an empty ``from_fixed_plate_id`` annotates the plate's
*appearance*: the oldest age at which the file defines it at all
(typically ``event_type`` ``emergence``). Appearance is not a handoff,
so an appearance without evidence is not reported as a gap.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Union

from .parser import RotationLine, RotationModel, parse_rot

SIDECAR_SUFFIX = ".handoff_evidence.csv"

SIDECAR_COLUMNS = (
    "moving_plate_id",
    "moving_plate_name",
    "handoff_age_ma",
    "from_fixed_plate_id",
    "to_fixed_plate_id",
    "event_type",
    "event_label",
    "evidence",
    "evidence_age_ma",
    "evidence_age_uncertainty_ma",
    "reference",
    "confidence",
)

EVENT_TYPES = (
    "rifting",
    "breakup",
    "collision",
    "suture",
    "accretion",
    "emergence",
    "ophiolite_obduction",
    "paleomagnetic_constraint",
    "reference_frame",
    "other",
)

CONFIDENCE_LEVELS = ("high", "medium", "low")

# One colour per event type, shared with GPlates Studio's tree history so a
# figure and the workbench read the same way. Hues follow the hand-drawn
# Neoproterozoic cladogram: crimson rifts, green sutures and accretion,
# orange terminal collisions, purple juvenile/arc crust, blue oceanic crust.
EVENT_COLORS = {
    "rifting": "#D62A4F",
    "breakup": "#8E1537",
    "collision": "#E3931B",
    "suture": "#3A9D23",
    "accretion": "#7CC43A",
    "emergence": "#8F2BD9",
    "ophiolite_obduction": "#3D63E0",
    "paleomagnetic_constraint": "#1B9AAA",
    "reference_frame": "#8A949C",
    "other": "#B5835A",
}
GAP_COLOR = "#C0392B"

# Two ages closer than this are the same age for matching purposes; .rot
# files and hand-typed CSVs round differently.
DEFAULT_TOLERANCE_MA = 0.5


@dataclass(frozen=True)
class Handoff:
    """One change of fixed plate detected in a rotation file.

    ``from_fixed`` is the fixed plate on the older side of ``age``,
    ``to_fixed`` the one on the younger side (see the module docstring).
    ``older_line`` / ``younger_line`` are the two rotation lines either
    side of the change, for their comments and line numbers. When the
    file leaves the plate undefined between the two sequences,
    ``undefined_from`` is the younger sequence's oldest age, so the
    change lies somewhere in ``[undefined_from, age]``.

    ``kind == "appearance"`` marks the oldest age at which the plate is
    defined at all; it has no ``from_fixed``.
    """

    moving_plate: int
    age: float
    from_fixed: Optional[int]
    to_fixed: int
    younger_line: Optional[RotationLine] = None
    older_line: Optional[RotationLine] = None
    undefined_from: Optional[float] = None
    kind: str = "handoff"

    @property
    def key(self) -> tuple:
        return (self.moving_plate, self.age, self.from_fixed, self.to_fixed, self.kind)

    def covers(self, age: float, tolerance: float) -> bool:
        young = self.undefined_from if self.undefined_from is not None else self.age
        return young - tolerance <= age <= self.age + tolerance


@dataclass(frozen=True)
class EvidenceRow:
    """One row of a handoff-evidence sidecar, typed."""

    moving_plate_id: int
    handoff_age_ma: float
    from_fixed_plate_id: Optional[int]
    to_fixed_plate_id: Optional[int]
    moving_plate_name: str = ""
    event_type: str = "other"
    event_label: str = ""
    evidence: str = ""
    evidence_age_ma: Optional[float] = None
    evidence_age_uncertainty_ma: Optional[float] = None
    reference: str = ""
    confidence: str = "low"
    row_number: int = 0  # 1-based line in the CSV, header is line 1

    @property
    def color(self) -> str:
        return EVENT_COLORS.get(self.event_type, EVENT_COLORS["other"])

    @property
    def title(self) -> str:
        return self.event_label or self.event_type.replace("_", " ")

    @property
    def age_text(self) -> str:
        if self.evidence_age_ma is None:
            return ""
        if self.evidence_age_uncertainty_ma:
            return f"{self.evidence_age_ma:g} ± {self.evidence_age_uncertainty_ma:g} Ma"
        return f"{self.evidence_age_ma:g} Ma"

    def span(self) -> Optional[tuple[float, float]]:
        """(older, younger) ages the evidence spans, or None if undated."""
        if self.evidence_age_ma is None:
            return None
        u = self.evidence_age_uncertainty_ma or 0.0
        return (self.evidence_age_ma + u, self.evidence_age_ma - u)


@dataclass
class AnnotatedHandoff:
    handoff: Handoff
    evidence: list[EvidenceRow] = field(default_factory=list)

    @property
    def is_gap(self) -> bool:
        """A real handoff with nothing recorded about why it happens."""
        return self.handoff.kind == "handoff" and not self.evidence


@dataclass
class EvidenceReport:
    """Detected handoffs, the evidence matched to each, and what did not fit."""

    handoffs: list[AnnotatedHandoff]
    unmatched: list[tuple[EvidenceRow, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)  # rows that could not be read
    sidecar: Optional[Path] = None

    @property
    def gaps(self) -> list[AnnotatedHandoff]:
        return [h for h in self.handoffs if h.is_gap]

    @property
    def annotated(self) -> list[AnnotatedHandoff]:
        return [h for h in self.handoffs if h.evidence]

    def summary(self, oldest: float = math.inf, youngest: float = -math.inf) -> str:
        real = [h for h in self.handoffs
                if h.handoff.kind == "handoff" and in_window(h, oldest, youngest)]
        gaps = [h for h in real if h.is_gap]
        where = "" if math.isinf(oldest) else f" in {oldest:g}–{youngest:g} Ma"
        return (
            f"{len(real)} handoff(s){where}: {len(real) - len(gaps)} with evidence, "
            f"{len(gaps)} gap(s); {len(self.unmatched)} unmatched sidecar row(s); "
            f"{len(self.warnings)} warning(s); {len(self.issues)} unreadable row(s)"
        )


def sidecar_path(rot_path: Union[str, Path]) -> Path:
    """Where the evidence sidecar for ``rot_path`` lives."""
    rot_path = Path(rot_path)
    return rot_path.with_name(rot_path.stem + SIDECAR_SUFFIX)


def find_sidecar(rot_path: Union[str, Path, None]) -> Optional[Path]:
    if rot_path is None:
        return None
    path = sidecar_path(rot_path)
    return path if path.exists() else None


def _sequences(model: RotationModel, plate: int) -> list[RotationLine]:
    # lines_for sorts by time with a stable sort, so the two lines of a
    # crossover keep file order: the younger sequence's last pole first.
    return model.lines_for(plate)


def detect_handoffs(
    model: RotationModel,
    include_appearances: bool = True,
    include_disabled: bool = False,
) -> list[Handoff]:
    """Every change of fixed plate along each moving plate's sequence.

    Sorted oldest first, then by plate. Plate 999 (GPlates' disabled-pole
    convention) is skipped unless ``include_disabled``.
    """
    out: list[Handoff] = []
    for plate in model.moving_plates:
        if plate == 999 and not include_disabled:
            continue
        rows = _sequences(model, plate)
        if not rows:
            continue
        for younger, older in zip(rows, rows[1:]):
            if younger.fixed_plate == older.fixed_plate:
                continue
            gap = younger.time if older.time - younger.time > 1e-9 else None
            out.append(
                Handoff(
                    moving_plate=plate,
                    age=older.time,
                    from_fixed=older.fixed_plate,
                    to_fixed=younger.fixed_plate,
                    younger_line=younger,
                    older_line=older,
                    undefined_from=gap,
                )
            )
        if include_appearances:
            first = rows[-1]
            out.append(
                Handoff(
                    moving_plate=plate,
                    age=first.time,
                    from_fixed=None,
                    to_fixed=first.fixed_plate,
                    younger_line=first,
                    kind="appearance",
                )
            )
    return sorted(out, key=lambda h: (-h.age, h.moving_plate, h.kind))


def _blank(text: Optional[str]) -> bool:
    return text is None or text.strip() == "" or text.strip().lower() in ("nan", "none", "na")


def _float(text: Optional[str]) -> Optional[float]:
    if _blank(text):
        return None
    value = float(str(text).strip())
    if math.isnan(value):
        return None
    return value


def _int(text: Optional[str]) -> Optional[int]:
    value = _float(text)
    if value is None:
        return None
    if value != int(value):
        raise ValueError(f"plate id {text!r} is not an integer")
    return int(value)


def load_evidence(
    source: Union[str, Path, Iterable[dict], None],
) -> tuple[list[EvidenceRow], list[str]]:
    """Read a sidecar into typed rows plus a list of problems.

    ``source`` may be a path, CSV text, or an iterable of dicts (from
    Python). A bad row is reported and skipped; one bad row never hides
    the rest of the file. Lines starting with ``#`` are comments.
    """
    if source is None:
        return [], []
    if isinstance(source, (str, Path)):
        if isinstance(source, Path) or ("\n" not in source and Path(source).exists()):
            text = Path(source).read_text(encoding="utf-8-sig")
        else:
            text = str(source)
        lines = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        records = list(reader)
        header = reader.fieldnames or []
        issues = []
        missing = [c for c in ("moving_plate_id", "handoff_age_ma") if c not in header]
        if missing:
            return [], [f"sidecar header lacks required column(s): {', '.join(missing)}"]
        unknown = [c for c in header if c and c not in SIDECAR_COLUMNS]
        if unknown:
            issues.append(f"sidecar has column(s) outside the contract, ignored: {', '.join(unknown)}")
    else:
        records = list(source)
        issues = []

    rows: list[EvidenceRow] = []
    for index, record in enumerate(records, start=2):
        get = lambda k: (record.get(k) or "").strip()  # noqa: E731
        try:
            plate = _int(get("moving_plate_id"))
            age = _float(get("handoff_age_ma"))
            if plate is None or age is None:
                raise ValueError("moving_plate_id and handoff_age_ma are required")
            event_type = get("event_type").lower() or "other"
            if event_type not in EVENT_TYPES:
                issues.append(
                    f"row {index}: event_type {event_type!r} is not in the vocabulary; read as 'other'"
                )
                event_type = "other"
            confidence = get("confidence").lower()
            if confidence not in CONFIDENCE_LEVELS:
                issues.append(
                    f"row {index}: confidence {confidence or '(empty)'!r} is not high|medium|low; read as 'low'"
                )
                confidence = "low"
            unc = _float(get("evidence_age_uncertainty_ma"))
            if unc is not None and unc < 0:
                raise ValueError("evidence_age_uncertainty_ma is negative")
            rows.append(
                EvidenceRow(
                    moving_plate_id=plate,
                    handoff_age_ma=age,
                    from_fixed_plate_id=_int(get("from_fixed_plate_id")),
                    to_fixed_plate_id=_int(get("to_fixed_plate_id")),
                    moving_plate_name=get("moving_plate_name"),
                    event_type=event_type,
                    event_label=get("event_label"),
                    evidence=get("evidence"),
                    evidence_age_ma=_float(get("evidence_age_ma")),
                    evidence_age_uncertainty_ma=unc,
                    reference=get("reference"),
                    confidence=confidence,
                    row_number=index,
                )
            )
        except (TypeError, ValueError) as error:
            issues.append(f"row {index}: not read — {error}")
    return rows, issues


def annotate(
    model: RotationModel,
    evidence: Union[str, Path, Iterable[dict], None] = None,
    tolerance: float = DEFAULT_TOLERANCE_MA,
    include_appearances: bool = True,
) -> EvidenceReport:
    """Match sidecar rows to the handoffs detected in ``model``.

    Without a sidecar every handoff is returned unannotated, which is the
    plain tree; the gaps are then every handoff, and are reported as such.
    """
    sidecar = None
    if isinstance(evidence, (str, Path)) and not (isinstance(evidence, str) and "\n" in evidence):
        sidecar = Path(evidence)
    rows, issues = load_evidence(evidence)
    handoffs = [AnnotatedHandoff(h) for h in detect_handoffs(model, include_appearances)]
    by_plate: dict[int, list[AnnotatedHandoff]] = {}
    for item in handoffs:
        by_plate.setdefault(item.handoff.moving_plate, []).append(item)

    report = EvidenceReport(handoffs=handoffs, issues=issues, sidecar=sidecar)
    for row in rows:
        candidates = by_plate.get(row.moving_plate_id, [])
        if not candidates:
            report.unmatched.append((row, f"plate {row.moving_plate_id} does not occur as a moving plate"))
            continue
        appearance = row.from_fixed_plate_id is None
        at_age = [
            c for c in candidates
            if c.handoff.covers(row.handoff_age_ma, tolerance)
            and (c.handoff.kind == "appearance") == appearance
        ]
        match = None
        for c in at_age:
            h = c.handoff
            if appearance:
                if row.to_fixed_plate_id in (None, h.to_fixed):
                    match = c
                    break
            elif (row.from_fixed_plate_id, row.to_fixed_plate_id) == (h.from_fixed, h.to_fixed):
                match = c
                break
        if match is None and not appearance:
            for c in at_age:
                h = c.handoff
                if (row.from_fixed_plate_id, row.to_fixed_plate_id) == (h.to_fixed, h.from_fixed):
                    match = c
                    report.warnings.append(
                        f"row {row.row_number}: plate {row.moving_plate_id} at {row.handoff_age_ma:g} Ma "
                        f"has from/to reversed; the file goes {h.from_fixed} → {h.to_fixed} forward "
                        "in time (from = older-side parent)"
                    )
                    break
        if match is None:
            real = [c.handoff for c in candidates if c.handoff.kind == "handoff"]
            if at_age:
                h = at_age[0].handoff
                what = (f"appears fixed to {h.to_fixed}" if h.kind == "appearance"
                        else f"hands off {h.from_fixed} → {h.to_fixed}")
                reason = (f"at {h.age:g} Ma plate {row.moving_plate_id} {what}, "
                          f"not {row.from_fixed_plate_id} → {row.to_fixed_plate_id}")
            elif appearance:
                first = next(c.handoff for c in candidates if c.handoff.kind == "appearance")
                reason = (f"plate {row.moving_plate_id} first appears at {first.age:g} Ma, "
                          f"not {row.handoff_age_ma:g} Ma")
            elif real:
                ages = ", ".join(f"{h.age:g}" for h in sorted(real, key=lambda h: -h.age))
                reason = (f"plate {row.moving_plate_id} hands off at {ages} Ma; none within "
                          f"±{tolerance:g} Myr of {row.handoff_age_ma:g} Ma")
            else:
                reason = f"plate {row.moving_plate_id} never changes fixed plate in this file"
            report.unmatched.append((row, reason))
            continue
        match.evidence.append(row)
        span = row.span()
        if span is not None:
            h = match.handoff
            young = h.undefined_from if h.undefined_from is not None else h.age
            if span[1] - tolerance > h.age or span[0] + tolerance < young:
                offset = span[1] - h.age if span[1] > h.age else span[0] - young
                report.warnings.append(
                    f"row {row.row_number}: evidence age {row.age_text} does not bracket the "
                    f"model's handoff at {h.age:g} Ma for plate {h.moving_plate} "
                    f"(nearest edge {abs(offset):.3g} Myr {'older' if offset > 0 else 'younger'})"
                )
    return report


def in_window(item: AnnotatedHandoff, oldest: float, youngest: float) -> bool:
    return youngest - 1e-9 <= item.handoff.age <= oldest + 1e-9


def write_template(
    model: RotationModel,
    out: Union[str, Path],
    oldest: float = math.inf,
    youngest: float = 0.0,
    names: Optional[dict[int, str]] = None,
) -> Path:
    """A sidecar skeleton: one row per detected handoff in the window, with
    the evidence columns empty for someone to fill in."""
    names = names if names is not None else model.plate_names()
    out = Path(out)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(SIDECAR_COLUMNS)
        for h in detect_handoffs(model, include_appearances=False):
            if not (youngest - 1e-9 <= h.age <= oldest + 1e-9):
                continue
            writer.writerow([
                h.moving_plate, names.get(h.moving_plate, ""), f"{h.age:g}",
                h.from_fixed, h.to_fixed, "", "", "", "", "", "", "",
            ])
    return out


def format_report(
    report: EvidenceReport,
    names: Optional[dict[int, str]] = None,
    oldest: float = math.inf,
    youngest: float = 0.0,
) -> str:
    """Plain-text listing: every handoff in the window with its evidence or
    an explicit GAP, then the rows that matched nothing."""
    names = names or {}

    def label(pid: Optional[int]) -> str:
        if pid is None:
            return "—"
        name = names.get(pid, "")
        return f"{pid} {name[:28]}".rstrip()

    lines = []
    shown = [h for h in report.handoffs if in_window(h, oldest, youngest)
             and (h.handoff.kind == "handoff" or h.evidence)]
    for item in shown:
        h = item.handoff
        if h.kind == "appearance":
            head = f"{h.age:8.2f} Ma  {label(h.moving_plate):<36} appears on {label(h.to_fixed)}"
        else:
            head = (f"{h.age:8.2f} Ma  {label(h.moving_plate):<36} "
                    f"{label(h.from_fixed)} → {label(h.to_fixed)}")
        lines.append(head)
        if item.is_gap:
            lines.append("              GAP: no evidence recorded for this handoff")
        for row in item.evidence:
            bits = [f"[{row.event_type}] {row.title}"]
            if row.age_text:
                bits.append(row.age_text)
            bits.append(f"confidence {row.confidence}")
            lines.append("              " + " · ".join(bits))
            if row.evidence:
                lines.append(f"                evidence: {row.evidence}")
            lines.append(f"                reference: {row.reference or '(none given)'}")
    if report.unmatched:
        lines.append("")
        lines.append("sidecar rows that match no handoff in the rotation file:")
        for row, reason in report.unmatched:
            lines.append(f"  row {row.row_number}: {row.title} — {reason}")
    for heading, items in (("warnings:", report.warnings), ("unreadable rows:", report.issues)):
        if items:
            lines.append("")
            lines.append(heading)
            lines.extend(f"  {w}" for w in items)
    lines.append("")
    lines.append(report.summary(oldest, youngest))
    return "\n".join(lines)


def load_model_and_evidence(
    rot: Union[str, Path, RotationModel],
    evidence: Union[str, Path, Iterable[dict], None, bool] = None,
    tolerance: float = DEFAULT_TOLERANCE_MA,
) -> tuple[RotationModel, EvidenceReport]:
    """Parse ``rot`` and annotate it. ``evidence=None`` looks for the sidecar
    next to the rotation file; ``False`` means none, even if one exists."""
    model = rot if isinstance(rot, RotationModel) else parse_rot(rot)
    if evidence is None:
        evidence = find_sidecar(model.path)
    elif evidence is False:
        evidence = None
    return model, annotate(model, evidence, tolerance=tolerance)
