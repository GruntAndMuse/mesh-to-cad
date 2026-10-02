# System Requirements — mesh-to-cad

Everything you need to run the pipeline, stated plainly. No guessing.

## Software

### Operating system

| OS | Status |
|---|---|
| Linux (Ubuntu 22.04+, Debian 12+) | **Tested** — primary dev platform |
| Windows 10 / 11 | **Untested but expected to work** — use `mesh-to-cad.bat` or `python mesh-to-cad`. Report issues on GitHub. |
| macOS 13+ | **Untested but expected to work** — Python + venv flow is identical. Report issues on GitHub. |

If you run it on Windows or Mac, tell us it worked (or didn't) at
https://github.com/GruntAndMuse/mesh-to-cad/issues — that's how the table
above gets more green.

### Python

- **Required:** Python 3.10 or newer
- **Tested on:** 3.12.3
- The pipeline will not run on Python 2. If `python3 --version` says
  3.8 or older, install a newer Python from https://www.python.org/downloads/

### Python packages

Installed automatically via `pip install -r scripts/requirements.txt`:

| Package | Minimum | Tested | What it's for |
|---|---|---|---|
| trimesh | 4.0 | 5.1.0 | Mesh loading, bounds, splitting, hole filling |
| numpy | 1.24 | 2.5.3 | All numeric work |
| scipy | 1.10 | 1.10 | cKDTree (symmetry check) |
| networkx | 3.0 | 3.7 | Boundary-loop detection for hole filling |

Version floors are deliberately loose (`>=`, not `==`) — this is a FOSS
pipeline meant to be forked on random laptops in 2027. Exact pins rot.
If a future version breaks an API we use, we'll pin it then and document why.

**Deliberately NOT required:** Open3D (~500 MB). The Taubin smoothing in
`quality_gate.py` is implemented in ~15 lines of numpy instead. See the
script's docstring for the full reasoning.

### CloudCompare (for `deviation` only)

- **Needed for:** `mesh-to-cad deviation` — the cloud-to-mesh distance check
- **Not needed for:** `mesh-to-cad <file>`, `units`, `check`, `analyze`
- **Where to get it:** https://www.cloudcompare.org/ (free, GPL)
- **Version:** any recent 2.x. Tested against the `-C2M_DIST` CLI flag,
  which has existed since CloudCompare 2.6.
- **Verify it's on PATH:** run `CloudCompare -SILENT` (or `cloudcompare`
  on some Linux distros). If you get a "not found" error, either add it
  to PATH or pass `--cc-bin /path/to/CloudCompare` — the CLI accepts it,
  though `mesh-to-cad deviation` doesn't yet forward it (use
  `scripts/deviation.py --cc-bin` directly for now).

### Other external tools (manual pipeline stages)

These aren't called by the CLI — they're for the hands-on stages the CLI
guides you to:

| Tool | License | Used for |
|---|---|---|
| FreeCAD 1.0+ | LGPL | Parametric CAD rebuild (Stage 3) |
| MeshLab | GPL | Mesh cleanup (Stage 1) |
| MeshToFeatures workbench | LGPL-2.1 | Auto reverse-engineering of clean prismatic meshes |

## Hardware

### Minimum

- **RAM:** 4 GB (handles meshes up to ~50 MB / ~500k faces)
- **CPU:** any 64-bit processor from the last 10 years. Single-threaded
  Python — more cores don't help, but they don't hurt.
- **Disk:** 100 MB for the repo + venv. Project folders are small
  (measurements are JSON; aligned STLs are the same size as inputs).
- **GPU:** **Not needed.** Nothing in this pipeline touches the GPU.
  If someone tells you to buy a GPU for mesh-to-CAD, they're selling you
  something.

### Measured resource usage

Real numbers from the test suite (2026-10-02, 2-core VM):

| Input | Verts / Faces | Peak RAM (quality gate) | Time |
|---|---|---|---|
| bracket (39 KB STL) | 392 / 796 | ~40 MB | <2 sec |
| blob (251 KB STL) | ~5k / ~10k | ~80 MB | ~3 sec |
| benchy (11 MB STL) | 112k / 225k | **~333 MB** | ~20 sec |

**Rule of thumb:** peak RAM ≈ 30× the STL file size during the quality
gate (Taubin smoothing + component splitting are the hungry steps).
A 50 MB scan → ~1.5 GB RAM. A 200 MB scan → ~6 GB — you'll want 16 GB
on the machine.

### Huge files

- **>500k faces:** works, but slow (minutes, not seconds). Decimate first
  in MeshLab if you don't need full density for measurement.
- **>2M faces / >200 MB:** likely to exhaust RAM on an 8 GB machine.
  The failure mode is Python raising `MemoryError` — the CLI will report
  it as a crash, not silently produce wrong numbers. Split the mesh or
  use a bigger machine.
- **What "too big" looks like:** the process gets slow, then dies with
  `MemoryError` or the OS kills it (OOM). It will NOT quietly give you
  bad measurements — that's a design rule.

## Security & privacy

**Privacy is a core design principle, not a docs section.** This pipeline
is built for people who don't want their files leaving their machine —
no telemetry to disable, no accounts to delete, no cloud to trust. The
architecture reflects that: everything runs local, period.

**This tool never sends your files or data anywhere.** Stated plainly:

- **No network calls.** The Python code makes zero HTTP requests, opens
  zero sockets, and contacts zero servers. Verified by code inspection —
  the only URLs in the codebase are in help text and error messages
  (links to CloudCompare's download page and the GitHub issue tracker).
- **No telemetry.** Nothing phones home. No usage stats, no crash reports,
  no "check for updates."
- **No accounts.** No login, no license server, no activation.
- **File access:** reads the mesh files you point it at; writes outputs
  (measurements JSON, aligned STL, manifest) into the project folder it
  creates. It never touches files outside the input path and the project
  folder.
- **The only network touchpoint** in the entire workflow is you downloading
  the code from GitHub in the first place. After that, it's fully offline —
  which also means it works on air-gapped machines.

- **Dependencies pinned and auditable.** Every package is listed in
  `scripts/requirements.txt` with its purpose. No hidden downloads, no
  auto-updaters, no binary blobs.
- **Input files never leave your machine.** Not for processing, not for
  "improvement," not for anything.

If you ever find a network call in the code that isn't documented here,
that's a bug — report it at
https://github.com/GruntAndMuse/mesh-to-cad/issues and we'll fix it.
