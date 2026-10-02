# Building mesh-to-cad for Windows

This builds a standalone `mesh-to-cad.exe` — one file, no Python install needed.
The user downloads it, double-clicks (or runs from Command Prompt), done.

## Why you build on Windows

PyInstaller cannot cross-compile. A Linux machine builds Linux binaries;
a Windows machine builds Windows binaries. There is no workaround — this
must run on Windows.

## Prerequisites (one-time setup)

1. **Python 3.10 or newer** from https://www.python.org/downloads/
   - During install, check **"Add python.exe to PATH"** — this is the step
     everyone misses. If you miss it, open the installer again → Modify →
     check the box.
   - Verify: open Command Prompt, type `python --version`. Should print
     `Python 3.10.x` or newer.

2. **The mesh-to-cad repo** — clone or download the ZIP from
   https://github.com/GruntAndMuse/mesh-to-cad, extract it somewhere
   (e.g. `C:\mesh-to-cad`).

## Build steps

Open Command Prompt in the repo folder and run:

```bat
REM 1. Create a clean build environment
python -m venv build-env
build-env\Scripts\activate

REM 2. Install dependencies + PyInstaller
pip install -r scripts\requirements.txt
pip install pyinstaller

REM 3. Build the exe (takes 2-5 minutes)
pyinstaller mesh-to-cad.spec

REM 4. The exe is at:
REM    dist\mesh-to-cad.exe
```

That's it. `dist\mesh-to-cad.exe` is the distributable.

## Testing the build

```bat
REM Smoke test — should print the help text
dist\mesh-to-cad.exe --help

REM Full pipeline test — use a known test file
dist\mesh-to-cad.exe path\to\test-file.stl
```

Compare the output against the Python version (`python mesh-to-cad test-file.stl`).
They should be identical except for startup time (the .exe is slower to
launch — it unpacks itself to a temp folder first).

### Windows test checklist

Run through these on the Windows PC and check each one:

- [ ] `mesh-to-cad.exe --help` prints help, exits 0
- [ ] `mesh-to-cad.exe bracket.stl` runs full pipeline (units → gate → analysis)
- [ ] Unicode symbols (✓ ✗ ⚠) display correctly in Command Prompt AND Windows Terminal
  - If they show as `?` in old Command Prompt, that's cosmetic — try Windows Terminal
- [ ] JSON output files are valid UTF-8 (open in Notepad, check for mojibake)
- [ ] `mesh-to-cad.exe check` on a bad file gives a friendly error, not a traceback
- [ ] `mesh-to-cad.exe deviation` without CloudCompare gives the install link
- [ ] Paths with spaces work: `mesh-to-cad.exe "C:\My Files\part.stl"`
- [ ] Non-ASCII filenames work (e.g. `pièce.stl`) — Windows loves these edge cases
- [ ] Output matches the Linux Python version for the same input file

## Distributing

- Upload `dist\mesh-to-cad.exe` to the GitHub release page
- Expected size: 80–120 MB (numpy + scipy are heavy — this is the cost of
  "no Python needed")
- Windows SmartScreen will warn on first run ("Unknown publisher") — this is
  normal for unsigned exes. Users click "More info" → "Run anyway."
  Code signing ($$$/year) removes this; not worth it yet.

## Rebuilding after code changes

Just re-run step 3 (`pyinstaller mesh-to-cad.spec`). Bump the version in
`version-info.txt` when you do a real release.

## Troubleshooting

| Problem | Fix |
|---|---|
| `pyinstaller` not recognized | `build-env\Scripts\activate` first, then `pip install pyinstaller` |
| Build fails on `scipy` | `pip install --upgrade pyinstaller`; older versions miss scipy DLLs |
| Exe crashes on launch with no output | Run from Command Prompt (not double-click) to see the error |
| "Failed to execute script" | Usually a hidden import PyInstaller missed — add it to `hiddenimports` in `mesh-to-cad.spec` |
| Antivirus flags the exe | Common with PyInstaller exes (false positive). Submit to the AV vendor or note it in the release. |
