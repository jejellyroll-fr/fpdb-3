"""iPoker parser package.

The legacy public parser remains exported from ``iPokerToFpdb``. This package
contains the skin-specific dispatch pieces used to split that monolith safely.
"""

from __future__ import annotations

from fpdb_3_legacy.iPoker.dispatcher import (
    IPokerSkin,
    IPokerSkinDispatcher,
    detect_skin,
    get_parser_class_for_path,
    get_parser_class_for_skin,
    resolve_site_id,
)

__all__ = [
    "IPokerSkin",
    "IPokerSkinDispatcher",
    "detect_skin",
    "get_parser_class_for_path",
    "get_parser_class_for_skin",
    "resolve_site_id",
]
