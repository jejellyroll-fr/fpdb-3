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
        _table_reads={},
        _ax_reader_enabled=True,
        _ff_trace=MagicMock(),
        AX_READS_PER_HAND=HUD_main.HudMain.AX_READS_PER_HAND,
        AX_FRUITLESS_READS_BEFORE_GIVING_UP=GIVE_UP_AT,
        HERO_SLOT=HUD_main.HudMain.HERO_SLOT,
        MIN_PLAYERS_TO_SHOW=HUD_main.HudMain.MIN_PLAYERS_TO_SHOW,
    )


def _hud(table_key: str = "Colorado 11 #3477872"):
    table = SimpleNamespace(title="Winamax Colorado 11", key=table_key, x=3845, y=39, number=3477872)
    return SimpleNamespace(table=table)


def _read(app, hand_id: str, table_key: str = "Colorado 11 #3477872") -> dict:
    return HUD_main.HudMain._ax_slots(app, _hud(table_key), hand_id, 6)


def test_the_reader_is_given_up_on_after_enough_empty_reads() -> None:
    app = _hud_main([{}] * (GIVE_UP_AT + 5))

    for hand in range(GIVE_UP_AT):
        _read(app, f"hand-{hand}")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is True


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
    """A client that does publish its table must keep the fast path forever.

    Slot 0 is the bottom-centre chair the hero is always drawn in; a read
    holding it, with enough players, is one the caller can act on.
    """
    app = _hud_main([{0: "jejellyroll", 1: "Bussy67"}] * (GIVE_UP_AT + 5))

    for hand in range(GIVE_UP_AT + 2):
        _read(app, f"hand-{hand}")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is False
    assert app._table_reads["Colorado 11 #3477872"].fruitless == 0


def test_one_good_read_forgives_the_empty_ones_before_it() -> None:
    """A table being redrawn is not a client that publishes nothing."""
    app = _hud_main([{}] * (GIVE_UP_AT - 1) + [{0: "jejellyroll", 1: "Bussy67"}] + [{}] * 5)

    for hand in range(GIVE_UP_AT + 4):
        _read(app, f"hand-{hand}")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is False


def test_one_table_giving_up_does_not_silence_another() -> None:
    """A single counter reached its threshold in half the hands with two tables.

    The evidence for "this client publishes nothing" has to be gathered per
    table, or multitabling gives up before one table has been asked five hands'
    worth of times.
    """
    app = _hud_main([{}] * (GIVE_UP_AT * 2 + 5))

    for hand in range(GIVE_UP_AT):
        _read(app, f"hand-{hand}", table_key="Colorado 11 #3477872")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is True
    assert "Colorado 12 #463544" not in app._table_reads

    reads_before = app.winamax_ax_seats.read_window.call_count
    _read(app, "another", table_key="Colorado 12 #463544")

    assert app.winamax_ax_seats.read_window.call_count == reads_before + 1


def test_reads_that_never_seat_anyone_are_given_up_on() -> None:
    """Measured on a live session, every read of every hand, on both tables:

        window-read ... 172ms read#1 players=2 slots={1: 'jejellyroll', 2: 'cr-scot'}

    Non-empty, so the old counter reset on every one of them and the breaker
    never tripped -- but slot 0 is missing, so the caller cannot place the hero
    and throws the answer away. Six reads a hand at 94-172ms, on two tables,
    for nothing. "Fruitless" has to mean "could not be acted on".
    """
    app = _hud_main([{1: "jejellyroll", 2: "cr-scot"}] * (GIVE_UP_AT + 5))

    for hand in range(GIVE_UP_AT):
        _read(app, f"hand-{hand}")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is True


def test_a_read_holding_the_hero_but_too_few_players_is_fruitless() -> None:
    """The caller needs MIN_PLAYERS_TO_SHOW as well as the hero's chair."""
    app = _hud_main([{0: "jejellyroll"}] * (GIVE_UP_AT + 5))

    for hand in range(GIVE_UP_AT):
        _read(app, f"hand-{hand}")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is True


def test_one_usable_read_forgives_the_useless_ones_before_it() -> None:
    app = _hud_main(
        [{1: "jejellyroll", 2: "x"}] * (GIVE_UP_AT - 1)
        + [{0: "jejellyroll", 1: "x"}]
        + [{1: "jejellyroll", 2: "x"}] * 5,
    )

    for hand in range(GIVE_UP_AT + 4):
        _read(app, f"hand-{hand}")

    assert app._table_reads["Colorado 11 #3477872"].gave_up is False


