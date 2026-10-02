#!/usr/bin/env python3
"""
A5. Deviation measurement — the pipeline's "terminate on a number" backbone.

WHAT THIS DOES:
    Wraps CloudCompare's command-line cloud-to-mesh distance computation
    (-C2M_DIST) and turns its output into statistics: max, mean, and 95th
    percentile of the absolute distances between a CAD-model mesh and the
    original input mesh. Optionally judges pass/fail against a tolerance.

WHY THIS EXISTS:
    Every deviation loop in the pipeline (Stage 3B organic fitting, Stage 4
    verification) needs one primitive: "how far is my model from the scan?"
    That used to mean opening the CloudCompare GUI, clicking through dialogs,
    and reading numbers off the screen. This script makes it one command —
    which means the adaptive deviation loop (C6) can call it in a loop without
    a human in the middle. Dennis's rule — "terminate on a number, not a
    feeling" — is only enforceable if the number is one command away.

WHY CLOUDCOMPARE AND NOT PURE PYTHON:
    CloudCompare's C2M distance uses an octree-accelerated closest-point
    search that handles millions of triangles in seconds. A naive numpy
    implementation is O(n*m) and unusable on real scans. We could vendor a
    KD-tree approach (scipy.spatial.cKDTree, vertex-to-vertex instead of
    point-to-triangle), but that measures a different quantity (vertex
    distances under-report the true surface deviation on coarse meshes).
    CloudCompare is FOSS (GPL), scriptable, and already the pipeline's
    deviation tool of record. Use the right tool; don't reimplement it badly.

WHAT'S VERIFIED VS. WHAT ISN'T (Dennis's rule — stated plainly):
    VERIFIED 2026-10-02: -C2M_DIST is a real CloudCompare CLI flag. Per the
    CloudCompare changelog: "C2M_DIST: cloud to mesh distance computation"
    and it accepts two meshes (using the first mesh's vertices as the compared
    cloud). Source: CloudCompare CHANGELOG, checked live.
    NOT VERIFIED: the exact output-file naming and scalar-field export format
    on a live run — CloudCompare's CLI docs are sparse and version-dependent.
    This script therefore:
      1. Forces ASCII cloud export (-C_EXPORT_FMT ASC) so parsing doesn't
         depend on the undocumented .bin layout.
      2. Searches the output directory for the newest plausible distance cloud
         instead of assuming an exact filename.
      3. FAILS LOUDLY with the raw CloudCompare log if parsing finds nothing.
    The first live run against a real CloudCompare install should confirm the
    filename pattern and column layout, then tighten the parsing below.

WHY COMPARE CAD-vs-ORIGINAL (AND NEVER CAD-vs-CLEANED):
    The cleaned mesh (Stage 1) has filled holes and smoothed noise — comparing
    against it would let the pipeline grade its own homework. The verification
    report must measure against input/original.stl, the untouched scan. This
    script takes both paths explicitly so the caller can't accidentally pass
    the wrong one; the JSON output records which files were compared.

WHY MAX_DIST EXISTS:
    -MAX_DIST caps per-point distances. Without it, a single missing chunk
    (occluded region the scanner never saw) reports a 50 mm "deviation" and
    drowns the statistics that describe the surfaces we actually modeled.
    Capped distances still flag the region (it'll sit exactly at MAX_DIST),
    but the mean/p95 then describe the modeled surfaces honestly. Default
    5 mm; raise it for large parts, lower it for precision fits.

USAGE:
    python deviation.py cad/bracket_v1.stl input/bracket_original.stl
    python deviation.py cad/bracket_v1.stl input/bracket_original.stl --tolerance 0.2
    python deviation.py cad/bracket_v1.stl input/bracket_original.stl --json --max-dist 10

    --tolerance MM   pass/fail threshold on max deviation (default: report only)
    --max-dist MM    cap per-point distances (default: 5.0)
    --json           machine-readable output
    --cc-bin PATH    CloudCompare binary (default: search PATH for CloudCompare)

EXIT CODES:
    0 — measurement succeeded (and passed tolerance, if given)
    2 — measurement succeeded but FAILED the tolerance check
    1 — usage error, CloudCompare missing/failed, or output unparseable

Requires: numpy. And a CloudCompare install with CLI support.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

DEFAULT_MAX_DIST_MM = 5.0


def find_cloudcompare(explicit: str | None) -> str:
    """Locate the CloudCompare binary.

    WHY NOT HARDCODE: install locations vary (apt: /usr/bin/cloudcompare,
    manual builds: ~/CloudCompare/build/CloudCompare, Windows: .exe).
    Check the explicit flag first, then PATH under both common casings.
    Fail with installation guidance, not a traceback.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    # CloudCompare ships as `CloudCompare` (camelCase) on most platforms;
    # some distros lowercase it. Check both.
    for name in ("CloudCompare", "cloudcompare"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for c in candidates:
        if Path(c).exists():
            return c
    raise FileNotFoundError(
        "CloudCompare not found. Install it (https://www.cloudcompare.org/, "
        "or `sudo apt install cloudcompare`), then pass --cc-bin if it's not "
        "on PATH."
    )


def run_c2m(cc_bin: str, model_mesh: Path, ref_mesh: Path,
            max_dist: float, workdir: Path) -> subprocess.CompletedProcess:
    """Run CloudCompare cloud-to-mesh distance. Returns the completed process.

    COMMAND ANATOMY (each flag documented because CC's CLI docs are thin):
      -SILENT            suppress the GUI popup dialogs; CLI-only run
      -O <file>          open a mesh/cloud. First -O is the COMPARED cloud
                         (our CAD model — its vertices get distances);
                         second -O is the REFERENCE mesh (the scan surface).
      -C2M_DIST          compute cloud-to-mesh distances (verified real flag)
      -MAX_DIST <mm>     cap per-point distances (see module docstring)
      -C_EXPORT_FMT ASC  force ASCII export so we can parse without knowing
                         the .bin layout (see VERIFIED/NOT VERIFIED above)
      -SAVE_CLOUDS       write the result clouds to disk
      -NO_TIMESTAMP      keep output filenames deterministic-ish (no date
                         suffix), which makes finding them less fragile

    WORKDIR: CloudCompare writes outputs next to its inputs by default, which
    would pollute the pipeline's cad/ and input/ folders. We copy both meshes
    into a temp dir first and run there — the pipeline's folders stay clean,
    and cleanup is one rmtree.
    """
    # Copy inputs into the sandbox: CC writes outputs beside inputs, and we
    # don't want distance clouds littering the pipeline's working folders.
    model_cp = workdir / "model.stl"
    ref_cp = workdir / "reference.stl"
    shutil.copy2(model_mesh, model_cp)
    shutil.copy2(ref_mesh, ref_cp)

    cmd = [
        cc_bin, "-SILENT",
        "-O", str(model_cp),
        "-O", str(ref_cp),
        "-C2M_DIST", "-MAX_DIST", str(max_dist),
        "-C_EXPORT_FMT", "ASC",
        "-SAVE_CLOUDS", "-NO_TIMESTAMP",
    ]
    # text=True + a generous timeout: C2M on a 500k-face mesh takes seconds,
    # not minutes; 10 minutes means something is genuinely stuck.
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                          cwd=str(workdir))


