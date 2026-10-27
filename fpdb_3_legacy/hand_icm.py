"""A tournament hand's all-in priced in prize equity, next to its chip EV (#446).

Chip EV tells what an all-in was worth in chips; in a tournament the chips are
not the money. This module takes one parsed tournament hand, finds its all-in
confrontation, and gives each of the two players:

- their equity when the money went in (the board known at that street);
- chip EV: that equity's share of the pot, less what they put in -- as the
  import's ``allInEV`` computes it;
- ICM $EV: the prize equity expected after the hand, less the prize equity the
  stacks held when it began (``icm.allin_icm_ev``);
- ICM result: the prize equity the hand actually moved, so $EV and result read
  like chip EV and winnings.

Limits, said rather than guessed at:

- heads-up only: a multiway all-in, or a side pot one of the two cannot win
  (a short stack all-in, then a deeper player folding), has more outcomes
  than this prices yet;
- flop games with one winner per pot: stud and draw are outside the equity
  engine, and a hi/lo split is not a scoop each half of the time;
- both hands shown;
- every remaining player's stack: the players at the table must be the whole
  field. A single-table tournament is; a field larger than the table is
  refused; an unknown field is computed and flagged ``table_only``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fpdb_3_legacy import icm
from fpdb_3_legacy.icm import AllInOutcome, ICMError

__all__ = ["AllInIcm", "HandIcm", "hand_allin_icm", "icm_for_replay", "icm_with_payouts"]

# Monte Carlo samples when the engine does not enumerate; as the replayer's own equity.
_ITERATIONS = 20_000


@dataclass(frozen=True)
class AllInIcm:
    """The two players of a hand's all-in, their equity, chip EV and ICM $EV."""

    street: str
    players: tuple[str, str]
    equity: Mapping[str, float]
    chip_ev: Mapping[str, Decimal]  # chips
    icm_ev: Mapping[str, float]  # in the payout's unit
    icm_result: Mapping[str, float]  # in the payout's unit: what the hand actually moved
    table_only: bool = False  # the field is unknown: priced as if this table were all of it


@dataclass(frozen=True)
class HandIcm:
    """A hand's ICM pricing, or why there is none."""

    allin: AllInIcm | None
    reason: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


def _known(cards: Sequence[str]) -> bool:
    return bool(cards) and all(len(str(card)) == 2 and str(card)[0] != "0" for card in cards)


def _hole_cards(hand: Any, player: str) -> list[str]:
    """The player's cards as last known in the hand (draw games keep the final ones)."""
    known: list[str] = []
    for street in getattr(hand, "holeStreets", None) or list(hand.holecards):
        entry = hand.holecards.get(street, {}).get(player)
        if entry:
            cards = list(entry[-1]) if isinstance(entry[0], list) else list(entry)
            if cards:
                known = cards
    return known


def _allin_street(hand: Any) -> str | None:
    """The last street on which someone went all-in: where the money was in."""
    found = None
    for street in hand.actionStreets:
        for action in hand.actions.get(street, []):
            if isinstance(action, (list, tuple)) and len(action) > 2 and action[-1] is True:
                found = street
    return found


def _board_until(hand: Any, street: str) -> list[str]:
    board: list[str] = []
    for name in hand.actionStreets:
        board.extend(hand.board.get(name, []) or [])
        if name == street:
            break
    return board


def _game(hand: Any) -> tuple[str | None, str]:
    """The equity engine's name for the hand's game, or None with why it is not priced."""
    from fpdb_3_legacy import Card
    from fpdb_3_legacy.equity import COMMUNITY_CARD_GAMES

    category = hand.gametype.get("category", "")
    info = Card.games.get(category)
    if not info or info[0] != "hold" or info[1] not in COMMUNITY_CARD_GAMES:
        # 5-card stud borrows hold'em's evaluator, but its cards are not a flop game's.
        return None, "only flop games are priced"
    if info[2] == "s":
        # Codex (#628): hi and lo wins overlap; a certain split is not two half-scoops.
        return None, "hi/lo split pots are not priced yet"
    return info[1], ""


def _side_pot(contenders: Sequence[str], committed: Mapping[str, Decimal]) -> bool:
    """Whether some chips in the pot are out of one contender's reach.

    Codex (#628): a short stack all-in, then a deeper player folding, leaves
    two contenders and a side pot only the deeper one can win.
    """
    return any(sum(max(Decimal(0), put - committed[name]) for put in committed.values()) > 0 for name in contenders)


def _contenders(hand: Any) -> tuple[list[str], str]:
    """The two players still in, sharing a single pot; or none, with why."""
    folded = {
        action[0]
        for actions in hand.actions.values()
        for action in actions
        if isinstance(action, (list, tuple)) and len(action) > 1 and action[1] == "folds"
    }
    seated = [player[1] for player in hand.players]
    contenders = [name for name in seated if name not in folded]
    if len(contenders) != 2:
        return [], "multiway all-in: ICM $EV is priced heads-up only"
    if _side_pot(contenders, {name: Decimal(hand.pot.committed.get(name, 0)) for name in seated}):
        return [], "side pot: ICM $EV is priced for a single pot only"
    return contenders, ""


