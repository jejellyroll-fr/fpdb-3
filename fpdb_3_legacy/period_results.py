"""Cash results per day, week and month, Qt free (#827).

The Results calendar shows what each day, week or month won. This module is
its reusable core: it takes the hero's cash hands, files each one under the
period it was played in and sums it there, and draws the four profit curves
(net, all-in EV, showdown, non-showdown) of any set of hands.

Days follow the HudCache rules of #600 (see ``hud_day``): a hand's UTC start
time is moved to the machine's local time by the offset in force at the hand's
own start, then back by ``day_start`` hours, so a session that runs past
midnight stays in one day and a hand near the boundary does not change day with
the season. Weeks start on Monday (ISO 8601); a week or a month is the set of
those days.

Amounts stay in the database's minor units (cents). Money is never summed
across currencies: each period keeps one total per currency. Big blinds are
summed across currencies, each hand divided by its own blind; only a positive
blind counts (``-1`` marks a fixed-limit game), and BB/100 for both profit and
all-in EV uses that same count of hands, as the Session Viewer does.

A hand without an all-in EV (older imports, other trackers) counts its result
as its EV, which is what fpdb stores for a hand that had no all-in.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from fpdb_3_legacy import hud_day

DAY = "day"
WEEK = "week"
MONTH = "month"
GRANULARITIES = (DAY, WEEK, MONTH)

#: Curves drawn by :func:`build_curves`, in drawing order.
CURVES = ("net", "ev", "showdown", "nonshowdown")

UNIT_BB = "BB"


@dataclass(frozen=True)
class HandResult:  # pylint: disable=too-many-instance-attributes  # one field per column of the query
    """One cash hand of the hero, as read from the database."""

    hand_id: int
    start_time: datetime  # naive UTC
    profit_minor: float
    all_in_ev_minor: float
    showdown: bool
    big_blind_minor: float
    currency: str
    player_id: int | None = None  # the hero's player of the hand, on its own site

    @property
    def has_bb(self) -> bool:
        """Whether the hand has a big blind to count in (fixed limit stores -1)."""
        return self.big_blind_minor > 0


@dataclass
class PeriodResult:  # pylint: disable=too-many-instance-attributes
    """What one day, week or month won."""

    start: date
    granularity: str
    hands: int = 0
    bb_hands: int = 0
    profit_bb: float = 0.0
    all_in_ev_bb: float = 0.0
    showdown_bb: float = 0.0
    nonshowdown_bb: float = 0.0
    profit_minor: dict[str, float] = field(default_factory=dict)
    all_in_ev_minor: dict[str, float] = field(default_factory=dict)
    hand_ids: list[int] = field(default_factory=list)

    @property
    def currencies(self) -> list[str]:
        """The currencies played in the period, sorted."""
        return sorted(self.profit_minor)

    @property
    def bb_per_100(self) -> float | None:
        """Big blinds won per 100 hands with a big blind, None without one."""
        return self.profit_bb / self.bb_hands * 100 if self.bb_hands else None

    @property
    def ev_bb_per_100(self) -> float | None:
        """All-in EV in big blinds per 100 hands, over the same hands as :attr:`bb_per_100`."""
        return self.all_in_ev_bb / self.bb_hands * 100 if self.bb_hands else None

    def add(self, hand: HandResult) -> None:
        """Count ``hand`` in the period."""
        self.hands += 1
        self.hand_ids.append(hand.hand_id)
        self.profit_minor[hand.currency] = self.profit_minor.get(hand.currency, 0.0) + hand.profit_minor
        self.all_in_ev_minor[hand.currency] = self.all_in_ev_minor.get(hand.currency, 0.0) + hand.all_in_ev_minor
        if hand.has_bb:
            profit_bb = hand.profit_minor / hand.big_blind_minor
            self.bb_hands += 1
            self.profit_bb += profit_bb
            self.all_in_ev_bb += hand.all_in_ev_minor / hand.big_blind_minor
            if hand.showdown:
                self.showdown_bb += profit_bb
            else:
                self.nonshowdown_bb += profit_bb

    def money(self, currency: str) -> float:
        """Profit in ``currency`` (minor units), zero when nothing was played in it."""
        return self.profit_minor.get(currency, 0.0)


def _number(value: Any) -> float:
    return float(value) if value is not None else 0.0


def parse_hands(rows: Iterable[Sequence[Any]]) -> list[HandResult]:
    """Rows of ``periodResultsHands``, ordered by start time then hand id.

    ``(hand id, start time, profit, all-in EV, saw showdown, big blind, currency,
    player id)``; the start time is a datetime, or text on SQLite. A missing
    all-in EV is the hand's result; the player id may be left out.
    """
    hands = []
    for row in rows:
        start = hud_day.parse_time(row[1])
        if start is None:
            continue
        profit = _number(row[2])
        hands.append(
            HandResult(
                hand_id=int(row[0]),
                start_time=start,
                profit_minor=profit,
                all_in_ev_minor=profit if row[3] is None else float(row[3]),
                showdown=bool(row[4]),
                big_blind_minor=_number(row[5]),
                currency=str(row[6] or "UNKNOWN").upper(),
                player_id=int(row[7]) if len(row) > 7 and row[7] is not None else None,
            ),
        )
    hands.sort(key=lambda hand: (hand.start_time, hand.hand_id))
    return hands


def local_day(start_time: datetime, day_start: float = 0.0) -> date:
    """The day a hand that started at ``start_time`` (UTC) is played on, as HudCache files it."""
    utc = hud_day.as_utc(start_time)
    return (utc + hud_day.local_offset(utc) - timedelta(hours=day_start)).date()


def period_start(day: date, granularity: str) -> date:
    """First day of the day, week (Monday) or month holding ``day``."""
    if granularity == DAY:
        return day
    if granularity == WEEK:
        return day - timedelta(days=day.weekday())
    if granularity == MONTH:
        return day.replace(day=1)
    msg = f"unknown granularity {granularity!r}"
    raise ValueError(msg)


def period_end(start: date, granularity: str) -> date:
    """Last day of the period that starts on ``start``."""
    if granularity == DAY:
        return start
    if granularity == WEEK:
        return start + timedelta(days=6)
    if granularity == MONTH:
        return start.replace(day=calendar.monthrange(start.year, start.month)[1])
    msg = f"unknown granularity {granularity!r}"
    raise ValueError(msg)


def aggregate(
    hands: Sequence[HandResult],
    granularity: str,
    day_start: float = 0.0,
    days: Sequence[date] | None = None,
) -> list[PeriodResult]:
    """The hands summed per period, oldest period first; periods without a hand are left out.

    ``days`` is each hand's local day when already known (see :func:`local_day`).
    """
    if days is None:
        days = [local_day(hand.start_time, day_start) for hand in hands]
    periods: dict[date, PeriodResult] = {}
    for hand, day in zip(hands, days, strict=True):
        start = period_start(day, granularity)
        period = periods.get(start)
        if period is None:
            period = periods[start] = PeriodResult(start=start, granularity=granularity)
        period.add(hand)
    return [periods[start] for start in sorted(periods)]


def total(periods: Iterable[PeriodResult], granularity: str = "total") -> PeriodResult | None:
    """All the periods as one, or None when there are none."""
    periods = list(periods)
    if not periods:
        return None
    result = PeriodResult(start=periods[0].start, granularity=granularity)
    for period in periods:
        result.hands += period.hands
        result.bb_hands += period.bb_hands
        result.profit_bb += period.profit_bb
        result.all_in_ev_bb += period.all_in_ev_bb
        result.showdown_bb += period.showdown_bb
        result.nonshowdown_bb += period.nonshowdown_bb
        result.hand_ids.extend(period.hand_ids)
        for currency, amount in period.profit_minor.items():
            result.profit_minor[currency] = result.profit_minor.get(currency, 0.0) + amount
        for currency, amount in period.all_in_ev_minor.items():
            result.all_in_ev_minor[currency] = result.all_in_ev_minor.get(currency, 0.0) + amount
    return result


def display_units(hands: Sequence[HandResult]) -> list[str]:
    """Units the hands can be shown in: BB when a blind is known, then their currency if only one."""
    units = []
    if any(hand.has_bb for hand in hands):
        units.append(UNIT_BB)
    currencies = {hand.currency for hand in hands}
    if len(currencies) == 1:
        units.append(next(iter(currencies)))
    return units


def hand_value(hand: HandResult, amount_minor: float, unit: str) -> float | None:
    """``amount_minor`` of ``hand`` in ``unit``: big blinds or major currency units.

    None when the hand cannot be shown in that unit (no usable blind, another
    currency).
    """
    if unit == UNIT_BB:
        return amount_minor / hand.big_blind_minor if hand.has_bb else None
    if hand.currency != unit:
        return None
    return amount_minor / 100


@dataclass(frozen=True)
class Curves:
    """Cumulative results hand by hand, each starting at 0 before the first hand."""

    unit: str
    hand_ids: tuple[int, ...]
    net: tuple[float, ...]
    ev: tuple[float, ...]
    showdown: tuple[float, ...]
    nonshowdown: tuple[float, ...]

    @property
    def hands(self) -> int:
        """How many hands the curves follow."""
        return len(self.hand_ids)

    def final(self, name: str) -> float:
        """Where curve ``name`` ends."""
        return getattr(self, name)[-1]


def build_curves(hands: Iterable[HandResult], unit: str) -> Curves:
    """The four profit curves of ``hands`` in ``unit``; hands that cannot be shown in it are skipped."""
    hand_ids: list[int] = []
    lines: dict[str, list[float]] = {name: [0.0] for name in CURVES}
    for hand in hands:
        net = hand_value(hand, hand.profit_minor, unit)
        if net is None:
            continue
        ev = hand_value(hand, hand.all_in_ev_minor, unit) or 0.0
        hand_ids.append(hand.hand_id)
        lines["net"].append(lines["net"][-1] + net)
        lines["ev"].append(lines["ev"][-1] + ev)
        lines["showdown"].append(lines["showdown"][-1] + (net if hand.showdown else 0.0))
        lines["nonshowdown"].append(lines["nonshowdown"][-1] + (0.0 if hand.showdown else net))
    return Curves(unit=unit, hand_ids=tuple(hand_ids), **{name: tuple(values) for name, values in lines.items()})


def period_value(period: PeriodResult, unit: str) -> float | None:
    """A period's profit in ``unit``: BB, or major units of one currency (None if not played in it)."""
    if unit == UNIT_BB:
        return period.profit_bb if period.bb_hands else None
    if unit not in period.profit_minor:
        return None
    return period.profit_minor[unit] / 100


