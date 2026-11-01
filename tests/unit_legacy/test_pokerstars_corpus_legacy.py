"""End-to-end parse tests over the PokerStars hand-history corpus.

Running the PokerStars converter over every regression sample drives the full
pipeline: PokerStarsToFpdb -> Hand (HoldemOmahaHand / StudHand / DrawHand)
construction -> DerivedStats assembly. This is the highest-leverage way to
exercise Hand.py and DerivedStats.py.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

ROOT = Path(__file__).resolve().parents[2]

_PATTERNS = [
    str(ROOT / "regression-test-files" / "cash" / "Stars" / "**" / "*.txt"),
    str(ROOT / "regression-test-files" / "tour" / "Stars" / "**" / "*.txt"),
]
HAND_FILES = sorted({f for pat in _PATTERNS for f in glob.glob(pat, recursive=True)})


@pytest.fixture
def corpus_config() -> Config:
    return Config()


def _ids(path: str) -> str:
    # Use forward slashes for cross-platform consistency and sanitize to safe ASCII to prevent Windows console encoding crashes
    rel = Path(path).relative_to(ROOT / "regression-test-files")
    return str(rel).replace("\\", "/").encode("ascii", "replace").decode("ascii")


@pytest.mark.parametrize("hand_file", HAND_FILES, ids=_ids)
def test_corpus_file_parses_without_error(hand_file: str, corpus_config: Config) -> None:
    """Every sample parses without raising; produced hands are well-formed."""
    parser = PokerStars(config=corpus_config, in_path=hand_file, autostart=True)
    hands = parser.getProcessedHands()
    # The parser never raises on these samples; it yields 0+ hands.
    for hand in hands:
        assert hand.handid
        assert hand.players, f"no players in {hand_file}"
        assert hand.gametype.get("category")
        # Run the full DerivedStats assembly pipeline (no DB needed). This is
        # what exercises DerivedStats.py end to end, including run-it-twice
        # hands now that getStreetTotals tolerates their extra board streets.
        hand.assembleHand()
        assert hand.handsplayers
        assert isinstance(hand.hands, dict)


def test_corpus_is_discovered() -> None:
    # Guard against the glob silently returning nothing (which would make the
    # parametrized test vacuously pass).
    assert len(HAND_FILES) > 100


def test_run_it_twice_hand_assembles(corpus_config: Config) -> None:
    """A run-it-twice hand (10 board streets) assembles without the IndexError
    that the fixed 6-slot Hand.getStreetTotals previously raised; the duplicate
    run streets are skipped and the base street pots are still produced."""
    rit_file = next(f for f in HAND_FILES if "RunItTwice" in f)
    hand = PokerStars(config=corpus_config, in_path=rit_file, autostart=True).getProcessedHands()[0]
    assert hand.runItTimes >= 2
    hand.assembleHand()
    assert hand.handsplayers
    totals = hand.getStreetTotals()
    assert len(totals) == 6
    # Base streets (preflop/flop/turn) carry the betting; final pot is positive.
    assert totals[5] > 0
