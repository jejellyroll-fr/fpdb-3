"""PT4 Adapter module for fpdb_3_legacy.

Provides read-only connection and query utilities for PT4 PostgreSQL database
comparison and parity testing.
"""

from .comparator import StatComparison, compare_hand
from .connection import Pt4Config, connect_pt4
from .models import Pt4PlayerStat
from .queries import PT4_STATS_PER_HAND, get_pt4_stats_for_hand

__all__ = [
    "Pt4Config",
    "connect_pt4",
    "get_pt4_stats_for_hand",
    "PT4_STATS_PER_HAND",
    "Pt4PlayerStat",
    "compare_hand",
    "StatComparison",
]
