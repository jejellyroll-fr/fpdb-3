"""Ship the COM bindings the Windows seat reader needs."""

from PyInstaller import compat

# winamax_ax_seats imports comtypes lazily, inside a try/except, so PyInstaller
# has no import to follow. Without these the frozen HUD quietly loses the
# ability to read a table's chairs from the window and falls back to the client
# log, which can only name a player once they have acted -- the stat blocks then
# appear one at a time over the first betting round.
hiddenimports = ["comtypes", "comtypes.client"] if compat.is_win else []
