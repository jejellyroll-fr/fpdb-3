"""Blocks must not survive the table they describe.

Taking a Fast-Fold table's blocks down was driven entirely by the client log:
the hand-over line, or the next hand's start. Neither arrives once the hero
has been moved away and the felt is waiting for players, and neither arrives
for a hand that had already finished when the reader began tailing -- so
starting the HUD mid-hand left one table showing the remains of a hand nobody
was playing. Measured on a real session, the blocks stayed up for 50, 80 and
124 seconds at a stretch, and two tables were still showing when the log
ended.

A table nobody has said anything about for a while is now asked directly.
"""

from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import HUD_main

HERO_SLOT = HUD_main.HudMain.HERO_SLOT
IDLE = HUD_main.HudMain.FF_IDLE_RECHECK_SECONDS


def _hud(*, showing: bool = True, title: str = "Winamax Bucarest 3") -> MagicMock:
    hud = MagicMock()
    hud.is_fast_fold = True
    hud.max = 6
    hud.table.title = title
    hud.stat_dict = {1: {"screen_name": "villain", "seat": 1}} if showing else {}
    hud.seat_players = {1: "villain"} if showing else {}
    return hud


def _hud_main(hud_dict: dict, slots) -> HUD_main.HudMain:
    """A HudMain wired to a window resolver returning ``slots``."""
    hud_main = HUD_main.HudMain.__new__(HUD_main.HudMain)
    hud_main.hud_dict = hud_dict
    hud_main._ff_last_activity = {}
    hud_main._clear_fast_fold_table = MagicMock()
    reader = MagicMock()
    if isinstance(slots, Exception):
        reader.read_window.side_effect = slots
    else:
        reader.read_window.return_value = slots
    hud_main.winamax_ax_seats = reader
    return hud_main


def _make_idle(hud_main: HUD_main.HudMain, temp_key: str, seconds: float) -> None:
    hud_main._ff_last_activity[temp_key] = time.monotonic() - seconds


def test_an_abandoned_table_is_cleared() -> None:
    """Hero alone on the felt, and the log silent: the blocks come down."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {HERO_SLOT: "jejellyroll"})
    _make_idle(hud_main, "Bucarest 3", IDLE + 5)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main._clear_fast_fold_table.assert_called_once()
    args = hud_main._clear_fast_fold_table.call_args.args
    assert args[0] == "Bucarest 3"
    assert args[2] == "idle-sweep"
    assert "1 player(s)" in args[3]


def test_an_empty_window_is_cleared() -> None:
    """The hero drawn and nobody else is the same answer as nobody at all."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {HERO_SLOT: "jejellyroll"})
    _make_idle(hud_main, "Bucarest 3", IDLE * 3)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main._clear_fast_fold_table.assert_called_once()


def test_a_table_still_being_played_is_left_alone() -> None:
    """A hand being tanked over must not be blanked."""
    hud = _hud()
    hud_main = _hud_main(
        {"Bucarest 3": hud},
        {HERO_SLOT: "jejellyroll", 1: "villain", 2: "other"},
    )
    _make_idle(hud_main, "Bucarest 3", IDLE + 5)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main._clear_fast_fold_table.assert_not_called()


