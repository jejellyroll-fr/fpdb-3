"""Pure session segmentation and poker-result calculations for the Session Viewer.

Hands are ordered by timestamp and ID, then split after a gap greater than 30 minutes
or at a currency change. Estimated playing time is the first-to-last-hand interval,
with a one-minute minimum plus five minutes for session overhead. Profit and blinds
remain in database minor units until converted to currency or normalized hand by hand.
Only positive blind sizes are usable for BB metrics (`-1` is the fixed-limit sentinel);
rates use that valid-hand count and remain unavailable if no usable blind exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SESSION_GAP_SECONDS = 30 * 60
SESSION_PADDING_SECONDS = 5 * 60


@dataclass(frozen=True)
class HandResult:
    hand_id: int
    timestamp: int
    profit_minor: float
    all_in_ev_minor: float
    big_blind_minor: float
    currency: str


@dataclass(frozen=True)
class SessionMetrics:
    number: int
    hands: int
    start_timestamp: int
    end_timestamp: int
    duration_seconds: int
    currency: str
    hand_ids: tuple[int, ...]
    bb_hands: int
    profit_minor: float
    profit_bb: float | None
    bb_per_100: float | None
    all_in_ev_minor: float
    all_in_ev_bb: float | None
    ev_bb_per_100: float | None
    ev_difference_minor: float
    peak_minor: float
    low_minor: float
    max_drawdown_minor: float
    bb_per_hour: float | None
    currency_per_hour: float | None


def _number(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _make_session(number: int, hands: list[HandResult]) -> SessionMetrics:
    profit_minor = sum(hand.profit_minor for hand in hands)
    ev_minor = sum(hand.all_in_ev_minor for hand in hands)
    bb_hands = [hand for hand in hands if hand.big_blind_minor > 0]
    profit_bb = sum(hand.profit_minor / hand.big_blind_minor for hand in bb_hands) if bb_hands else None
    ev_bb = sum(hand.all_in_ev_minor / hand.big_blind_minor for hand in bb_hands) if bb_hands else None
    duration = max(60, hands[-1].timestamp - hands[0].timestamp) + SESSION_PADDING_SECONDS
    hours = duration / 3600
    cumulative_minor = 0.0
    peak_minor = low_minor = max_drawdown_minor = 0.0
    for hand in hands:
        cumulative_minor += hand.profit_minor
        peak_minor = max(peak_minor, cumulative_minor)
        low_minor = min(low_minor, cumulative_minor)
        max_drawdown_minor = max(max_drawdown_minor, peak_minor - cumulative_minor)

    return SessionMetrics(
        number=number,
        hands=len(hands),
        start_timestamp=hands[0].timestamp,
        end_timestamp=hands[-1].timestamp,
        duration_seconds=duration,
        currency=hands[0].currency,
        hand_ids=tuple(hand.hand_id for hand in hands),
        bb_hands=len(bb_hands),
        profit_minor=profit_minor,
        profit_bb=profit_bb,
        bb_per_100=profit_bb / len(bb_hands) * 100 if profit_bb is not None else None,
        all_in_ev_minor=ev_minor,
        all_in_ev_bb=ev_bb,
        ev_bb_per_100=ev_bb / len(bb_hands) * 100 if ev_bb is not None else None,
        ev_difference_minor=ev_minor - profit_minor,
        peak_minor=peak_minor,
        low_minor=low_minor,
        max_drawdown_minor=max_drawdown_minor,
        bb_per_hour=profit_bb / hours if profit_bb is not None and bb_hands and len(bb_hands) == len(hands) else None,
        currency_per_hour=(profit_minor / 100) / hours if hours else 0.0,
    )


def build_sessions(rows: list[tuple[Any, ...]]) -> list[SessionMetrics]:
    """Segment ordered `(hand_id, timestamp, profit, all-in EV, BB, currency)` rows."""
    parsed = [
        HandResult(
            hand_id=int(row[0]),
            timestamp=int(float(row[1])),
            profit_minor=_number(row[2]),
            all_in_ev_minor=_number(row[3]),
            big_blind_minor=_number(row[4]),
            currency=str(row[5] or "UNKNOWN").upper(),
        )
        for row in rows
    ]
    parsed.sort(key=lambda hand: (hand.timestamp, hand.hand_id))
    if not parsed:
        return []

    groups: list[list[HandResult]] = [[parsed[0]]]
    for hand in parsed[1:]:
        previous = groups[-1][-1]
        if hand.timestamp - previous.timestamp > SESSION_GAP_SECONDS or hand.currency != previous.currency:
            groups.append([hand])
        else:
            groups[-1].append(hand)

    sessions: list[SessionMetrics] = []
    for number, group in enumerate(groups, start=1):
        metrics = _make_session(number, group)
        sessions.append(metrics)
    return sessions


def summarize_sessions(sessions: list[SessionMetrics]) -> dict[str, Any]:
    """Aggregate BB-compatible values and only combine native currency when safe."""
    if not sessions:
        return {
            "sessions": 0,
            "hands": 0,
            "bb_hands": 0,
            "duration_seconds": 0,
            "profit_bb": None,
            "bb_per_100": None,
            "bb_per_hour": None,
        }
    hands = sum(session.hands for session in sessions)
    duration = sum(session.duration_seconds for session in sessions)
    bb_hands = sum(session.bb_hands for session in sessions)
    usable_bb_results = [session.profit_bb for session in sessions if session.profit_bb is not None]
    profit_bb = sum(usable_bb_results) if usable_bb_results else None
    all_hands_have_blinds = bb_hands == hands
    currencies = {session.currency for session in sessions}
    summary: dict[str, Any] = {
        "sessions": len(sessions),
        "hands": hands,
        "bb_hands": bb_hands,
        "duration_seconds": duration,
        "profit_bb": profit_bb,
        "bb_per_100": profit_bb / bb_hands * 100 if profit_bb is not None and bb_hands else None,
        "bb_per_hour": profit_bb / (duration / 3600)
        if profit_bb is not None and all_hands_have_blinds and duration
        else None,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
    }
    if summary["currency"] is not None:
        profit_minor = sum(session.profit_minor for session in sessions)
        summary["profit_minor"] = profit_minor
        summary["currency_per_hour"] = (profit_minor / 100) / (duration / 3600) if duration else 0.0
    return summary
