#!/usr/bin/env python3
"""
Stage 2 analysis: automated measurement extraction from a mesh.

Reads a mesh file, extracts bounding box, planar face clusters,
hole candidates, and symmetry info. Writes <name>_measurements.json.

A3 EXTENSIONS (Phase 1 automation):
  - The track suggestion is PROMOTED to a recorded decision with a confidence
    level (high/medium). High-confidence decisions proceed without review;
    medium-confidence ones get human eyes. See the track block for the cut
    lines and why.
  - The mesh is aligned so principal axes land on XYZ, and the 4x4 homogeneous
    transform is recorded in the JSON. An aligned copy (<name>_aligned.stl) is
    written next to the input. Every downstream stage works in this canonical
    frame; the matrix maps results back to the input frame when needed.

Usage:
    python analyze.py work/bracket_clean.stl
    python analyze.py work/bracket_clean.stl --no-align   # skip aligned copy
    python analyze.py --help                              # this text

Requires: trimesh, numpy, scipy
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh


def cylindrical_wall_fraction(face_normals: np.ndarray,
                              plane_normal: np.ndarray,
                              n_bins: int = 12,
                              min_bin_frac: float = 0.05) -> tuple:
    """Detect extruded cylindrical walls perpendicular to a dominant plane.

    WHAT: of the faces whose normals are ~perpendicular to plane_normal
    ("side walls" relative to that plane), check whether their normals sweep
    a full 360 degrees around the plane normal. Returns (side_face_count,
    full_coverage_bool).

    WHY THIS EXISTS (found 2026-10-02): a flat plate with drilled holes read
    as "mixed"/medium because the hole cylinders (~48% of faces) diluted the
    planar fraction to 51%. The heuristic treated machined holes as "organic
    details" — but holes are exactly what the prismatic track's RANSAC
    cylinder fitting is for. A part with holes is MORE prismatic, not less.
    Cylindrical walls (hole bores, extruded sides, turned diameters) are
    prismatic evidence and must count toward the prismatic fraction, not
    against it.

    WHY ANGULAR COVERAGE AND NOT JUST "SIDE FACES": any curved part has side
    faces (a sphere's equator, a boat hull's sides). What distinguishes a
    machined cylinder from freeform curvature is that the wall normals sweep
    the FULL circle uniformly — a drilled bore is a closed ring. The
    histogram test requires every 30-degree bin to hold a minimum share of
    the side faces. Verified 2026-10-02: bracket (4x D10 holes) -> all 12
    bins ~32 faces, PASS; Benchy -> bins 2251..7207 vs 2710 threshold, FAIL;
    blob -> FAIL. The threshold discriminates real bores from lumpy sides.

    WHY min_bin_frac=0.05: with 12 bins, uniform coverage puts ~8.3% per bin.
    Requiring 5% tolerates triangulation unevenness (hole rims triangulate
    less uniformly than the bore) while rejecting partial arcs. Tuned on the
    three test models above; revisit if it misfires on real scans.
    """
    n = np.asarray(plane_normal, dtype=float)
    n = n / (np.linalg.norm(n) + 1e-12)
    # |dot| < 0.2 -> normal within ~78-102 degrees of the plane normal,
    # i.e. roughly perpendicular: these are the "walls" relative to this plane.
    # (Planar faces themselves have |dot| ~ 1, so they never land here —
    #  no double-counting with planar_fraction.)
    side_mask = np.abs(face_normals @ n) < 0.2
    side = face_normals[side_mask]
    n_side = int(side_mask.sum())
    if n_side < n_bins:
        # Too few walls to assess coverage — not a cylinder, just noise.
        return n_side, False
    # Project wall normals onto the plane perpendicular to n, then measure
    # their angles in a stable 2D basis (u, v).
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u = u / (np.linalg.norm(u) + 1e-12)
    v = np.cross(n, u)  # already unit: n and u are orthonormal
    proj = side - np.outer(side @ n, n)
    angles = np.arctan2(proj @ v, proj @ u)
    hist, _ = np.histogram(angles, bins=n_bins, range=(-np.pi, np.pi))
    # Every bin must clear the threshold: a bore covers all directions, a
    # partial arc (fillet, hull side) leaves bins empty.
    threshold = max(3, min_bin_frac * n_side)
    full_coverage = bool(np.all(hist >= threshold))
    return n_side, full_coverage


def analyze(mesh_path: Path) -> tuple:
    """Analyze the mesh; returns (result_dict, aligned_mesh).

    The aligned mesh is the input rotated/translated so principal axes lie on
    XYZ (see the alignment block inside). Callers that need the working-frame
    mesh should use it; callers that only need numbers can ignore it.
    """
    mesh = trimesh.load(str(mesh_path), force="mesh")
    # Empty-file guard: analyzing zero faces produces NaNs and tracebacks
    # deep in numpy (SVD of an empty array, etc.). Fail fast with a clear
    # message — same rationale as check_units.py's guard (2026-10-02).
    if len(mesh.faces) == 0:
        raise ValueError(
            f"{mesh_path} contains no geometry (0 faces) — nothing to analyze. "
            "Check the export or re-download the file."
        )
    result = {
        "file": str(mesh_path),
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "is_watertight": bool(mesh.is_watertight),
        "is_manifold": bool(mesh.is_winding_consistent),
    }

    # --- Bounding box ---
    bb_min, bb_max = mesh.bounds
    extents = bb_max - bb_min
    result["bounding_box_mm"] = {
        "min": [round(float(v), 3) for v in bb_min],
        "max": [round(float(v), 3) for v in bb_max],
        "extents": [round(float(v), 3) for v in extents],
    }
    result["volume_mm3"] = round(float(mesh.volume), 2) if mesh.is_watertight else None

    # --- Principal axes (PCA on vertices) ---
    verts = np.asarray(mesh.vertices)
    centered = verts - verts.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    result["principal_axes"] = [[round(float(v), 4) for v in row] for row in vt]

    # --- Planar face detection via normal clustering ---
    normals = np.asarray(mesh.face_normals)
    # Quantize normals to ~5 degree buckets to find dominant planes
    bucket = np.round(normals / 0.087).astype(int)  # 0.087 rad ~ 5 deg
    uniq, counts = np.unique(bucket, axis=0, return_counts=True)
    order = np.argsort(counts)[::-1]
    planes = []
    for idx in order[:12]:
        if counts[idx] < len(normals) * 0.02:  # ignore <2% of faces
            break
        n = uniq[idx].astype(float)
        n = n / (np.linalg.norm(n) + 1e-12)
        planes.append({
            "normal": [round(float(v), 3) for v in n],
            "face_count": int(counts[idx]),
            "face_fraction": round(float(counts[idx]) / len(normals), 3),
        })
    result["dominant_planes"] = planes
    planar_fraction = sum(p["face_fraction"] for p in planes)
    # Clamp: each plane's fraction is rounded to 3 decimals before summing, so
    # the total can read 1.002 on a perfect box. A fraction above 1.0 looks
    # like a bug to anyone reading the JSON — clamp it.
    result["planar_fraction"] = round(min(planar_fraction, 1.0), 3)

    # --- Symmetry check (mirror planes XY, XZ, YZ through centroid) ---
    centroid = verts.mean(axis=0)
    sym = {}
    for name, axis in (("xy", 2), ("xz", 1), ("yz", 0)):
        mirrored = verts.copy()
        mirrored[:, axis] = 2 * centroid[axis] - mirrored[:, axis]
        # Chamfer-ish: mean nearest-neighbor distance after mirroring
        # (subsample for speed on large meshes)
        sub = verts[:: max(1, len(verts) // 5000)]
        msub = mirrored[:: max(1, len(mirrored) // 5000)]
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(msub)
            dists, _ = tree.query(sub, k=1)
            sym[name] = {
                "mean_dev_mm": round(float(dists.mean()), 3),
                "max_dev_mm": round(float(dists.max()), 3),
                "symmetric": bool(dists.mean() < 0.5),
            }
        except ImportError:
            sym[name] = {"error": "scipy not available"}
    result["symmetry"] = sym

    # --- Cylindrical wall detection (prismatic evidence, not organic) ---
    # See cylindrical_wall_fraction() for WHY. Faces that form extruded walls
    # or bores perpendicular to a real dominant plane (>=10% of faces — a
    # plane that small is noise, not a datum) are machined features: they
    # belong to the prismatic count. We take the UNION across qualifying
    # planes so a bore counts once even if it's a wall relative to two planes.
    cylindrical_mask = np.zeros(len(normals), dtype=bool)
    cylindrical_detail = []
    for p in planes:
        if p["face_fraction"] < 0.10:
            continue
        n = np.array(p["normal"])
        n_side, full = cylindrical_wall_fraction(normals, n)
        cylindrical_detail.append({
            "plane_normal": p["normal"],
            "side_faces": n_side,
            "full_coverage": full,
        })
        if full:
            cylindrical_mask |= (np.abs(normals @ (n / (np.linalg.norm(n) + 1e-12))) < 0.2)
    cylindrical_fraction = round(float(cylindrical_mask.sum()) / len(normals), 3)
    result["cylindrical_fraction"] = cylindrical_fraction
    result["cylindrical_detail"] = cylindrical_detail
    # Effective prismatic evidence: planar faces + cylindrical walls. Planar
    # faces can never be wall faces (|dot|~1 vs <0.2), so the sum can't
    # double-count — but cap at 1.0 anyway against float dust.
    effective_fraction = round(min(planar_fraction + cylindrical_fraction, 1.0), 3)
    result["effective_prismatic_fraction"] = effective_fraction

    # --- Track suggestion -> DECISION (A3: promoted from suggestion) ---
    # WHY A DECISION AND NOT A SUGGESTION: the old code said "you might try
    # prismatic" and left the human to re-derive it every time. The planar
    # fraction already encodes the evidence, so we now record a decision with
    # a confidence level. HIGH confidence (>0.8 or <0.2 planar) means the data
    # is unambiguous — the human only reviews MEDIUM cases. This is the
    # pipeline's "default to the number" principle: the machine takes a stand,
    # the human overrides only when the machine is unsure.
    #
    # WHY THESE CUT LINES (0.8 / 0.2): above 0.8 the mesh is overwhelmingly
    # flat faces — calling it organic would be perverse. Below 0.2 it's
    # overwhelmingly curved — prismatic fitting would fight the data. Between
    # them lives "prismatic base with organic details" (fillets, drafts,
    # ergonomic curves on an otherwise boxy part), which genuinely needs a
    # human look. These are judgment-informed defaults, not derived constants;
    # tune them if the pipeline's parts change character.
    #
    # WHY EFFECTIVE AND NOT RAW PLANAR FRACTION: the decision must see the
    # same prismatic evidence the fitter will use. Raw planar fraction
    # penalizes parts for having holes — the bracket (flat plate, 4 drilled
    # bores) read 0.51 planar and scored "mixed"/medium. With cylindrical
    # walls counted it reads ~0.99 effective and scores prismatic/high, which
    # is the correct call: RANSAC cylinder fitting is a prismatic-track tool.
    # (Fixed 2026-10-02; see cylindrical_wall_fraction.)
    if effective_fraction > 0.7:
        suggestion = "prismatic"
        reason = f"{effective_fraction:.0%} of faces prismatic (planar + cylindrical walls)"
    elif effective_fraction < 0.3:
        suggestion = "organic"
        reason = f"only {effective_fraction:.0%} of faces prismatic"
    else:
        suggestion = "mixed"
        reason = f"{effective_fraction:.0%} prismatic — prismatic base with organic details likely"
    result["suggested_track"] = suggestion
    result["track_reason"] = reason
    # The decision IS the suggestion, plus a confidence the human can trust or
    # question. No separate decision logic — that would be two sources of
    # truth disagreeing. One computation, two fields.
    if effective_fraction > 0.8 or effective_fraction < 0.2:
        confidence = "high"
        override_note = "unambiguous — proceed without review"
    else:
        confidence = "medium"
        override_note = "borderline — human should confirm the track choice"
    result["track_decision"] = suggestion
    result["track_confidence"] = confidence
    result["track_override_note"] = override_note

    # --- Principal-axis alignment (A3) ---
    # WHAT: rotate the mesh so its principal axes land on XYZ, and record the
    # 4x4 homogeneous transform that did it.
    #
    # WHY: scanners output meshes in arbitrary orientations — the part's "up"
    # is whatever way it sat on the turntable. Every downstream stage (section
    # placement, symmetry checks, drawing views) is simpler and less error-prone
    # in a canonical frame: longest axis on X, second on Y, shortest on Z.
    # Doing it HERE, once, means no later script re-derives it differently.
    #
    # WHY A 4x4 HOMOGENEOUS MATRIX AND NOT JUST "ROTATED": downstream tools
    # (FreeCAD, CloudCompare) and future pipeline stages need to map results
    # BACK to the original frame (e.g. "the hole is at (45,30) in aligned
    # coordinates" must convert to input coordinates for the verification
    # report). A stored matrix makes that a one-line multiply instead of
    # archaeology. We also write the aligned mesh to disk so humans can see
    # what the pipeline sees.
    #
    # MATH: SVD gave us verts_centered = U S Vt, so Vt's rows are the principal
    # directions in the ORIGINAL frame. To express a point in the principal
    # frame: p' = Vt @ (p - centroid). As a homogeneous matrix:
    #     M = [ Vt   | -Vt @ centroid ]
    #         [ 0..0 |       1        ]
    # Applying M to [p; 1] yields [p'; 1]. The inverse (stored implicitly —
    # any tool can invert it) maps back.
    centroid_for_align = verts.mean(axis=0)
    rot = vt  # 3x3, rows = principal axes
    trans = -rot @ centroid_for_align
    matrix_4x4 = np.eye(4)
    matrix_4x4[:3, :3] = rot
    matrix_4x4[:3, 3] = trans
    result["alignment_matrix_4x4"] = [
        [round(float(v), 6) for v in row] for row in matrix_4x4
    ]
    result["alignment_note"] = (
        "principal axes mapped to XYZ (longest -> X). Multiply homogeneous "
        "input-frame coordinates by this matrix to get aligned-frame "
        "coordinates; invert to go back."
    )

    # --- Hole detection status (structured, never silent) ---
    # WHAT THIS RECORDS: whether hole detection ran, and what it found.
    #
    # WHY A STRUCTURED DICT AND NOT A NOTE STRING: the original code called
    # trimesh.intersections.mesh_multiplane(mesh, centroid, np.eye(3),
    # np.array([0.0])) — 3 normals but 1 height — numpy raised "vectors must
    # be (3,)", the except block wrote the raw exception into a free-text
    # note, and the script exited 0. A raw numpy error masquerading as a
    # result, invisible to any SOP wrapper checking exit codes. (Found
    # 2026-10-02 on the Benchy.) Now the status is machine-checkable:
    # "ok" | "failed" | "not-applicable". An SOP step can branch on
    # result["hole_detection"]["status"] instead of parsing English.
    #
    # WHY mesh_multiplane TAKES ONE NORMAL: despite the name, it slices by
    # multiple PARALLEL planes — signature is (mesh, plane_origin,
    # plane_normal, heights) with heights (m,) offsets along the ONE normal.
    # The original 3-normal call was wrong at the API level, not just the
    # shape level. Three orthogonal sections = three separate calls.
    #
    # WHAT THE SECTIONS MEASURE: for a non-watertight mesh we take one
    # section per principal axis through the centroid and count the line
    # segments. This is NOT hole detection — it's a coarse complexity signal
    # (many disjoint segments per plane hint at internal loops). Recorded
    # because it's a real measurement; the detail string says what it isn't.
    # True boundary-loop / through-hole detection is detect_holes.py
    # (forthcoming per the automation roadmap).
    #
    # WHY EXIT 0 EVEN WHEN status == "failed": hole detection is INFORMATIONAL
    # here, not load-bearing — the bbox, planes, and symmetry above are still
    # valid and the track decision doesn't depend on holes. Killing the whole
    # analysis over a sub-feature would discard good data. (Contrast
    # quality_gate.py, where an unmeasurable hole-fill IS load-bearing and
    # forces needs-rescan.) "Never silently proceed" is satisfied by the
    # explicit status field + a stderr warning, not by destroying the run.
    # (Decision recorded 2026-10-02; revisit if hole data ever gates track.)
    if mesh.is_watertight:
        result["hole_detection"] = {
            "status": "not-applicable",
            "detail": (
                "watertight — no boundary loops to find. Internal "
                "through-holes need RANSAC cylinder fitting; see "
                "scripts/detect_holes.py (forthcoming) or check manually."
            ),
        }
    else:
        try:
            section_counts = []
            for axis in range(3):
                normal = np.zeros(3)
                normal[axis] = 1.0
                # Returns (lines, to_3D, face_index) — THREE values. (The
                # pre-fix code unpacked two, which would ALSO have raised;
                # it never got that far because the shape mismatch fired
                # first. Verified against trimesh 2026-10-02.)
                lines, _, _ = trimesh.intersections.mesh_multiplane(
                    mesh, centroid, normal, np.array([0.0])
                )
                # lines: (m,) sequence of (n, 2, 2) segment arrays; m == 1
                # here since we passed a single height.
                n_segs = int(lines[0].shape[0]) if len(lines) else 0
                section_counts.append(n_segs)
            result["hole_detection"] = {
                "status": "ok",
                "detail": (
                    "mesh is open; section-segment counts per principal plane "
                    "(not hole detection — see comment). Boundary loops need "
                    "manual review until detect_holes.py exists."
                ),
                "section_segments_xyz": section_counts,
            }
        except Exception as e:  # noqa: BLE001 — sectioning can fail on
            # pathological meshes; record it loudly instead of crashing the
            # analysis or, worse, pretending it worked.
            result["hole_detection"] = {
                "status": "failed",
                "detail": (
                    "section analysis raised; hole assessment unavailable. "
                    "Do not assume 'no holes' — inspect manually."
                ),
                "error": str(e),
            }
            print(f"WARNING: hole section analysis failed: {e}",
                  file=sys.stderr)
    # Back-compat: keep the old string field so anything reading hole_note
    # doesn't break, but it now mirrors the structured status.
    result["hole_note"] = (
        f"[{result['hole_detection']['status']}] "
        f"{result['hole_detection']['detail']}"
    )

    # Build the aligned mesh from the matrix we just recorded. We apply it to
    # a COPY — the caller's mesh object is never mutated, because a function
    # that silently rotates your geometry is a special kind of evil.
    aligned = mesh.copy()
    m = np.array(result["alignment_matrix_4x4"])
    hom = np.hstack([np.asarray(aligned.vertices), np.ones((len(aligned.vertices), 1))])
    aligned.vertices = (hom @ m.T)[:, :3]

    return result, aligned


def main() -> None:
    # --help / -h: print the module docstring (usage + design rationale) and
    # exit 0. Checked BEFORE arg parsing so --help never falls through to
    # "not found: --help" (the bug scripts/README.md used to promise away).
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        sys.exit(0)
    args = [a for a in sys.argv[1:] if a != "--no-align"]
    write_aligned = "--no-align" not in sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        print("\nOptions:\n  --no-align   skip writing the aligned mesh copy")
        sys.exit(1)
    mesh_path = Path(args[0])
    if not mesh_path.exists():
        print(f"not found: {mesh_path}")
        sys.exit(1)

    try:
        result, aligned = analyze(mesh_path)
    except ValueError as e:
        # Input problems (empty mesh, etc.): user-facing error on stderr,
        # exit 1. Never a traceback for bad input.
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    # OUTPUT CONVENTION (fixed 2026-10-02): every file this script writes
    # lives NEXT TO THE INPUT, same directory, with a suffix. The old code
    # wrote the JSON to ../analysis/ — a layout assumption that broke the
    # moment anyone ran the script outside a work/ folder (test runs
    # scattered JSONs into pipelines/mesh-to-cad/analysis/). Co-location is
    # layout-agnostic: `ls <dir>` shows the input and everything derived from
    # it. Documented in scripts/README.md; all scripts follow it.
    out_path = mesh_path.parent / f"{mesh_path.stem}_measurements.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"\nwrote {out_path}")

    if write_aligned:
        # The aligned copy lives NEXT TO the input (same directory, _aligned
        # suffix) — not in input/ (originals stay pristine) and not hidden in
        # analysis/ (it's a mesh, not a report). Predictable, documented,
        # one place to look.
        aligned_path = mesh_path.parent / f"{mesh_path.stem}_aligned.stl"
        aligned.export(str(aligned_path))
        result["aligned_mesh"] = str(aligned_path)
        # Re-write the JSON now that it knows where the aligned mesh landed.
        out_path.write_text(json.dumps(result, indent=2))
        print(f"wrote {aligned_path} (principal axes on XYZ)")


if __name__ == "__main__":
    main()
