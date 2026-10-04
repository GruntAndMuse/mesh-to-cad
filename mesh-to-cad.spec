# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for mesh-to-cad — standalone Windows executable.

WHAT THIS BUILDS: a single mesh-to-cad.exe that bundles Python + all
dependencies (trimesh, numpy, scipy, networkx). The user downloads one file,
double-clicks (or runs from cmd), no Python install needed.

BUILD ON WINDOWS ONLY: PyInstaller cannot cross-compile. Run this on a
Windows machine with Python 3.10+ installed. See BUILD-WINDOWS.md for the
full reproducible steps.

    pyinstaller mesh-to-cad.spec

OUTPUT: dist/mesh-to-cad.exe (~80-120MB — numpy/scipy are heavy; this is
the price of "no Python needed." The .exe is self-contained.)

WHY console=True: this is a CLI tool. console=False would hide the output
window and the user would see nothing. Keep the console.
"""

block_cipher = None

# WHY: sigstore's trusted-root assets live in sigstore._store, which is only
# referenced as a string (importlib.resources.files("sigstore._store")) —
# PyInstaller's scanner misses it. Without these, `update`'s automatic
# signature verification dies with ModuleNotFoundError in the frozen binary.
# (Found 2026-10-04 via frozen-binary test; verified working after.)
from PyInstaller.utils.hooks import collect_data_files
_sigstore_datas = collect_data_files('sigstore')

a = Analysis(
    ['mesh-to-cad'],
    pathex=['.', 'scripts'],
    binaries=[],
    datas=[
        *_sigstore_datas,
        # Bundle scripts/ as data files — the CLI resolves SCRIPTS_DIR via
        # sys._MEIPASS at runtime and imports from there. WHY both pathex
        # AND datas: pathex lets PyInstaller find the modules for bundling,
        # datas ensures the .py files exist on disk in the frozen app.
        # Belt and suspenders — the import works either way.
        ('scripts', 'scripts'),
        # Ship the docs with the exe so --help-adjacent info is available.
        # WHY: a user with just the .exe has no repo; bundle the essentials.
        ('QUICKSTART.md', '.'),
        ('REQUIREMENTS.md', '.'),
        ('SECURITY.md', '.'),
        ('CHANGELOG.md', '.'),
    ],
    # Scientific Python needs explicit hidden imports — PyInstaller's
    # dependency scanner misses these because they're imported dynamically.
    hiddenimports=[
        'trimesh',
        'trimesh.exchange',
        'trimesh.exchange.stl',
        'numpy',
        'scipy',
        'scipy.spatial',
        'scipy.spatial.cKDTree',
        'networkx',
        # sigstore._store holds the trusted-root assets; referenced only via
        # importlib.resources string, invisible to PyInstaller's scanner.
        # WHY here: `mesh-to-cad update` verifies release signatures
        # automatically (v1.0.3+). Without this the frozen binary can't.
        'sigstore._store',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim the bundle: we don't need these.
        'tkinter',       # no GUI
        'matplotlib',    # not used
        'IPython',       # not used
        'pytest',        # not used at runtime
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='mesh-to-cad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # compress the exe; saves ~30% size, costs a few seconds at startup
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI tool — user needs to see output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
