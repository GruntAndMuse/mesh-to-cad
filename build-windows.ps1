<#
.SYNOPSIS
    One-command Windows build for mesh-to-cad. Run as Administrator.
.DESCRIPTION
    Installs Python (if needed), clones the repo, builds a standalone
    mesh-to-cad.exe with PyInstaller. One command, no manual steps.
.EXAMPLE
    # Right-click PowerShell -> Run as Administrator, then:
    irm https://raw.githubusercontent.com/GruntAndMuse/mesh-to-cad/main/build-windows.ps1 | iex
#>

$ErrorActionPreference = "Stop"

# Log everything to a file so we can diagnose if the window closes
$logFile = "$env:TEMP\mesh-to-cad-build.log"
"=== Build started: $(Get-Date) ===" | Out-File $logFile
function Log($msg) {
    $msg | Tee-Object -FilePath $logFile -Append | Write-Host
}

try {

Write-Host ""
Write-Host "=== mesh-to-cad Windows Builder ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Python ---
Write-Host "[1/5] Checking for Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "  Python not found. Installing via winget (this takes a minute)..." -ForegroundColor Yellow
    winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    # Refresh PATH for this session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "  ERROR: Python installed but not on PATH. Close and reopen PowerShell as Admin, then re-run." -ForegroundColor Red
        exit 1
    }
}
$ver = python --version 2>&1
Write-Host "  Found: $ver" -ForegroundColor Green

# --- Step 2: Get the repo ---
Write-Host "[2/5] Getting mesh-to-cad source..." -ForegroundColor Yellow
$workDir = "$env:TEMP\mesh-to-cad-build"
if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }
New-Item -ItemType Directory -Path $workDir | Out-Null
Set-Location $workDir

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    git clone --quiet https://github.com/GruntAndMuse/mesh-to-cad.git .
} else {
    Write-Host "  Git not found, downloading ZIP..." -ForegroundColor Yellow
    $zip = "$workDir\repo.zip"
    Invoke-WebRequest -Uri "https://github.com/GruntAndMuse/mesh-to-cad/archive/refs/heads/main.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $workDir
    Set-Location "$workDir\mesh-to-cad-main"
    $workDir = "$workDir\mesh-to-cad-main"
}
Write-Host "  Source ready." -ForegroundColor Green

# --- Step 3: Build environment ---
Write-Host "[3/5] Setting up build environment..." -ForegroundColor Yellow
python -m venv build-env
& "$workDir\build-env\Scripts\Activate.ps1"
python -m pip install --quiet --upgrade pip
pip install --quiet -r scripts\requirements.txt
pip install --quiet pyinstaller
Write-Host "  Dependencies installed." -ForegroundColor Green

# --- Step 4: Build ---
Write-Host "[4/5] Building mesh-to-cad.exe (2-5 minutes)..." -ForegroundColor Yellow
if (Test-Path "mesh-to-cad.spec") {
    pyinstaller --noconfirm mesh-to-cad.spec
} else {
    # Fallback: build without a spec file
    pyinstaller --noconfirm --onefile --name mesh-to-cad --add-data "scripts;scripts" mesh-to-cad
}
$exe = "$workDir\dist\mesh-to-cad.exe"
if (-not (Test-Path $exe)) {
    Write-Host "  ERROR: Build failed, exe not found at $exe" -ForegroundColor Red
    exit 1
}
Write-Host "  Build succeeded." -ForegroundColor Green

# --- Step 5: Deliver ---
Write-Host "[5/5] Delivering..." -ForegroundColor Yellow
$dest = "$env:USERPROFILE\Desktop\mesh-to-cad.exe"
Copy-Item $exe $dest -Force
Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Cyan
Write-Host "  mesh-to-cad.exe is on your Desktop." -ForegroundColor Green
Write-Host "  Double-click it, or run from Command Prompt:" -ForegroundColor White
Write-Host "    `"$dest`" your-file.stl" -ForegroundColor Gray
Write-Host ""
Write-Host "  Smoke test:" -ForegroundColor White
& $dest --help 2>&1 | Select-Object -First 5

} catch {
    Write-Host ""
    Write-Host "=== BUILD FAILED ===" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Full log saved to: $logFile" -ForegroundColor Yellow
    Write-Host "Paste the last 20 lines of that file here and I'll diagnose it." -ForegroundColor Yellow
} finally {
    Write-Host ""
    Write-Host "Press Enter to close..." -ForegroundColor Cyan
    Read-Host | Out-Null
}
