# scripts/ — Phase 1 automation for the mesh-to-CAD pipeline

Each script is standalone (`python <script>.py --help`), heavily commented
(Dennis's rule: explain WHY, not just what — write for the stranger who'll
modify this next year), and runnable from a venv (see requirements.txt).

## The scripts

| Script | Stage | What it does |
|---|---|---|
| `check_units.py` | 0 — Intake | Guesses the mesh's units (mm/m/um/in) from bbox diagonal. Suggests a scale factor + confidence. Never rescales silently. |
| `quality_gate.py` | 1 — Cleanup | Four quality metrics (watertight, hole-fill area fraction, noise floor via Taubin smoothing, component count) → verdict: `clean` / `noisy` / `needs-rescan` (exit 2). |
| `analyze.py` | 2 — Analysis | Bounding box, planar faces, symmetry, hole notes. **Phase 1 additions:** track suggestion promoted to a recorded decision with confidence; PCA alignment applied and the 4×4 matrix + aligned mesh written out. |
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

No test suite yet (Phase 1). Each script was smoke-tested 2026-10-02 against
synthetic trimesh meshes (clean/noisy/holey boxes at scan-like density).
`deviation.py`'s CloudCompare invocation is correct per the CC changelog but
**not live-tested** — no CloudCompare on the build machine. First live run
should verify the output filename pattern and ASCII column layout (the script
fails loudly if its assumptions are wrong, by design).
