# Mesh-to-CAD Automation Roadmap

**Question:** which manual steps in the pipeline can be automated, and how?

**Method:** every step marked manual or semi-automated in PIPELINE.md was broken into its atomic human actions. Each action was then tested against: does an existing FOSS tool do this with scripting? Could custom code do it with known algorithms? Or is it genuine human judgment?

**Dennis's rule applies throughout:** verified claims are marked. Unverified claims say so and say why.

---

## Master ranking

| # | Step (pipeline stage) | What the human does | Rank | Why |
|---|---|---|---|---|
| 1 | Units check (Stage 0) | Eyeballs bbox, decides mm vs m vs in | **Automatable now** | Heuristic + confidence score; human confirms |
| 2 | License check (Stage 0) | Reads license on download page | **Custom code** | Scrape license badge from source URL |
| 3 | Rescan decision (Stage 1) | Judges "too noisy / too many holes" | **Automatable now** | Quantifiable metrics + thresholds; human overrides |
| 4 | Hole confirmation, noisy scans (Stage 2) | Eyeballs suspected holes | **Custom code** | RANSAC cylinder fitting on sections (already planned as `detect_holes.py`) |
| 5 | Track decision (Stage 2) | Reviews suggestion, picks prismatic/organic/mixed | **Automatable now** | `analyze.py` already suggests it; promote to decision with confidence + override |
| 6 | Principal-axis alignment (Stage 2) | — (not yet applied) | **Automatable now** | `analyze.py` computes PCA; apply the transform, save it |
| 7 | MeshToFeatures on scans (Stage 3A) | Falls back to manual measure-and-remodel because MTF fails on noisy scans | **Custom code** | Denoise → run MTF core headless → snap → generate code. The core is importable Python; the gap is the driver, not the math |
| 8 | Measure-and-remodel (Stage 3A) | Measures mesh, writes CAD by hand | **Custom code** | Primitive list → build123d code generator. The measuring is already automated (Stage 2); the CAD-writing is templating |
| 9 | Section placement, organic (Stage 3B) | Decides where to cut sections | **Automatable now** | Uniform sectioning along principal axis via `trimesh.section()` |
| 10 | Section curve cleanup (Stage 3B) | Smooths jagged section polylines | **Custom code** | B-spline fit via `scipy.interpolate.splprep` |
| 11 | Loft through sections (Stage 3B) | Builds loft manually in FreeCAD | **Automatable now** | build123d/FreeCAD loft from wires is scriptable |
| 12 | Deviation measurement (Stage 3B/4) | Runs CloudCompare GUI, reads numbers | **Automatable now** | `C2M_DIST` CLI flag verified real (see below) |
| 13 | Iteration: refine where it's off (Stage 3B) | Eyeballs deviation heatmap, adds detail | **Custom code** | Adaptive refinement: deviation hotspots → auto-place new sections |
| 14 | Interpreting verification failures (Stage 4) | Figures out *why* it failed | **Custom code** | Rule-based diagnostics mapping failure signatures to fixes |
| 15 | Drawing completeness (Stage 5) | Checks all dims made it onto the drawing | **Custom code** | Cross-check measurements JSON vs. TechDraw dimension list |
| 16 | Red-pen sign-off (Stage 5) | Dennis reviews and approves | **Human forever** | Deliberate human gate by design |
| 17 | Which regions are "critical" (Stage 3B) | Marks mating surfaces, functional dims | **Human** (assisted) | Human marks; everything downstream is auto |
| 18 | Design-intent on ambiguous features (Stage 3A) | "Is this bump a feature or noise?" | **Hard** | Needs manufacturing-context inference; partial heuristics possible |
| 19 | Guaranteed-tolerance organic fit, arbitrary topology | — (nobody does this) | **Hard** | Active research area; our deviation loop bounds the error empirically instead |

