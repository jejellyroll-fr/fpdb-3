from __future__ import annotations

from fpdb_3_legacy.PokerStarsToFpdb import PokerStars


def test_converter_checkpoints_after_each_complete_hand() -> None:
    converter = PokerStars.__new__(PokerStars)
    converter.in_path = "history.txt"
    converter.processedHands = []
    converter.autoPop = False
    converter.sanityCheck = lambda: True
    converter.allHandsAsList = lambda: ["hand one", "hand two", "hand three"]
    converter.isSummary = lambda _hand_text: False
    converter.processHand = lambda hand_text: hand_text.upper()
    checkpoint_snapshots: list[list[str]] = []
    converter.cooperative_checkpoint = lambda: checkpoint_snapshots.append(list(converter.processedHands))

    converter.start()

    assert checkpoint_snapshots == [["HAND ONE"], ["HAND ONE", "HAND TWO"], ["HAND ONE", "HAND TWO", "HAND THREE"]]
    assert converter.getProcessedHands() == ["HAND ONE", "HAND TWO", "HAND THREE"]
