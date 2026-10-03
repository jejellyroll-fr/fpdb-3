"""Session Guard: limits for the session being played, and when they are reached (#395).

A player sets limits before or during a session -- a loss or a win in money or big blinds,
a duration, a number of hands, a drawdown from the session's best point -- and is told,
once, when one is reached. That is all it does: it reads imported hands and never touches
a poker client.

The session is the Session Viewer's (:mod:`fpdb_3_legacy.session_analytics`): cash hands
split after a 30-minute gap or a currency change. The *current* session is the last one,
while its last hand is less than that gap old; past it the session is over and nothing is
monitored until the next hand starts a new one.

Each guard fires once. Acknowledged, it stays quiet until its value has gone back under the
threshold and crosses it again -- a loss limit hit, recovered and hit again warns twice; a
duration, which only grows, warns once. A reset re-arms everything. A new session starts
with every guard armed: an alert from the previous session is never carried over.

Nothing here knows about Qt: :mod:`fpdb_3_legacy.session_guard_dialog` configures the
guard and presents what it reports.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, fields
from typing import Any, Final

from fpdb_3_legacy.session_analytics import SESSION_GAP_SECONDS, SessionMetrics, build_sessions

# The guards, in the order they are shown.
LOSS_MONEY: Final = "loss_money"
LOSS_BB: Final = "loss_bb"
WIN_MONEY: Final = "win_money"
WIN_BB: Final = "win_bb"
DURATION: Final = "duration"
HANDS: Final = "hands"
DRAWDOWN_BB: Final = "drawdown_bb"
DRAWDOWN_MONEY: Final = "drawdown_money"
GUARDS: Final = (LOSS_MONEY, LOSS_BB, WIN_MONEY, WIN_BB, DURATION, HANDS, DRAWDOWN_BB, DRAWDOWN_MONEY)

# What a guard's value is counted in.
MONEY: Final = "money"  # currency minor units (cents), as the database stores profit
BB: Final = "bb"
SECONDS: Final = "seconds"
COUNT: Final = "hands"
UNITS: Final = {
    LOSS_MONEY: MONEY,
    LOSS_BB: BB,
    WIN_MONEY: MONEY,
    WIN_BB: BB,
    DURATION: SECONDS,
    HANDS: COUNT,
    DRAWDOWN_BB: BB,
    DRAWDOWN_MONEY: MONEY,
}

# A guard's state within one session.
ARMED: Final = "armed"
FIRED: Final = "fired"  # reached, not yet acknowledged
ACKNOWLEDGED: Final = "acknowledged"  # quiet until the value goes back under the threshold

#: How far back hands are read to find the current session; doubled for as long as the
#: session may have started before it (a long grind has no 30-minute gap to stop at).
LOOKBACK_SECONDS: Final = 24 * 3600


@dataclass(frozen=True)
class GuardLimits:
    """The limits of one session; ``None`` leaves a guard off.

    Money is in currency minor units (cents), like the profit the database stores, so a
    threshold and a result are compared without a conversion in between.
    """

    loss_money: int | None = None
    loss_bb: float | None = None
    win_money: int | None = None
    win_bb: float | None = None
    duration: int | None = None  # seconds
    hands: int | None = None
    drawdown_bb: float | None = None
    drawdown_money: int | None = None

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if value is not None and value <= 0:
                msg = f"{item.name} must be positive, not {value!r}"
                raise ValueError(msg)

    def enabled(self) -> tuple[str, ...]:
        return tuple(guard for guard in GUARDS if getattr(self, guard) is not None)

    def to_dict(self) -> dict[str, Any]:
        return {guard: getattr(self, guard) for guard in GUARDS if getattr(self, guard) is not None}

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> GuardLimits:
        """Limits read back from saved defaults; anything unreadable is left off."""
        kwargs: dict[str, Any] = {}
        for guard in GUARDS:
            raw = values.get(guard)
            if raw in (None, ""):
                continue
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            # "1e309", "inf" and "nan" read as floats but are no limit: an infinite one would
            # never fire, and an integral one would not even convert.
            if not math.isfinite(number):
                continue
            value = int(number) if UNITS[guard] in (MONEY, SECONDS, COUNT) else number
            # Checked once converted: a duration of 0.4 seconds truncates to nothing.
            if value > 0:
                kwargs[guard] = value
        return cls(**kwargs)


@dataclass(frozen=True)
class SessionSnapshot:
    """Where the current session stands, as the guards read it.

    BB values are ``None`` when a hand of the session has no usable big blind (the Session
    Viewer's rule): a BB guard is then unavailable rather than measured on part of it.
    """

    key: tuple[int, int, str]  # first hand's time and id, currency: which session this is
    hands: int
    started_at: int
    last_hand_at: int
    elapsed_seconds: int
    currency: str
    profit_money: float
    profit_bb: float | None
    peak_money: float
    peak_bb: float | None

    @property
    def drawdown_money(self) -> float:
        return self.peak_money - self.profit_money

    @property
    def drawdown_bb(self) -> float | None:
        if self.peak_bb is None or self.profit_bb is None:
            return None
        return self.peak_bb - self.profit_bb

    def value(self, guard: str) -> float | None:
        """The guard's current value, in its unit; ``None`` when it cannot be measured."""
        values: dict[str, float | None] = {
            LOSS_MONEY: -self.profit_money,
            LOSS_BB: None if self.profit_bb is None else -self.profit_bb,
            WIN_MONEY: self.profit_money,
            WIN_BB: self.profit_bb,
            DURATION: float(self.elapsed_seconds),
            HANDS: float(self.hands),
            DRAWDOWN_BB: self.drawdown_bb,
            DRAWDOWN_MONEY: self.drawdown_money,
        }
        return values[guard]


def snapshot_of(session: SessionMetrics, now: float) -> SessionSnapshot:
    """The guards' view of one Session Viewer session, at *now*."""
    complete_bb = session.bb_hands == session.hands
    return SessionSnapshot(
        key=(session.start_timestamp, session.hand_ids[0], session.currency),
        hands=session.hands,
        started_at=session.start_timestamp,
        last_hand_at=session.end_timestamp,
        # Wall-clock time since the first hand: the session goes on between hands.
        elapsed_seconds=max(0, int(now) - session.start_timestamp),
        currency=session.currency,
        profit_money=session.profit_minor,
        profit_bb=session.profit_bb if complete_bb else None,
        peak_money=session.peak_minor,
        peak_bb=session.peak_bb if complete_bb else None,
    )


def current_session(rows: Sequence[tuple[Any, ...]], now: float) -> SessionMetrics | None:
    """The session being played: the last one, unless its last hand is a gap old."""
    sessions = build_sessions(list(rows))
    if not sessions:
        return None
    last = sessions[-1]
    if now - last.end_timestamp > SESSION_GAP_SECONDS:
        return None
    return last


def load_current_session(
    fetch: Callable[[float], Iterable[tuple[Any, ...]]],
    now: float,
    *,
    lookback: int = LOOKBACK_SECONDS,
) -> SessionMetrics | None:
    """Read the hands since a cut-off and find the current session in them.

    *fetch(since)* returns the Session Viewer's rows for hands played since the epoch time
    *since*. A session that may have begun before the cut-off -- its first hand within a gap
    of it -- is read again twice as far back, until its first hand is known: a long session
    is never measured from halfway. Hands run out eventually, so this ends.
    """
    while True:
        since = now - lookback
        session = current_session(list(fetch(since)), now)
        if session is None or session.start_timestamp - since > SESSION_GAP_SECONDS:
            return session
        lookback *= 2


@dataclass(frozen=True)
class GuardStatus:
    """One guard against the current session."""

    guard: str
    threshold: float
    value: float | None
    state: str

    @property
    def unit(self) -> str:
        return UNITS[self.guard]

    @property
    def available(self) -> bool:
        return self.value is not None

    @property
    def reached(self) -> bool:
        return self.value is not None and self.value >= self.threshold


class SessionGuard:
    """The limits of a session, and which of them have fired.

    :meth:`update` is fed the current session each time hands may have been imported (and
    with ``None`` when there is no session); it returns the guards that have just been
    reached, each once.
    """

    def __init__(self, limits: GuardLimits) -> None:
        self.limits = limits
        self.session_key: tuple[int, int, str] | None = None
        self.states: dict[str, str] = {}
        self.statuses: list[GuardStatus] = []

    def set_limits(self, limits: GuardLimits) -> None:
        """Change the limits; a guard whose threshold changed is armed again."""
        changed = {guard for guard in GUARDS if getattr(limits, guard) != getattr(self.limits, guard)}
        self.limits = limits
        for guard in changed:
            self.states.pop(guard, None)

    def update(self, snapshot: SessionSnapshot | None) -> list[GuardStatus]:
        """Measure *snapshot* against the limits; the guards that fire now."""
        if snapshot is None:
            self.statuses = []
            return []
        if snapshot.key != self.session_key:
            # Another session: nothing fired in the previous one carries over.
            self.session_key = snapshot.key
            self.states = {}
        fired: list[GuardStatus] = []
        statuses: list[GuardStatus] = []
        for guard in self.limits.enabled():
            threshold = float(getattr(self.limits, guard))
            value = snapshot.value(guard)
            reached = value is not None and value >= threshold
            state = self.states.get(guard, ARMED)
            if state == ARMED and reached:
                state = FIRED
            elif state == ACKNOWLEDGED and not reached and value is not None:
                state = ARMED
            if state == FIRED and self.states.get(guard, ARMED) == ARMED:
                fired.append(GuardStatus(guard, threshold, value, state))
            self.states[guard] = state
            statuses.append(GuardStatus(guard, threshold, value, state))
        self.statuses = statuses
        return fired

    def pending(self) -> list[GuardStatus]:
        """Guards that fired and have not been acknowledged."""
        return [status for status in self.statuses if status.state == FIRED]

    def acknowledge(self, guards: Iterable[str] | None = None) -> None:
        """Quiet fired guards until their value goes back under the threshold."""
        targets = set(GUARDS if guards is None else guards)
        for guard, state in self.states.items():
            if guard in targets and state == FIRED:
                self.states[guard] = ACKNOWLEDGED
        self.statuses = [
            GuardStatus(status.guard, status.threshold, status.value, self.states.get(status.guard, status.state))
            for status in self.statuses
        ]

    def reset(self) -> None:
        """Arm every guard again; one still past its threshold fires on the next update."""
        self.states = {}
        self.statuses = [GuardStatus(s.guard, s.threshold, s.value, ARMED) for s in self.statuses]


def fetch_since(db: Any, player_ids: Iterable[int]) -> Callable[[float], list[tuple[Any, ...]]]:
    """Read the Session Viewer's rows for the hero's cash hands, for :func:`load_current_session`.

    One fixed query per hero id, with the id and the cut-off as parameters, rather than a
    list built into the SQL text.
    """
    ids = sorted({int(player_id) for player_id in player_ids})
    query = db.sql.query["sessionGuardHands"]

    def fetch(since: float) -> list[tuple[Any, ...]]:
        cutoff = datetime.datetime.fromtimestamp(since, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cursor = db.get_cursor()
        rows: list[tuple[Any, ...]] = []
        for player_id in ids:
            cursor.execute(query, (player_id, cutoff))
            rows.extend(tuple(row) for row in cursor.fetchall())
        return rows

    return fetch
