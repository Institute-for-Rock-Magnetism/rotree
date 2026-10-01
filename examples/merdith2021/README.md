# Seed handoff evidence for Merdith et al. (2021)

`1000_0_rotfile_Merdith_et_al.handoff_evidence.csv` annotates handoffs in the
rotation file of the published Merdith et al. (2021) v1.1b package
(`1000_0_rotfile_Merdith_et_al.rot`, Zenodo
[10.5281/zenodo.4485738](https://doi.org/10.5281/zenodo.4485738)). The rotation
file is not copied here; put the CSV beside your copy of it, or pass it with
`--evidence`:

```bash
rotree handoffs /path/to/1000_0_rotfile_Merdith_et_al.rot \
  --evidence examples/merdith2021/1000_0_rotfile_Merdith_et_al.handoff_evidence.csv --window 1000 500
rotree cladogram /path/to/1000_0_rotfile_Merdith_et_al.rot \
  --evidence examples/merdith2021/1000_0_rotfile_Merdith_et_al.handoff_evidence.csv \
  --window 1000 500 --plates 5901 5902 5903 5904 5905 5906 5907 5908 5909 5912 5913 \
    5031 5032 508 503 501 702 77021 77022 5014 --time 780 -o handoffs.html
```

The ANS-GC1 talk model uses the same rotation file byte for byte, so the CSV
applies to `ANS-GC1.rot` too (rename it `ANS-GC1.handoff_evidence.csv`).

## It is a seed, not a compilation

24 rows. Against the rotation file (1000–500 Ma): 72 handoffs, 17 with
evidence, **55 gaps**; 1 row matches no handoff; 14 rows carry evidence whose
age does not bracket the model's handoff. Every one of those is reported by
`rotree handoffs`, and each is a real finding rather than an error in the file:

- the Allaqi–Heiani suture row (ophiolite emplaced before 709 ± 4 Ma) matches
  nothing because the model keeps Egyptian Desert (5905) fixed to
  Gebeit/Gabgaba (5904) from 820 to 410 Ma — the suture has no handoff;
- the terminal East–West Gondwana suturing window (570–540 Ma) sits 20 Myr
  older than the model's 520 Ma handoff of Arabia-Somalia (503); the Beraketa
  suture window (580–520 Ma) just brackets the 520 Ma Madagascar handoffs;
- emergence rows compare a domain's valid-from age in the Merdith geometry with
  the start of its rotation sequence, which is often 10–40 Myr older.

## Where each row comes from

Only two kinds of source were used, and nothing else was cited:

1. **The hand-drawn cladogram** `Neoprot_cladogram_June29.pdf` (Paleogeography
   compilation, `Nature_Review/cladograms`). Its coloured boxes were measured
   against its own age axis: crimson rifts, green accretion/collision (numbered
   orogens), orange terminal Gondwana collisions, purple juvenile/arc crust.
   Box spans give the evidence age and its ±. The cladogram carries no
   citations, so these rows have an **empty reference and confidence low**,
   and their `evidence` text says they come from the cladogram. Its plate IDs
   (5-digit, TC17 style) are not Merdith IDs; rows were placed on the Merdith
   plate the handoff actually concerns, by name.
2. **The ANS-GC1 talk package** (`ans_evolution_model/README.md` and
   `source_data/`): the constraint ledger `model_constraints.csv`
   (ANS-CON-0003, -0005, -0006, -0023, -0024), the domain age ledger, and the
   principal sources listed in its README. Full citations were resolved from
   the compilation's `ans_mozambique/geochronology/references.csv`, which that
   README names as the canonical source metadata. These rows carry the
   reference and confidence medium, except where the link between the
   constraint and this particular handoff is itself an interpretation (low).

Direction follows the contract: `from_fixed_plate_id` is the parent on the
older side of the handoff, `to_fixed_plate_id` the parent on the younger side.
Hand-drawn joins that the Merdith file does not encode as handoffs are not
given rows of their own, because a row needs parents the model does not have:
the Halaban suture of Afif and the Atmur-Delgo accretion are described in the
`evidence` text of those plates' emergence rows; the E. Ghats (ca. 986–969 Ma)
and Jiangnan (ca. 840–820 Ma) stops of the cladogram's top panel are left out,
since India and the South China blocks keep their Merdith parents through
them.
