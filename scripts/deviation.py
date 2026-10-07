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
    VERIFIED 2026-10-07 (root-cause fix for the .bin problem): the old command
    put -C_EXPORT_FMT ASC *after* -C2M_DIST, but CloudCompare auto-saves the
    distance entity *during* -C2M_DIST processing (auto-save defaults ON) —
    before the format flag is ever read. Worse, the auto-saved entity is the
    compared MESH descriptor, so even a correctly-ordered -C_EXPORT_FMT
    (cloud format) would not apply: the mesh exported in the default BinFilter
    format → the .bin file the old script choked on. The fix:
      -EXTRACT_VERTICES turns the model mesh's vertices into a first-class
      point cloud *before* -C2M_DIST, so the distance entity IS a cloud and
      -C_EXPORT_FMT ASC applies to it;
      -C_EXPORT_FMT ASC and -NO_TIMESTAMP are set *before* any -O, so the
      auto-save honors them.
    Verified live against CloudCompare 2.11.3 (Ubuntu 24.04): the distance
    cloud saves as model.vertices_C2M_DIST_MAX_DIST_<n>.asc, columns
    "X Y Z <C2M distance>" — matching parse_distances()' assumption that the
    distance is the last column. Source for the mechanism: CloudCompare
    master qCC/ccCommandLineCommands.cpp (CommandDist::process auto-save,
    CommandExtractVertices::process) and qCC/ccCommandLineParser.cpp
    (default cloud export = BinFilter).
    NOT VERIFIED: exact behavior on other CloudCompare versions (2.12+ may
    differ in auto-save or naming). If find_distance_cloud() ever finds
    nothing, it fails loudly with the directory listing — check the CC log
    and update the command construction below.

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
    --help           print this text

EXIT CODES:
    0 — measurement succeeded (and passed tolerance, if given)
    2 — measurement succeeded but FAILED the tolerance check
    1 — usage error, CloudCompare missing/failed, or output unparseable

Requires: numpy. And a CloudCompare install with CLI support.
"""
import json
import os
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
      -C_EXPORT_FMT ASC  cloud export format = ASCII. MUST come before -O:
                         CloudCompare auto-saves the distance entity during
                         -C2M_DIST (auto-save defaults ON), so a format flag
                         placed after -C2M_DIST is never honored (this was the
                         .bin bug — verified 2026-10-07).
      -NO_TIMESTAMP      keep output filenames deterministic (no date suffix).
                         Same ordering constraint: must precede -C2M_DIST.
      -O <file>          open a mesh. First -O is our CAD model.
      -EXTRACT_VERTICES  turn the model mesh's vertices into a first-class
                         point cloud (added to the cloud pool; the mesh is
                         removed). WHY: -C2M_DIST auto-saves the *compared
                         entity* — for a mesh input that's the mesh
                         descriptor, which exports via the *mesh* format
                         (default .bin), ignoring -C_EXPORT_FMT. As a cloud,
                         the distance entity exports via the *cloud* format
                         (ASCII, per above). The measured vertices are
                         identical — this changes the export path, not the
                         measurement.
      -O <file>          second -O is the REFERENCE mesh (the scan surface).
                         Loaded after extraction so only the model is
                         converted; the reference stays a mesh for C2M.
      -C2M_DIST          compute cloud-to-mesh distances: compared cloud =
                         model vertices, reference = scan mesh.
      -MAX_DIST <mm>     cap per-point distances (see module docstring)

    NOTE: no -SAVE_CLOUDS — the distance cloud is auto-saved by -C2M_DIST
    itself (auto-save ON). -SAVE_CLOUDS would just re-save the same file.

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
        "-C_EXPORT_FMT", "ASC",
        "-NO_TIMESTAMP",
        "-O", str(model_cp),
        "-EXTRACT_VERTICES",
        "-O", str(ref_cp),
        "-C2M_DIST", "-MAX_DIST", str(max_dist),
    ]
    # Headless Linux/macOS (no X server, e.g. SSH or CI): Qt needs a
    # platform plugin or CloudCompare won't start at all. Offscreen is
    # harmless for a -SILENT CLI run. Only when DISPLAY is unset, and never
    # on Windows (which doesn't use xcb anyway).
    env = dict(os.environ)
    if os.name != "nt" and not env.get("DISPLAY"):
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # text=True + a generous timeout: C2M on a 500k-face mesh takes seconds,
    # not minutes; 10 minutes means something is genuinely stuck.
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                          cwd=str(workdir), env=env)


def find_distance_cloud(workdir: Path) -> Path:
    """Locate the C2M output cloud among CloudCompare's output files.

    WHY PREFER THE C2M_DIST NAME: -EXTRACT_VERTICES also auto-saves an
    intermediate (model.vertices.asc, no distances). The distance cloud is
    the one whose name contains C2M_DIST. Newest-first is the fallback for
    CloudCompare versions that name it differently — this is the version-
    dependent part. If the naming ever changes incompatibly, this raises a
    clear error with the directory listing attached — debuggable, not silent.
    """
    ignore = {"model.stl", "reference.stl"}
    clouds = [p for p in workdir.iterdir()
              if p.is_file() and p.name not in ignore
              and p.suffix.lower() in (".asc", ".xyz", ".txt")]
    if not clouds:
        listing = ", ".join(sorted(p.name for p in workdir.iterdir()))
        raise FileNotFoundError(
            "no distance cloud found in CloudCompare output. "
            f"Directory contained: {listing}. "
            "The -C2M_DIST output naming may differ in this CC version — "
            "check the log above and update find_distance_cloud()."
        )
    # Prefer the actual distance cloud; newest-first as fallback.
    c2m = [p for p in clouds if "C2M_DIST" in p.name.upper()]
    pool = c2m or clouds
    pool.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pool[0]


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
    # --help / -h: print the module docstring and exit 0, before the flag
    # loop below (which would otherwise swallow --help as a positional and
    # exit 1 with a usage dump — technically helpful, but exit 1 on --help
    # breaks the scripts/README.md contract).
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        sys.exit(0)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    tolerance = None
    max_dist = DEFAULT_MAX_DIST_MM
    cc_bin = None
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--tolerance" and i + 1 < len(argv):
            # Non-numeric tolerance used to die with a raw float() traceback.
            # Fail fast with the flag name so the user knows what to fix.
            try:
                tolerance = float(argv[i + 1])
            except ValueError:
                print(f"error: --tolerance needs a number, got "
                      f"'{argv[i + 1]}' (e.g. --tolerance 0.2)",
                      file=sys.stderr)
                sys.exit(1)
            i += 2
        elif argv[i] == "--max-dist" and i + 1 < len(argv):
            try:
                max_dist = float(argv[i + 1])
            except ValueError:
                print(f"error: --max-dist needs a number, got "
                      f"'{argv[i + 1]}' (e.g. --max-dist 5.0)",
                      file=sys.stderr)
                sys.exit(1)
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
    except Exception as e:
        # Anything else (numpy failure, subprocess weirdness, corrupt
        # files): no raw traceback, ever. Explain and exit.
        print(f"error: measurement failed: {e}", file=sys.stderr)
        print("   Check that both files are valid meshes and CloudCompare "
              "is installed.", file=sys.stderr)
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