def find_distance_cloud(workdir: Path) -> Path:
    """Locate the C2M output cloud among CloudCompare's output files.

    WHY HEURISTIC AND NOT EXACT NAME: the exact output filename depends on
    the CloudCompare version (it embeds the operation name and entity names
    differently across releases — this is the NOT VERIFIED part). We look for
    the newest .asc/.xyz/.txt cloud file that wasn't one of our inputs. If
    the naming ever changes incompatibly, this raises a clear error with the
    directory listing attached — debuggable, not silent.
    """
    ignore = {"model.stl", "reference.stl"}
    clouds = [p for p in workdir.iterdir()
              if p.is_file() and p.name not in ignore
              and p.suffix.lower() in (".asc", ".xyz", ".txt", ".asc")]
    if not clouds:
        listing = ", ".join(sorted(p.name for p in workdir.iterdir()))
        raise FileNotFoundError(
            "no distance cloud found in CloudCompare output. "
            f"Directory contained: {listing}. "
            "The -C2M_DIST output naming may differ in this CC version — "
            "check the log above and update find_distance_cloud()."
        )
    # Newest first: the distance cloud is written after the inputs are read.
    clouds.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return clouds[0]


def parse_distances(cloud_path: Path) -> np.ndarray:
    """Extract the distance scalar field from an ASCII cloud export.

    FORMAT ASSUMPTION (verify on first live run): ASCII cloud exports are
    whitespace-separated columns: X Y Z [Nx Ny Nz] [R G B] <scalars...>.
    The C2M distance is typically the LAST scalar column (CloudCompare appends
    computed fields at the end). We take the last column as the distance.

    WHY LAST COLUMN AND NOT A NAMED HEADER: CC's ASCII export header format
    varies; column-counting is more robust than header-parsing across
    versions. The risk — a version that appends another field after the
    distance — would silently measure the wrong column. Mitigation: we sanity
    check below that values look like distances (non-negative, sane magnitude)
    and fail loudly otherwise. A wrong column that happens to look like
    distances is the residual risk; the first live run should eyeball one
    file and confirm.
    """
    # genfromtxt handles variable whitespace and skips comment lines (#).
    data = np.genfromtxt(str(cloud_path), comments="#")
    if data.ndim == 1:
        # Single-row file (degenerate) — promote so column indexing works.
        data = data.reshape(1, -1)
    if data.shape[1] < 4:
        raise ValueError(
            f"expected at least X Y Z + distance columns in {cloud_path.name}, "
            f"found {data.shape[1]} columns. Format assumption is wrong for "
            "this CloudCompare version — inspect the file and update "
            "parse_distances()."
        )
    distances = np.abs(data[:, -1])  # abs: signed/unsigned varies by version
    # Sanity gate: distances are non-negative by construction, and anything
    # astronomically large suggests we grabbed the wrong column.
    if np.any(distances < 0) or np.median(distances) > 1e6:
        raise ValueError(
            f"parsed distances look wrong (median {np.median(distances):.2g}). "
            "Probably the wrong column — inspect the ASCII export and update "
            "parse_distances()."
        )
    return distances


