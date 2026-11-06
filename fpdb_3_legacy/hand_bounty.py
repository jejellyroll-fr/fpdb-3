"""A knockout tournament hand's all-in, priced with the bounty it can win (#447).

In a knockout tournament, busting a player pays their bounty, so an all-in's
value is not only its chip EV. For a heads-up all-in this gives each player:

- the bounty they collect by winning: the opponent's, if winning busts them,
  that is when the opponent has put every chip in, antes and blinds included.
  The pot is a single one (a side pot is refused), so whoever wins it then
  takes all the opponent has left. A split pot busts nobody;
- how it is paid. A regular knockout pays it all in cash. A progressive one
  (PKO) pays half in cash and adds the other half to the winner's own bounty,
  as PokerStars does. PokerStars prints each seat's bounty only in progressive
  knockouts, so a hand that prints them is read as one, whatever its stored
  tournament type says (that flag is only set by an imported elimination);
- the bounty EV: the probability of winning times the cash part. The half added
  to the winner's own bounty is reported apart, since it is only paid when
  someone busts them in turn;
- when the tournament's starting stack is known, the bounty-adjusted chip EV:
  chip EV plus the bounty EV in chips, a chip being worth the prize part of the
  buy-in divided by the starting stack. That is the usual approximation; it
  says nothing of how a chip's worth changes as the field shrinks.

The confrontation itself, and its limits (heads-up, flop games, both hands
shown), are :func:`fpdb_3_legacy.hand_icm.heads_up_allin`'s.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from fpdb_3_legacy.hand_icm import heads_up_allin

__all__ = ["AllInBounty", "BountyRules", "HandBounty", "bounty_for_replay", "hand_allin_bounty"]

_HALF = Decimal("0.5")


@dataclass(frozen=True)
class BountyRules:
    """What a tournament pays for a knockout, in money."""

    bounty: Decimal | None = None  # the bounty on each head when it does not grow (regular knockout)
    progressive: bool = False  # half the bounty paid in cash, half added to the winner's own
    chip_value: Decimal | None = None  # money per chip: the prize part of the buy-in over the starting stack
    currency: str | None = None  # the buy-in's currency, which the bounties are paid in


@dataclass(frozen=True)
class AllInBounty:
    """The two players of a knockout all-in, the bounty each can win, and its EV."""

    players: tuple[str, str]
    win: Mapping[str, float]  # the probability of winning the whole pot
    collects: Mapping[str, Decimal]  # money: the bounty won by winning (0 when it busts nobody)
    cash: Mapping[str, Decimal]  # money: the part of it paid now
    bounty_ev: Mapping[str, Decimal]  # money: win x cash
    head_ev: Mapping[str, Decimal]  # money: win x the part added to the winner's own bounty
    chip_ev: Mapping[str, Decimal]  # chips
    adjusted_chip_ev: Mapping[str, Decimal] | None = None  # chips: chip EV plus the bounty EV in chips
    currency: str | None = None  # the bounties' currency


@dataclass(frozen=True)
class HandBounty:
    """A hand's bounty pricing, or why there is none."""

    allin: AllInBounty | None
    reason: str = ""


def _money(value: Any) -> Decimal | None:
    """A seat's bounty as the hand holds it ("3.41", 3.41, "None", None)."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value).strip().lstrip("$€£₹").replace(",", ""))
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def hand_allin_bounty(
    hand: Any,
    rules: BountyRules,
    *,
    equity_fn: Callable[..., Any] | None = None,
) -> HandBounty:
    """Price ``hand``'s heads-up all-in with the bounties at stake under ``rules``."""
    if hand.gametype.get("type") != "tour":
        return HandBounty(None, "not a tournament hand")
    allin, unpriced = heads_up_allin(hand, equity_fn)
    if allin is None:
        return HandBounty(None, unpriced)
    seat_bounty = {player[1]: _money(player[4] if len(player) > 4 else None) for player in hand.players}
    progressive = rules.progressive or any(amount is not None for amount in seat_bounty.values())
    a, b = allin.players
    win = {a: allin.win[0], b: allin.win[1]}
    collects: dict[str, Decimal] = {}
    for player, opponent in ((a, b), (b, a)):
        # Codex (#633): coverage is what the opponent put in, forced bets included, not the
        # starting stacks: a 3,000 stack posting a 200 ante is busted by a 2,800 one.
        busts = allin.committed[opponent] >= allin.start[opponent]
        if not busts:
            collects[player] = Decimal(0)
            continue
        bounty = seat_bounty.get(opponent) or (None if progressive else rules.bounty)
        if bounty is None:
            return HandBounty(None, "the bounty in play is not in the hand history")
        collects[player] = bounty
    cash = {name: amount * _HALF if progressive else amount for name, amount in collects.items()}
    bounty_ev = {name: Decimal(str(win[name])) * cash[name] for name in cash}
    head_ev = {name: Decimal(str(win[name])) * (collects[name] - cash[name]) for name in cash}
    chip_ev = allin.chip_ev
    adjusted = None
    if rules.chip_value:
        adjusted = {name: chip_ev[name] + bounty_ev[name] / rules.chip_value for name in chip_ev}
    return HandBounty(
        AllInBounty(
            players=allin.players,
            win=win,
            collects=collects,
            cash=cash,
            bounty_ev=bounty_ev,
            head_ev=head_ev,
            chip_ev=chip_ev,
            adjusted_chip_ev=adjusted,
            currency=rules.currency,
        )
    )


def _stored_rules(db: Any, hand_id: int) -> BountyRules | None:
    """The knockout rules of the tournament ``hand_id`` was played in; None when it is not a knockout."""
    cursor = db.get_cursor()
    cursor.execute(db.sql.query["selectHandKnockoutRules"], (hand_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    knockout, ko_bounty, progressive, buy_in, buy_in_chips, currency = row
    bounty = Decimal(int(ko_bounty)) / 100 if ko_bounty else None
    if not knockout and bounty is None:
        return None
    chip_value = None
    if buy_in and buy_in_chips:
        prize = Decimal(int(buy_in)) / 100 - (bounty or 0)
        if prize > 0:
            chip_value = prize / Decimal(int(buy_in_chips))
    return BountyRules(bounty=bounty, progressive=bool(progressive), chip_value=chip_value, currency=currency)


def bounty_for_replay(db: Any, hand: Any, hand_id: int | None) -> HandBounty:
    """What the replayer shows: a stored hand's tournament rules looked up, else the parsed hand's own."""
    if hand.gametype.get("type") != "tour":
        return HandBounty(None, "not a tournament hand")
    if hand_id is not None and db is not None:
        rules = _stored_rules(db, hand_id)
    elif getattr(hand, "koBounty", 0):
        rules = BountyRules(
            bounty=Decimal(int(hand.koBounty)) / 100,
            progressive=bool(getattr(hand, "isProgressive", False)),
            currency=getattr(hand, "buyinCurrency", None),
        )
    else:
        rules = None
    if rules is None:
        return HandBounty(None, "not a knockout tournament")
    return hand_allin_bounty(hand, rules)
