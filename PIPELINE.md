# Mesh-to-CAD Pipeline

**The Mesh Wall pipeline** — turning dumb meshes (3D scans, downloaded STLs) into editable, parametric CAD.

## The problem

A mesh is a shell of triangles. It has no features, no dimensions, no history. You can't change a hole diameter, can't thicken a wall, can't mate it to anything. Every scanner owner and everyone who's ever downloaded an STL hits this wall: *"I have the shape, now what?"*

The answer isn't "just use the mesh." The answer is **rebuild it as real CAD, using the mesh as evidence.**

## Dennis's core insight

Don't ask "does this look good" (aesthetic judgment). Ask **"what's the deviation between my model and the mesh?"** (a quantitative number).

Fit a surface → measure max/mean deviation against the mesh → adjust → repeat until within tolerance. It's optimization, not art. Every stage of this pipeline ends with a number, not a feeling.

## Audience

Not just scanner owners. **Anyone with a mesh:**
- 3D scanner users (Revopoint, Creality, Einstar, photogrammetry)
- Anyone who downloads STLs and wants to *modify* them
- Game devs, animators, video producers working with mesh assets

Phase 1 targets 3D printing (where we have hardware and can prove fit physically). The same pipeline extends to animation, game dev, and video production — Phase 2.

## FOSS commitment

Everything in this pipeline is free and open source. No paywalled tools, no "take our word for it," no license servers, no account gates. Every claim is verifiable by running the tools yourself.

| Stage tool | License | Role |
|---|---|---|
| MeshLab | GPL | Mesh cleanup, repair, decimation |
| CloudCompare | GPL | Alignment, cloud-to-mesh deviation measurement |
| FreeCAD | LGPL | Parametric CAD, STEP/FCStd output |
| MeshToFeatures | LGPL-2.1-or-later | FreeCAD workbench: STL → PartDesign bodies (prismatic) |
| Detessellate | (verify during build) | FreeCAD macro set: clean-mesh → parametric |
| trimesh | MIT | Python mesh analysis, measurement automation |
| Open3D | MIT | Point cloud processing, surface reconstruction |
| manifold3d | Apache-2.0 | Code-based CAD backend (our existing stack) |
| build123d | Apache-2.0 | Python parametric CAD on OpenCASCADE |
| Blender | GPL | Organic cleanup only — never the CAD authority |

**Versions:** verify during build. Never assume "current" matches what was tested. Record exact versions in every project's manifest.

---

## Pipeline stages

### Stage 0 — Intake

**Input:** One mesh file. Accepted formats: STL, PLY, OBJ, 3MF.

**Source types:**
- `scanner` — from a 3D scanner (Revopoint, Creality Raptor, etc.)
- `download` — from a model repository (Printables, MakerWorld, Thingiverse, etc.)
- `photogrammetry` — from phone/camera reconstruction

**Intake checklist:**
1. Copy the original file into `input/` — **never modify the original.**
2. Record the source manifest (`manifest.json`): filename, source type, scanner model (if any), units, date, who provided it.
3. **Units check:** confirm the mesh is in millimeters. Scanners and downloads disagree on units constantly. Measure a known feature or compare against a physical dimension. Wrong units here corrupt everything downstream — verify before proceeding.
4. **Provenance (downloads):** record the source URL and license. Do not redistribute someone else's mesh without checking their license. The CAD you *build from* it is your work; the mesh itself isn't.

**Output:** `input/<name>.stl` (untouched), `manifest.json` started.

**Automation:** Fully scriptable (Python + trimesh). File copy, format detection, bounding-box report.

---

### Stage 1 — Cleanup

**Goal:** A watertight, manifold mesh with noise removed. Garbage in = garbage CAD.

