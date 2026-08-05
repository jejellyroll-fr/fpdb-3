"""Regression tests for the stud mucked-cards grid (Mucked.Stud_cards).

Focus: empty seats (no player dealt in) must not render a phantom row of
seven face-down card backs, while dealt-in seats show faces for known cards
and backs for hidden ones.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QVBoxLayout

# Uses the pytest-qt `qapp` fixture; group with the other Qt UI tests so it is
# deselected in the default (non-qt) run instead of erroring on a missing fixture.
pytestmark = pytest.mark.qt

from fpdb_3_legacy import Card
from fpdb_3_legacy.Mucked import Stud_cards


def _fake_card_images() -> dict:
    """Build a card_images dict shaped like Deck.get_all_card_images()."""
    images: dict = {0: QPixmap(2, 2)}  # key 0 == card back
    for suit in ("s", "h", "d", "c"):
        images[suit] = {rank: QPixmap(2, 2) for rank in range(2, 15)}
    return images


def _make_stud_cards(cards_by_seat: dict, stat_dict: dict, images: dict) -> Stud_cards:
    deck = SimpleNamespace(get_all_card_images=lambda: images)
    hud = SimpleNamespace(cards=cards_by_seat, stat_dict=stat_dict, parent=SimpleNamespace(deck=deck))
    parent = SimpleNamespace(hud=hud)
    return Stud_cards(parent, params={}, config=None)


def test_empty_seats_are_blank_not_card_backs(qapp) -> None:
    images = _fake_card_images()
    # Seats 1 and 4 dealt in; the other six seats are empty.
    seat1 = (Card.encodeCard("7s"), 0, 0, 0, 0, 0, 0)  # one upcard, rest hidden/undealt
    seat4 = tuple(Card.encodeCard(c) for c in ("7h", "4s", "Jc", "As", "2d", "9h", "Kc"))
    stat_dict = {
        10: {"seat": 1, "screen_name": "Nikolay780"},
        40: {"seat": 4, "screen_name": "edinapoker"},
    }
    sc = _make_stud_cards({1: seat1, 4: seat4}, stat_dict, images)
    sc.create(QVBoxLayout())
    sc.update_gui("h1")

    back_key = images[0].cacheKey()

    # Seat 4 (row 3): every card is known -> all faces, none blank, none a back.
    for c in range(sc.cols):
        pm = sc.eb[(c, 3)].pixmap()
        assert not pm.isNull(), f"seat4 card {c} unexpectedly blank"
        assert pm.cacheKey() != back_key, f"seat4 card {c} rendered as a back"

    # Seat 1 (row 0): first cell is the known upcard; remaining cells are backs.
    assert not sc.eb[(0, 0)].pixmap().isNull()
    assert sc.eb[(0, 0)].pixmap().cacheKey() != back_key
    for c in range(1, sc.cols):
        assert sc.eb[(c, 0)].pixmap().cacheKey() == back_key, f"seat1 hidden card {c} not a back"

    # Empty seats (rows 1, 2, 4, 5, 6, 7): all cells blank (no phantom backs).
    for row in (1, 2, 4, 5, 6, 7):
        for c in range(sc.cols):
            assert sc.eb[(c, row)].pixmap().isNull(), f"empty seat row {row} card {c} not blank"


def test_out_of_range_seat_number_is_ignored(qapp) -> None:
    images = _fake_card_images()
    # Seat 9 does not fit the fixed 8-row grid; must not raise.
    stat_dict = {90: {"seat": 9, "screen_name": "Overflow"}}
    sc = _make_stud_cards({9: (Card.encodeCard("As"), 0, 0, 0, 0, 0, 0)}, stat_dict, images)
    sc.create(QVBoxLayout())
    sc.update_gui("h1")  # should not raise KeyError

    for row in range(sc.rows):
        for c in range(sc.cols):
            assert sc.eb[(c, row)].pixmap().isNull()


def test_short_card_tuple_does_not_raise(qapp) -> None:
    images = _fake_card_images()
    stat_dict = {10: {"seat": 1, "screen_name": "Shorty"}}
    # Only three cards recorded for the seat (e.g. folded on third street).
    short = tuple(Card.encodeCard(c) for c in ("7h", "4s", "Jc"))
    sc = _make_stud_cards({1: short}, stat_dict, images)
    sc.create(QVBoxLayout())
    sc.update_gui("h1")  # must not raise IndexError

    back_key = images[0].cacheKey()
    for c in range(3):
        assert sc.eb[(c, 0)].pixmap().cacheKey() != back_key
    for c in range(3, sc.cols):
        assert sc.eb[(c, 0)].pixmap().cacheKey() == back_key
