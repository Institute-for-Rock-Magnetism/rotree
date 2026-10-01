"""Handoff detection, the evidence sidecar contract, and the timeline views."""

import csv
from pathlib import Path

import pytest

from rotree import annotate, detect_handoffs, find_sidecar, load_evidence, parse_rot, sidecar_path
from rotree.cli import main
from rotree.evidence import (
    EVENT_TYPES,
    SIDECAR_COLUMNS,
    format_report,
    load_model_and_evidence,
    write_template,
)
from rotree.timeline import build_layout, plate_intervals, save_timeline, timeline_html

DATA = Path(__file__).parent / "data"
ROT = DATA / "handoff_demo.rot"
SIDECAR = DATA / "handoff_demo.handoff_evidence.csv"
HEADER = ",".join(SIDECAR_COLUMNS)


def real(report):
    return [h for h in report.handoffs if h.handoff.kind == "handoff"]


def test_sidecar_is_found_by_name():
    assert sidecar_path(ROT) == SIDECAR
    assert find_sidecar(ROT) == SIDECAR
    assert find_sidecar(DATA / "no_such_model.rot") is None


def test_handoffs_read_forward_in_time():
    model = parse_rot(ROT)
    found = {(h.moving_plate, h.age): h for h in detect_handoffs(model, include_appearances=False)}
    assert set(found) == {(201, 600.0), (5901, 780.0)}
    # from = the older-side parent, to = the younger-side parent
    assert (found[201, 600.0].from_fixed, found[201, 600.0].to_fixed) == (101, 701)
    assert (found[5901, 780.0].from_fixed, found[5901, 780.0].to_fixed) == (701, 201)
    assert found[201, 600.0].older_line.line_number < found[201, 600.0].younger_line.line_number + 2


def test_appearances_are_not_gaps():
    model = parse_rot(ROT)
    report = annotate(model, None)
    appear = [h for h in report.handoffs if h.handoff.kind == "appearance"]
    assert {h.handoff.moving_plate for h in appear} == {101, 701, 201, 5901}
    assert not any(h.is_gap for h in appear)


def test_no_sidecar_is_the_plain_tree_with_every_handoff_a_gap():
    model = parse_rot(ROT)
    report = annotate(model, None)
    assert len(real(report)) == 2
    assert len(report.gaps) == 2
    assert not report.unmatched and not report.issues


def test_sidecar_rows_match_and_unmatched_rows_are_reported():
    model, report = load_model_and_evidence(ROT)  # found beside the .rot
    assert report.sidecar == SIDECAR
    by_key = {(h.handoff.moving_plate, h.handoff.age, h.handoff.kind): h for h in report.handoffs}
    amazonia = by_key[201, 600.0, "handoff"]
    assert [e.event_type for e in amazonia.evidence] == ["rifting"]
    assert amazonia.evidence[0].evidence_age_uncertainty_ma == 10
    assert amazonia.evidence[0].confidence == "high"
    assert by_key[5901, 780.0, "handoff"].evidence[0].event_label == "Arc suture"
    assert by_key[5901, 860.0, "appearance"].evidence[0].event_type == "emergence"
    assert report.gaps == []
    reasons = {row.moving_plate_id: reason for row, reason in report.unmatched}
    assert set(reasons) == {201, 999}
    assert "600" in reasons[201] and "650" in reasons[201]
    assert "does not occur" in reasons[999]


def test_reversed_direction_matches_with_a_warning():
    text = HEADER + "\n201,Amazonia,600,701,101,rifting,Reversed,,,,,low\n"
    report = annotate(parse_rot(ROT), text)
    assert not report.unmatched
    assert any("reversed" in w for w in report.warnings)


def test_age_tolerance_and_evidence_that_does_not_bracket_the_handoff():
    ok = HEADER + "\n201,Amazonia,600.3,101,701,rifting,Close enough,,,,,low\n"
    assert not annotate(parse_rot(ROT), ok).unmatched
    far = HEADER + "\n201,Amazonia,601,101,701,rifting,Too far,,,,,low\n"
    assert annotate(parse_rot(ROT), far).unmatched
    assert annotate(parse_rot(ROT), far, tolerance=2).unmatched == []
    off = HEADER + "\n201,Amazonia,600,101,701,rifting,Dated elsewhere,,640,5,,low\n"
    warnings = annotate(parse_rot(ROT), off).warnings
    assert any("does not bracket" in w and "35 Myr older" in w for w in warnings)