def hand_allin_icm(
    hand: Any,
    payouts: Sequence[float],
    *,
    table_only: bool = False,
    equity_fn: Callable[..., Any] | None = None,
) -> HandIcm:
    """Price ``hand``'s heads-up all-in under ICM with ``payouts`` (first place first, money)."""
    if hand.gametype.get("type") != "tour":
        return HandIcm(None, "not a tournament hand")
    game, unpriced = _game(hand)
    if game is None:
        return HandIcm(None, unpriced)
    street = _allin_street(hand)
    if street is None:
        return HandIcm(None, "no all-in in this hand")
    contenders, unpriced = _contenders(hand)
    if not contenders:
        return HandIcm(None, unpriced)
    seated = [player[1] for player in hand.players]
    committed = {
        name: Decimal(hand.pot.committed.get(name, 0)) + Decimal(hand.pot.common.get(name, 0)) for name in seated
    }
    pockets = [_hole_cards(hand, name) for name in contenders]
    if not all(_known(cards) for cards in pockets):
        return HandIcm(None, "both hands must be shown to price the all-in")

    if equity_fn is None:
        from fpdb_3_legacy.equity import calculate_equity

        equity_fn = calculate_equity
    try:
        result = equity_fn(game, pockets, _board_until(hand, street), iterations=_ITERATIONS)
    except (RuntimeError, ValueError) as exc:
        return HandIcm(None, f"equity unavailable: {exc}")

    start = {player[1]: Decimal(str(player[2])) for player in hand.players}
    pot = Decimal(hand.totalpot)
    a, b = contenders
    samples = result.samples or 1
    win_a, win_b, tie = (
        result.players[0].wins / samples,
        result.players[1].wins / samples,
        result.players[0].ties / samples,
    )
    total = win_a + win_b + tie or 1.0
    win_a, win_b, tie = win_a / total, win_b / total, tie / total

    def after(share_a: Decimal, share_b: Decimal) -> dict[str, float]:
        stacks = {name: float(start[name] - committed[name]) for name in seated}
        stacks[a] += float(share_a)
        stacks[b] += float(share_b)
        return stacks

    outcomes = [
        outcome
        for outcome in (
            AllInOutcome(win_a, after(pot, Decimal(0))),
            AllInOutcome(win_b, after(Decimal(0), pot)),
            AllInOutcome(tie, after(pot / 2, pot / 2)),
        )
        if outcome.probability > 0
    ]
    before = {name: float(start[name]) for name in seated}
    actual = {name: float(start[name] - committed[name] + Decimal(hand.collectees.get(name, 0))) for name in seated}
    try:
        icm_ev = {name: icm.allin_icm_ev(before, outcomes, payouts, name) for name in contenders}
        now = dict(zip(seated, icm.icm_equities([before[n] for n in seated], payouts), strict=True))
        settled = icm.outcome_equities(before, actual, payouts)
    except ICMError as exc:
        return HandIcm(None, f"ICM not computed: {exc}")

    equity = {a: win_a + tie / 2, b: win_b + tie / 2}
    chip_ev = {name: Decimal(str(equity[name])) * pot - committed[name] for name in contenders}
    notes = ("priced as if this table were the whole field",) if table_only else ()
    return HandIcm(
        AllInIcm(
            street=street,
            players=(a, b),
            equity=equity,
            chip_ev=chip_ev,
            icm_ev=icm_ev,
            icm_result={name: settled[name] - now[name] for name in contenders},
            table_only=table_only,
        ),
        notes=notes,
    )


def icm_for_replay(db: Any, hand: Any, hand_id: int | None) -> HandIcm:
    """What the replayer shows for a stored hand: its payout structure looked up, then priced."""
    from fpdb_3_legacy import tourney_payouts

    if hand.gametype.get("type") != "tour":
        return HandIcm(None, "not a tournament hand")
    if hand_id is None or db is None:
        return HandIcm(None, "the hand is not stored: its tournament's payouts are unknown")
    lookup = tourney_payouts.payouts_for_hand(db, hand_id)
    if lookup.payouts is None:
        return HandIcm(None, lookup.reason)
    return icm_with_payouts(hand, lookup.payouts.as_money(), tourney_payouts.field_size_for_hand(db, hand_id))


def icm_with_payouts(
    hand: Any,
    payouts: Sequence[float],
    field_size: int | None,
    *,
    equity_fn: Callable[..., Any] | None = None,
) -> HandIcm:
    """Price ``hand`` with its tournament's ``payouts`` (money) once the field is known to fit the table."""
    max_seats = int(getattr(hand, "maxseats", 0) or 0)
    if field_size is not None and max_seats and field_size > max_seats:
        return HandIcm(None, "multi-table tournament: the other tables' stacks are unknown")
    return hand_allin_icm(hand, payouts, table_only=field_size is None, equity_fn=equity_fn)
