"""Verify Flop_Mucked can render a full 7-card stud hand.

This is the pre-check before switching stud games from the legacy Stud_mucked
grid to the per-seat Flop_Mucked overlay used by hold'em/omaha. Flop_Mucked was
written for 2-4 hole cards, so we confirm it lays out all seven stud cards
side by side without truncation or error, for both unscaled and scaled decks.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

from fpdb_3_legacy import Card
from fpdb_3_legacy.Mucked import Flop_Mucked


CARD_W, CARD_H = 30, 42


def _fake_card_images() -> dict:
    images: dict = {0: QPixmap(CARD_W, CARD_H)}
    for suit in ("s", "h", "d", "c"):
        images[suit] = {rank: QPixmap(CARD_W, CARD_H) for rank in range(2, 15)}
    return images


def _make_flop_mucked(cards_by_seat: dict, scale: float, images: dict) -> Flop_Mucked:
    # Bypass __init__ (needs a live deck/HUD) and inject only what
    # update_contents touches.
    fm = Flop_Mucked.__new__(Flop_Mucked)
    fm.card_images = images
    fm.card_width = CARD_W
    fm.card_height = CARD_H
    fm.card_scale = scale
    fm.displayed = False
    fm.m_windows = {}
    fm.hud = SimpleNamespace(
        cards=cards_by_seat,
        layout=SimpleNamespace(hh_seats={s: s for s in cards_by_seat}),
        stat_dict={},
    )
    # Neutralise positioning/tooltip side effects.
    fm._move_next_to_hud = lambda *a, **k: None
    fm.get_id_from_seat = lambda i: None
    return fm


def _fake_container() -> SimpleNamespace:
    return SimpleNamespace(seen_cards=QLabel(), adjustSize=lambda: None, show=lambda: None)


def test_flop_mucked_renders_seven_stud_cards_unscaled(qapp) -> None:
    images = _fake_card_images()
    seat = 2
    hand = tuple(Card.encodeCard(c) for c in ("7h", "4s", "Jc", "As", "2d", "9h", "Kc"))
    fm = _make_flop_mucked({seat: hand}, scale=1.0, images=images)
    container = _fake_container()

    fm.update_contents(container, seat)

    pm = container.seen_cards.pixmap()
    assert not pm.isNull(), "no pixmap rendered for a 7-card stud hand"
    # All seven cards laid side by side, none dropped or clipped.
    assert pm.width() == CARD_W * 7
    assert pm.height() == CARD_H
    assert fm.displayed is True


def test_flop_mucked_renders_seven_stud_cards_scaled(qapp) -> None:
    images = _fake_card_images()
    seat = 5
    hand = tuple(Card.encodeCard(c) for c in ("Ts", "Td", "2c", "3c", "4c", "5c", "6c"))
    fm = _make_flop_mucked({seat: hand}, scale=0.7, images=images)
    container = _fake_container()

    fm.update_contents(container, seat)

    pm = container.seen_cards.pixmap()
    assert not pm.isNull()
    # Scratch is allocated at card_width * n_cards regardless of scale.
    assert pm.width() == CARD_W * 7
    assert pm.height() == CARD_H


def test_flop_mucked_folder_shows_only_exposed_upcards(qapp) -> None:
    images = _fake_card_images()
    seat = 1
    # Folded on an early street: only the door/upcards are known (rest 0).
    hand = (0, 0, Card.encodeCard("7s"), Card.encodeCard("2h"), 0, 0, 0)
    fm = _make_flop_mucked({seat: hand}, scale=1.0, images=images)
    container = _fake_container()

    fm.update_contents(container, seat)

    pm = container.seen_cards.pixmap()
    assert not pm.isNull()
    # visible_cards() drops the zeros -> two exposed cards only.
    assert pm.width() == CARD_W * 2


def test_flop_mucked_no_cards_renders_nothing(qapp) -> None:
    images = _fake_card_images()
    seat = 3
    fm = _make_flop_mucked({seat: (0, 0, 0, 0, 0, 0, 0)}, scale=1.0, images=images)
    container = _fake_container()

    fm.update_contents(container, seat)

    assert container.seen_cards.pixmap().isNull()
    assert fm.displayed is False
