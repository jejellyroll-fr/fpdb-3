#!/usr/bin/env python3
"""Check that fpdb reproduces CoinPoker's own settlement, hand by hand.

Every earlier attempt in this area reconstructed the settlement by residual --
guessing what a player must have received from what changed around them -- and
each of those guesses was wrong in a different way. The capture states the
answer outright, so this reads it instead of deriving it:

    the true pot      last game.potInfo with isRoundEnd
    chips returned    game.return_chips.chipsToReturn
    poker winnings    every winnerInfo winAmountFromPot
    the splash        cumulativeWinnerInfo.splashPotAmount
    who received it   winnersData[].isSplashPotWinner
    the net result    winnersData[].cumulativeProfitLoss

``cumulativeProfitLoss`` is the acceptance criterion, and the stack movement
is its independent control: a hand whose two disagree is a hand this harness
cannot speak for, and is reported rather than silently averaged in.

Usage:
    python -m tools.aof_settlement_check [capture.jsonl]
"""

from __future__ import annotations

import collections
import json
import os
import sys
from decimal import Decimal

CENT = Decimal("0.01")


def _dec(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:  # noqa: BLE001 - a malformed amount is simply absent
        return Decimal(0)


def load(path: str) -> dict[str, list[tuple]]:
    hands: dict[str, list[tuple]] = collections.defaultdict(list)
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            hand_id = record.get("hand_id")
            if hand_id:
                hands[str(hand_id)].append((record.get("event"), record.get("payload")))
    return hands


def stack_moves(events: list[tuple]) -> dict[str, Decimal]:
    """First and last stack seen for each player, as a net movement."""
    first: dict[str, Decimal] = {}
    last: dict[str, Decimal] = {}
    for name, data in events:
        if not isinstance(data, dict):
            continue
        seats = data.get("seatResponseDataList") if name == "game.seatInfo" else None
        rows = seats or ([data] if name == "game.seat" and data.get("userName") else [])
        for row in rows or []:
            player = row.get("userName")
            if not player or row.get("userChips") is None:
                continue
            chips = _dec(row.get("userChips")) + _dec(row.get("betAmout"))
            first.setdefault(player, chips)
            last[player] = chips
    return {p: (last[p] - first[p]).quantize(CENT) for p in last}


def _paid_from_pots(winners: list[dict]) -> dict[str, Decimal]:
    """What each player was paid out of the pots, across every settlement.

    A repeated envelope inside one settlement is the room saying the same
    thing twice; the same amount in a later settlement is another board.
    """
    paid: dict[str, Decimal] = collections.defaultdict(Decimal)
    seen: set[tuple] = set()
    for index, event in enumerate(winners):
        for pot in event.get("winnerDataList") or []:
            for detail in (pot.get("winnerDetails") or {}).get("winnerList") or []:
                player = detail.get("playerName")
                amount = _dec(detail.get("winAmountFromPot"))
                key = (index, pot.get("potId"), player, amount)
                if not player or key in seen:
                    continue
                seen.add(key)
                paid[player] += amount
    return dict(paid)


def settlement(events: list[tuple]) -> dict:
    """The room's own account of the hand, or None when it never settled."""
    cumulative = next(
        (d for n, d in events if n == "game.cumulativeWinnerInfo" and isinstance(d, dict)),
        None,
    )
    winners = [d for n, d in events if n == "game.winnerInfo" and isinstance(d, dict)]
    if cumulative is None or not winners:
        return {}

    paid = _paid_from_pots(winners)

    returned: dict[str, Decimal] = collections.defaultdict(Decimal)
    for name, data in events:
        if name == "game.return_chips" and isinstance(data, dict):
            player = data.get("userName") or data.get("playerName")
            if player:
                returned[player] += _dec(data.get("chipsToReturn"))

    pot_total = Decimal(0)
    for name, data in events:
        if name == "game.potInfo" and isinstance(data, dict) and data.get("isRoundEnd"):
            pot_total = _dec(data.get("totalPotAmount"))

    return {
        "splash": _dec(cumulative.get("splashPotAmount")),
        "pot": pot_total,
        "paid": paid,
        "returned": dict(returned),
        "net": {
            w.get("userName"): _dec(w.get("cumulativeProfitLoss"))
            for w in cumulative.get("winnersData") or []
        },
        "splash_winners": {
            w.get("userName") for w in cumulative.get("winnersData") or [] if w.get("isSplashPotWinner")
        },
    }


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else os.path.expanduser(
        "~/.fpdb/coinpoker-capture/coinpoker-raw-2026-07-27.jsonl",
    )
    hands = load(path)
    complete, incomplete, agree, disagree = 0, [], 0, []
    for hand_id, events in hands.items():
        head = next((d for n, d in events if n == "game.cumulativeWinnerInfo" and isinstance(d, dict)), None)
        if head is None or _dec(head.get("splashPotAmount")) <= 0:
            continue
        account = settlement(events)
        if not account:
            incomplete.append(hand_id)
            continue
        complete += 1
        moved = stack_moves(events)
        for player, net in account["net"].items():
            delta = moved.get(player)
            if delta is not None and abs(delta - net) < CENT:
                agree += 1
            else:
                disagree.append((hand_id, player, net, delta))

    print(f"mains a splash completes   : {complete}")
    print(f"mains sans reglement final : {len(incomplete)}  {incomplete}")
    print("\nCONTROLE  variation de tapis == cumulativeProfitLoss")
    print(f"  concordent : {agree}")
    print(f"  divergent  : {len(disagree)}")
    for hand_id, player, net, delta in disagree[:12]:
        print(f"    {hand_id} {player:18} annonce={net:>7} tapis={delta}")
    return 0 if not disagree else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
