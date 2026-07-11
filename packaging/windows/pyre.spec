# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Pyre Windows one-folder bundle."""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

spec_dir = Path(SPECPATH)
pyre_root = spec_dir.parent.parent
entry_script = pyre_root / "pyre" / "__main__.py"

hiddenimports = [
    "pyre",
    "pyre.__main__",
    "pyre.launcher",
    "pyre.container",
    "pyre.frozen_paths",
    "pyre.resource_paths",
    "pyre.settings",
    "pyre.settings.app",
    "dependency_injector",
    "dependency_injector.wiring",
    "dependency_injector.providers",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt",
    "nornir_shared",
    "nornir_shared.misc",
    "nornir_pools",
    "nornir_imageregistration",
    "nornir_buildmanager",
    "PIL",
    "PIL.Image",
    "scipy",
    "scipy.ndimage",
    "scipy.spatial",
    "skimage",
    "rtree",
    "yaml",
    "pydantic",
]

hiddenimports += collect_submodules("pyre")
hiddenimports += collect_submodules("nornir_imageregistration")
hiddenimports += collect_submodules("nornir_buildmanager")
hiddenimports += collect_submodules("dependency_injector")

datas = collect_data_files("pyre", includes=["resources/*.png"])
datas += collect_data_files("matplotlib")
readme_path = pyre_root / "README.rst"
if readme_path.is_file():
    datas.append((str(readme_path), "."))

binaries: list[tuple[str, str]] = []
for pkg in ("PyQt6", "scipy", "skimage"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    [str(entry_script)],
    pathex=[str(pyre_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(dict.fromkeys(hiddenimports)),
    hookspath=[str(spec_dir)],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["cupy", "cupyx"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pyre",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="pyre",
)
