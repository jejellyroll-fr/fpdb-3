"""OnGame draw hands: the draw and the betting after it belong to DRAWONE (#793).

OnGame writes no draw header, so the parser inserts one before the first
"changed N cards" line. A DOTALL pattern used to match the whole hand, which put
the marker before the deal and left every action in DEAL.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.OnGameToFpdb import OnGame

DRAW_FILES = sorted(
    (Path(__file__).resolve().parents[1] / "regression-test-files" / "cash" / "OnGame" / "Draw").glob("*.txt")
)
NO_DELIMITER = next(path for path in DRAW_FILES if "No.Street.Delimiter" in path.name)
DRAW_ACTIONS = ("discards", "stands pat")


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _hands(path: Path, config: Config) -> list:
    logging.disable(logging.CRITICAL)
    try:
        return OnGame(config=config, in_path=str(path), autostart=True).getProcessedHands()
    finally:
        logging.disable(logging.NOTSET)


@pytest.mark.parametrize("path", DRAW_FILES, ids=[path.name for path in DRAW_FILES])
def test_no_draw_action_is_left_before_the_draw(path: Path, config: Config) -> None:
    hands = _hands(path, config)
    assert hands
    for hand in hands:
        assert not [a for a in hand.actions["DEAL"] if a[1] in DRAW_ACTIONS], hand.handid
        drawone = hand.actions.get("DRAWONE", [])
        if drawone:
            # The street opens with the draw itself, then the betting after it.
            assert drawone[0][1] in DRAW_ACTIONS, hand.handid


def test_post_draw_betting_lands_in_drawone(config: Config) -> None:
    hand = _hands(NO_DELIMITER, config)[0]
    assert [(a[0], a[1]) for a in hand.actions["DEAL"]] == [
        ("Player1", "raises"),
        ("Hero", "folds"),
        ("Player0", "raises"),
        ("Player3", "folds"),
        ("Player1", "calls"),
    ]
    assert [(a[0], a[1]) for a in hand.actions["DRAWONE"]] == [
        ("Player0", "discards"),
        ("Player1", "discards"),
        ("Player0", "bets"),
        ("Player1", "folds"),
    ]


def test_post_draw_stats_read_round_one(config: Config) -> None:
    stats = DerivedStats()
    stats.getStats(_hands(NO_DELIMITER, config)[0])
    players = stats.getHandsPlayers()
    raiser, caller = players["Player0"], players["Player1"]
    assert raiser["street1Seen"] and caller["street1Seen"]
    assert raiser["street1Aggr"]
    assert raiser["street1CBChance"] and raiser["street1CBDone"]
    assert raiser["street0Bets"] == 0  # the post-draw bet is no longer counted before the draw
    assert caller["foldToStreet1CBChance"] and caller["foldToStreet1CBDone"]
