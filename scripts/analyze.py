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

Requires: trimesh, numpy, scipy
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh


def analyze(mesh_path: Path) -> tuple:
    """Analyze the mesh; returns (result_dict, aligned_mesh).

    The aligned mesh is the input rotated/translated so principal axes lie on
    XYZ (see the alignment block inside). Callers that need the working-frame
    mesh should use it; callers that only need numbers can ignore it.
    """
    mesh = trimesh.load(str(mesh_path), force="mesh")
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
    if planar_fraction > 0.7:
        suggestion = "prismatic"
        reason = f"{planar_fraction:.0%} of faces on dominant planes"
    elif planar_fraction < 0.3:
        suggestion = "organic"
        reason = f"only {planar_fraction:.0%} of faces on dominant planes"
    else:
        suggestion = "mixed"
        reason = f"{planar_fraction:.0%} planar — prismatic base with organic details likely"
    result["suggested_track"] = suggestion
    result["track_reason"] = reason
    # The decision IS the suggestion, plus a confidence the human can trust or
    # question. No separate decision logic — that would be two sources of
    # truth disagreeing. One computation, two fields.
    if planar_fraction > 0.8 or planar_fraction < 0.2:
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

    # --- Hole candidates: boundary loops ---
    # (watertight meshes have no boundary loops; report only if open)
    if not mesh.is_watertight:
        try:
            paths, _ = trimesh.intersections.mesh_multiplane(
                mesh, centroid, np.eye(3), np.array([0.0])
            )
            result["hole_note"] = (
                "mesh is open; boundary-loop hole detection needs manual review"
            )
        except Exception as e:  # noqa: BLE001
            result["hole_note"] = f"hole detection skipped: {e}"
    else:
        result["hole_note"] = (
            "watertight — internal holes (through-holes) need RANSAC cylinder "
            "fitting; run scripts/detect_holes.py (forthcoming) or check manually"
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

    result, aligned = analyze(mesh_path)
    out_name = mesh_path.stem.replace("_clean", "") + "_measurements.json"
    out_path = mesh_path.parent.parent / "analysis" / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
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
