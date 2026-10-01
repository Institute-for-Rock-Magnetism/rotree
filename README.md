# rotree

Cladogram visualization of the plate-rotation hierarchy in any
[GPlates](https://www.gplates.org) rotation (`.rot`) file.

A GPlates rotation file encodes a *rotation tree*: every moving plate is
positioned relative to a fixed plate, which is positioned relative to
another, until the chain reaches the anchor (plate 0). `rotree` parses the
`.rot` file directly (no pygplates dependency), builds that hierarchy at any
reconstruction age, and renders it as a cladogram — so you can see at a
glance how a model is wired, where plates re-parent through time
(crossovers), and which plates never connect to the anchor.

![Mollweide reconstruction of the Torsvik/Doubrovine 2012–2016 hybrid-frame model playing forward from 540 Ma to today, above a time-axis cladogram of the same model revealed in step with the map](docs/rotree_reconstruction.gif)

*The Torsvik/Doubrovine 2012–2016 hybrid-frame model (Torsvik et al. 2012;
CEED6 land polygons) playing forward from 540 Ma to today. Top: a
pygplates + cartopy Mollweide reconstruction, each plate colored by its
circuit — the nearest anchor plate (Laurentia, Gondwana, Siberia, …) up the
rotation-tree parent chain at that age, so a reference-frame hand-off shows
up as a color change on the map. Bottom: the Laurentia and Gondwana/Africa
circuits as examples, each land-carrying plate a lineage against the shared
time axis, colored by the same scheme through time; the cladogram grows with
the moving cursor instead of re-arranging, and orange ticks mark the
hand-offs (crossovers). Regenerate both versions with
[docs/make_reconstruction_gif.py](docs/make_reconstruction_gif.py).*

<details>
<summary><b>Every circuit, spaced out</b> — the same animation with all eleven
plate circuits on the timeline (click to expand)</summary>

![The same animation with every plate circuit on the timeline, spaced out with labeled circuit blocks](docs/rotree_reconstruction_full.gif)

</details>

## Handoffs through time, with the evidence for each

A plate's parent changes through time: a terrane rides an ocean plate, then
accretes to a craton; a craton rifts away from its Rodinian neighbour. The
`.rot` file records *that* the fixed plate changes. `rotree cladogram` also
shows *why*, from a small CSV of evidence kept beside the rotation file:

![Handoffs of the Arabian-Nubian Shield and Azania plates in Merdith et al. (2021), 1000–500 Ma, each stop coloured by the geological event behind it, with hollow stops where no evidence is recorded](docs/example_merdith2021_ANS_handoffs.png)

*Merdith et al. (2021), 1000–500 Ma, Arabian-Nubian Shield and Azania plates,
annotated with the seed sidecar in
[`examples/merdith2021`](examples/merdith2021). Time runs left to right,
older on the left; each plate is a line coloured by the plate it is fixed to,
drawn heavier the more plates it carries. At each handoff a connector joins the
plate to its new parent (a dashed one leaves the old parent) and a **stop**
spans the evidence's age uncertainty, in the colour of the event: rifting,
breakup, collision, suture, accretion, emergence, ophiolite obduction,
paleomagnetic constraint. A **hollow dashed stop is a gap** — a handoff with
no evidence recorded — never hidden. The thin black tick in each stop is the
age at which the file changes the fixed plate, so evidence dated elsewhere
shows up as a stop beside its tick. Numbered stops refer to the evidence
table under the figure. [Interactive version](docs/example_merdith2021_ANS_handoffs.html)
(hover a stop for its evidence and reference, click it to move the time
cursor; [every handoff in the model](docs/example_merdith2021_handoffs_1100-500Ma.html)).*

```bash
# static figure (svg, pdf or png) or interactive page (html)
rotree cladogram model.rot --window 1100 500 -o handoffs.svg
rotree cladogram model.rot --window 1000 500 --circuit 5904 --time 780 -o handoffs.html

# every handoff with its evidence, or GAP; sidecar rows that match nothing
rotree handoffs model.rot --window 1000 500

# start a sidecar: one row per detected handoff, evidence columns empty
rotree handoffs model.rot --window 1000 500 --template model.handoff_evidence.csv
```

### The evidence sidecar

For `model.rot` the sidecar is `model.handoff_evidence.csv` in the same
directory; it is found automatically (`--evidence FILE` points elsewhere,
`--no-evidence` ignores it). Columns:

| column | meaning |
| --- | --- |
| `moving_plate_id`, `moving_plate_name` | the plate that hands off |
| `handoff_age_ma` | the age at which the `.rot` file changes its fixed plate |
| `from_fixed_plate_id`, `to_fixed_plate_id` | the parent on the **older** side, and on the **younger** side — read forward in time |
| `event_type` | `rifting`, `breakup`, `collision`, `suture`, `accretion`, `emergence`, `ophiolite_obduction`, `paleomagnetic_constraint`, `reference_frame` or `other` |
| `event_label`, `evidence` | a short name, and what the evidence is |
| `evidence_age_ma`, `evidence_age_uncertainty_ma` | the evidence's own age and its ± |
| `reference` | the citation; leave it empty rather than guess |
| `confidence` | `high`, `medium` or `low` |

Handoffs are detected from the `.rot` file — every change of fixed plate along
a moving plate's sequence — and the sidecar only annotates them, so:

- a handoff with no row is reported and drawn as a **gap**;
- a row that matches no handoff (wrong plate, wrong age, or parents the file
  does not have) is **reported with the reason**, never silently dropped;
- a row with `from`/`to` swapped still matches, with a warning;
- a row with an empty `from_fixed_plate_id` annotates the plate's
  *appearance* — the oldest age the file defines it, e.g. terrane emergence as
  distinct from a later collision;
- evidence whose age ± uncertainty does not bracket the file's handoff age is
  flagged, with how far off it is: that is often the most useful finding;
- ages match within `--tolerance` (default 0.5 Myr).

GPlates Studio reads the same sidecar beside a loaded `.rot` file and draws it
in its rotation tree history.

```python
from rotree import parse_rot, annotate, save_timeline

model = parse_rot("model.rot")
report = annotate(model, "model.handoff_evidence.csv")
print(report.summary(1000, 500))
for gap in report.gaps:
    print(gap.handoff.moving_plate, gap.handoff.age)
save_timeline(model, "handoffs.pdf", oldest=1000, youngest=500, circuit=5904)
```

## Install

```bash
pip install git+https://github.com/Institute-for-Rock-Magnetism/rotree.git
```

## Command line

```bash
# render the hierarchy at 600 Ma
rotree plot TC2017-SHM2017-D2018-extended.rot --time 600 -o tree_600Ma.png

# interactive version (plotly): hover any node to see how its reference
# frame is defined, every fixed-plate hand-off (crossover) it undergoes,
# and the .rot file's own annotations/citations with source line numbers
rotree html model.rot --time 600 -o tree_600Ma.html

# emphasize the Arabian-Nubian Shield plates
rotree plot model.rot --time 700 --highlight 50311 50312

# where does the wiring change through time?
rotree crossovers model.rot

# plain-text view
rotree tree model.rot --time 600
```

![Cladogram of the extended Torsvik & Cocks (2017) model at 700 Ma](docs/example_extended_TC17_700Ma.png)

*The extended Torsvik & Cocks (2017) model at 700 Ma: branches colored by
depth, orange rings marking plates that re-parent at another age, and
unreachable plates on the dotted orphans branch.*

## Python

```python
from rotree import parse_rot, build_tree, plot_cladogram, save_interactive

model = parse_rot("model.rot")
ax = plot_cladogram(model, time=600, highlight={50311, 50312})
ax.figure.savefig("tree_600Ma.pdf")

# standalone interactive HTML with hover cards on every node
save_interactive(model, "tree_600Ma.html", time=600)

root = build_tree(model, time=600)
for crossover in model.crossovers(201):
    print(crossover)  # (time, old_fixed, new_fixed)

for x in model.crossover_details(201):  # hand-offs with their annotations
    print(x.time, x.old_fixed, "->", x.new_fixed, "|", x.after.comment)
```

## Interactive view

`rotree html` (or `save_interactive`) writes a self-contained HTML page
built with [plotly](https://plotly.com/python/) — install it with
`pip install rotree[interactive]`. Hovering a node, in particular the
bifurcation points where branches join a fixed plate, shows:

- the rotation segment pinning the plate at the chosen age (pole,
  time span, and the `.rot` source line number);
- every reference-frame hand-off (crossover) through time, quoting the
  file's `!` annotations before and after the switch — in well-annotated
  models these carry the citation or reasoning behind the frame choice —
  again with line numbers so each link can be traced back to the data;
- the plates the node carries at that age.

Nodes ringed in orange re-parent at some other age. Pass `--cdn` for a
small file that loads plotly.js from the internet instead of embedding it.

## Sidecar annotations

A `.rot` file records only the rotation tree; hand-drawn cladograms are
usually richer — named orogenies, arcs, rifts, and supergroups with time
spans and references. rotree accepts that curated knowledge as a sidecar
JSON file, keeping the rotation file untouched:

```json
{
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
```

Each event needs `plates` (one id or a list) and a `label`; `start`/`end`
(Ma, either order — one alone makes a point event), `kind`, `ref`, `note`,
and `color` are optional.

```bash
rotree plot model.rot --time 990 --annotations events.json   # active plates drawn as diamonds
rotree html model.rot --time 990 --annotations events.json   # events join the hover cards
```

In Python, pass `annotations=` (a path, JSON text, or a list of dicts /
`PlateEvent`) to `plot_cladogram`, `save_cladogram`, `plot_interactive`,
or `save_interactive`. Hover cards list every event attached to a plate —
span, kind, reference, note — flagging those active at the plotted age.

## Notes

- Plate names are harvested best-effort from the trailing `!` comments on
  rotation lines; models without comments still plot with bare plate IDs.
- Plates with no path to the anchor at the chosen age are collected under a
  labelled `orphans` branch rather than dropped — useful for debugging a
  model's rotation-tree completeness.
- `999` moving-plate lines (GPlates' disabled-pole convention) are ignored
  unless `include_disabled=True`.

## License

MIT — Institute for Rock Magnetism, University of Minnesota.
