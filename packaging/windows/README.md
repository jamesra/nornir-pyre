# Pyre Windows packaging (quick reference)

Build scripts for the frozen Windows installer. Full maintainer documentation:
https://nornir.github.io/development/pyre_development.html (packaging section).

## Prerequisites

- Windows 10/11 x64
- Python 3.13+
- Monorepo checkout at a release tag
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for the Setup.exe)

  Install once (per machine):

  ```powershell
  winget install --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements
  ```

  `build-installer.ps1` auto-detects `ISCC.exe` (PATH, Program Files, or `%LOCALAPPDATA%\Programs\Inno Setup 6\`).
  Override with the `INNO_SETUP_ISCC` environment variable if needed.

## Local build

From this directory:

```powershell
.\build-freeze.ps1
.\validate-frozen.ps1
```

Compile the installer (adjust `/DMyAppVersion` to match root `VERSION`):

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.7.0 pyre-installer.iss
```

Output: `dist/installer/Pyre-<version>-Setup.exe`

## Files

| File | Purpose |
|------|---------|
| `build-freeze.ps1` | Venv, local monorepo install, PyInstaller freeze |
| `pyre.spec` | PyInstaller spec (one-folder bundle) |
| `hook-pyre.py` | Collect Pyre resources and submodules |
| `pyre-installer.iss` | Inno Setup installer script |
| `validate-frozen.ps1` | Pre-installer smoke checks |

## End-user install

See https://nornir.github.io/packages/pyre_install.html
