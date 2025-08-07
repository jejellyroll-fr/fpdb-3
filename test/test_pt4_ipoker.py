"""Test script for PokerTracker4 iPoker hands parsing."""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from Configuration import Config
from PokerTrackerToFpdb import PokerTracker

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


def test_pt4_ipoker_detection() -> bool:
    """Test PokerTracker4 iPoker skin detection."""
    """Test PokerTracker4 iPoker skin detection."""
    # Create a minimal config
    config = Config()

    # Create PokerTracker instance
    pt = PokerTracker(config=config, autostart=False)

    try:
        gametype = pt.determineGameType(sample_hand)

        # Test specific skin detection method
        pt.detectiPokerSkin(sample_hand)

        # Test is_ipoker_skin method
        pt.is_ipoker_skin()

        # Verify detection worked
        if pt.sitename is None:
            msg = "Sitename detection failed"
            raise ValueError(msg)
        if pt.siteId is None:
            msg = "SiteId detection failed"
            raise ValueError(msg)
        if gametype is None:
            msg = "Gametype detection failed"
            raise ValueError(msg)

    except (ValueError, AssertionError, ImportError):
        traceback.print_exc()
        return False
    else:
        return True


if __name__ == "__main__":
    test_pt4_ipoker_detection()
