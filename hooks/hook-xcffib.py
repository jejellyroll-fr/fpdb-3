# hook-xcffib.py

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules("xcffib")
datas = collect_data_files("xcffib")
