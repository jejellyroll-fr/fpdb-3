# hook-xcffib.py

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = collect_submodules("xcffib")
datas = collect_data_files("xcffib")
