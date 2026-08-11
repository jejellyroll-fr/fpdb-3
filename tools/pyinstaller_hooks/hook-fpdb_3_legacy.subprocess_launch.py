"""Include the HUD backend hidden behind the macOS ``--hud`` dispatcher."""

from PyInstaller import compat

# fpdb.pyw reaches HUD_main.pyw through runpy, so PyInstaller cannot see the
# platform import inside that data file.  The main executable nevertheless has
# to contain this graph: macOS launches the HUD through that same executable to
# preserve one TCC/code-signing identity.
hiddenimports = (
    [
        "fpdb_3_legacy.OSXTables",
        "fpdb.infrastructure.platform.macos",
    ]
    if compat.is_darwin
    else []
)