def test_bad_rows_are_reported_not_fatal():
    text = HEADER + (
        "\nabc,Bad id,600,101,701,rifting,,,,,,low"
        "\n201,Amazonia,600,101,701,volcano,Unknown type,,,,,sure"
        "\n# a comment line\n"
    )
    rows, issues = load_evidence(text)
    assert len(rows) == 1 and rows[0].event_type == "other" and rows[0].confidence == "low"
    assert any("not read" in i for i in issues)
    assert any("volcano" in i for i in issues) and any("sure" in i for i in issues)
    assert load_evidence("x,y\n1,2\n")[1][0].startswith("sidecar header lacks")


def test_vocabulary_is_the_shared_contract():
    assert SIDECAR_COLUMNS == (
        "moving_plate_id", "moving_plate_name", "handoff_age_ma", "from_fixed_plate_id",
        "to_fixed_plate_id", "event_type", "event_label", "evidence", "evidence_age_ma",
        "evidence_age_uncertainty_ma", "reference", "confidence")
    assert EVENT_TYPES == (
        "rifting", "breakup", "collision", "suture", "accretion", "emergence",
        "ophiolite_obduction", "paleomagnetic_constraint", "reference_frame", "other")


def test_template_has_one_row_per_handoff(tmp_path):
    out = write_template(parse_rot(ROT), tmp_path / "t.csv", oldest=1100, youngest=500)
    rows = list(csv.DictReader(out.open()))
    assert [(r["moving_plate_id"], r["from_fixed_plate_id"], r["to_fixed_plate_id"]) for r in rows] == [
        ("5901", "701", "201"), ("201", "101", "701")]
    assert tuple(rows[0].keys()) == SIDECAR_COLUMNS


def test_report_lists_gaps_explicitly():
    model = parse_rot(ROT)
    text = format_report(annotate(model, None), model.plate_names(), 1100, 500)
    assert text.count("GAP") == 2
    assert "2 handoff(s) in 1100–500 Ma: 0 with evidence, 2 gap(s)" in text


def test_intervals_and_layout_order():
    model, report = load_model_and_evidence(ROT)
    spans = plate_intervals(model, 201, 1100, 500)
    assert [(s.older, s.younger, s.parent) for s in spans] == [(1100, 600, 101), (600, 500, 701)]
    layout = build_layout(model, report, 1100, 500)
    order = [r.plate for r in layout.rows]
    # rows hang under the plate they end up fixed to
    assert order.index(701) < order.index(201) < order.index(5901)
    assert [s.number for s in layout.stops] == [1, 2, 3]
    assert layout.stops[0].item.handoff.kind == "appearance"
    assert layout.row_of(701).line_class in ("major", "intermediate")


@pytest.mark.parametrize("suffix", [".svg", ".pdf", ".png"])
def test_static_outputs(tmp_path, suffix):
    out = save_timeline(ROT, tmp_path / f"t{suffix}", oldest=1100, youngest=500, time=700)
    assert out.exists() and out.stat().st_size > 1000
    if suffix == ".svg":
        text = out.read_text()
        assert "Arc suture" in text and "Tonian" in text


def test_interactive_html_is_self_contained_and_carries_the_evidence(tmp_path):
    page = timeline_html(ROT, oldest=1100, youngest=500)
    assert "<script src" not in page and "plotly" not in page.lower()
    assert "Test et al. (2000)" in page and "Arc suture" in page
    assert "match no handoff" in page and "A plate that is not in the file" in page
    plain = timeline_html(ROT, oldest=1100, youngest=500, evidence=False)
    assert "no evidence sidecar" in plain and plain.count('class="stop gap"') == 2


def test_cli(tmp_path, capsys):
    out = tmp_path / "c.html"
    assert main(["cladogram", str(ROT), "--window", "1100", "500", "-o", str(out)]) == 0
    assert out.exists()
    assert main(["handoffs", str(ROT), "--template", str(tmp_path / "t.csv")]) == 0
    text = capsys.readouterr().out
    assert "Arc suture" in text and "match no handoff" in text
    assert main(["handoffs", str(ROT), "--strict"]) == 1
    assert main(["handoffs", str(ROT), "--no-evidence", "--strict"]) == 0


def test_title_is_kept(tmp_path):
    from rotree.timeline import plot_timeline

    fig = plot_timeline(ROT, oldest=1100, youngest=500, title="Hello title")
    assert fig.texts[0].get_text() == "Hello title"
