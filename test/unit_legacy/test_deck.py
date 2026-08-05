"""Unit tests for fpdb_3_legacy.Deck.

A QApplication is required because the Deck constructor builds QPixmap objects.
SVG files do not need to exist on disk: QSvgRenderer fails gracefully and the
QPixmaps are simply blank, which is fine for exercising the pure-logic paths.
"""
from __future__ import annotations

import os
import sys
import types

import pytest

pytestmark = pytest.mark.qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@pytest.fixture(scope="module")
def _qapp():
    qtwidgets = pytest.importorskip("PySide6.QtWidgets")
    app = qtwidgets.QApplication.instance()
    if app is None:
        app = qtwidgets.QApplication([])
    return app


@pytest.fixture
def deck(_qapp):
    from fpdb_3_legacy.Deck import Deck

    config = types.SimpleNamespace(graphics_path="/tmp/fpdb_test_gfx_does_not_exist")
    return Deck(config)


class TestDeckConstruction:
    def test_all_suits_loaded(self, deck) -> None:
        images = deck.get_all_card_images()
        for suit in ("s", "h", "d", "c"):
            assert suit in images
            assert len(images[suit]) == 13

    def test_card_back_under_key_zero(self, deck) -> None:
        images = deck.get_all_card_images()
        assert 0 in images
        assert images[0] is deck.back()

    def test_custom_dimensions(self, _qapp) -> None:
        from fpdb_3_legacy.Deck import Deck

        config = types.SimpleNamespace(graphics_path="/tmp/fpdb_test_gfx")
        d = Deck(config, deck_type="simple", card_back="back04", width=10, height=14)
        pm = d.card("s", 14)
        assert pm.width() == 10
        assert pm.height() == 14


class TestCardLookup:
    @pytest.mark.parametrize("suit", ["s", "h", "d", "c"])
    @pytest.mark.parametrize("rank", [2, 9, 10, 11, 12, 13, 14])
    def test_card_returns_pixmap(self, deck, suit, rank) -> None:
        pm = deck.card(suit, rank)
        assert pm is not None
        assert pm.width() == 30
        assert pm.height() == 42

    def test_card_invalid_rank_raises(self, deck) -> None:
        with pytest.raises(KeyError):
            deck.card("s", 1)

    def test_card_invalid_suit_raises(self, deck) -> None:
        with pytest.raises((KeyError, TypeError)):
            deck.card("x", 14)


class TestBack:
    def test_back_returns_pixmap(self, deck) -> None:
        assert deck.back() is not None


class TestRank:
    @pytest.mark.parametrize(
        ("token", "expected"),
        [
            ("2", 2),
            ("9", 9),
            ("t", 10),
            ("T", 10),
            ("j", 11),
            ("J", 11),
            ("q", 12),
            ("k", 13),
            ("a", 14),
            ("A", 14),
        ],
    )
    def test_rank_values(self, deck, token, expected) -> None:
        assert deck.rank(token) == expected

    def test_rank_unknown_raises(self, deck) -> None:
        with pytest.raises(KeyError):
            deck.rank("Z")


class TestGetAllCardImages:
    def test_structure(self, deck) -> None:
        images = deck.get_all_card_images()
        # 4 suits + the back image under key 0 == 5 top-level keys
        assert len(images) == 5
        # Each card image must be the same object returned by card()
        assert images["s"][14] is deck.card("s", 14)
