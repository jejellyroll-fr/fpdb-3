"""Session Guard: limits for the current session (#395).

Rows are the Session Viewer's -- ``(hand id, epoch time, profit, all-in EV, big blind,
currency)`` in minor units -- so the session the guard watches is the one the viewer shows.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.session_analytics import SESSION_GAP_SECONDS
from fpdb_3_legacy.session_guard import (
    ACKNOWLEDGED,
    ARMED,
    DRAWDOWN_BB,
    DRAWDOWN_MONEY,
    DURATION,
    FIRED,
    HANDS,
    LOSS_BB,
    LOSS_MONEY,
    WIN_BB,
    WIN_MONEY,
    GuardLimits,
    SessionGuard,
    current_session,
    load_current_session,
    snapshot_of,
)

START = 1_790_000_000
BB = 100  # one big blind is 100 minor units ($1)


def hands(*profits_bb: float, start: int = START, step: int = 60, first_id: int = 1, bb: int = BB) -> list[tuple]:
    """One hand per minute, each winning or losing that many big blinds."""
    return [
        (first_id + index, start + index * step, profit * bb, profit * bb, bb, "USD")
        for index, profit in enumerate(profits_bb)
    ]


def snapshot(rows: list[tuple], now: float | None = None):
    now = rows[-1][1] + 30 if now is None else now
    session = current_session(rows, now)
    assert session is not None
    return snapshot_of(session, now)


def fired(guard: SessionGuard, rows: list[tuple], now: float | None = None) -> list[str]:
    return [status.guard for status in guard.update(snapshot(rows, now))]


# -- the current session ----------------------------------------------------------


def test_the_current_session_is_the_last_one_while_it_goes_on() -> None:
    earlier = hands(5, 5, start=START)
    later = hands(-1, -2, start=START + 3 * 3600, first_id=10)
    rows = earlier + later

    session = current_session(rows, later[-1][1] + 60)

    assert session is not None
    assert session.hand_ids == (10, 11)


def test_after_a_gap_there_is_no_current_session() -> None:
    rows = hands(-3, -4)
    assert current_session(rows, rows[-1][1] + SESSION_GAP_SECONDS + 1) is None
    assert current_session([], START) is None


def test_a_session_older_than_the_window_is_read_again_further_back() -> None:
    # A 30-hour grind with a hand every 20 minutes: no 30-minute gap anywhere.
    rows = hands(*([1.0] * 91), step=20 * 60)
    now = rows[-1][1] + 60
    asked: list[float] = []

    def fetch(since: float) -> list[tuple]:
        asked.append(since)
        return [row for row in rows if row[1] >= since]

    session = load_current_session(fetch, now)

    assert session is not None
    assert session.hands == 91, "the whole session, not the part inside the first 24 hours"
    assert len(asked) == 2


def test_the_window_is_not_widened_for_a_session_that_started_inside_it() -> None:
    rows = hands(1, 1)
    asked: list[float] = []

    def fetch(since: float) -> list[tuple]:
        asked.append(since)
        return rows

    assert load_current_session(fetch, rows[-1][1] + 60) is not None
    assert len(asked) == 1


# -- thresholds -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("limits", "profits", "expected"),
    [
        (GuardLimits(loss_money=500), [-2, -2], []),
        (GuardLimits(loss_money=500), [-2, -2, -1], [LOSS_MONEY]),  # $5 lost
        (GuardLimits(loss_bb=5), [-2, -3], [LOSS_BB]),
        (GuardLimits(win_money=300), [1, 2], [WIN_MONEY]),
        (GuardLimits(win_bb=3.5), [1, 2], []),
        (GuardLimits(win_bb=3), [1, 2], [WIN_BB]),
        (GuardLimits(hands=3), [0, 0, 0], [HANDS]),
        (GuardLimits(drawdown_bb=4), [5, -1, -3], [DRAWDOWN_BB]),  # peak +5, now +1
        (GuardLimits(drawdown_money=400), [5, -1, -3], [DRAWDOWN_MONEY]),
    ],
)
def test_each_guard_fires_when_its_threshold_is_reached(limits, profits, expected) -> None:
    assert fired(SessionGuard(limits), hands(*profits)) == expected


def test_money_and_bb_are_measured_in_their_own_units() -> None:
    # 2 BB at $0.50/$1 blinds... and 2 BB at $5/$10: the same in BB, ten times the money.
    rows = hands(-2, bb=100) + hands(-2, start=START + 120, first_id=5, bb=1000)
    status = {
        status.guard: status.value
        for status in [
            *SessionGuard(GuardLimits(loss_money=1, loss_bb=1)).update(snapshot(rows)),
        ]
    }

    assert status[LOSS_MONEY] == 2200
    assert status[LOSS_BB] == 4


def test_duration_runs_on_the_clock_between_hands() -> None:
    rows = hands(0, 0, 0, step=20 * 60)  # at 0, 20 and 40 minutes
    guard = SessionGuard(GuardLimits(duration=3600))

    assert fired(guard, rows, now=START + 2500) == []
    # No hand since minute 40, yet the session goes on and an hour has passed since it began.
    assert fired(guard, rows, now=START + 3600) == [DURATION]


def test_a_guard_fires_once_until_it_is_acknowledged() -> None:
    guard = SessionGuard(GuardLimits(loss_bb=5))
    rows = hands(-6)

    assert fired(guard, rows) == [LOSS_BB]
    assert fired(guard, rows + hands(-1, start=START + 60, first_id=2)) == [], "no alert on every later hand"
    assert [status.guard for status in guard.pending()] == [LOSS_BB]

    guard.acknowledge()

    assert guard.pending() == []
    assert guard.statuses[0].state == ACKNOWLEDGED


def test_an_acknowledged_guard_fires_again_only_after_going_back_under() -> None:
    guard = SessionGuard(GuardLimits(loss_bb=5))
    rows = hands(-6)
    assert fired(guard, rows) == [LOSS_BB]
    guard.acknowledge([LOSS_BB])

    still_down = rows + hands(-1, start=START + 60, first_id=2)
    assert fired(guard, still_down) == []

    recovered = still_down + hands(4, start=START + 120, first_id=3)  # -3 BB
    assert fired(guard, recovered) == []
    assert guard.statuses[0].state == ARMED

    lost_again = recovered + hands(-3, start=START + 180, first_id=4)  # -6 BB
    assert fired(guard, lost_again) == [LOSS_BB]


def test_reset_arms_every_guard_again() -> None:
    guard = SessionGuard(GuardLimits(hands=1, loss_bb=1))
    rows = hands(-2)
    assert sorted(fired(guard, rows)) == sorted([LOSS_BB, HANDS])
    guard.acknowledge()

    guard.reset()

    assert sorted(fired(guard, rows)) == sorted([LOSS_BB, HANDS])


def test_a_new_session_starts_with_every_guard_armed() -> None:
    guard = SessionGuard(GuardLimits(loss_bb=5))
    first = hands(-6)
    assert fired(guard, first) == [LOSS_BB]

    second = first + hands(-6, start=START + 4 * 3600, first_id=20)
    assert fired(guard, second) == [LOSS_BB], "the previous session's alert is not carried over"
    assert guard.statuses[0].state == FIRED


def test_no_session_means_no_status() -> None:
    guard = SessionGuard(GuardLimits(loss_bb=5))
    assert guard.update(None) == []
    assert guard.statuses == []


def test_bb_guards_are_unavailable_when_a_hand_has_no_big_blind() -> None:
    # A fixed-limit hand stores -1: no usable big blind, as in the Session Viewer.
    rows = hands(-6) + [(2, START + 60, -500, -500, -1, "USD")]
    guard = SessionGuard(GuardLimits(loss_bb=5, drawdown_bb=1, loss_money=1000))

    assert fired(guard, rows) == [LOSS_MONEY]
    by_guard = {status.guard: status for status in guard.statuses}
    assert not by_guard[LOSS_BB].available
    assert not by_guard[DRAWDOWN_BB].available


def test_changing_a_threshold_arms_that_guard_again() -> None:
    guard = SessionGuard(GuardLimits(loss_bb=5, hands=1))
    rows = hands(-6)
    assert sorted(fired(guard, rows)) == sorted([LOSS_BB, HANDS])
    guard.acknowledge()

    guard.set_limits(GuardLimits(loss_bb=6, hands=1))

    assert fired(guard, rows) == [LOSS_BB]


# -- limits -----------------------------------------------------------------------


def test_limits_must_be_positive() -> None:
    with pytest.raises(ValueError, match="loss_bb"):
        GuardLimits(loss_bb=0)


def test_limits_round_trip_through_saved_defaults() -> None:
    limits = GuardLimits(loss_money=50_000, loss_bb=500, duration=7200, hands=1000, drawdown_bb=300)

    assert GuardLimits.from_dict({k: str(v) for k, v in limits.to_dict().items()}) == limits
    assert limits.enabled() == (LOSS_MONEY, LOSS_BB, DURATION, HANDS, DRAWDOWN_BB)


@pytest.mark.parametrize("raw", ["1e309", "inf", "-inf", "nan", "0.4"])
def test_saved_defaults_that_are_no_limit_are_left_off(raw: str) -> None:
    # Infinite or overflowing values; and a duration under a second truncates to nothing.
    assert GuardLimits.from_dict({"duration": raw, "loss_bb": raw if raw != "0.4" else "nan"}) == GuardLimits()


def test_unreadable_saved_defaults_are_left_off() -> None:
    assert GuardLimits.from_dict({"loss_bb": "lots", "hands": "-3", "win_bb": "", "duration": "60"}) == GuardLimits(
        duration=60
    )


def test_the_configuration_saves_and_forgets_the_defaults(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    import fpdb_3_legacy.Configuration as configuration

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(configuration, "CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(configuration, "_find_example_config", lambda _: str(root / "HUD_config.xml.example"))
    path = tmp_path / "HUD_config.xml"
    path.write_text((root / "HUD_config.xml.example").read_text(encoding="utf-8"), encoding="utf-8")
    limits = GuardLimits(loss_bb=500, duration=7200)

    config = configuration.Config(file=str(path))
    assert config.get_session_guard_defaults() == {}
    config.set_session_guard_defaults(limits.to_dict())

    reloaded = configuration.Config(file=str(path))
    assert GuardLimits.from_dict(reloaded.get_session_guard_defaults()) == limits
    assert not reloaded.wrongConfigVersion
    reloaded.set_session_guard_defaults(limits.to_dict())  # saved twice: still one element
    assert path.read_text(encoding="utf-8").count("<session_guard") == 1

    reloaded.set_session_guard_defaults(None)
    assert configuration.Config(file=str(path)).get_session_guard_defaults() == {}


# -- reachable from the application -----------------------------------------------


def test_the_tools_menu_offers_the_session_guard() -> None:
    from fpdb_3_legacy import menu_layout

    tools = next(menu for menu in menu_layout.menu_layout() if "Tools" in menu.title)
    assert "dia_session_guard" in {item.handler for item in tools.items}


def test_the_main_window_keeps_one_monitor_and_shows_it_in_the_status_bar() -> None:
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw").read_text(encoding="utf-8")
    action = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef) and node.name == "dia_session_guard"
    )
    dumped = ast.dump(action)

    for name in ("SessionGuardMonitor", "SessionGuardDialog", "SessionGuardIndicator", "SessionGuardAlert"):
        assert name in dumped
    assert "addPermanentWidget" in dumped
    # The monitor outlives the dialog: it is created once and kept on the window.
    assert "session_guard" in dumped


def test_a_session_longer_than_a_week_is_read_whole() -> None:
    rows = hands(*([0.5] * (8 * 72)), step=20 * 60)  # eight days, a hand every 20 minutes
    now = rows[-1][1] + 60

    def fetch(since: float) -> list[tuple]:
        return [row for row in rows if row[1] >= since]

    session = load_current_session(fetch, now)

    assert session is not None
    assert session.hands == len(rows), "never a total measured from halfway"
