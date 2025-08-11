"""Test script for site identification with PokerTracker4 iPoker hands."""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from Configuration import Config
from IdentifySite import IdentifySite

# Sample PokerTracker4 hand text from FDJ/iPoker
sample_hand = """GAME #8043869466 Version:24.7.1.16 Uncalled:Y Omaha PL €0.01/€0.02 2024-11-06 23:38:55/GMT
Table Size 6
Table Saratov, 560234179
Seat 3: kermen56 (€0.44 in chips)
Seat 5: maresdelsur (€0.70 in chips)
Seat 6: trooperbold15 (€0.50 in chips)  DEALER
Seat 8: louisaf55 (€2.11 in chips)
Seat 10: jejellyroll (€2.00 in chips)
louisaf55: Post SB €0.01
jejellyroll: Post BB €0.02
*** HOLE CARDS ***
Dealt to jejellyroll [C9 H5 H9 S9]
kermen56: Call €0.02
maresdelsur: Call €0.02
trooperbold15: Call €0.02
louisaf55: Call €0.01
jejellyroll: Check
*** FLOP *** [C6 CA D10]
louisaf55: Check
jejellyroll: Check
kermen56: Check
maresdelsur: Check
trooperbold15: Check
*** TURN *** [CJ]
louisaf55: Check
jejellyroll: Check
kermen56: Check
maresdelsur: Check
trooperbold15: Check
*** RIVER *** [H8]
louisaf55: Bet €0.05
jejellyroll: Fold
kermen56: Fold
maresdelsur: Raise (NF) €0.25
trooperbold15: Fold
louisaf55: Call €0.20
*** SUMMARY ***
Total pot €0.56 Rake €0.04
maresdelsur: Shows [DQ HK S7 D7] Straight, Ace High
louisaf55: Shows [S8 CQ C5 C8] Flush, Ace High
louisaf55: wins €0.56"""


def test_site_identification() -> bool:
    """Test site identification for PokerTracker4 iPoker hands."""
    # Create a minimal config
    config = Config()

    # Create IdentifySite instance
    identifier = IdentifySite(config)

    try:
        # Test site identification
        fpdb_file = identifier.idSite("test_file.txt", sample_hand, "utf8")

        if fpdb_file and fpdb_file.site:
            # Verify we have the expected attributes
            if not fpdb_file.site.name:
                msg = "Site name not identified"
                raise ValueError(msg)
            return True

        msg = "Failed to identify site"
        raise ValueError(msg)

    except (ValueError, ImportError, AttributeError):
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_site_identification()
