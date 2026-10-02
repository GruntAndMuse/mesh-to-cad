#!/usr/bin/env python3
"""
A1. Unit heuristic — catch the "1000x wrong" mistake before it corrupts everything.

WHAT THIS DOES:
    Reads a mesh, measures its bounding-box diagonal, and guesses whether the
    file's units are millimeters, meters, inches, or micrometers. It outputs a
    suggested scale factor plus a confidence level. A human confirms with one
    keystroke — this script never silently rescales anything.

WHY THIS EXISTS:
    Scanners and download sites disagree on units constantly. A 100 mm bracket
    exported in meters arrives as 0.1 "mm". If you build CAD from that without
    noticing, every downstream dimension is wrong by 1000x — and the error is
    silent, because the geometry *looks* right, just tiny. Of all the cheap
    mistakes in this pipeline, wrong units is the most expensive per second of
    prevention. This script is that one second.

WHY BOUNDING-BOX DIAGONAL (AND NOT VOLUME OR EXTENTS):
    - A single number is easier to reason about in threshold bands than three.
    - Diagonal captures overall scale regardless of part orientation.
    - Volume collapses for thin/flat parts (a 200 mm plate can have tiny volume),
      which would false-trigger the "meters" branch. Diagonal doesn't have that
      failure mode.

WHY THESE THRESHOLDS:
    This pipeline's world is human-scale physical parts: brackets, mounts,
    housings, printer components. Realistically 1 mm to ~2000 mm.
    - diagonal < 5: absurdly small for millimeters. A real 4 mm part exists, but
      a 0.1-diagonal "part" is almost certainly 100 mm expressed in meters.
      Suggest x1000, confidence HIGH. (The 4 mm real-part case is why the human
      still confirms — the script suggests, never decides.)
    - diagonal < 2000: the sane band. A part between 5 mm and 2 m diagonal is
      plausibly millimeters. Suggest x1, confidence HIGH.
    - diagonal >= 2000: absurdly large for millimeters. Either micrometers
      (divide by 1000) or inches (multiply by 25.4). We can't distinguish those
      two from scale alone — a 2540-diagonal part could be 2540 um (= 2.54 mm,
      tiny) or 2540 "mm" that are really inches (= 64.5 m, absurd). We report
      both candidates and mark confidence MEDIUM, because this branch genuinely
      needs the human to know what the part is.

    These bands are HEURISTICS, not physics. They encode "what do parts in this
    pipeline usually look like." If the pipeline ever handles microfluidics or
    architecture, revisit them.

USAGE:
    python check_units.py work/bracket_clean.stl
    python check_units.py work/bracket_clean.stl --json   # machine-readable

EXIT CODES:
    0 — a suggestion was produced (check the confidence field)
    1 — usage error / file not found / mesh unreadable
    NOTE: exit 0 does NOT mean "units confirmed." It means "here's my best
    guess." The human (or the calling SOP step) must still confirm.

Requires: trimesh, numpy
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

# --- Threshold bands (see module docstring for WHY these numbers) ---
# Everything below is in "whatever units the file claims are millimeters."
DIAGONAL_METERS_SUSPECT = 5.0      # below this: probably meters, suggest x1000
DIAGONAL_MM_PLAUSIBLE_MAX = 2000.0  # above this: probably um or inches
MM_PER_INCH = 25.4                  # exact, by international definition


def suggest_units(mesh_path: Path) -> dict:
    """Measure the mesh and return a unit suggestion with confidence.

    Returns a dict with:
      diagonal        — bbox diagonal in file units (the raw number)
      extents         — [x, y, z] bbox sizes, for the human's sanity check
      suggestion      — "meters" | "millimeters" | "micrometers-or-inches"
      scale_factor    — multiply file units by this to get millimeters
      scale_factor_alt— second candidate (only for the ambiguous branch)
      confidence      — "high" | "medium"
      why             — human-readable reasoning string
    """
    # force="mesh": trimesh.load can return a Scene for some formats; we want
    # the raw triangle soup so bounds are always computable.
    mesh = trimesh.load(str(mesh_path), force="mesh")
    extents = mesh.bounds[1] - mesh.bounds[0]
    diagonal = float(np.linalg.norm(extents))

    result = {
        "file": str(mesh_path),
        "diagonal_file_units": round(diagonal, 4),
        "extents_file_units": [round(float(e), 4) for e in extents],
    }

    if diagonal < DIAGONAL_METERS_SUSPECT:
        # A sub-5-unit diagonal is either a genuinely tiny part or a
        # meters-vs-millimeters mixup. The mixup is far more common, so we
        # suggest x1000 — but keep confidence honest about the ambiguity.
        # (If the human knows the part is really 3 mm across, they reject.)
        result.update({
            "suggestion": "meters",
            "scale_factor": 1000.0,
            "confidence": "high",
            "why": (
                f"diagonal {diagonal:.3f} is implausibly small for millimeters; "
                "most likely the file is in meters — multiply by 1000 to get mm. "
                "If the part really is under 5 mm across, reject this."
            ),
        })
    elif diagonal < DIAGONAL_MM_PLAUSIBLE_MAX:
        result.update({
            "suggestion": "millimeters",
            "scale_factor": 1.0,
            "confidence": "high",
            "why": (
                f"diagonal {diagonal:.1f} falls in the normal human-scale part "
                "band (5 mm – 2000 mm). No rescaling needed."
            ),
        })
    else:
        # Ambiguous branch: could be micrometers (÷1000) or inches (×25.4).
        # Scale alone cannot distinguish "2.54 mm expressed in um" from
        # "100 inches expressed as unitless numbers." We present both and let
        # the human — who has seen the physical part — pick.
        result.update({
            "suggestion": "micrometers-or-inches",
            "scale_factor": 0.001,          # candidate A: file is micrometers
            "scale_factor_alt": MM_PER_INCH,  # candidate B: file is inches
            "confidence": "medium",
            "why": (
                f"diagonal {diagonal:.1f} is implausibly large for millimeters. "
                "Two candidates: micrometers (x0.001) or inches (x25.4). "
                "Check against a known physical dimension of the part."
            ),
        })
    return result


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv[1:]
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    mesh_path = Path(args[0])
    if not mesh_path.exists():
        print(f"not found: {mesh_path}", file=sys.stderr)
        sys.exit(1)

    result = suggest_units(mesh_path)
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"file:      {result['file']}")
        print(f"diagonal:  {result['diagonal_file_units']} (file units)")
        print(f"extents:   {result['extents_file_units']}")
        print(f"suggestion: {result['suggestion']} "
              f"(x{result['scale_factor']}, confidence {result['confidence']})")
        if "scale_factor_alt" in result:
            print(f"  alt:      x{result['scale_factor_alt']}")
        print(f"why: {result['why']}")
        print("\nHuman: confirm or reject before any rescaling. "
              "This script never modifies the input file.")


if __name__ == "__main__":
    main()
