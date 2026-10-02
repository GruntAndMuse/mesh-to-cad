# Security & Privacy Commitment

**Our principle:** security and privacy are baked in, not bolted on.
Privacy is a core human right. Your mesh files are *your* work — this
pipeline treats them that way.

## What we promise about your data

1. **No network calls. Ever.**
   The pipeline scripts and the `mesh-to-cad` CLI make zero HTTP requests,
   download nothing, and phone home for no reason. Once dependencies are
   installed, everything runs fully offline. Your input files are read from
   your disk, output files are written to your disk, and nothing leaves the
   machine in between.

2. **No telemetry, no analytics, no crash reporting.**
   We don't track usage, count runs, or send error reports anywhere. If a
   script fails, the error goes to *your* terminal and nowhere else.

3. **Local-only by design.**
   There are no accounts, no API keys, no cloud services, no sign-ins. The
   pipeline has no concept of "upload" — the word doesn't appear in the code
   except in error messages telling you to re-download *your own* file.

4. **Auditable dependencies.**
   `scripts/requirements.txt` names every third-party package (four of them:
   trimesh, numpy, scipy, networkx) with minimum versions.
   `scripts/requirements-locked.txt` pins the exact versions the pipeline was
   tested against, for bit-for-bit reproducible installs. There are no
   unpinned installs, no curl-piped-to-shell, no binary blobs.

5. **No secrets in code.**
   Nothing in this repository contains, requests, or expects API keys,
   tokens, passwords, or credentials of any kind.

6. **CloudCompare is local too.**
   `deviation.py` shells out to a CloudCompare binary *on your machine*
   (installed by you, via apt or download). It runs with your files in a
   temp directory and cleans up after itself. No CloudCompare account,
   no online services involved.

## How to verify this yourself

Don't take our word for it — that's the whole point of FOSS.

```bash
# 1. Confirm no network code exists (should print nothing):
grep -rn "urllib\|requests\|urlopen\|socket\.connect" scripts/ mesh-to-cad

# 2. Disconnect from the internet entirely, then run the pipeline:
#    (it works — every test in test-samples/ was run this way)
.venv/bin/python mesh-to-cad myfile.stl

# 3. Confirm exact dependency versions:
.venv/bin/pip freeze | sort
# compare against scripts/requirements-locked.txt
```

## Scope

This commitment covers everything in this repository: the `scripts/`
pipeline stages, the `mesh-to-cad` CLI, and their documented dependencies.
It does not cover tools you choose to run yourself (your slicer, FreeCAD,
MeshLab) — audit those separately if it matters to you.

## Reporting a concern

If you find anything in this repo that contradicts the above — a network
call, a tracking pixel, a credential prompt — that's a bug, and a serious
one. Open an issue at
https://github.com/GruntAndMuse/mesh-to-cad/issues with what you found.
We treat privacy violations like data-loss bugs: fix first, explain after.

---
*This file is a living commitment, not a marketing page. If the pipeline's
behavior ever needs to change in a way that weakens these guarantees, that
change lands here first, with the reason stated plainly — before a line of
code ships.*
