# Site detection utility for legacy FPDB parsers
from __future__ import annotations
import re

# Import all site parsers
from fpdb_3_legacy import PokerStarsToFpdb
from fpdb_3_legacy import SealsWithClubsToFpdb
from fpdb_3_legacy import GGPokerToFpdb

# Map site header patterns to (parser_module, parser_class, site_name)
SITE_DETECTORS = [
    (r"SwCPoker Hand #", SealsWithClubsToFpdb.SealsWithClubs, "SealsWithClubs"),
    (r"PokerStars Game #", PokerStarsToFpdb.PokerStars, "PokerStars"),
    (r"Poker Hand #", GGPokerToFpdb.GGPoker, "GGPoker"),
]


def detect_site(hand_text: str):
    """Detect the poker site from hand text and return (parser_class, site_name)."""
    first_line = hand_text.split("\n")[0] if hand_text else ""
    for pattern, parser_cls, site_name in SITE_DETECTORS:
        if re.search(pattern, first_line):
            return parser_cls, site_name
    return None, None
