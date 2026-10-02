# Competitive Landscape — FOSS Scan-to-CAD / Mesh Processing

**Date:** 2026-10-02
**Researched by:** Muninn (subagent), for the mesh-to-cad project (https://github.com/GruntAndMuse/mesh-to-cad)
**Purpose:** Know where mesh-to-cad fits and what gap it can own. This is NOT to copy — it's positioning.

## URL verification

Every tool URL below was checked live on 2026-10-02 (successful fetch or HTTP 200).
Three exceptions, marked honestly where cited:

- `reddit.com` and `old.reddit.com` are blocked by policy in this research environment — subreddit links are listed from knowledge + corroborating sources, not live-verified.
- `forum.freecad.org` is behind an Anubis bot-check in this environment (humans get through fine).
- The Facebook group link below appears in a YouTube video description (not live-fetched).

---

## 1. Comparable tools

### MeshLab (+ PyMeshLab) — the mesh surgeon's scalpel
- **What it is:** The classic open-source mesh processing system from the Visual Computing Lab (CNR-ISTI). Cleans, repairs, remeshes, decimates, smooths, reconstructs (Poisson, ball-pivoting), inspects, converts.
- **License:** GPL-3.0 (verified live in repo README, 2026-10-02)
- **Alive:** Yes. 10,937 commits, 5,848 stars, 27 releases; the `2025.07` release line is packaged for university clusters today. PyMeshLab (Python bindings) is also GPL-3.0 and actively maintained on conda-forge.
- **Does well:** Batch mesh cleanup (crucial for dirty scans), decimation, hole filling, Poisson reconstruction, scriptable via PyMeshLab.
- **Falls short:** It stops at the mesh. There is no path to parametric CAD — no feature recognition, no B-rep/STEP output, no "rebuild the part." GPL-3.0 is viral, so any bundled use infects the whole project.
- **URL:** https://github.com/cnr-isti-vclab/meshlab

### CloudCompare — the point-cloud king
- **What it is:** 3D point-cloud (and triangular-mesh) processing, originally built for change detection between laser scans. Famous for its cloud-to-mesh (C2M) distance/deviation analysis — which is exactly what mesh-to-cad's `deviation.py` already shells out to.
- **License:** GPL-3.0 (README links the GPL text; verified live, 2026-10-02)
- **Alive:** Yes. 5,387 commits, 4,781 stars, 34 releases; v2.14 beta builds were being tested Sep 2026.
- **Does well:** Huge point clouds (10M+ points), registration, alignment, deviation analysis, tons of formats (E57, LAS, PTS…).
- **Falls short:** Treats triangular mesh as a second-class citizen (it's a point-cloud tool). Zero CAD authoring, zero parametric rebuild, interactive GUI-first. GPL again.
- **URL:** https://github.com/cloudcompare/cloudcompare

### FreeCAD — the FOSS CAD workbench (with a reverse-engineering side)
- **What it is:** The FOSS parametric CAD modeler (OpenCASCADE kernel). The classic FOSS scan-to-CAD tutorial path is: import STL → Mesh workbench → "Create shape from mesh" → convert to solid → refine → export STEP. It also ships a dedicated `ReverseEngineering` module (mesh segmentation, approximate B-spline surfaces).
- **License:** LGPL-2.1 (verified via project docs, 2026-09-22)
- **Alive:** Very. v1.1.3 stable (2026-07-25); commits landing daily; ~144 active maintainers over the last year; weekly dev builds.
- **Does well:** Real parametric CAD end-state (sketches, features, drawings, STEP export), huge community, Addon Manager ecosystem.
- **Falls short:** The scan-to-CAD path is manual, GUI-only, and brittle. A documented tolerance-confusion bug (issue #20455: a single overloaded tolerance parameter) still haunts the mesh→shape conversion. "Shape from mesh" on dense scans produces face-per-triangle soup that re-opens slowly and can't be edited. FreeCAD users themselves complain about crashes on complex ops and hit-or-miss docs. There is no guided pipeline and no deviation gate — you eyeball it.
- **URL:** https://github.com/FreeCAD/FreeCAD

### Detessellate — the FreeCAD add-on that proves the itch is real
- **What it is:** A collection of FreeCAD macros that introduce an **algorithm-assisted workflow** for reverse engineering imported geometry: mesh models (STL/OBJ/3MF), scan point clouds, and non-parametric STEP solids. Tools like MeshToBody, CoplanarSketch, EdgeLoopToSketch, ReconstructSolid.
- **License:** LGPL-2.1 (verified live on the repo, 2026-10-02)
- **Alive:** Yes — new and moving fast. Created 2026-06-03, 253 commits, v1.1.0 (2026-05-12), added to the official FreeCAD Addon Manager index. This is the freshest FOSS activity in this exact problem space.
- **Does well:** Bridges the manual FreeCAD workflow with algorithm assists; installable in one click via Addon Manager; demo video + icons + per-macro docs.
- **Falls short:** Still interactive/GUI-driven — it's a better hammer, not a pipeline. No deviation gating, no quality gates, no "stop and rescan" honesty, no parametric rebuild generation. Requires FreeCAD as the host.
- **URL:** https://github.com/pushkk/detessellate

### stl2step (BlinkingSun) — the best-in-class converter
- **What it is:** A C++ engine (OCCT-based) that converts triangle meshes (STL) into real B-rep STEP solids: weld → split into solids → build B-rep (parallel) → repair → merge coplanar facets → verify → STEP. Two modes: **Verbatim** (geometry-preserving, one face per triangle where needed) and **TrueForm** (analytic recovery of planes, cylinders, fillet strips, prismatic profiles).
- **License:** MIT — stated in the repo's own README (GitHub's auto-detect shows "NOASSERTION," but the README says "MIT — see LICENSE"; trust the README). Verified live 2026-10-02.
- **Alive:** Extremely. Created 2026-07-05, already 372 commits, 287 stars, 7 releases, v1.4.4 current. This is the project to watch — it's moving at a pace that suggests one very focused engineer.
- **Does well:** Fast, machine-friendly (`RESULT {json}` + exit codes), cross-platform CLI + embeddable library + browser WebAssembly demo (nothing uploaded), honest docs about what converts well and what doesn't, per-version changelogs with measured fixture results. Ships a closed-source desktop app (SolidOut) on top of the MIT engine. 15/15 cylinders recovered analytically at 0.3% radius match and 0.000000% volume deviation on a prismatic fixture — with the receipts published.
- **Falls short:** It is a **converter, not a pipeline.** Organic/freeform/3D-scanned meshes convert but stay faceted (by its own honest admission: "a parametric surface can only be recovered where one actually existed"). TrueForm doesn't do cones, spheres, tori, or freeform. No scan cleanup, no quality gate, no units handling (output is always mm; input units are your problem), no parametric feature tree — you get a solid, not an editable model.
- **URL:** https://github.com/BlinkingSun/stl2step
- **Live web demo:** https://makerinparadise.com/solidout/ (linked from the README; WASM runs in-browser)

### Crypto69/stlToSolid — the spiritual competitor (but NOT FOSS)
- **What it is:** Turns STL/OBJ (also PLY, OFF, 3MF, GLB) into clean prismatic STEP solids — real planes, cylinders, holes — replicating Fusion 360's paid "Prismatic" mesh conversion, plus an editable CadQuery script of the recognized sketches/extrudes. Also has a **sliced-loft** mode for organic shells and a **Blueprint** mode (dimensioned drawing photo → parametric Fusion script). Reports acceptance gates and deviation numbers.
- **License:** **PolyForm Noncommercial 1.0.0** — personal/hobby/educational/research/noncommercial only. Any commercial use needs the author's permission. **This is not FOSS.** (Stated in the repo README; verified via search-cached README text, 2026-10-02.)
- **Alive:** Yes. Created 2026-08-22, 93 commits, v0.4.x series, web app in the repo.
- **Does well:** Closest thing to mesh-to-cad's philosophy in the wild: deviation gates reported per run, CadQuery script output (parametric intent, not just a solid), prismatic AND loft tracks, honest limitations docs.
- **Falls short (for us):** The license. A GruntAndMuse user who scans a part to reproduce it for a customer can't legally use this commercially. Also its roadmap openly admits "Region growing for 3D scans — real faces on scanned parts instead of a faceted solid" is **not done yet** — even the best-funded-style competitor hasn't solved scan face recovery.
- **URL:** https://github.com/Crypto69/stl2prism

### mesh2step (tommasobbianchi) — the friendly wrapper + web app
- **What it is:** Python wrapper around the stl2step C++ engine with a live web app. Converts STL/OBJ/3MF/PLY → STEP (AP203/AP214/AP242), verbatim mode (one face per triangle, topology shared by construction) + `--engine trueform` option. Stands out for its **USER_GUIDE.md**, which includes a "good mesh vs problem mesh" table with real measured examples (a 62,028-triangle scanned bracket → 26 seconds, 149 MB STEP that re-opens slowly).
- **License:** not verified at research time (repo is public; check before depending on it).
- **Alive:** Yes, recent commits; web app deployed.
- **Does well:** Lowest-friction entry point in the space (drop a file in a browser, get STEP). Honest about dense-scan heaviness.
- **Falls short:** Same as stl2step's Verbatim: it's a converter, not a rebuild. No cleanup, no deviation gate, no parametric output.
- **URL:** https://github.com/tommasobbianchi/mesh2step
- **Web app:** https://mesh2step.nativemedica.it/ (advertised in the README)

### TheTesla/stl2step — the cautionary tale
- **What it is:** A Python CLI that segments STLs into basic shapes (planes, cylinders, spheres) and writes STEP.
- **License:** AGPL-3.0
- **Alive:** Barely. "Experimental state: Only planes are implemented! Holes are supported now!" — the classic abandoned-in-ambition FOSS 3D project. This is what "feels abandoned" looks like: a README that promises the world and a codebase that never got past planes.
- **URL:** https://github.com/TheTesla/stl2step

### Blender + CAD Sketcher — the organic route
- **What it is:** Blender (GPL-3.0) is the de-facto free tool for cleaning up scans and modeling organic shapes; the **CAD Sketcher** add-on (by hlorus) adds constraint-based parametric 2D sketching with extrude/revolve, powered by the SolveSpace solver.
- **License:** Blender GPL-3.0; CAD Sketcher GPL v3. Verified: CAD Sketcher v0.30.0 released ~Aug 2026, very active.
- **Does well:** Best free scan-cleanup and organic modeling experience; the `jonyross` point-cloud-RE playbook uses Blender as its interactive review workbench. Project Geometry pulls mesh edges into a linked sketch.
- **Falls short:** Blender is not a CAD kernel — no STEP export, no tolerances, no deviation analysis, models stay "dumb" for manufacturing. CAD Sketcher is 2D sketches + extrude; it doesn't reverse-engineer scans, it just lets you draw over them.
- **URLs:** https://www.blender.org/ · https://github.com/hlorus/CAD_Sketcher · https://extensions.blender.org/add-ons/cad-sketcher/

### Open3D — the library every pipeline quietly stands on
- **What it is:** The modern 3D data-processing library (Intel Intelligent Systems Lab): point clouds, meshes, registration/ICP, Poisson reconstruction, and — relevant here — **geometry metrics (Chamfer distance, Hausdorff distance, F-score)**.
- **License:** MIT (verified via libraries.io + release docs)
- **Alive:** Very. v0.20.0 released ~Sep 2026; 14,022 stars; pip wheels for CPU/CUDA/XPU.
- **Does well:** Best-in-class registration, cleanup, and deviation metrics as a *library*. If mesh-to-cad ever needs its own deviation engine instead of shelling to CloudCompare, this is the substrate.
- **Falls short:** A library, not a tool. No CAD output, no pipeline, no end-user workflow.
- **URL:** https://github.com/isl-org/Open3D

### Supporting cast (substrate, not competitors)
- **trimesh / manifold3d** (MIT): mesh editing and watertight validation in Python — the mesh_tool of choice for agents and pipelines.
- **build123d / CadQuery** (Apache-2.0): code-first parametric CAD on OCCT — the natural *output* format for a rebuild track (editable script, not just STEP).
- **pymeshlab** (GPL-3.0): scriptable MeshLab — note the GPL, don't bundle it in an MIT project.
- **CGAL** (GPL-3.0/LGPL-3.0 dual): the heavy algorithms library (Efficient RANSAC primitive fitting lives here).

### The commercial price anchor (why FOSS matters here)
These are what people pay when the free path fails — the reason a trustworthy FOSS pipeline has an audience:

| Tool | Price | Notes |
|---|---|---|
| Geomagic Design X | Go from ~US$1,900/yr; Pro = quote | The gold standard: scan regions, primitive fitting, deviation analysis, feature-based reconstruction |
| QuickSurface | Pro €1,700/yr or €5,250 perpetual; Lite €480/yr | Standalone reverse-engineering app, excellent tutorials |
| Artec Studio | Pro US$1,700/yr or US$4,300 perpetual | Scanner software with CAD export |
| Mesh2Surface (Rhino plugin) | €1,245 perpetual + Rhino | |
| Fusion 360 | Free personal tier — **but Mesh→Solid is Faceted-only on personal**; Prismatic (face groups) needs a paid license | Confirmed by Autodesk forum workflow posts |
| SOLIDWORKS ScanTo3D | Part of SW Pro/Premium | Has a real Deviation Analysis tool — the pros consider deviation checking table stakes |

Sources: [scansor tool-landscape](https://github.com/altendky/scansor/blob/HEAD/docs/src/project/tool-landscape.md) (2026-09), [Autodesk forum thread](https://forums.autodesk.com/t5/fusion-design-validate-document/help-converting-complex-scan-mesh-to-stp-file/td-p/13756787), [TriMech ScanTo3D guide](https://mfg.trimech.com/from-3d-scan-to-cad-when-to-use-solidworks-scanto3d/).

---

## 2. Best-in-class presentation

What separates the FOSS 3D tools people trust from the ones that feel abandoned:

**Try it without installing.** stl2step's WASM demo and mesh2step's web app let you drop a file and get a STEP in the browser. This is the single strongest trust signal in the space — it says "we're not afraid of your data." Anything that requires compiling OCCT before you see a result loses 90% of its audience at the door.

**Honest limitations, stated up front.** stl2step's README has a "What it is and isn't" section that says plainly: scanned/organic meshes stay faceted, TrueForm doesn't do cones/spheres/tori. mesh2step's guide shows a 62k-triangle scanned bracket that converts to a *149 MB STEP that re-opens slowly* — and tells you to simplify first. Trustworthy tools document their failure modes. Abandoned tools promise "intelligent conversion" and deliver planes-only (see TheTesla/stl2step).

**Machine-friendly output.** stl2step ends every run with `RESULT {json}` + meaningful exit codes, and ships an AGENTS.md integration guide. That's a 2026-era trust signal: the tool expects to be *used by agents and scripts*, not just clicked.

**Measured claims, not adjectives.** "0.000000% volume deviation," "15/15 cylinders recovered at 0.3% radius match," "converts in under 20 seconds on an M-series Mac" — stl2step publishes fixture results. QuickSurface publishes full step-by-step scan→CAD guides for free. This is the GruntAndMuse principle too: *show the work.*

**One-step install.** Detessellate: install via FreeCAD Addon Manager. pymeshlab: `pip install`. Anything requiring a wiki page of build steps reads as "maintainer-only."

**Living changelog.** Per-release notes with measured deltas (stl2step's CHANGELOG: "STEP faces 413 → 314, polyline edges 204 → 138"). A repo whose last commit was 3 years ago with "experimental" in the README is dead — say so and move on.

**The trustworthy checklist for mesh-to-cad:** live demo or at least example gallery with numbers, README that states limitations, install in one command, changelog with measured results, docs for agents as well as humans.

---

## 3. Unmet needs — what users actually complain about

**"I scanned it. Now what?"** This is the central cry. QuickSurface's own free guide opens with it: *"If you own a 3D scanner, you've probably already created STL or OBJ files — but then came the frustrating part: you can't really edit them like CAD."* ([source](https://www.quicksurface.com/3d-scan-to-cad-how-to-turn-stl-obj-scan-data-into-an-editable-model/)) A MakeWithTech forum user, after being told every scanner needs post-processing, replied: *"I guess I'm looking for any easy way out that the scan will produce perfect file ready to print."* There is no easy way out today, and nobody honest pretends there is — that's the opening.

**Dirty scans, no guidance.** Budget scanners produce noisy, layered, overlapping meshes. The standard advice is "clean it up in MeshLab/Blender" — a manual, skill-gated step. Nobody's tool says *"this scan is too dirty, rescan it"* — every tool either silently produces garbage or chokes. A quality gate with a stop-and-rescan rule doesn't exist in the FOSS space.

**Fusion's free tier is a trap door.** Multiple Autodesk forum users discover that Mesh→Solid on the free personal license gives them faceted soup (thousands of unselectable triangles), while the Prismatic conversion that makes real faces needs a paid license. One user scanning a transmission housing hit PC-stall/overkill results trying to work around it. ([source](https://forums.autodesk.com/t5/fusion-design-validate-document/help-converting-complex-scan-mesh-to-stp-file/td-p/13756787))

**STL has no units, and it bites everyone.** "A number in an STL file is a number. Every consumer assumes millimetres by convention and nothing enforces it." ([source](https://github.com/neuman/atompipe/blob/HEAD/packs/cad-solid/sourcing.md)) Metre-scale exports arrive as 0.08 mm parts; quoting tools accept them. No FOSS converter makes unit validation a first-class intake step.

**Hidden tolerances.** FreeCAD's mesh→shape conversion has a documented tolerance-confusion bug (issue #20455): vertex dedup tolerance is hardcoded and invisible while the user-facing tolerance only reaches the sewing step — so loosening the tolerance to fix a failure silently does nothing upstream. Users can't reason about accuracy they can't see. (Documented in [mesh2step's SELECTION.md](https://github.com/tommasobbianchi/mesh2step/blob/HEAD/SELECTION.md).)

**Scan face recovery is unsolved.** stlToSolid — the most advanced tool in this space, non-FOSS — lists "Region growing for 3D scans: real faces on scanned parts instead of a faceted solid" as *still on the roadmap*. Nobody has shipped analytic face recovery on noisy scan data, FOSS or otherwise.

**No deviation-first tool exists.** Deviation *analysis* exists everywhere (SolidWorks ScanTo3D, CloudCompare C2M, stlToSolid's acceptance gates) — always as a checkbox feature buried in a menu. No tool makes the deviation number the headline of every step, publishes per-example deviation reports, or gates the pipeline on it. The philosophy "every step ends with a deviation number" has no product attached to it yet.

**Organic is a second-class citizen.** Every FOSS path handles prismatic parts (planes/cylinders) and punts on organic (faceted fallback, or "model it by hand in Blender"). The scan use cases that matter to makers — knobs, housings, handles, car parts — are the organic ones.

---

## 4. Standards and formats — what the pipeline must read and write

**Read (intake):**
| Format | Role | Notes |
|---|---|---|
| STL (binary + ASCII) | The universal scan/download mesh | **Has no units.** A number is a number. This is why `check_units.py` exists — unit validation is an intake step, not an assumption. |
| OBJ | Scans with groups/materials | No units either; never use for manufacturing |
| PLY | Scans with per-vertex data (color, normals) | Good archival mesh format; preserves scalar fields |
| 3MF | Modern print container | **Carries real units**, color, multi-part — preferred by Bambu/Prusa/Cura |
| Point clouds: E57, LAS/LAZ, ASC, PCD, PTS, XYZ | Raw scanner output | **E57** (ASTM E2807) is the vendor-neutral scan-exchange standard — stores registered scans, poses, RGB, metadata. FreeCAD's Points module reads ASC/PCD/PLY/E57. |

**Write (output):**
| Format | Role | Notes |
|---|---|---|
| STEP AP203/AP214/AP242 | **The** CAD exchange format | Exact surfaces, units, assembly structure. Loses the feature tree/parameters — that's why the pipeline should also emit the *rebuild script*. AP242 is the merged modern standard. "Send STEP to a machinist, mesh to a printer." |
| IGES | Legacy surface interchange | Surfaces only, no solidity — legacy use only, expect stitching |
| STL (binary) | Print output | Only after units are fixed by convention |
| 3MF | Modern print output | Units + color + multi-part |
| DXF | 2D drawings | The pipeline's drawing deliverable |

**Key realities:**
- **Triangle-wrapped STEP is hard.** Putting one face per triangle into a STEP file technically works but produces unusable files (149 MB STEP from a 62k-triangle scan that re-opens slowly). The value is in *fewer, analytic faces* — or an honest faceted fallback.
- **No scan-intent interchange standard exists.** Nothing carries "this mesh came from scan X, at Y accuracy, with Z provenance." The pipeline's manifest/report is filling a real gap — provenance is a deliverable, not metadata.
- **The output that matters most isn't a file.** Every FOSS converter stops at the STEP. Nobody ships the *rebuild script* (the editable CadQuery/build123d source with named dimensions) as a first-class artifact — stlToSolid does it as a bonus. A STEP you can't edit is a dead end; a script you can tweak is a living model.

---

## 5. Communities — where these users hang out

**Reddit** (blocked in this research environment — listed from knowledge + corroborating sources, not live-verified):
- r/3Dscanning — https://www.reddit.com/r/3Dscanning/ — scanner owners; constant "scan to CAD?" threads. (Revopoint's official community page links its own subreddit presence.)
- r/3Dprinting — https://www.reddit.com/r/3Dprinting/ — the "I downloaded an STL, now I need to modify it" crowd.
- r/FreeCAD — https://www.reddit.com/r/FreeCAD/ — reverse-engineering questions land here regularly.

**Forums:**
- FreeCAD forum — https://forum.freecad.org/ (bot-walled for scrapers; fine for humans). Detessellate's announcement thread lives here.
- Autodesk Fusion forums — https://forums.autodesk.com/ — scan→STEP help threads are common.
- MakeWithTech — https://forum.makewithtech.com/ — maker-friendly, scan-to-CAD newbie threads.
- CNCZone — https://www.cnczone.com/ — scan-to-CNC workflows.
- Revopoint community hub — https://global.revopoint3d.com/pages/community — forums, Discord, Facebook groups per scanner line.

**Facebook:**
- 3D Scan - Reverse Engineering group — https://www.facebook.com/groups/1666231177371941/ — active community that shares the *same scan* across members so different people demo different software workflows on identical data. (Link from the group's YouTube channel description.)

**Discord:**
- Open3D Discord (via the Open3D repo readme), CAD Sketcher Discord, Revopoint Discord (via the community hub above).

**YouTube (the real classroom for this space):**
- **@3ds-re** ("3D Scan - Reverse Engineering") — https://www.youtube.com/@3ds-re — same-scan shootouts: QuickSurface vs Fusion 360 vs FreeCAD on identical data. The single best window into comparative workflows.
- **Quicksurface** — https://www.youtube.com/@quicksurface — professional scan-to-CAD tutorials, free.
- **Thomas Sanladerer** — recommended on maker forums for scan/CAD topics.
- **Deltahedra3D** — FreeCAD-focused channel, covered the 1.1 release in depth.

**Hacker News / press:** occasional deep CAD threads (FreeCAD, OpenSCAD); Hackaday covers FOSS scan→CAD tutorials (e.g. "Reverse Engineering STL Files With FreeCAD," Oct 2025).

---

## 6. Where we fit — the angle mesh-to-cad can own

**The one-sentence version:** Every tool in this space answers "what did you make?" — mesh-to-cad is the only one built to answer **"prove it matches the scan, with a number, at every step."**

**What the landscape actually shows:**

1. **The deviation philosophy is unclaimed.** Deviation *analysis* is a checkbox in every pro tool (SolidWorks ScanTo3D, Geomagic, CloudCompare C2M) and an acceptance gate in stlToSolid — but always buried, never the product identity. Nobody publishes per-step deviation reports as the headline artifact. mesh-to-cad's "every step ends with a deviation number" isn't a feature; it's a *position* nobody occupies.

2. **The closest spiritual competitor is not FOSS.** stlToSolid does prismatic recovery + CadQuery scripts + deviation gates + a loft track for organic — and it's PolyForm Noncommercial. Anyone who scans a part to reproduce it for a paying customer can't use it. The FOSS user who needs the same rigor has: stl2step (best converter, MIT, but faceted fallback on scans and no pipeline) or FreeCAD (manual, GUI, tolerance bugs). **The FOSS, commercial-usable, metrology-gated pipeline slot is empty.**

3. **Nobody says "rescan."** Every tool either silently produces garbage from dirty scans or chokes. A quality gate with an explicit stop-and-rescan rule (`quality_gate.py`) is a differentiator in itself — it's the honest answer to the #1 user complaint ("my scan is bad and I don't know it").

4. **Nobody handles units at intake.** STL has no units; every converter makes it your problem. `check_units.py` as a named, documented pipeline stage is a small thing that signals "this tool has been burned by reality before."

5. **Nobody ships the rebuild script as the artifact.** STEP drops the feature tree. stlToSolid emits a CadQuery script as a bonus; mesh-to-cad's rebuild tracks (prismatic + organic) should make the *editable, named-dimension script* the primary output and the STEP the derived artifact — inverted from everyone else's priorities.

6. **Organic is the open frontier.** Everyone does planes and cylinders; everyone punts on organic (faceted fallback, or "go model it in Blender"). The scan use cases that matter to makers — knobs, housings, handles, brackets that fit real objects — are organic. The organic track with quantitative deviation loops is where mesh-to-cad can do genuinely new work. Even stlToSolid's roadmap admits scan face recovery isn't done.

**What to steal (presentation, not code):**
- stl2step's honest "What it is and isn't" section, `RESULT {json}` machine-friendly output, AGENTS.md, and fixture-measured changelogs.
- mesh2step's "good mesh vs problem mesh" guide — mesh-to-cad should ship the same, with its own deviation numbers.
- Detessellate's one-click Addon Manager presence — distribution matters as much as code.
- The @3ds-re same-scan shootout format — publish mesh-to-cad's results on a public scan next to QuickSurface/Fusion/FreeCAD outputs, *with deviation numbers*. That's the demo that makes the philosophy concrete.

**What NOT to do:**
- Don't be TheTesla/stl2step: a README that promises intelligence and a repo that never got past planes.
- Don't bundle GPL code (pymeshlab, CGAL) into the MIT pipeline — shell out to GPL tools (like deviation.py already does with CloudCompare) instead of linking them.
- Don't chase stl2step on raw conversion speed/quality — use it as an *engine inside* the pipeline where it fits, and own the layers it doesn't do: intake, quality gates, rebuild, verification, reporting.

**Bottom line:** The space has great *components* (MeshLab cleans, CloudCompare measures, stl2step converts, FreeCAD models, Open3D computes) and zero *pipelines* that are FOSS, commercial-usable, honest about dirty scans, and gated on measured deviation at every step. That's the gap. Own the number.
