<#
.SYNOPSIS
    Compile the Inno Setup installer after build-freeze.ps1.

.DESCRIPTION
    Reads VERSION from the monorepo root unless -Version is supplied, then invokes
    ISCC.exe against pyre-installer.iss.

    ISCC discovery order:
    1. -IsccPath parameter (if the file exists)
    2. INNO_SETUP_ISCC environment variable
    3. ISCC.exe on PATH
    4. Common install locations (Inno Setup 6 and 7)
#>
[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-InnoSetupCompiler {
    param([string]$PreferredPath)

    if ($PreferredPath -and (Test-Path $PreferredPath)) {
        return (Resolve-Path $PreferredPath).Path
    }

    if ($env:INNO_SETUP_ISCC -and (Test-Path $env:INNO_SETUP_ISCC)) {
        return (Resolve-Path $env:INNO_SETUP_ISCC).Path
    }

    $pathHit = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($pathHit -and (Test-Path $pathHit.Source)) {
        return $pathHit.Source
    }

    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..\..")

if (-not $Version) {
    $Version = (Get-Content (Join-Path $RepoRoot "VERSION") -Raw).Trim()
}

$BundleExe = Join-Path $ScriptDir "dist\pyre\pyre.exe"
if (-not (Test-Path $BundleExe)) {
    throw "Missing $BundleExe. Run build-freeze.ps1 first."
}

$ResolvedIscc = Resolve-InnoSetupCompiler -PreferredPath $IsccPath
if (-not $ResolvedIscc) {
    throw @"
Inno Setup compiler (ISCC.exe) was not found.

Install Inno Setup 6, then re-run this script:
  winget install --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements

Or download from https://jrsoftware.org/isinfo.php

After install, ISCC.exe is usually at:
  ${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe

You can also set INNO_SETUP_ISCC to the full path to ISCC.exe.
"@
}

Write-Host "Using Inno Setup compiler: $ResolvedIscc"
Write-Host "Building Pyre-$Version-Setup.exe ..."
& $ResolvedIscc "/DMyAppVersion=$Version" (Join-Path $ScriptDir "pyre-installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compile failed" }

$Installer = Join-Path $ScriptDir "dist\installer\Pyre-$Version-Setup.exe"
Write-Host "Installer ready: $Installer"