def test_a_table_the_log_just_spoke_about_is_not_even_read() -> None:
    """Recent activity settles it without walking the accessibility tree."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {HERO_SLOT: "jejellyroll"})
    _make_idle(hud_main, "Bucarest 3", IDLE / 2)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main.winamax_ax_seats.read_window.assert_not_called()
    hud_main._clear_fast_fold_table.assert_not_called()


def test_a_table_showing_nothing_is_not_read_either() -> None:
    """Already down: there is nothing to take down."""
    hud = _hud(showing=False)
    hud_main = _hud_main({"Bucarest 3": hud}, {HERO_SLOT: "jejellyroll"})
    _make_idle(hud_main, "Bucarest 3", IDLE * 5)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main.winamax_ax_seats.read_window.assert_not_called()
    hud_main._clear_fast_fold_table.assert_not_called()


def test_an_ordinary_table_is_never_swept() -> None:
    """A cash-table HUD is driven by imports and has no log to go quiet."""
    hud = _hud()
    hud.is_fast_fold = False
    hud_main = _hud_main({"Some Cash Table": hud}, {HERO_SLOT: "jejellyroll"})
    _make_idle(hud_main, "Some Cash Table", IDLE * 5)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main._clear_fast_fold_table.assert_not_called()


@pytest.mark.parametrize(
    "slots",
    [
        {},  # read returned nothing at all
        {1: "villain"},  # the hero is missing: a half-drawn or failed read
        RuntimeError("accessibility timed out"),
    ],
    ids=["empty-read", "hero-missing", "read-failed"],
)
def test_a_read_that_cannot_be_trusted_changes_nothing(slots) -> None:
    """The client always draws the hero; a read without it proves nothing.

    Blanking a live table every time the accessibility API is slow would be a
    worse bug than the stale blocks this sweep exists to remove.
    """
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, slots)
    _make_idle(hud_main, "Bucarest 3", IDLE + 5)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main._clear_fast_fold_table.assert_not_called()


def test_the_window_is_not_re_read_every_tick() -> None:
    """Each read walks another process's accessibility tree; pace them."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {1: "villain"})  # unreadable: hero missing
    _make_idle(hud_main, "Bucarest 3", IDLE + 5)

    hud_main._sweep_stale_fast_fold_tables()
    hud_main._sweep_stale_fast_fold_tables()  # the 2s timer fires again
    hud_main._sweep_stale_fast_fold_tables()

    assert hud_main.winamax_ax_seats.read_window.call_count == 1


def test_a_table_never_heard_from_is_given_its_idle_period() -> None:
    """A HUD created this instant is not swept before it can be updated."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {HERO_SLOT: "jejellyroll"})
    # No _ff_last_activity entry at all, as just after create_HUD.

    hud_main._sweep_stale_fast_fold_tables()

    hud_main.winamax_ax_seats.read_window.assert_not_called()
    hud_main._clear_fast_fold_table.assert_not_called()


def test_only_the_idle_table_is_cleared() -> None:
    """Two tables, one abandoned: the other keeps its blocks."""
    abandoned, live = _hud(), _hud(title="Winamax Bucarest 4")
    hud_main = _hud_main({"Bucarest 3": abandoned, "Bucarest 4 #61826": live}, {HERO_SLOT: "jejellyroll"})
    _make_idle(hud_main, "Bucarest 3", IDLE + 5)
    _make_idle(hud_main, "Bucarest 4 #61826", 1.0)

    hud_main._sweep_stale_fast_fold_tables()

    assert hud_main._clear_fast_fold_table.call_count == 1
    assert hud_main._clear_fast_fold_table.call_args.args[0] == "Bucarest 3"


def test_no_resolver_means_no_sweep() -> None:
    """Without a window resolver there is no second opinion to act on."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {})
    hud_main.winamax_ax_seats = None
    _make_idle(hud_main, "Bucarest 3", IDLE * 5)

    hud_main._sweep_stale_fast_fold_tables()

    hud_main._clear_fast_fold_table.assert_not_called()


def test_a_live_update_resets_the_idle_clock() -> None:
    """A log line about a table is what keeps its blocks alive."""
    hud = _hud()
    hud_main = _hud_main({"Bucarest 3": hud}, {HERO_SLOT: "jejellyroll"})
    hud_main._ff_started = {}
    hud_main._ff_trace = MagicMock()
    hud_main._find_fast_fold_hud = MagicMock(return_value=("Bucarest 3", hud))
    hud_main._clear_fast_fold_table = MagicMock()
    hud_main.AX_RECHECK_DELAYS_MS = ()
    _make_idle(hud_main, "Bucarest 3", IDLE * 5)

    update = MagicMock(
        pool=f"{HUD_main.FAST_FOLD_POOL_PREFIX}.t1.2",
        hand_id="hand-1",
        finished=True,
        hero_left=False,
        logged_at_ms=0,
        table_no="3",
    )
    HUD_main.HudMain._on_winamax_table_update(hud_main, update)

    assert time.monotonic() - hud_main._ff_last_activity["Bucarest 3"] < 1.0
