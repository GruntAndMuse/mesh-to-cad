# mesh-to-cad

FOSS pipeline: convert 3D scan meshes and downloaded STLs into parametric CAD.

## The problem

A scan (or a downloaded STL) is "dumb" geometry — triangles with no design
intent. Practical CAD work usually means **rebuilding** the part over the
mesh: extracting real dimensions, identifying features (holes, cylinders,
fillets), and producing a parametric model you can actually modify.

This pipeline doesn't ask "does the rebuilt curve look good?" — it asks
**"how much does it deviate from the source mesh?"** Aesthetic questions
decompose into measurable quantities: fidelity, smoothness, symmetry,
continuity, proportion.

## Pipeline stages

1. **Intake** — provenance, license, and unit validation (`check_units.py`)
2. **Cleanup** — mesh repair with a stop-and-rescan rule (`quality_gate.py`)
3. **Analysis** — automated geometry analysis and track selection (`analyze.py`)
4. **Rebuild** — two tracks:
   - *Prismatic*: parametric reconstruction from detected features
   - *Organic*: surface fitting with quantitative deviation loops
5. **Verification** — deviation check against the **original** mesh (`deviation.py`)
6. **Output** — STEP/FCStd/STL, 2D drawing, report, manifest

## Scripts

All scripts are standalone with `--help`. See [scripts/README.md](scripts/README.md)
for the SOP order, exit codes, and test status.

| Script | Stage | Purpose |
|---|---|---|
| `check_units.py` | Intake | Unit heuristic from bounding-box diagonal |
| `quality_gate.py` | Cleanup | 4-metric quality gate → clean/noisy/needs-rescan |
| `analyze.py` | Analysis | Track suggestion + PCA alignment |
| `deviation.py` | Verification | CloudCompare C2M distance → pass/fail vs tolerance |

## Requirements

- Python 3.10+
- `pip install -r scripts/requirements.txt`
- CloudCompare (for `deviation.py`) — CLI must be on PATH

## Status

Phase 1 (intake → verification tooling) is built and syntax-tested.
`deviation.py` needs one live CloudCompare run to confirm output parsing.
See [PIPELINE.md](PIPELINE.md) for the full SOP and
[automation-roadmap.md](automation-roadmap.md) for what's next.

## License

MIT — see [LICENSE](LICENSE).
