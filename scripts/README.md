# scripts/ — Phase 1 automation for the mesh-to-CAD pipeline

Each script is standalone (`python <script>.py --help` prints usage and exits 0),
heavily commented (Dennis's rule: explain WHY, not just what — write for the
stranger who'll modify this next year), and runnable from a venv
(see requirements.txt).

## Output convention

Every file a script writes lands **next to the input file**, same directory,
with a descriptive suffix — never in a hardcoded folder elsewhere. (Why: the
old `analyze.py` wrote its JSON to `../analysis/`, which scattered files across
the repo the moment anyone ran it outside a `work/` folder. Co-location is
layout-agnostic: `ls` shows the input and everything derived from it.)
The `mesh-to-cad` CLI wrapper organizes outputs into project folders itself;
the scripts stay dumb about layout.

## The scripts

| Script | Stage | What it does |
|---|---|---|
| `check_units.py` | 0 — Intake | Guesses the mesh's units (mm/m/um/in) from bbox diagonal. Suggests a scale factor + confidence. Never rescales silently. |
| `quality_gate.py` | 1 — Cleanup | Four quality metrics (watertight, hole-fill area fraction, noise floor via Taubin smoothing, component count) → verdict: `clean` / `noisy` / `needs-rescan` (exit 2). More than 10 disconnected components forces `noisy` — a fragmented scan needs cleanup before it's trusted. |
| `analyze.py` | 2 — Analysis | Bounding box, planar faces, **cylindrical-wall detection** (bores and extruded walls count as prismatic evidence, so holed plates classify correctly), symmetry, structured hole-detection status. **Phase 1 additions:** track decision (prismatic/organic/mixed) with confidence, driven by `effective_prismatic_fraction` (planar + cylindrical); PCA alignment with the 4×4 matrix + aligned mesh written out. Outputs (`*_measurements.json`, `*_aligned.stl`) go next to the input. |
| `deviation.py` | 3B/4 — Fit+Verify | Wraps CloudCompare `-C2M_DIST` (CLI) and parses the distance field → max/mean/p95, optional `--tolerance` pass/fail. The measurement backbone for every deviation loop. |

## Suggested SOP order

```bash
../.venv/bin/python check_units.py input/bracket.stl      # 1. units sane?
../.venv/bin/python quality_gate.py input/bracket.stl     # 2. scan good enough?
# ... MeshLab cleanup → work/bracket_clean.stl ...
../.venv/bin/python analyze.py work/bracket_clean.stl     # 3. measure + decide track
# ... rebuild CAD ...
../.venv/bin/python deviation.py cad/bracket_v1.stl input/bracket.stl --tolerance 0.2
```

## Exit codes

- `0` — success (or, for quality_gate, verdict is `clean`/`noisy`: proceed)
- `1` — usage error, missing file, missing dependency, or unparseable output
- `2` — quality_gate `needs-rescan`, or deviation.py tolerance FAIL.
  SOP wrappers can branch on this: `quality_gate.py f.stl || [ $? -eq 2 ] && echo RESCAN`

## Testing

No automated test suite yet (Phase 1). Two shakedown rounds, 2026-10-02:
- **Round 1** (`test-samples/TEST-REPORT.md`): Benchy (real), holed bracket
  and organic blob (synthetic, known ground truth). Found 5 bugs — a swallowed
  hole-detection crash, prismatic misclassification on holed parts, false
  `--help` claim, inconsistent output dirs, and a "clean" verdict on a
  300-component mesh. All fixed; see CHANGELOG.md.
- **Round 2** (`test-samples/round2/`, results in `test-samples/TEST-REPORT-2.md`):
  4 real-world models (knob, enclosure, case lid, glider) + edge cases
  (single triangle, empty file, ASCII vs binary STL, non-manifold mess,
  82k-face dense mesh).
`deviation.py`'s CloudCompare invocation is correct per the CC changelog but
**not live-tested** — no CloudCompare on the build machine. First live run
should verify the output filename pattern and ASCII column layout (the script
fails loudly if its assumptions are wrong, by design).
