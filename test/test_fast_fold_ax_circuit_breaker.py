"""A window reader that never finds anyone must stop being paid for.

Measured on a live 3.8.1 session against the Winamax client, with the trace on:

    window-read 'Winamax Colorado 11' 47ms read#1 players=0 slots={} empty=[0..5]
    window-read 'Winamax Colorado 11' 16ms read#2 players=0 slots={} empty=[0..5]
    ... six a hand, on both tables, every one of them players=0

The client does not publish its table content through UIAutomation, so the read
can only ever come back empty. Each one is a synchronous walk of another
process's tree on the GUI thread, at hand-start -- exactly when the HUD is
trying to draw. The seats then come from the client log either way.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fpdb_3_legacy import HUD_main  # noqa: E402

GIVE_UP_AT = HUD_main.HudMain.AX_FRUITLESS_READS_BEFORE_GIVING_UP


def _hud_main(slots_per_read):
    """A HudMain stub carrying only what _ax_slots touches."""
    reader = MagicMock()
    reader.read_window.side_effect = slots_per_read
    return SimpleNamespace(
        winamax_ax_seats=reader,
        _ax_rings={},
        _ax_fruitless_reads=0,
        _ax_reader_gave_up=False,
        _ff_trace=MagicMock(),
        AX_READS_PER_HAND=HUD_main.HudMain.AX_READS_PER_HAND,
        AX_FRUITLESS_READS_BEFORE_GIVING_UP=GIVE_UP_AT,
        HERO_SLOT=HUD_main.HudMain.HERO_SLOT,
    )


def _hud(table_key: str = "Colorado 11 #3477872"):
    table = SimpleNamespace(title="Winamax Colorado 11", key=table_key, x=3845, y=39, number=3477872)
    return SimpleNamespace(table=table)


def _read(app, hand_id: str) -> dict:
    return HUD_main.HudMain._ax_slots(app, _hud(), hand_id, 6)


def test_the_reader_is_given_up_on_after_enough_empty_reads() -> None:
    app = _hud_main([{}] * (GIVE_UP_AT + 5))

    for hand in range(GIVE_UP_AT):
        _read(app, f"hand-{hand}")

    assert app._ax_reader_gave_up is True


def test_no_further_reads_are_paid_for_once_it_has_given_up() -> None:
    """The point of the change: the GUI thread stops walking another process."""
    app = _hud_main([{}] * (GIVE_UP_AT + 5))
    for hand in range(GIVE_UP_AT):
        _read(app, f"hand-{hand}")
    calls_when_it_gave_up = app.winamax_ax_seats.read_window.call_count

    _read(app, "later-hand")
    _read(app, "later-hand-2")

    assert app.winamax_ax_seats.read_window.call_count == calls_when_it_gave_up


def test_a_reader_that_works_is_never_given_up_on() -> None:
    """A client that does publish its table must keep the fast path forever."""
    app = _hud_main([{0: "jejellyroll", 1: "Bussy67"}] * (GIVE_UP_AT + 5))

    for hand in range(GIVE_UP_AT + 2):
        _read(app, f"hand-{hand}")

    assert app._ax_reader_gave_up is False
    assert app._ax_fruitless_reads == 0


def test_one_good_read_forgives_the_empty_ones_before_it() -> None:
    """A table being redrawn is not a client that publishes nothing."""
    app = _hud_main([{}] * (GIVE_UP_AT - 1) + [{0: "jejellyroll"}] + [{}] * 5)

    for hand in range(GIVE_UP_AT + 4):
        _read(app, f"hand-{hand}")

    assert app._ax_reader_gave_up is False