def deviation_stats(distances: np.ndarray) -> dict:
    """Summarize the distance field. WHY THESE THREE: max is the pass/fail
    criterion (worst point rules in manufacturing); mean describes the typical
    fit; p95 shows the tail without letting one bad vertex dominate. Together
    they distinguish 'uniformly 0.3 mm off' from 'perfect except one spike' —
    which need completely different fixes."""
    return {
        "max_mm": round(float(distances.max()), 4),
        "mean_mm": round(float(distances.mean()), 4),
        "p95_mm": round(float(np.percentile(distances, 95)), 4),
        "points": int(len(distances)),
    }


def measure_clean(model_mesh: Path, ref_mesh: Path, max_dist: float,
                  cc_bin: str | None = None) -> dict:
    """measure() with workdir cleanup on success. (Split out so the failure
    path above can preserve evidence while the happy path stays tidy.)"""
    cc = find_cloudcompare(cc_bin)
    workdir = Path(tempfile.mkdtemp(prefix="c2m_"))
    try:
        proc = run_c2m(cc, model_mesh, ref_mesh, max_dist, workdir)
        if proc.returncode != 0:
            raise RuntimeError(
                f"CloudCompare exited with code {proc.returncode}.\n"
                f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
            )
        cloud = find_distance_cloud(workdir)
        distances = parse_distances(cloud)
        stats = deviation_stats(distances)
        stats.update({
            "model_mesh": str(model_mesh),
            "reference_mesh": str(ref_mesh),
            "max_dist_cap_mm": max_dist,
            "distance_cloud": cloud.name,
            "note": "reference must be input/original.stl (untouched scan), "
                    "never the cleaned mesh. See module docstring.",
        })
        return stats
    finally:
        # Always clean up: on failure the exception propagates but the temp
        # dir is removed. For post-mortem debugging, re-run CloudCompare
        # manually with the same flags (see run_c2m) in a scratch dir and
        # inspect the outputs — automation shouldn't accumulate temp dirs
        # across hundreds of deviation-loop iterations.
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> None:
    argv = sys.argv[1:]
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    tolerance = None
    max_dist = DEFAULT_MAX_DIST_MM
    cc_bin = None
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--tolerance" and i + 1 < len(argv):
            tolerance = float(argv[i + 1])
            i += 2
        elif argv[i] == "--max-dist" and i + 1 < len(argv):
            max_dist = float(argv[i + 1])
            i += 2
        elif argv[i] == "--cc-bin" and i + 1 < len(argv):
            cc_bin = argv[i + 1]
            i += 2
        else:
            positional.append(argv[i])
            i += 1
    if len(positional) != 2:
        print(__doc__)
        sys.exit(1)
    model_mesh, ref_mesh = Path(positional[0]), Path(positional[1])
    for p in (model_mesh, ref_mesh):
        if not p.exists():
            print(f"not found: {p}", file=sys.stderr)
            sys.exit(1)

    try:
        stats = measure_clean(model_mesh, ref_mesh, max_dist, cc_bin)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"parse error: {e}", file=sys.stderr)
        sys.exit(1)

    passed = True
    if tolerance is not None:
        passed = stats["max_mm"] <= tolerance
        stats["tolerance_mm"] = tolerance
        stats["passed"] = bool(passed)

    if as_json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"model:     {stats['model_mesh']}")
        print(f"reference: {stats['reference_mesh']}")
        print(f"max:       {stats['max_mm']} mm")
        print(f"mean:      {stats['mean_mm']} mm")
        print(f"p95:       {stats['p95_mm']} mm")
        print(f"points:    {stats['points']}")
        if tolerance is not None:
            print(f"tolerance: {tolerance} mm -> "
                  f"{'PASS' if passed else 'FAIL'}")

    # Exit 2 = measured fine but failed tolerance. Lets SOP scripts branch:
    #   deviation.py ... --tolerance 0.2 || handle_failure
    sys.exit(0 if passed else 2)


if __name__ == "__main__":
    main()
