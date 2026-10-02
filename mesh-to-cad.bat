@echo off
REM mesh-to-cad.bat — Windows launcher for the mesh-to-cad pipeline.
REM
REM WHY THIS EXISTS: on Windows, running `mesh-to-cad myfile.stl` doesn't work
REM because the extensionless script isn't executable. This .bat lets Windows
REM users type `mesh-to-cad` the same way. It finds Python and forwards all
REM arguments to the real script.
REM
REM SETUP: put the mesh-to-cad folder on your PATH (see QUICKSTART.md), or
REM copy this .bat next to the `mesh-to-cad` script.

setlocal

REM Find the real script: same folder as this .bat.
set "SCRIPT_DIR=%~dp0"
set "SCRIPT=%SCRIPT_DIR%mesh-to-cad"

REM Prefer the venv Python if it exists (same layout as the docs).
if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    "%SCRIPT_DIR%.venv\Scripts\python.exe" "%SCRIPT%" %*
) else (
    REM Fall back to whatever python is on PATH.
    python "%SCRIPT%" %*
)
