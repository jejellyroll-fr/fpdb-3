"""How long a Fast-Fold table waits for its players is the player's call.

The client log names a player only once they have acted, so a six-handed table
is named over several seconds -- +734ms, +3265ms, +15890ms in measured sessions.
Showing what is known so far means blocks appearing one at a time; waiting for
the ring means they appear together, later. Neither is right for everyone, and
the wait used to be 500ms with no way to say otherwise.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config


def _hud_ui(**attributes) -> Config:
    config = Config.__new__(Config)
    config.ui = SimpleNamespace(**attributes)
    return config


def _wait_ms(**attributes) -> int:
    config = _hud_ui(**attributes)
    # get_hud_ui_parameters reads many attributes; only ours is under test, and
    # the rest fall back to their own defaults through the same getattr guards.
    return Config.get_hud_ui_parameters(config)["fast_fold_seat_wait_ms"]


def test_the_default_is_what_the_hud_has_always_done() -> None:
    assert _wait_ms() == 500


def test_a_longer_wait_is_honoured() -> None:
    """Blocks together, later: the whole point of exposing this."""
    assert _wait_ms(fast_fold_seat_wait_ms="5000") == 5000


def test_zero_shows_the_first_player_at_once() -> None:
    assert _wait_ms(fast_fold_seat_wait_ms="0") == 0


def test_a_negative_wait_is_treated_as_none() -> None:
    assert _wait_ms(fast_fold_seat_wait_ms="-1") == 0


@pytest.mark.parametrize("bad", ["", "soon", "5s", None])
def test_an_unreadable_value_falls_back_to_the_default(bad) -> None:
    """A typo in the config must not stop a table getting a HUD."""
    assert _wait_ms(fast_fold_seat_wait_ms=bad) == 500


def _window_seats(**attributes) -> str:
    return Config.get_hud_ui_parameters(_hud_ui(**attributes))["fast_fold_window_seats"]


def test_the_window_reader_is_on_by_default() -> None:
    """It is what makes the seats arrive at once, where the client publishes them."""
    assert _window_seats() == "auto"


def test_the_window_reader_can_be_turned_off() -> None:
    """Each read is 94-218ms of GUI thread; a client that never answers is pure stutter."""
    assert _window_seats(fast_fold_window_seats="off") == "off"


@pytest.mark.parametrize("written", ["OFF", " Off ", "off"])
def test_the_value_is_read_the_way_a_person_writes_it(written) -> None:
    assert _window_seats(fast_fold_window_seats=written) == "off"


@pytest.mark.parametrize("bad", ["", "no", "false", None, 3])
def test_anything_unrecognised_leaves_the_reader_on(bad) -> None:
    """A typo must not silently cost the fast path where it works."""
    assert _window_seats(fast_fold_window_seats=bad) == "auto"


class _Update:
    def __init__(self, pool: str = "gf.t1.0", hand_id: str = "hand-1") -> None:
        self.pool, self.hand_id = pool, hand_id


def _waiter(wait_ms: int, scheduled: list):
    """A HudMain stub carrying only what _schedule_seat_wait_recheck touches."""
    from types import SimpleNamespace

    from fpdb_3_legacy import HUD_main

    return SimpleNamespace(
        _fast_fold_seat_wait_ms=wait_ms,
        _ff_seat_wait_scheduled=set(),
        AX_RECHECK_DELAYS_MS=HUD_main.HudMain.AX_RECHECK_DELAYS_MS,
        FF_SEAT_WAIT_MEMO_LIMIT=HUD_main.HudMain.FF_SEAT_WAIT_MEMO_LIMIT,
        _recheck_window=lambda pool: None,
    ), scheduled


def _schedule(app, update, elapsed, monkeypatch, scheduled):
    from fpdb_3_legacy import HUD_main

    monkeypatch.setattr(
        HUD_main.QTimer,
        "singleShot",
        staticmethod(lambda ms, _slot: scheduled.append(ms)),
    )
    HUD_main.HudMain._schedule_seat_wait_recheck(app, update, elapsed)


def test_a_long_wait_schedules_its_own_recheck(monkeypatch) -> None:
    """The hand's other rechecks stop at 1500ms; a 5s wait needs its own.

    Otherwise a short-handed table whose last ring update lands before the
    deadline is never drawn: nothing looks again until the hand is over, and
    then it is cleared.
    """
    scheduled = []
    app, _ = _waiter(5000, scheduled)

    _schedule(app, _Update(), elapsed=0.5, monkeypatch=monkeypatch, scheduled=scheduled)

    assert scheduled == [4500]


def test_a_short_wait_leans_on_the_rechecks_already_scheduled(monkeypatch) -> None:
    """Below AX_RECHECK_DELAYS_MS this would be a second timer saying the same thing."""
    scheduled = []
    app, _ = _waiter(500, scheduled)

    _schedule(app, _Update(), elapsed=0.0, monkeypatch=monkeypatch, scheduled=scheduled)

    assert scheduled == []


def test_one_recheck_per_hand_and_table(monkeypatch) -> None:
    """Every ring update of the hand comes through here; one timer is enough."""
    scheduled = []
    app, _ = _waiter(5000, scheduled)

    for elapsed in (0.2, 0.4, 0.8):
        _schedule(app, _Update(), elapsed=elapsed, monkeypatch=monkeypatch, scheduled=scheduled)

    assert len(scheduled) == 1


def test_two_tables_each_get_one(monkeypatch) -> None:
    scheduled = []
    app, _ = _waiter(5000, scheduled)

    _schedule(app, _Update(pool="gf.t1.0"), 0.2, monkeypatch, scheduled)
    _schedule(app, _Update(pool="gf.t1.1"), 0.2, monkeypatch, scheduled)

    assert len(scheduled) == 2


def test_the_memo_does_not_grow_without_bound(monkeypatch) -> None:
    """A session plays thousands of hands and nothing else prunes this."""
    scheduled = []
    app, _ = _waiter(5000, scheduled)

    for hand in range(app.FF_SEAT_WAIT_MEMO_LIMIT + 5):
        _schedule(app, _Update(hand_id=f"hand-{hand}"), 0.2, monkeypatch, scheduled)

    assert len(app._ff_seat_wait_scheduled) <= app.FF_SEAT_WAIT_MEMO_LIMIT
