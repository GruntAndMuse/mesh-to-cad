# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Unified `mesh-to-cad` command** — one entry point for the whole pipeline.
  `mesh-to-cad myfile.stl` runs intake (units check), quality gate, and
  analysis in order, sets up the project folder, and prints next steps.
  Subcommands (`units`, `check`, `analyze`, `deviation`) cover the individual
  stages. You no longer need to know the scripts in `scripts/` exist —
  they're internal modules now. (Why: four scripts doing one pipeline is four
  chances to run them in the wrong order or forget a step. One command can't
  be misordered.)
- **QUICKSTART.md** — beginner guide assuming zero command-line experience.
  Covers installation, the one command to learn, what each stage does in
  plain English, what success/failure look like, and common errors with fixes.
- **Annotated screenshots** in `docs/screenshots/` — what the terminal looks
  like at each step, with the important parts circled. Referenced from
  QUICKSTART.md.
- **Friendly error messages** across the CLI — every error now says what
  happened AND what to do about it. Wrong file type, missing file, missing
  Python packages, missing CloudCompare, and bad arguments all produce
  actionable guidance instead of tracebacks.
- **`mesh-to-cad.bat`** — Windows wrapper so `mesh-to-cad` works from
  Command Prompt / PowerShell without typing `python` first.
- **REQUIREMENTS.md** — full system requirements: OS support table (tested
  vs untested), Python version, every dependency with tested versions,
  CloudCompare setup, measured RAM/time numbers per mesh size, and an
  explicit security statement (no network calls, no telemetry, no accounts —
  verified by code inspection).

### Changed
- **README.md** — now points at QUICKSTART.md as the entry point; the
  scripts table is reframed as "under the hood" (modules, not user interface).
- **Consistent output layout** — all pipeline outputs now live in a project
  folder (`<name>/input/`, `<name>/analysis/`, `<name>/manifest.json`).
  Previously each script wrote next to the input with its own convention.
- **`analyze.py` output placement** — measurements JSON and aligned STL now
  go next to the input file (previously JSON went to `../analysis/`).
  The CLI's full-pipeline mode places them in the project folder instead.
- **Step numbering in next-steps guidance** — fixed skipped numbers in the
  printed "what to do next" for prismatic and organic tracks.

### Fixed
- **analyze.py no longer silently skips hole detection on non-watertight meshes.**
  Previously it would report success while the hole-detection step had crashed
  internally — the raw error text was buried in a note field, and any automated
  workflow would proceed believing the step was "handled." Now hole detection
  reports an explicit machine-checkable status (`ok` / `failed` /
  `not-applicable`) in the measurements JSON, and failures also print a loud
  warning to stderr. If you automate the pipeline, check
  `hole_detection.status` — you'll never be misled again.
- **analyze.py no longer misclassifies holed prismatic parts as "mixed."**
  A flat plate with drilled holes used to score "mixed" with medium confidence
  because the hole bores diluted the planar-face count — the pipeline treated
  machined holes as "organic details." Holes are exactly what the prismatic
  track's cylinder fitting is for, so cylindrical walls (bores, extruded sides,
  turned diameters) now count as prismatic evidence. The holed bracket that
  exposed this now correctly scores prismatic/high. The JSON gains
  `cylindrical_fraction` and `effective_prismatic_fraction` fields so you can
  see the reasoning.
- **All four scripts now support `--help`.** The README always claimed they
  did; they actually rejected it with `not found: --help`. Now `--help` (or
  `-h`) prints the full usage and design documentation and exits 0.
- **quality_gate.py: high component counts now affect the verdict.** A mesh
  with more than 10 disconnected components now scores `noisy` instead of
  `clean`. Previously a 300-fragment Benchy read "clean" — measurable, but a
  scan that messy needs Stage 1 cleanup to isolate the real part before
  anything downstream trusts it. This is "proceed with caution," not "rescan":
  fragmentation is a cleanup problem, not missing data. (Assemblies with many
  real parts will also trip this — correctly, since the pipeline works one
  part at a time.)
- **Empty files no longer crash or mislead.** A 0-byte file used to crash
  `check_units.py` and `analyze.py` with a bare traceback, and
  `quality_gate.py` called it "clean" (every metric trivially passes on
  nothing). Now the first two print a clear error and exit 1, and the quality
  gate reports `needs-rescan` — because metrics passing on nothing is not a
  good scan.

### Security
- **Privacy is now an architectural guarantee, documented in SECURITY.md.**
  Audited the full codebase: zero network calls, zero telemetry, zero
  credentials anywhere in the repo. The pipeline runs fully offline after
  install (verified with networking disabled at the OS level). Added
  `scripts/requirements-locked.txt` with exact tested dependency versions
  for reproducible, auditable installs. SECURITY.md tells you how to verify
  all of this yourself instead of trusting us.
