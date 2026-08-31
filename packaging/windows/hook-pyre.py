"""PyInstaller hook to collect Pyre package data and submodules."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("pyre")
datas = collect_data_files("pyre", includes=["resources/**", "settings.json", "README.txt"])
