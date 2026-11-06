"""Knockout HUD statistics: a player's bounty, and who covers whom (#447).

Both read the last imported hand, like the stack statistics of
:mod:`fpdb_3_legacy.stats_tournament`:

- ``bounty``: the bounty on the player's head after that hand. A progressive
  knockout raises the winner's bounty when they bust someone; the hand records
  it (``Hand.endBounty``, in hundredths). Otherwise it is the bounty the seat
  line printed. A regular knockout prints none (every head is worth the same),
  and the statistic then shows no value.
- ``covers``: whether the hero covers the player, so that winning an all-in
  against them busts them and collects their bounty, or the player covers the
  hero. It compares the two end-of-hand stacks, and says nothing on the hero's
  own label.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.stats_context import get_hand_instance
from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat
from fpdb_3_legacy.stats_tournament import calculate_end_stack

__all__ = ["bounty", "covers"]


def _seat_bounty(hand: Any, name: str) -> Decimal | None:
    for player in hand.players:
        if player[1] == name and len(player) > 4 and player[4] not in (None, "", "None"):
            try:
                amount = Decimal(str(player[4]).lstrip("$€£₹").replace(",", ""))
            except InvalidOperation:
                return None
            return amount if amount > 0 else None
    return None


def _current_bounty(hand: Any, name: str) -> Decimal | None:
    raised = (getattr(hand, "endBounty", None) or {}).get(name)
    if raised:
        return Decimal(str(raised)) / 100
    return _seat_bounty(hand, name)


def bounty(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the bounty on the player's head after the last hand."""
    hand = get_hand_instance()
    name = (stat_dict or {}).get(player, {}).get("screen_name")
    amount = _current_bounty(hand, name) if hand and name else None
    if amount is None:
        return format_no_data_stat("bounty", "bounty (last hand)")
    currency = getattr(hand, "buyinCurrency", None)
    text = format_currency(amount, currency) if currency else format_number(amount, 2)
    return float(amount), text, f"bounty={text}", f"bounty={text}", f"({text})", "bounty (last hand)"


def _end_stack(hand: Any, name: str) -> float | None:
    if not any(item[1] == name for item in hand.players):
        return None
    return calculate_end_stack({0: {"screen_name": name}}, 0, hand)


def covers(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return whether the hero covers the player (1), the player covers the hero (-1), or neither (0)."""
    hand = get_hand_instance()
    name = (stat_dict or {}).get(player, {}).get("screen_name")
    hero = getattr(hand, "hero", "") if hand else ""
    if not hand or not name or not hero or name == hero:
        return format_no_data_stat("covers", "who covers whom (last hand)")
    theirs, yours = _end_stack(hand, name), _end_stack(hand, hero)
    if theirs is None or yours is None or theirs <= 0 or yours <= 0:
        return format_no_data_stat("covers", "who covers whom (last hand)")
    if yours > theirs:
        value, text = 1, "you cover"
    elif theirs > yours:
        value, text = -1, "covers you"
    else:
        value, text = 0, "even"
    return value, text, f"covers={text}", f"covers={text}", f"({text})", "who covers whom (last hand)"
