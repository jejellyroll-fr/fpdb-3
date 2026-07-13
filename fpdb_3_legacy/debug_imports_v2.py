from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.modules["PySide6"] = MagicMock()
sys.modules["PySide6.QtCore"] = MagicMock()
sys.modules["PySide6.QtGui"] = MagicMock()
sys.modules["PySide6.QtWidgets"] = MagicMock()

sys.path.append(os.getcwd())

print(f"CWD: {os.getcwd()}")

try:
    import fpdb_3_legacy.DerivedStats as DerivedStats  # noqa: F401 -- import diagnostic

    print("DerivedStats imported successfully")
except ImportError as e:
    print(f"Failed to import DerivedStats: {e}")

try:
    import fpdb_3_legacy.PokerStarsToFpdb as PokerStarsToFpdb  # noqa: F401 -- import diagnostic

    print("PokerStarsToFpdb imported successfully")
except ImportError as e:
    print(f"Failed to import PokerStarsToFpdb: {e}")