**Verified during this analysis:**
- CloudCompare `-C2M_DIST` is a real CLI flag (changelog: "C2M_DIST: cloud to mesh distance computation"; also accepts 2 meshes, using first mesh's vertices as the compared cloud). Source: CloudCompare CHANGELOG, checked 2026-10-02.
- MeshToFeatures exists at `github.com/MasoudMiM/MeshToFeatures`, v0.17.x, actively maintained (README updated ~12 days before check), LGPL-2.1-or-later, geometry core is FreeCAD-free (numpy/scipy/trimesh/shapely), 450+ pytest suite runs without FreeCAD, headless via `freecadcmd`. Source: repo README + VERIFY.md, checked 2026-10-02.

**Not verified (verify during build):**
- Exact CloudCompare CLI syntax for extracting scalar-field statistics programmatically (parsing approach sketched below; the precise flags/output format need a live test).
- pymeshlab API version for scripted MeshLab (well-established library; pin version at build).
- `trimesh.section()` / `scipy.interpolate.splprep` / Open3D Taubin smoothing — standard APIs from training knowledge, not live-tested here.

---

## "Automatable now" — script immediately, no new algorithms

These need only glue code around existing tools. Highest ROI per hour.

### A1. Unit heuristic (`scripts/check_units.py`, ~50 lines)
```
bbox_diagonal = <from analyze.py>
if diagonal < 5:      likely meters    → suggest scale ×1000, confidence high
elif diagonal < 2000: likely mm       → suggest scale ×1,   confidence high
else:                 likely µm/inch  → suggest scale ÷1000 or ÷25.4, confidence medium
```
Output: suggested scale factor + confidence + the raw numbers. Human confirms with one keystroke. The failure mode it prevents (1000× wrong CAD) is the most expensive cheap mistake in the pipeline.

### A2. Quality gate (`scripts/quality_gate.py`, ~150 lines)
Computable metrics, no judgment:
- `is_watertight` (trimesh — already in analyze.py)
- Hole-fill area fraction: run fill, compare face count before/after → filled area / total area
- Noise estimate: mean vertex distance between mesh and its Taubin-smoothed copy (Open3D `filter_smooth_taubin`)
- Isolated component count (trimesh `split()`)

Thresholds (tune on real data):
- Filled-hole area > 5% of surface → `needs-rescan`
- Mean noise > 0.3mm → `noisy` (proceed with caution, Route 3)
- Otherwise → `clean`

The human override stays, but the default is now a number, not a feeling.

### A3. Track decision + axis alignment (extend `analyze.py`, ~40 lines)
`analyze.py` already computes `planar_fraction` and suggests a track. Promote it: write the suggestion into the manifest as the decision, with confidence (`high` if planar_fraction > 0.8 or < 0.2, `medium` otherwise). Human overrides only the medium cases.

Apply the PCA transform: rotate mesh so principal axes → XYZ, save the 4×4 matrix in the manifest. Every downstream stage then works in a sane frame. This is pure linear algebra, already computed, just not applied.

### A4. Headless MeshToFeatures (verify-then-script)
The MTF core is importable Python. The workbench runs headless via `freecadcmd`. So the "automated" Route 1 claim in PIPELINE.md is real — but nobody has wrapped it in a one-command driver yet. Task: write `scripts/mtf_headless.py` that takes a clean STL, runs the MTF pipeline via freecadcmd, and drops the resulting PartDesign body + snap audit into `cad/`. Verify the exact invocation during build (the smoke-test script in their repo is the starting point).

### A5. CloudCompare deviation via CLI (the measurement backbone)
Verified: `-C2M_DIST` computes cloud-to-mesh distances from the command line. The pipeline's entire "measure the number" step becomes:
```bash
CloudCompare -SILENT \
  -O cad_model.stl -O input/original.stl \
  -C2M_DIST -MAX_DIST 5 \
  -SAVE_CLOUDS
# then parse the output cloud's scalar field for max/mean/95th percentile
```
Parsing: read the output cloud (BIN or ASCII), extract the distance scalar field with numpy, compute statistics. The exact output format needs a live test — mark "verify during build," but the flag itself is confirmed real.

This one command automates the measurement half of every deviation loop in Stages 3B and 4.

---

## "Automatable with custom code" — feasible, needs writing

Each item below is sketched to the level where a developer can pick it up. No ML hand-waving; all named algorithms with known implementations.

### C1. License scraper (`scripts/check_license.py`, ~100 lines)
**Problem:** Stage 0 requires recording the download license; currently manual.
**Approach:** `requests` + `beautifulsoup4`. Given a source URL:
- Printables: license badge in page meta (`og:` tags or the license icon alt-text)
- MakerWorld / Thingiverse: same pattern, different selectors
- Output: `{license: "CC-BY-NC-SA", redistribution_ok: false, commercial_ok: false}`

**Caveat:** page layouts change; this needs maintenance. Mitigation: fail loudly (not silently) when the parse finds nothing — "could not determine license, check manually." A wrong license is worse than no license.

### C2. RANSAC hole detection (`scripts/detect_holes.py`, ~200 lines)
**Problem:** `analyze.py` punts on through-holes in watertight meshes ("forthcoming").
**Approach:**
1. Slice the mesh with planes perpendicular to each principal axis (trimesh `section()`), at ~20 evenly spaced positions per axis.
2. On each 2D section, run circle RANSAC: sample 3 points, fit circle, count inliers within 0.1mm, iterate ~500 times, keep best.
3. Cluster detected circles across adjacent sections: same (x, y) center within tolerance + consistent radius across ≥3 consecutive sections = a cylindrical hole.
4. Output per hole: center (3D), axis vector, diameter, depth, confidence (inlier ratio × section count).

**Why it works:** through-holes are cylinders; cylinders section into circles. Noisy scans blur the circles, but RANSAC is noise-tolerant by design — that's what the R is for. False positives (fillets, grooves) are filtered by the multi-section consistency check.

### C3. Denoise → MTF core driver (`scripts/mtf_scan_driver.py`, ~300 lines)
**Problem:** MeshToFeatures fails on noisy scans; humans fall back to manual measure-and-remodel.
**Approach — the gap is a driver, not new math:**
1. **Denoise:** Open3D Taubin smoothing (`filter_smooth_taubin`, ~10 iterations) or bilateral filtering via pymeshlab. Taubin preserves volume better than Laplacian; bilateral preserves edges better than both. Try bilateral first, fall back to Taubin.
2. **Fit:** `import meshtofeatures` (the FreeCAD-free core) → `reconstruct(denoised_mesh)` → recognized primitives (planes, cylinders, cones, spheres) + snap audit trail.
3. **Emit:** write `analysis/<name>_primitives.json` — every recognized surface with fitted parameters, snap decisions, and unrecognized-area fraction.
4. **Build:** feed the primitives JSON into C4 (below).

**Why this is feasible:** the MTF core already does region-growing segmentation, geometric fitting, parameter snapping, and feature detection, with 450+ tests. We're not reimplementing fitting — we're preprocessing the input so the existing fitter can handle scans, then driving it headless. If unrecognized-area fraction > 30%, fall back to manual with a clear report (the driver tells you *which regions* it couldn't handle).

### C4. Primitive → CAD code generator (`scripts/prims_to_cad.py`, ~200 lines)
**Problem:** a human currently translates "4 holes at these positions" into CAD operations by hand.
**Approach:** template-based code generation. Input: primitives JSON (from C2/C3) or measurements JSON (from analyze.py).
- Start: bounding-box solid (`build123d.Solid.make_box` or `manifold3d` cube).
- For each plane pair (parallel, opposing): already implied by the box; verify extents match.
- For each cylinder with axis through the solid: subtract (`Hole` in build123d, `cylinder` difference in manifold3d).
- For each cylinder protruding from a face: add boss.
- Output: `<name>.py` (the build123d/manifold3d script — human-readable, editable) + exported STEP.

**This is the "measure-and-remodel" step with the computer doing both halves.** The generated `.py` is itself parametric — the human can tweak numbers afterward. The design-intent snapping (round 9.97mm → 10mm) comes from the MTF snap audit, not from this script.

### C5. Section → smoothed spline → loft (`scripts/section_loft.py`, ~250 lines)
**Problem:** Stage 3B section-loft is manual in FreeCAD.
**Approach:**
1. Section the mesh at N planes along the longest principal axis (`trimesh.section()`, N configurable, default 12).
2. Each section returns a polyline (possibly multiple disjoint loops — handle each).
3. Fit a closed B-spline to each polyline: `scipy.interpolate.splprep(s, per=1)` with smoothing factor tied to the mesh noise estimate (noisier mesh → more smoothing). Resample to uniform point count.
4. Build `build123d.Spline` wires from the smoothed points → `build123d.Solid.loft(wires)`.
5. Output: solid + STEP.

**Failure handling:** if a section has a topology change (1 loop → 2 loops between adjacent sections), flag it — lofting across topology changes needs human guidance on correspondence. The script reports *where* it happened; the human resolves only that region.

### C6. Adaptive deviation loop (`scripts/deviation_loop.py`, ~400 lines)
**Problem:** Stage 3B's "refine where it's off" is human eyeballing a heatmap.
**Approach — Dennis's insight as a control loop:**
```
tolerance = manifest.tolerance_mm.default
sections = initial_uniform_sections(mesh, n=8)
loop:
    solid = loft(sections)                          # C5
    stl = export(solid)
    dev = c2m_distance(stl, input_mesh)              # A5
    record(max, mean, p95)
    if max <= tolerance: break → PASS
    if iterations > max_iter: break → FAIL with report
    hotspots = regions where dev > tolerance        # from scalar field
    sections += place_sections_at(hotspots)         # adaptive refinement
    iterations += 1
```

**`place_sections_at`:** for each hotspot cluster (connected region of high-deviation sample points), insert a new section plane at the cluster centroid, perpendicular to the local surface normal direction. This is adaptive mesh refinement applied to section placement — put effort where the error is.

**Termination is on a number** (max deviation ≤ tolerance), exactly as Dennis specified. The iteration log goes into the manifest. If it fails to converge, the report shows *where* — the human then intervenes only on the unconverged regions, not the whole part.

**This is the highest-leverage script in the roadmap.** It turns Track B from "assisted" to "supervised" — the human sets tolerance and reviews, the loop does the fitting.

### C7. Verification diagnostics (`scripts/diagnose.py`, ~150 lines)
**Problem:** Stage 4 pass/fail is automatic, but understanding *why* it failed is manual.
**Approach:** rule-based expert system over the verification report:
- Max deviation localized to <5% of surface → "refine region near (x,y,z); consider +2 sections"
- Max deviation widespread → "global fit issue; increase section count or check track decision"
- Dimension mismatch on hole diameter → "hole fit off by {delta}mm; check C2 hole detection confidence"
- Solid invalid (FreeCAD check) → surface the specific error (self-intersection at…, open shell near…)
- Wall thickness below minimum → "region at (x,y,z) is {t}mm, minimum is {min}mm"
- Deviation concentrated at sharp edges → "expected; edges are not design intent unless marked critical"

Output: human-readable suggestions ordered by impact. Not magic — just the troubleshooting table the pipeline doc would grow anyway, executed by code.

### C8. Drawing completeness check (`scripts/check_drawing.py`, ~100 lines)
**Problem:** Stage 5 requires every critical dimension on the 2D drawing; currently eyeballed.
**Approach:** parse `analysis/<name>_measurements.json` (critical dims) and the TechDraw page (via FreeCAD Python: iterate `DrawViewDimension` objects, read their referenced geometry). Set-difference → list of missing dimensions. Output: "these 3 dimensions from the measurements report are not on the drawing: hole Ø12 at (45, 30), wall thickness 3.2mm…"

The red-pen review itself stays human (C-drawings are Dennis's sign-off gate by design). This script just makes sure the review isn't wasted on "you forgot a dimension."

---

## Suggested build order (dependencies first)

```
A1 units ──┐
A2 quality ─┼─→ Stage 0/1 solid ─→ C2 holes ─→ C3 MTF driver ─→ C4 prims→CAD
A3 track/axes ┘                         │
                                        ├─→ C5 section loft ─→ C6 deviation loop
A4 MTF headless ────────────────────────┘         │
A5 C2M CLI ───────────────────────────────────────┘
                                        ↓
                                  C7 diagnostics ─→ C8 drawing check
C1 license ──→ (independent, anytime)
```

**Phase 1 (weekend-sized):** A1, A2, A3, A5. Pure glue code, no new algorithms. Immediately makes Stages 0, 1, 2, and the measurement half of 3B/4 one-command operations.

**Phase 2:** C2 (holes), C5 (section loft). Unlocks automated Track B scaffolding.

**Phase 3:** C3 (MTF scan driver), C4 (prims→CAD). Unlocks automated Track A on scans — the biggest manual block in the pipeline.

**Phase 4:** C6 (deviation loop). The flagship — supervised organic fitting. Depends on C5 + A5.

**Phase 5:** C7, C8, C1. Polish and completeness.

**Estimated total:** ~2,000 lines of Python across 13 scripts. No new research, no ML, no breakthroughs required. Every algorithm named above has a reference implementation in a FOSS library.

---

## Honest boundary: what stays human

1. **Red-pen sign-off (Stage 5).** Deliberate. It's Dennis's manufacturing gate; automating it would remove the point.
2. **Marking critical regions (Stage 3B).** "This face mates to another part" is project context, not mesh data. The human marks it once; everything downstream respects the tighter tolerance automatically.
3. **Borderline rescan calls.** The quality gate (A2) handles the clear cases. When metrics sit exactly on a threshold, a human who knows the part's function makes a better call than a threshold.
4. **Design-intent on ambiguous features.** "Is this bump functional or a print artifact?" gets *better* with the snap audit trail (C3 reports what it rounded and why), but genuinely ambiguous cases need someone who knows what the part does.
5. **Guaranteed-tolerance organic fitting on arbitrary topology.** The deviation loop (C6) bounds error *empirically* — it tells you the number. A mathematical *guarantee* for arbitrary shapes is still research territory. For 3D printing, the empirical number plus a physical fit test is the right standard anyway.

**What this roadmap does NOT claim:** one-click scan-to-CAD. What it claims: every manual step either becomes a script, becomes a supervised loop that terminates on a number, or is identified as genuinely human — with the reason stated.

---

*Analysis 2026-10-02. Tool claims verified where marked; everything else follows Dennis's rule: say what's unverified and why. Next step: Phase 1 scripts, then prove it on the Raptor Pro's first real scan.*
