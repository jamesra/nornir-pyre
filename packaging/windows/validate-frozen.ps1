<#
.SYNOPSIS
    Smoke-check a frozen Pyre bundle before packaging the installer.

.DESCRIPTION
    Verifies pyre.exe exists, performs a subprocess import smoke test, and
    confirms frozen log/settings paths resolve. Full GUI validation still
    requires a clean Windows VM without Python installed.
#>
[CmdletBinding()]
param(
    [string]$BundleDir = "",
    [switch]$LaunchGui
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($BundleDir) {
    $ResolvedBundle = Resolve-Path $BundleDir
} else {
    $ResolvedBundle = Join-Path $ScriptDir "dist\pyre"
}

$PyreExe = Join-Path $ResolvedBundle "pyre.exe"
if (-not (Test-Path $PyreExe)) {
    throw "Missing frozen executable: $PyreExe (run build-freeze.ps1 first)"
}

Write-Host "Found bundle: $PyreExe"

Write-Host "Running import smoke test..."
$SmokeOutput = & $PyreExe --smoke-test 2>&1 | Out-String
Write-Host $SmokeOutput
if ($SmokeOutput -notmatch 'SMOKE_OK') {
    throw "Smoke test failed: SMOKE_OK not found in output"
}

Write-Host "Smoke test passed."

if ($LaunchGui) {
    Write-Host "Launching GUI (manual verification)..."
    Start-Process -FilePath $PyreExe
}

Write-Host ""
Write-Host "VM checklist (manual, clean Windows VM without Python):"
Write-Host "  1. Install Pyre-*-Setup.exe"
Write-Host "  2. Launch from Start Menu; confirm window opens"
Write-Host "  3. Open a sample STOS/mosaic from test fixtures"
Write-Host "  4. Confirm logs under %LOCALAPPDATA%\Nornir\Pyre\logs"
