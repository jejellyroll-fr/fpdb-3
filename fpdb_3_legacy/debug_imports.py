from __future__ import annotations

import os
import sys

sys.path.append(os.getcwd())

print(f"CWD: {os.getcwd()}")
print(f"Path: {sys.path}")

try:
    import fpdb_3_legacy.DerivedStats as DerivedStats

    print("DerivedStats imported successfully")
except ImportError as e:
    print(f"Failed to import DerivedStats: {e}")

try:
    import fpdb_3_legacy.PokerStarsToFpdb as PokerStarsToFpdb

    print("PokerStarsToFpdb imported successfully")
except ImportError as e:
    print(f"Failed to import PokerStarsToFpdb: {e}")
