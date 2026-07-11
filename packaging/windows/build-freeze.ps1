<#
.SYNOPSIS
    Build a PyInstaller one-folder Pyre bundle for Windows.

.DESCRIPTION
    Creates a clean virtual environment, installs monorepo packages from local
    file URLs (CPU-only imageregistration), installs third-party dependencies,
    and runs PyInstaller using pyre.spec. Output is written to dist/pyre/.
#>
[CmdletBinding()]
param(
    [string]$MonorepoRoot = "",
    [string]$Python = "python",
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyreRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
if ($MonorepoRoot) {
    $RepoRoot = Resolve-Path $MonorepoRoot
} else {
    $RepoRoot = Resolve-Path (Join-Path $PyreRoot "..")
}

$BuildVenv = Join-Path $PyreRoot ".packaging-venv"
$DistDir = Join-Path $ScriptDir "dist"
$WorkDir = Join-Path $ScriptDir "build"
$ConstraintsScript = Join-Path $RepoRoot "release\generate_pyre_windows_constraints.py"
$ConstraintsFile = Join-Path $RepoRoot "release\pyre-windows-constraints.txt"
$ThirdPartyReqs = Join-Path $RepoRoot "release\pyre-windows-third-party.txt"

Write-Host "Monorepo root: $RepoRoot"
Write-Host "Pyre root:     $PyreRoot"

if (-not $SkipVerify) {
    Write-Host "Verifying package versions..."
    & $Python $RepoRoot\release\verify_package_versions.py
    if ($LASTEXITCODE -ne 0) { throw "verify_package_versions.py failed" }
}

Write-Host "Generating local constraints..."
& $Python $ConstraintsScript
if ($LASTEXITCODE -ne 0) { throw "generate_pyre_windows_constraints.py failed" }

if (Test-Path $BuildVenv) {
    Write-Host "Removing existing build venv: $BuildVenv"
    Remove-Item -Recurse -Force $BuildVenv
}

Write-Host "Creating build venv..."
& $Python -m venv $BuildVenv
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"
$VenvPip = Join-Path $BuildVenv "Scripts\pip.exe"

& $VenvPython -m pip install --upgrade pip wheel setuptools

Write-Host "Installing third-party dependencies..."
& $VenvPip install --no-cache-dir -r $ThirdPartyReqs

Write-Host "Installing monorepo packages (CPU-only, --no-deps)..."
Get-Content $ConstraintsFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        Write-Host "  pip install --no-deps $line"
        & $VenvPip install --no-cache-dir --no-deps $line
        if ($LASTEXITCODE -ne 0) { throw "Failed to install $line" }
    }
}

if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir
}
if (Test-Path $WorkDir) {
    Remove-Item -Recurse -Force $WorkDir
}

Write-Host "Running PyInstaller..."
Push-Location $ScriptDir
try {
    & $VenvPython -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistDir `
        --workpath $WorkDir `
        (Join-Path $ScriptDir "pyre.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
} finally {
    Pop-Location
}

$BundleExe = Join-Path $DistDir "pyre\pyre.exe"
if (-not (Test-Path $BundleExe)) {
    throw "Expected frozen executable at $BundleExe"
}

Write-Host ""
Write-Host "Freeze complete: $BundleExe"
Write-Host "Next: compile pyre-installer.iss with Inno Setup, or run validate-frozen.ps1"
