#!/usr/bin/env python3
"""
A2. Quality gate — replace "does this scan look okay?" with four numbers.

WHAT THIS DOES:
    Computes four objective mesh-quality metrics and issues a verdict:
    `clean` (proceed), `noisy` (proceed with caution, organic-friendly route),
    or `needs-rescan` (stop — no pipeline fixes missing data). The human can
    override, but the DEFAULT is now a number, not a feeling.

WHY THIS EXISTS:
    Stage 1's honest rule is "garbage in = garbage CAD," and the rescan decision
    used to be pure eyeballing. Eyeballing doesn't scale, isn't reproducible,
    and two people disagree about the same scan. These four metrics capture
    what the eyeball was actually checking: Are there holes? Is it noisy? Is
    there floating junk? Each metric is computable, each threshold is stated,
    and every threshold is tunable in one place (see THRESHOLDS below).

THE FOUR METRICS (and what each one is really measuring):
    1. is_watertight (bool) — does the mesh enclose a volume with no boundary
       edges? Non-watertight usually means holes or open surfaces. We report it
       but don't gate on it alone: some valid inputs (thin-walled scans) are
       legitimately open, and hole-filling (metric 2) quantifies HOW open.
    2. hole_fill_fraction (0..1) — fill all holes, then measure
       (faces_after - faces_before) / faces_after. This is "what fraction of
       the final surface did we invent?" Small fractions (<5%) are normal scan
       cleanup. Large fractions mean the scanner missed real geometry and we'd
       be CAD-modeling our own guesses. That's the rescan trigger.
    3. noise_mm (float) — mean per-vertex distance between the mesh and its
       Taubin-smoothed copy. Smoothing removes high-frequency jitter but keeps
       real features; the distance between original and smoothed therefore
       approximates the noise floor. Above 0.3 mm the scan is fighting the
       pipeline's tolerances — proceed, but expect the organic track.
    4. component_count (int) — number of disconnected pieces (trimesh.split).
       1 is normal. More means floating triangles, double-scanned fragments, or
       the turntable got scanned too. Above COMPONENT_NOISY_COUNT (10) the
       verdict drops to `noisy`: the geometry is usually intact (so not a
       rescan), but Stage 1 MUST isolate the part before downstream stages
       trust the mesh. (Was purely informational until 2026-10-02, when a
       300-component Benchy read "clean.")

WHY TAUBIN SMOOTHING (AND NOT PLAIN LAPLACIAN):
    Plain Laplacian smoothing shrinks the mesh toward its centroid — after
    enough iterations your bracket is a pebble. For a NOISE ESTIMATE that's
    fatal: the original-vs-smoothed distance would measure shrinkage, not
    noise. Taubin's two-parameter scheme (inflate with lambda, deflate with mu)
    is approximately volume-preserving: it kills high-frequency jitter while
    leaving low-frequency shape alone. So the distance we measure is mostly
    noise. (Gabriel Taubin, 1995 — "A Signal Processing Approach to Fair
    Surface Design". The standard parameters below are his.)

WHY NUMPY AND NOT OPEN3D:
    Open3D's filter_smooth_taubin does exactly this — but Open3D installs at
    ~500 MB, which is hostile to the pipeline's "forkable on a laptop" goal.
    Taubin smoothing is ~15 lines of numpy over a vertex-adjacency structure.
    We implement it here, cite the paper, and keep the dependency list to
    trimesh/numpy/scipy. If Open3D is ever needed elsewhere in the pipeline,
    this function can delegate — the interface (mesh in, smoothed verts out)
    stays the same.

THRESHOLDS — TUNE THESE ON REAL DATA:
    The defaults below are starting points from general scan experience, NOT
    calibrated values. The first time this runs on the Raptor Pro's real scans,
    revisit them. A threshold is a hypothesis; the scan data is the experiment.

USAGE:
    python quality_gate.py work/bracket_clean.stl
    python quality_gate.py work/bracket_clean.stl --json   # machine-readable
    python quality_gate.py --help                          # this text

EXIT CODES:
    0 — verdict `clean` or `noisy` (proceed)
    2 — verdict `needs-rescan` (stop; distinct code so SOP scripts can branch)
    1 — usage error / unreadable file

Requires: trimesh, numpy, scipy, networkx (trimesh's fill_holes needs it;
gracefully degrades to "unavailable" if missing — see hole_fill_fraction).
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

# ---------------------------------------------------------------------------
# Thresholds. All in millimeters unless noted. TUNE ON REAL SCAN DATA.
# See module docstring: these are starting hypotheses, not calibrated truths.
# ---------------------------------------------------------------------------
HOLE_FILL_RESCAN_FRACTION = 0.05  # >5% invented surface -> needs-rescan
NOISE_MM_WARN = 0.3               # mean noise above this -> "noisy" verdict

# Fragmentation threshold: more disconnected components than this -> "noisy".
# WHY 10: 1 component is a clean single part; 2-3 is a part plus a couple of
# floating triangles (normal scan debris, cleanup handles it silently). Past
# ~10 the scan session was genuinely messy — turntable scanned, double-scan
# fragments, shattered shells — and Stage 1 cleanup MUST isolate the part
# before anything downstream trusts the mesh. (The Benchy mirror that
# motivated this had 300 components and still read "clean" — 2026-10-02.)
# WHY "noisy" AND NOT "needs-rescan": fragmentation is a cleanup problem, not
# missing data. The primary component's geometry is usually intact; rescan is
# for geometry the scanner never captured. "Noisy" = proceed with caution,
# which is exactly what a fragmented scan needs. Multi-part assemblies will
# also trip this — honestly, since an assembly ISN'T a single part and the
# pipeline works per-part. Like all thresholds here: a starting hypothesis,
# tune on real Raptor Pro scans.
COMPONENT_NOISY_COUNT = 10

# Taubin smoothing parameters (Taubin 1995). lambda > 0 inflates, mu < 0
# deflates; |mu| slightly larger than lambda gives the volume-preserving
# behavior. 10 iterations is plenty for a noise estimate — we're measuring
# jitter, not producing a display mesh.
TAUBIN_LAMBDA = 0.5
TAUBIN_MU = -0.53
TAUBIN_ITERATIONS = 10

# Minimum vertex count for a meaningful noise estimate. WHY: the noise metric
# compares the mesh against its Taubin-smoothed copy. On a DENSE mesh (a real
# scan — thousands of vertices), smoothing removes high-frequency jitter and
# the distance approximates the noise floor. On a COARSE mesh (an 8-vertex
# box), the sharp corners ARE the highest-frequency content, so smoothing
# rounds them and the "noise" reads as tens of millimeters on a perfect part.
# That's not a bug in the smoother; it's the metric being applied outside its
# design envelope. Below this count we report noise as unavailable rather than
# a misleading number. The pipeline's Stage 1 input is always scan-density,
# so this guard should rarely trigger — when it does, it means someone pointed
# the gate at a CAD primitive, and "n/a" is the honest answer.
NOISE_MIN_VERTICES = 500


def vertex_adjacency(mesh: trimesh.Trimesh):
    """Build vertex -> neighbor-vertex adjacency as a list of index arrays.

    WHY WE NEED THIS: smoothing moves each vertex toward the average of its
    neighbors, so we need the neighbor list. trimesh has vertex_neighbors but
    it returns a generator of arrays in arbitrary order; building it explicitly
    from faces is transparent and lets us document exactly what's happening.
    """
    n_verts = len(mesh.vertices)
    # Collect neighbor pairs from every triangle edge (each face contributes
    # 3 undirected edges). Using a set of frozensets dedupes shared edges.
    edges = set()
    for tri in np.asarray(mesh.faces):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edges.add((min(a, b), max(a, b)))
    neighbors: list[set] = [set() for _ in range(n_verts)]
    for a, b in edges:
        neighbors[a].add(b)
        neighbors[b].add(a)
    # Convert to numpy arrays once, up front — the smoothing loop below then
    # does pure vectorized math with no Python-level per-vertex work.
    return [np.fromiter(s, dtype=np.int64) for s in neighbors]


def taubin_smooth(vertices: np.ndarray, adjacency, lam=TAUBIN_LAMBDA,
                   mu=TAUBIN_MU, iterations=TAUBIN_ITERATIONS) -> np.ndarray:
    """Taubin (lambda|mu) smoothing. Returns new vertex positions.

    Each iteration does TWO Laplacian passes with opposite signs:
        pass 1: v += lam * (mean(neighbors) - v)    # lam > 0: shrink
        pass 2: v += mu  * (mean(neighbors) - v)    # mu  < 0: inflate back
    The shrink pass kills high-frequency noise; the inflate pass restores the
    low-frequency volume the shrink pass stole. Net effect: noise gone, shape
    kept. That's the whole trick, and why plain Laplacian (shrink only) would
    corrupt our noise estimate with shrinkage bias.

    Isolated vertices (no neighbors — shouldn't happen in a real mesh, but
    defensive) are left in place: dividing by zero neighbors would NaN them.
    """
    v = vertices.astype(np.float64).copy()
    for _ in range(iterations):
        for step in (lam, mu):
            # Compute mean-neighbor position per vertex. The loop below is over
            # vertices in Python, which is O(n) Python overhead per iteration —
            # acceptable for meshes under ~1M verts; for larger, vectorize with
            # a sparse adjacency matrix (left as an exercise with a comment,
            # not a mystery).
            means = np.empty_like(v)
            for i, nbrs in enumerate(adjacency):
                if len(nbrs):
                    means[i] = v[nbrs].mean(axis=0)
                else:
                    means[i] = v[i]  # isolated: don't move
            v = v + step * (means - v)
    return v


def hole_fill_fraction(mesh: trimesh.Trimesh) -> dict:
    """Fill holes and report what fraction of the surface area was invented.

    WHY AREA FRACTION AND NOT FACE-COUNT FRACTION: fan-filled triangles are
    much larger than the mesh's average triangle — one fan triangle can span
    what were dozens of small scan triangles. Counting faces under-reports a
    big hole filled coarsely: "46 faces added" sounds small, but those 46 span
    the entire missing patch. Area is the honest unit: square millimeters
    invented over square millimeters total. (We shipped face counts first,
    2026-10-02; a 176-face hole read as 1.56% by count. Area is the fix.)

    NOTE: fill_holes MUTATES NOTHING — we operate on a copy. The input mesh is
    never modified by this script. Stage 1 cleanup is a separate, deliberate
    step; the gate only measures.

    ROBUSTNESS: trimesh's fill_holes needs networkx (an optional dependency).
    If it's missing — or the fill itself fails on pathological input — we
    report the hole metric as unavailable instead of crashing the whole gate.
    A gate that crashes on a weird mesh is worse than a gate that says "I
    couldn't measure this part." The verdict logic treats unavailable as
    "not clean" (fail safe, not fail silent).
    """
    before = len(mesh.faces)
    area_before = float(mesh.area)
    try:
        filled = mesh.copy()
        # use_fan=True: trimesh's fill_holes DEFAULT only fills triangular and
        # quad holes — larger boundary loops are silently skipped, because fan
        # triangulation "may result in bad answers if the holes are non
        # convex." That's the right default for REPAIR (don't invent bad
        # geometry), but we're MEASURING, not repairing: we want to know how
        # much surface is missing, and a fan fill approximates that even if
        # individual triangles are imperfect. A 48-edge hole filled with ~46
        # fan triangles reports "5% missing" correctly even if two of those
        # triangles are slightly folded. The fan's geometric imperfection is
        # noise on the metric, not bias. (Found empirically 2026-10-02: the
        # default filled 0 of 176 missing faces on a test mesh.)
        trimesh.repair.fill_holes(filled, use_fan=True)
    except Exception as e:  # noqa: BLE001 — any fill failure -> unavailable
        return {
            "faces_before": int(before),
            "area_before_mm2": round(area_before, 2),
            "faces_after": None,
            "area_added_mm2": None,
            "fraction": None,
            "unavailable": f"hole fill failed: {e}",
        }
    after = len(filled.faces)
    added = after - before
    area_after = float(filled.area)
    area_added = area_after - area_before
    # area_added can be ~0 (or tiny-negative from float noise) when nothing
    # was fillable; clamp at zero so the fraction never goes negative.
    area_added = max(area_added, 0.0)
    return {
        "faces_before": int(before),
        "area_before_mm2": round(area_before, 2),
        "faces_after": int(after),
        "area_added_mm2": round(area_added, 2),
        # Guard against area_after == 0 (degenerate input): fraction 0.
        "fraction": round(area_added / area_after, 4) if area_after else 0.0,
    }


def noise_estimate_mm(mesh: trimesh.Trimesh) -> dict:
    """Estimate the scan's noise floor in millimeters.

    METHOD: smooth a copy with Taubin (kills jitter, keeps shape), then take
    the mean Euclidean distance between each original vertex and its smoothed
    position. On a clean CAD-derived mesh this is ~0. On a raw scan it's the
    sensor noise + surface roughness. That's the number we want: it tells the
    pipeline how much it's fighting the data.

    WHY MEAN AND NOT MAX: max is dominated by single worst vertices (often at
    scan boundaries or hole rims — real artifacts, but not representative).
    Mean characterizes the surface the fitter will actually work on. We also
    report p95 so a human can see the tail without it driving the verdict.

    DENSITY GUARD: returns None (unavailable) when the mesh has fewer than
    NOISE_MIN_VERTICES vertices — see the constant's comment for why the
    metric is meaningless on coarse meshes. Callers must handle None as
    "could not measure," never as "zero noise."
    """
    verts = np.asarray(mesh.vertices)
    if len(verts) < NOISE_MIN_VERTICES:
        return None
    adjacency = vertex_adjacency(mesh)
    smoothed = taubin_smooth(verts, adjacency)
    dists = np.linalg.norm(verts - smoothed, axis=1)
    return {
        "mean_mm": round(float(dists.mean()), 4),
        "p95_mm": round(float(np.percentile(dists, 95)), 4),
        "max_mm": round(float(dists.max()), 4),
    }


def quality_gate(mesh_path: Path) -> dict:
    """Run all four metrics and issue a verdict. See module docstring."""
    mesh = trimesh.load(str(mesh_path), force="mesh")

    watertight = bool(mesh.is_watertight)
    holes = hole_fill_fraction(mesh)
    noise = noise_estimate_mm(mesh)
    # split() returns disconnected components; drop empty/degenerate ones.
    # as_sparse=False keeps it simple; for huge meshes this copies data, but
    # the gate runs once per scan, not in a hot loop.
    components = [c for c in mesh.split(only_watertight=False) if len(c.faces)]
    component_count = len(components)

    # --- Verdict logic. Order matters: rescan dominates noisy dominates clean.
    # A mesh can be both holey AND noisy; we report the worse verdict because
    # the SOP branches on it (stop vs. proceed-with-caution).
    #
    # FAIL-SAFE ON UNAVAILABLE METRICS: if we couldn't measure something, we
    # do NOT assume it's fine. Unknown hole-fill -> can't rule out missing
    # geometry -> needs-rescan (the conservative call). Unknown noise on a
    # dense-enough mesh shouldn't happen; unknown noise from the density guard
    # just means "not a scan," which is informational, not a failure.
    reasons = []
    hole_fraction = holes["fraction"]  # None if fill was unavailable
    noise_mean = noise["mean_mm"] if noise else None

    # Empty mesh: no geometry at all. This is "stop," not "clean" — there is
    # nothing to build CAD from. (Found 2026-10-02: an empty file read
    # "clean" because every metric trivially passed. Metrics passing on
    # nothing is not the same as a good scan.)
    if len(mesh.faces) == 0:
        verdict = "needs-rescan"
        reasons.append(
            "file contains no geometry (0 faces) — empty mesh, nothing to "
            "build CAD from. Check the export or re-download the file."
        )
    elif hole_fraction is None:
        verdict = "needs-rescan"
        reasons.append(
            f"hole-fill metric unavailable ({holes.get('unavailable', 'unknown reason')}) — "
            "cannot rule out missing geometry. Fix the measurement or inspect manually."
        )
    elif hole_fraction > HOLE_FILL_RESCAN_FRACTION:
        verdict = "needs-rescan"
        reasons.append(
            f"hole-fill would invent {hole_fraction:.1%} of the surface "
            f"(>{HOLE_FILL_RESCAN_FRACTION:.0%} threshold) — large regions are "
            "missing, not just pinholes. Rescan; don't model guesses."
        )
    elif noise_mean is not None and noise_mean > NOISE_MM_WARN:
        verdict = "noisy"
        reasons.append(
            f"mean noise {noise_mean} mm exceeds {NOISE_MM_WARN} mm — "
            "proceed, but prefer the organic track and expect fitting effort."
        )
    elif component_count > COMPONENT_NOISY_COUNT:
        # Fragmented scan: many disconnected shells. Not missing data
        # (that's needs-rescan), but the session was messy and Stage 1 must
        # isolate the real part. See the threshold comment for WHY noisy.
        verdict = "noisy"
        reasons.append(
            f"{component_count} disconnected components exceeds "
            f"{COMPONENT_NOISY_COUNT} — fragmented scan; Stage 1 cleanup "
            "must isolate the part before downstream stages trust the mesh."
        )
    else:
        verdict = "clean"
        if noise is None:
            reasons.append(
                "all measurable metrics within thresholds "
                f"(noise estimate skipped: <{NOISE_MIN_VERTICES} vertices — "
                "not scan-density; see threshold comment)."
            )
        else:
            reasons.append("all metrics within thresholds.")

    # Informational flags: don't change the verdict, but the human should know.
    notes = []
    if not watertight:
        notes.append("mesh is not watertight (open boundaries present).")
    if component_count > 1:
        notes.append(
            f"{component_count} disconnected components — floating junk or "
            "multi-part scan; Stage 1 cleanup should isolate the part."
        )

    return {
        "file": str(mesh_path),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "is_watertight": watertight,
        "hole_fill": holes,
        "noise": noise,
        "component_count": int(component_count),
        "verdict": verdict,
        "reasons": reasons,
        "notes": notes,
        # Echo thresholds so the report is self-describing: anyone reading
        # this JSON a year from now sees what "clean" meant on that day.
        "thresholds": {
            "hole_fill_rescan_fraction": HOLE_FILL_RESCAN_FRACTION,
            "noise_mm_warn": NOISE_MM_WARN,
        },
    }


def main() -> None:
    # --help / -h: print the module docstring and exit 0, before arg parsing
    # so it never falls through to "not found: --help".
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        sys.exit(0)
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    mesh_path = Path(args[0])
    if not mesh_path.exists():
        print(f"not found: {mesh_path}", file=sys.stderr)
        sys.exit(1)

    result = quality_gate(mesh_path)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        hf = result["hole_fill"]
        nz = result["noise"]
        print(f"file:        {result['file']}")
        print(f"verts/faces: {result['vertices']} / {result['faces']}")
        print(f"watertight:  {result['is_watertight']}")
        if hf["fraction"] is None:
            print(f"hole-fill:   UNAVAILABLE ({hf.get('unavailable')})")
        else:
            print(f"hole-fill:   +{hf['area_added_mm2']} mm2 "
                  f"({hf['fraction']:.2%} invented)")
        if nz is None:
            print("noise:       n/a (mesh too coarse for noise estimate)")
        else:
            print(f"noise:       mean {nz['mean_mm']} mm, "
                  f"p95 {nz['p95_mm']} mm")
        print(f"components:  {result['component_count']}")
        print(f"VERDICT:     {result['verdict']}")
        for r in result["reasons"]:
            print(f"  - {r}")
        for n in result["notes"]:
            print(f"  note: {n}")

    # Exit 2 = needs-rescan, so SOP wrappers can branch: `||` won't do, but
    # `case $?` will. Exit 0 covers clean AND noisy (both proceed).
    sys.exit(2 if result["verdict"] == "needs-rescan" else 0)


if __name__ == "__main__":
    main()