def month_weeks(year: int, month: int) -> list[list[date]]:
    """The weeks (Monday first) a month calendar shows, days of the adjacent months included."""
    return calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(year, month)


def shift_month(year: int, month: int, step: int) -> tuple[int, int]:
    """The month ``step`` months away from ``year``-``month``."""
    index = year * 12 + (month - 1) + step
    return index // 12, index % 12 + 1


@dataclass(frozen=True)
class Results:
    """Everything the Results calendar shows, built once per load."""

    hands: tuple[HandResult, ...]
    days: tuple[date, ...]  # each hand's local day
    periods: dict[str, tuple[PeriodResult, ...]]

    def by_start(self, granularity: str) -> dict[date, PeriodResult]:
        """The periods of ``granularity`` by their first day."""
        return {period.start: period for period in self.periods[granularity]}

    def hands_between(self, first: date, last: date) -> list[HandResult]:
        """The hands played from day ``first`` to day ``last``, both included."""
        return [hand for hand, day in zip(self.hands, self.days, strict=True) if first <= day <= last]

    def last_day(self) -> date | None:
        """The day the last hand was played on, None without hands."""
        return self.days[-1] if self.days else None


def build_results(rows: Iterable[Sequence[Any]], day_start: float = 0.0) -> Results:
    """Parse ``periodResultsHands`` rows and sum them per day, week and month."""
    hands = parse_hands(rows)
    days = [local_day(hand.start_time, day_start) for hand in hands]
    periods = {granularity: tuple(aggregate(hands, granularity, days=days)) for granularity in GRANULARITIES}
    return Results(hands=tuple(hands), days=tuple(days), periods=periods)


__all__ = [
    "CURVES",
    "DAY",
    "GRANULARITIES",
    "MONTH",
    "UNIT_BB",
    "WEEK",
    "Curves",
    "HandResult",
    "PeriodResult",
    "Results",
    "aggregate",
    "build_curves",
    "build_results",
    "display_units",
    "hand_value",
    "local_day",
    "month_weeks",
    "parse_hands",
    "period_end",
    "period_start",
    "period_value",
    "shift_month",
    "total",
]
