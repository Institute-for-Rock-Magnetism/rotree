from pathlib import Path

import pytest

from rotree import all_crossovers, build_tree, parse_rot

SAMPLE = """
! demo rotation file
101 0.0 0.0 0.0 0.0 000 !ANC-Laurentia
101 600.0 30.0 40.0 12.5 000 !ANC-Laurentia
201 0.0 0.0 0.0 0.0 101 !ANC-Baltica
201 400.0 10.0 20.0 5.0 101 !ANC-Baltica
201 700.0 15.0 25.0 9.0 301 !ANC-Baltica crossover to Gondwana frame
301 0.0 0.0 0.0 0.0 000 !ANC-Gondwana
301 800.0 -5.0 100.0 22.0 000 !ANC-Gondwana
999 100.0 1.0 1.0 1.0 101 !disabled pole
"""


def test_parse_counts_and_names():
    model = parse_rot(SAMPLE)
    assert model.moving_plates == [101, 201, 301, 999]
    names = model.plate_names()
    assert names[101] == "Laurentia"
    assert "Gondwana" in names[301]


def test_plate_names_drop_modelwide_boilerplate():
    # a comment shared by >=10 plates is a citation, not a plate name
    text = "\n".join(
        f"{pid} 0.0 0.0 0.0 0.0 000 !Same Citation (2020)" for pid in range(101, 113)
    )
    text += "\n555 0.0 0.0 0.0 0.0 000 !Distinct Plate Name"
    names = parse_rot(text).plate_names()
    assert names[555] == "Distinct Plate Name"
    assert 101 not in names


def test_parent_of_interval_and_range():
    model = parse_rot(SAMPLE)
    assert model.parent_of(201, 100.0) == 101
    assert model.parent_of(201, 500.0) == 101  # still in the 400 Ma segment
    assert model.parent_of(201, 700.0) == 301  # crossover takes effect at its line
    assert model.parent_of(201, 900.0) is None  # beyond last pole
    assert model.parent_of(101, 0.0) == 0


def test_crossovers_detected():
    model = parse_rot(SAMPLE)
    xs = all_crossovers(model)
    assert (201, 700.0, 101, 301) in xs


def test_build_tree_structure():
    model = parse_rot(SAMPLE)
    root = build_tree(model, time=100.0)
    ids = {n.plate_id for n in root.walk()}
    assert {0, 101, 201, 301} <= ids
    assert 999 not in ids
    lau = next(n for n in root.walk() if n.plate_id == 101)
    assert [c.plate_id for c in lau.children] == [201]


def test_crossover_details_carry_annotations():
    model = parse_rot(SAMPLE)
    (x,) = model.crossover_details(201)
    assert (x.time, x.old_fixed, x.new_fixed) == (700.0, 101, 301)
    assert "crossover to Gondwana frame" in x.after.comment
    assert x.before.line_number < x.after.line_number


def test_segment_at():
    model = parse_rot(SAMPLE)
    seg = model.segment_at(201, 500.0)
    assert seg is not None and seg.time == 400.0 and seg.fixed_plate == 101
    assert model.segment_at(201, 900.0) is None


def test_interactive_smoke(tmp_path: Path):
    pytest.importorskip("plotly")
    from rotree import plot_interactive, save_interactive

    fig = plot_interactive(parse_rot(SAMPLE), time=100.0, highlight={201})
    hovers = [
        h
        for trace in fig.data
        if getattr(trace, "hovertext", None)
        for h in trace.hovertext
    ]
    baltica = next(h for h in hovers if "plate 201" in h)
    assert "hand-off" in baltica and "crossover to Gondwana frame" in baltica
    assert "line " in baltica  # cites the .rot source line

    out = save_interactive(parse_rot(SAMPLE), tmp_path / "clado.html", time=100.0)
    assert out.exists() and out.stat().st_size > 0


def test_plot_smoke(tmp_path: Path):
    pytest.importorskip("matplotlib")
    from rotree import save_cladogram

    out = save_cladogram(parse_rot(SAMPLE), tmp_path / "clado.png", time=100.0)
    assert out.exists() and out.stat().st_size > 0