def test_the_reader_can_be_switched_off_outright() -> None:
    """A player whose client never publishes its felt should not pay two hands a session."""
    app = _hud_main([{0: "jejellyroll", 1: "Bussy67"}] * 5)
    app._ax_reader_enabled = False

    assert _read(app, "hand-1") == {}
    app.winamax_ax_seats.read_window.assert_not_called()


def _sweeper(gave_up: bool = False, enabled: bool = True):
    """A HudMain stub carrying only what _read_window_slots touches."""
    reader = MagicMock()
    reader.read_window.return_value = {0: "jejellyroll", 1: "Bussy67"}
    table = SimpleNamespace(title="Winamax Colorado 11", key="Colorado 11 #3477872", number=3477872)
    return (
        SimpleNamespace(
            winamax_ax_seats=reader,
            _table_reads=({"Colorado 11 #3477872": HUD_main.TableReadState(gave_up=True)} if gave_up else {}),
            _ax_reader_enabled=enabled,
        ),
        SimpleNamespace(table=table, max=6),
    )


def test_the_idle_sweep_reads_a_table_that_still_answers() -> None:
    app, hud = _sweeper()

    assert HUD_main.HudMain._read_window_slots(app, hud) == {0: "jejellyroll", 1: "Bussy67"}


def test_the_idle_sweep_stops_reading_a_table_given_up_on() -> None:
    """It ran every FF_IDLE_RECHECK_SECONDS regardless, for the whole session.

    The per-hand path stopped and this one did not, so an abandoned table went on
    walking another process's accessibility tree -- on exactly the clients the
    breaker exists to stop reading, and for a table nobody was playing.
    """
    app, hud = _sweeper(gave_up=True)

    assert HUD_main.HudMain._read_window_slots(app, hud) is None
    app.winamax_ax_seats.read_window.assert_not_called()


def test_the_idle_sweep_respects_the_reader_being_switched_off() -> None:
    app, hud = _sweeper(enabled=False)

    assert HUD_main.HudMain._read_window_slots(app, hud) is None
    app.winamax_ax_seats.read_window.assert_not_called()


def test_a_retiring_table_takes_the_breaker_s_verdict_with_it() -> None:
    """A pool hands the same name back to the next table it opens.

    Close a table and Winamax gives the next one the same "Colorado 3", so a HUD
    built after a restart inherited "this client will not answer" from a client
    that is no longer running: it never read its window, never asked for
    accessibility, and went straight to the log-derived seats for the session.
    """
    app = SimpleNamespace(
        _table_reads={"Colorado 3": HUD_main.TableReadState(gave_up=True, fruitless=12, reads=12)},
    )

    HUD_main.HudMain._forget_window_seat_state(app, "Colorado 3")

    assert app._table_reads == {}


def test_forgetting_one_table_leaves_the_others_alone() -> None:
    app = SimpleNamespace(
        _table_reads={
            "Colorado 3": HUD_main.TableReadState(gave_up=True),
            "Colorado 4": HUD_main.TableReadState(gave_up=True),
        },
    )

    HUD_main.HudMain._forget_window_seat_state(app, "Colorado 3")

    assert list(app._table_reads) == ["Colorado 4"]


def test_forgetting_survives_a_hud_built_without_the_full_constructor() -> None:
    """The same shape _clear_fast_fold_table's neighbours guard against."""
    HUD_main.HudMain._forget_window_seat_state(SimpleNamespace(), "Colorado 3")


def test_retiring_a_table_releases_its_window_state_too(monkeypatch) -> None:
    """Nothing released it in production, which is how a handle carried its past.

    Winamax hands one table's HWND to another of its own, so the owner's pid is
    identical and says nothing; only the HUD knows the table has gone.
    """
    from fpdb_3_legacy import winamax_ax_seats

    forgotten = []
    monkeypatch.setattr(winamax_ax_seats, "forget_window_state", forgotten.append)
    app = SimpleNamespace(_table_reads={"Colorado 3": HUD_main.TableReadState()})

    HUD_main.HudMain._forget_window_seat_state(app, "Colorado 3", 3477872)

    assert forgotten == [3477872]
    assert app._table_reads == {}


def test_retiring_a_table_with_no_window_forgets_only_what_it_has(monkeypatch) -> None:
    """A HUD torn down before its window resolved has no handle to release."""
    from fpdb_3_legacy import winamax_ax_seats

    forgotten = []
    monkeypatch.setattr(winamax_ax_seats, "forget_window_state", forgotten.append)
    app = SimpleNamespace(_table_reads={"Colorado 3": HUD_main.TableReadState()})

    HUD_main.HudMain._forget_window_seat_state(app, "Colorado 3", None)

    assert forgotten == []
    assert app._table_reads == {}