**Steps (MeshLab or scripted):**
1. Remove isolated components (floating triangles that aren't the part).
2. Remove duplicate faces and unreferenced vertices.
3. Fill holes (small ones only — large missing regions are flagged, not invented).
4. Remove noise: Laplacian smoothing, conservative (1–2 iterations). **Do not over-smooth** — you're erasing real features.
5. Recompute normals.
6. Decimate if >500k faces (keep detail on features, simplify flat areas). Target: workable size, not minimal size.

**The honest rule:** If the scan is too noisy or has large occluded regions, **stop and rescan.** No pipeline fixes missing data. Flag it in the manifest (`quality: needs-rescan`) and go back to the scanner.

**Output:** `work/<name>_clean.stl`

**Automation:** Fully scriptable via MeshLab's `meshlabserver`/pymeshlab or trimesh + Open3D. This stage should be one command.

---

### Stage 2 — Analysis

**Goal:** Extract everything measurable from the mesh *before* any CAD is built. This is the measurement report the rebuild is judged against.

**Automated extraction (Python + trimesh/Open3D):**
1. **Bounding box:** X/Y/Z extents in mm.
2. **Principal axes:** orient the part to a sensible coordinate frame (longest axis = X, etc.). Record the transform.
3. **Planar face detection:** find faces whose normals cluster — these are the flat faces of prismatic parts. Report count and orientations.
4. **Cylindrical hole detection:** find circular openings. Report center positions, diameters, axes. (Hough-style or RANSAC cylinder fitting on boundary loops.)
5. **Symmetry detection:** check for mirror planes. If the part is symmetric, the CAD only needs to model half.
6. **Wall thickness estimate:** ray-cast sampling, report min/mean. Flags thin regions that may not print.

**Output:** `analysis/<name>_measurements.json` — every number the CAD must match.

**Automation:** Mostly scriptable. Hole detection on noisy scans may need manual confirmation. **Track classification:** after analysis, decide prismatic vs. organic:
- **Prismatic** (mostly flat faces, cylinders, clear features) → Track A
- **Organic** (freeform curves, no clear analytic features) → Track B
- **Mixed** (prismatic base + organic details) → Track A for the base, Track B for the details, assembled in FreeCAD

**The track decision is recorded in the manifest and is reviewable.** Wrong track = wrong tools = bad output.

---

### Stage 3A — Prismatic rebuild (Track A)

**Goal:** A fully parametric CAD model built from measured features.

**Three routes, in order of preference:**

**Route 1 — MeshToFeatures (automated).** The [MeshToFeatures](https://github.com/MasoudMiM/MeshToFeatures) FreeCAD workbench (LGPL-2.1) reverse-engineers STL meshes of prismatic parts into editable PartDesign bodies. Its geometry core is FreeCAD-free (numpy/scipy/trimesh), so the fitting pipeline is unit-testable. Best for: clean, CAD-derived meshes (downloaded STLs that were originally modeled in CAD).

**Route 2 — Detessellate macros (semi-automated).** The [Detessellate](https://github.com/designweaver3d/detessellate) FreeCAD macro set extracts faces, edges, and sketches from meshes and rebuilds them as parametric solids. **Limitation (documented by the author):** designed for clean, manifold, CAD-derived meshes — *not* 3D scans, *not* organic shapes, *not* noisy meshes. Use for downloaded STLs, not raw scans.

**Route 3 — Measure-and-remodel (manual, always works).** Import the mesh into FreeCAD as a reference. Build the part fresh in Part Design: sketch → pad → pocket → fillet, measuring every dimension from the mesh. This is the fallback that never fails and the standard for scanned parts. Slower, but the output is clean design-intent CAD.

**Our code-based route (manifold3d / build123d):** For parts we generate programmatically (brackets, adapters, spacers), skip FreeCAD entirely — measure the mesh, write the Python, generate STEP + STL. This is our existing stack and the fastest path for simple parts.

**Design-intent rule:** The CAD doesn't have to match every triangle. It has to match every *functional* dimension: mating faces, hole positions/diameters, wall thicknesses, overall envelope. Cosmetic noise in the scan is not design intent — don't model it.

**Output:** `cad/<name>.FCStd` (FreeCAD) and/or `cad/<name>.py` (code-generated), plus `cad/<name>.step`.

---

### Stage 3B — Organic rebuild (Track B)

**Goal:** A surface/solid model whose deviation from the mesh is within tolerance. **This is Dennis's insight as a procedure.**

**The deviation loop:**
1. **Fit:** Build an initial surface. Options:
   - FreeCAD Curves workbench: Gordon surfaces, sweep on 2 rails (manual, guided)
   - Section-loft: cut the mesh with parallel planes → extract section curves → loft through them (semi-automated, works well for symmetric organic parts)
   - Open3D Poisson reconstruction → convert to solid (automated, but output is still mesh-like — use as reference, not final CAD)
2. **Measure:** CloudCompare cloud-to-mesh distance. Sample points from your CAD surface, compute distance to the input mesh. Report **max deviation** and **mean deviation**.
3. **Judge:** Is max deviation within tolerance? (Default: 0.3mm for print-fit parts, 0.1mm for mating surfaces — configurable per project.)
4. **Iterate:** If no, refine the surface (more sections, tighter fits, manual adjustment) and measure again.

**The loop terminates on a number, not a feeling.** Record every iteration's deviation in the manifest.

**Output:** `cad/<name>.FCStd` + `cad/<name>.step` + `verification/deviation_report.txt` with the iteration history.

**Honest limits:** This track is semi-automated at best. Freeform surfacing needs human guidance on *where* to put sections and *which* regions matter. The pipeline automates the measurement and bookkeeping; the surface design is assisted, not automatic. **What the pipeline guarantees:** you'll know exactly how far off your model is, everywhere, in numbers.

---

### Stage 4 — Verification

**Goal:** Prove the CAD matches the mesh. Every project ends here, no exceptions.

**Checks:**
1. **Deviation analysis (mandatory):** CloudCompare cloud-to-mesh distance between final CAD (tessellated) and the *original input mesh* (not the cleaned one — verify against the source). Report max, mean, 95th percentile. **Pass/fail against the project tolerance.**
2. **Dimension check:** every measurement in `analysis/<name>_measurements.json` re-measured on the CAD. All within tolerance? List any that aren't, with the delta.
3. **Solid validity:** FreeCAD geometry check — is it a valid solid? No open shells, no self-intersections.
4. **Printability (Phase 1):** manifold STL, no inverted normals, wall thickness ≥ nozzle × 2 (configurable), overhangs flagged.

**Output:** `verification/<name>_report.md` — the complete verification record.

**The rule:** No verification report = no done. A CAD file without its deviation numbers is just a guess.

---

### Stage 5 — Output

**Deliverables (every project produces all of these):**
- `output/<name>.step` — parametric CAD, the primary deliverable (editable in FreeCAD, SolidWorks, Fusion, etc.)
- `output/<name>.stl` — print-ready mesh derived from the CAD (not the original scan)
- `output/<name>_drawing.pdf` — 2D drawing with key dimensions (for our workflow: red-pen review before manufacturing)
- `verification/<name>_report.md` — deviation numbers, dimension checks, pass/fail
- `manifest.json` — complete project record (see schema below)

**For 3D printing (Phase 1):** the STL goes through our normal slicer workflow. Physical fit test is the final verification — the numbers predict it, the print proves it.

---

## Project structure (data schema)

Every mesh-to-CAD project uses this layout:

```
<project>/
├── manifest.json          # source, track decision, tolerances, tool versions, iteration log
├── input/
│   └── <name>.stl         # ORIGINAL — never modified
├── work/
│   └── <name>_clean.stl   # cleaned mesh
├── analysis/
│   └── <name>_measurements.json
├── cad/
│   ├── <name>.FCStd       # FreeCAD parametric model (if used)
│   ├── <name>.py          # code-generated model (if used)
│   └── <name>.step        # exported STEP
├── verification/
│   ├── deviation_report.txt
│   └── <name>_report.md
└── output/
    ├── <name>.step
    ├── <name>.stl
    └── <name>_drawing.pdf
```

**manifest.json schema (v1):**
```json
{
  "project": "bracket-01",
  "source": {
    "type": "scanner|download|photogrammetry",
    "original_file": "input/bracket-01.stl",
    "scanner": "Creality CR-Scan Raptor Pro",
    "source_url": "(downloads only)",
    "source_license": "(downloads only)",
    "date": "2026-10-02",
    "units": "mm"
  },
  "quality": "clean|noisy|needs-rescan",
  "track": "prismatic|organic|mixed",
  "track_reason": "mostly planar faces, 4 holes detected",
  "tolerance_mm": {
    "default": 0.3,
    "mating_surfaces": 0.1
  },
  "tools": {
    "meshlab": "2023.12",
    "cloudcompare": "2.13",
    "freecad": "1.0.1",
    "trimesh": "4.x",
    "meshtofeatures": "commit-hash"
  },
  "iterations": [
    {"stage": "3B", "attempt": 1, "max_dev_mm": 1.2, "mean_dev_mm": 0.4, "result": "fail"},
    {"stage": "3B", "attempt": 2, "max_dev_mm": 0.2, "mean_dev_mm": 0.08, "result": "pass"}
  ],
  "verification": "pass|fail",
  "notes": ""
}
```

---

## Automation vs. manual (honest matrix)

| Stage | Automated now | Needs human | Notes |
|---|---|---|---|
| 0 Intake | ✅ file handling, bbox | units check, license check | Units kill — verify physically |
| 1 Cleanup | ✅ scriptable | rescan decision | Can't fix missing data |
| 2 Analysis | ✅ bbox, planes, symmetry | hole confirmation on noisy scans | RANSAC needs clean data |
| 3A Prismatic | ✅ MeshToFeatures (clean meshes) | measure-and-remodel (scans) | Scans → manual; downloads → auto |
| 3B Organic | ⚠️ measurement loop | surface design decisions | Numbers are auto; shapes are assisted |
| 4 Verification | ✅ deviation, dimensions, validity | interpreting failures | Pass/fail is automatic |
| 5 Output | ✅ export all formats | drawing review | Red-pen before manufacturing |

**What we're NOT claiming:** One-click scan-to-CAD. That doesn't exist in FOSS and barely exists in $20k software. What we're claiming: a repeatable process where every step is documented, every decision is recorded, and the output is verified with numbers.

---

## SOP (stranger-proof)

### You need
- FreeCAD (1.0+) with MeshToFeatures workbench installed
- MeshLab
- CloudCompare
- Python 3 with trimesh, numpy, scipy
- A mesh file (scan or download)

### Steps
1. **Create the project folder** using the structure above. Copy your mesh into `input/`. Don't rename it yet — record the original name in the manifest.
2. **Fill in `manifest.json`** — source type, date, units. If it's a download, paste the URL and license.
3. **Verify units.** Run `scripts/check_units.py input/<file>` — it measures the bounding-box diagonal and suggests whether the file is in mm, meters, or um/inches, with a confidence level. Confirm or reject its suggestion (it never rescales silently), then record the scale factor in the manifest. Wrong units here corrupt everything downstream — verify before proceeding.
4. **Clean the mesh** (Stage 1). First run `scripts/quality_gate.py input/<file>` — it reports watertightness, hole-fill area fraction, noise floor, and component count, with a verdict: `clean`, `noisy`, or `needs-rescan` (exit code 2). More than 10 disconnected components forces `noisy` — a fragmented scan must have its real part isolated before you trust it. If `needs-rescan`, stop and go back to the scanner — no pipeline fixes missing data. Otherwise proceed to MeshLab: remove isolated pieces → remove duplicates → fill small holes → light smoothing → recompute normals. Save to `work/`.
5. **Run analysis** (Stage 2). Run `scripts/analyze.py work/<file>`: bounding box, planar faces, cylindrical walls (bores/extrusions count as prismatic evidence), symmetry, hole-detection status. It records a **track decision** (prismatic/organic/mixed) with confidence — high-confidence decisions proceed without review; medium-confidence ones get human eyes. It also writes an **aligned copy** (`<name>_aligned.stl>`, principal axes on XYZ) plus the 4x4 alignment matrix in the JSON, so every downstream stage works in a canonical frame. Standalone, it writes `<name>_measurements.json` and `<name>_aligned.stl` **next to the input file**; the `mesh-to-cad` CLI instead organizes them into the project's `analysis/` folder. Check `hole_detection.status` in the JSON — `failed` means the step didn't run, not "no holes."
6. **Rebuild** (Stage 3A or 3B):
   - *Prismatic, clean mesh:* Try MeshToFeatures in FreeCAD first. If it handles it, you're done — skip to verification.
   - *Prismatic, scan:* Import mesh as reference in FreeCAD. Build it fresh in Part Design, measuring from the mesh. Or write a Python script (manifold3d/build123d) if it's simple.
   - *Organic:* Section-loft or Curves workbench. Run the deviation loop — fit, measure with `scripts/deviation.py`, iterate until max deviation is within your tolerance.
7. **Verify** (Stage 4). Run `scripts/deviation.py cad/<model>.stl input/<original>.stl --tolerance <mm>`: cloud-to-mesh distance via CloudCompare, reporting max/mean/p95 and pass/fail. Always verify against the *original input mesh* (not the cleaned one — verify against the source). Check every dimension from Stage 2. Run FreeCAD geometry check. Write the report.
8. **Export** (Stage 5). STEP, STL, drawing PDF. All in `output/`.
9. **If 3D printing:** slice the *output* STL (never the scan), print, fit-test. Physical fit is the final word.

---

## Failure modes (known issues)

Document failures here as they're found. Starter list:

1. **Wrong units on import.** Mesh is in meters or inches, CAD comes out 25.4x or 1000x wrong. *Fix: verify units at intake, always.*
2. **Over-smoothing erases features.** Aggressive Laplacian smoothing rounds off edges and shrinks holes. *Fix: 1–2 iterations max, compare before/after.*
3. **MeshToFeatures fails on noisy scans.** It's built for clean CAD-derived meshes. *Fix: use measure-and-remodel for scans.*
4. **Detessellate on organic shapes.** Documented limitation — not for scans or organic. *Fix: don't.*
5. **Inventing missing data.** Hole-filling on large gaps creates geometry that was never scanned. *Fix: flag large gaps, rescan. Never ship invented geometry as verified.*
6. **Verifying against the cleaned mesh instead of the original.** The cleaned mesh has already been altered — deviation numbers look better than they are. *Fix: always verify against `input/`, never `work/`.*
7. **Download license violations.** Remixing someone's CC-NC mesh into a product. *Fix: check the license at intake.*

---

## Contributing

This pipeline is user-contributable by default:
- **New scripts** go in `scripts/` with a docstring explaining inputs, outputs, and the stage they serve.
- **New tool evaluations** go in `evals/` — what you tried, what version, what worked, what didn't. Failed evaluations are welcome (the wreckage teaches).
- **Bug reports** include the manifest.json and the stage that failed.
- All contributions are FOSS-licensed (LGPL-2.1-or-later to match the most restrictive tool in the chain, or more permissive).

---

## Roadmap

### Phase 1 — 3D printing (now)
Prove the pipeline on real parts. Scanner → CAD → print → fit-test. Target users: makers, printer owners, anyone modifying downloaded STLs. Success metric: printed parts that fit, with deviation reports to prove it.

### Phase 2 — Media expansion
Same pipeline, new outputs: game-ready topology (retopology guidance), animation-friendly rigs (Blender handoff), video production assets. The mesh-to-CAD core doesn't change — the output stage grows format options (FBX, glTF, USD).

### Phase 3 — Automation push
As the deviation loop gets more project data, automate more of Track B: auto-sectioning, auto-surface-fitting with tolerance guarantees. The measurement infrastructure from Phase 1 is what makes this possible — you can't automate what you can't measure.

---

## Related

- GruntAndMuse pipeline catalog (forthcoming) — this is a flagship entry
- Raptor CAD pipeline prep: `~/workspace/raptor-cad-pipeline/prep-plan.md` — scanner-specific companion
- Standing rule: verify tool versions during build; record exact versions in every manifest
- Standing rule: if you can't verify something, say so and why

---

*Drafted 2026-10-02. Status: plan — not yet proven on real hardware. The Raptor Pro arrival is the first live test.*
