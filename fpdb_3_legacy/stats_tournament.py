"""Tournament stack statistics extracted from the legacy catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.localized_formats import format_currency, format_number
from fpdb_3_legacy.stats_context import get_hand_instance
from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat

# Currencies that are chips rather than money: no symbol, no cents.
_CHIP_CURRENCIES = frozenset({"T$", "PLAY"})
_COMPACT_CHIPS_FROM = 10_000
# Float noise left by summing bets, below any real fraction of a chip.
_FRACTION_NOISE = 0.005


def calculate_end_stack(stat_dict: Mapping[int, Mapping[str, Any]], player: int, hand: Any) -> float:
    """Reconstruct a player's end-of-hand stack from hand actions."""
    name = stat_dict[player]["screen_name"]
    stack = 0.0
    for item in hand.players:
        if item[1] == name:
            stack = float(item[2])
    for street in hand.bets:
        for actor in hand.bets[street]:
            if actor == name:
                for amount in hand.bets[street][name]:
                    stack -= float(amount)
    for actor in hand.pot.returned:
        if actor == name:
            stack += float(hand.pot.returned[actor])
    for actor in hand.collectees:
        if actor == name:
            stack += float(hand.collectees[actor])
    # A room-funded splash reaches the stack too. Hand-history converters seed
    # it into the pot (pot.stp) and it comes back through the collections;
    # live-capture builders pay it beside the pot, in splashWinnings only.
    # Same rule as DerivedStats' stored profit, so it is never counted twice.
    if not float(getattr(hand.pot, "stp", 0) or 0):
        stack += float((getattr(hand, "splashWinnings", None) or {}).get(name, 0))
    return stack


def m_ratio(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return tournament M-ratio from the reconstructed end stack."""
    stat = 0.0
    compulsory_bets = 0.0
    hand = get_hand_instance()
    if not hand:
        return stat / 100.0, "0", "M=0", "M=0", "(0)", "M ratio"
    for actor in hand.bets["BLINDSANTES"]:
        for amount in hand.bets["BLINDSANTES"][actor]:
            compulsory_bets += float(amount)
    compulsory_bets += float(hand.gametype.get("sb", 0))
    compulsory_bets += float(hand.gametype.get("bb", 0))
    stack = calculate_end_stack(stat_dict, player, hand)
    if compulsory_bets != 0:
        stat = stack / compulsory_bets
    value = int(stat)
    return value, f"{value}", f"M={value}", f"M={value}", f"({value})", "M ratio"


def bbstack(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return reconstructed tournament stack size in big blinds."""
    stat = 0.0
    hand = get_hand_instance()
    if not hand:
        return stat, "NA", "v=NA", "vpip=NA", "(0/0)", "bb stack"
    bigblind = float(hand.gametype.get("bb", 0))
    stack = calculate_end_stack(stat_dict, player, hand)
    stat = stack / bigblind if bigblind != 0 else 0
    value = int(stat)
    return stat / 100.0, f"{value}", f"bb's={value}", f"#bb's={value}", f"({value})", "bb stack"


# -- stack in the hand's own unit (#402) ----------------------------------------
#
# Every form below reads the one reconstructed stack ``bbstack`` reads: the
# player's stack at the end of the last imported hand, rebuilt from that hand's
# starting stacks, bets, returned bets and collections. None of them is a live
# table stack, and none recomputes it another way.


def _reconstructed_stack(stat_dict: Mapping[int, Mapping[str, Any]], player: int, hand: Any) -> float | None:
    """The end-of-hand stack ``bbstack`` uses, or None when it cannot be known."""
    name = stat_dict.get(player, {}).get("screen_name")
    if not name or not any(item[1] == name for item in hand.players):
        return None
    return calculate_end_stack(stat_dict, player, hand)


def _plays_for_chips(hand: Any) -> bool:
    gametype = hand.gametype
    return gametype.get("type") == "tour" or str(gametype.get("currency", "")).upper() in _CHIP_CURRENCIES


def _big_blind(hand: Any) -> float:
    try:
        return float(hand.gametype.get("bb", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _stack_amount_text(stack: float, hand: Any, *, compact: bool = False) -> str:
    """The stack in the hand's unit: localized money, or plain chips."""
    if not _plays_for_chips(hand):
        return format_currency(stack, str(hand.gametype.get("currency", "USD")))
    if compact and abs(stack) >= _COMPACT_CHIPS_FROM:
        return f"{format_number(stack / 1000, 1, grouping=False)}k"
    # Chips are usually whole, but some rooms (BetOnline) keep fractions.
    whole = abs(stack - round(stack)) < _FRACTION_NOISE
    return format_number(stack, 0 if whole else 2)


def _stack_bb_text(stack: float, bigblind: float) -> str:
    return f"{format_number(stack / bigblind, 1, grouping=False)}bb"


def stack_amount(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the reconstructed stack in money or chips, as the table shows it."""
    hand = get_hand_instance()
    stack = _reconstructed_stack(stat_dict, player, hand) if hand else None
    if stack is None:
        return format_no_data_stat("stack", "stack (last hand)")
    text = _stack_amount_text(stack, hand)
    return stack, text, f"stack={text}", f"stack={text}", f"({text})", "stack (last hand)"


def stack_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the reconstructed stack in big blinds, to one decimal."""
    hand = get_hand_instance()
    stack = _reconstructed_stack(stat_dict, player, hand) if hand else None
    bigblind = _big_blind(hand) if hand else 0.0
    if stack is None or bigblind <= 0:
        return format_no_data_stat("stack_bb", "stack in bb (last hand)")
    text = _stack_bb_text(stack, bigblind)
    return stack / bigblind, text, f"stack={text}", f"stack={text}", f"({text})", "stack in bb (last hand)"


def stack_native_bb(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the stack in its own unit and in big blinds, e.g. ``€42.75 / 42.8bb``."""
    hand = get_hand_instance()
    stack = _reconstructed_stack(stat_dict, player, hand) if hand else None
    bigblind = _big_blind(hand) if hand else 0.0
    if stack is None:
        return format_no_data_stat("stack", "stack and bb stack (last hand)")
    text = _stack_amount_text(stack, hand, compact=True)
    if bigblind > 0:
        text = f"{text} / {_stack_bb_text(stack, bigblind)}"
    return stack, text, f"stack={text}", f"stack={text}", f"({text})", "stack and bb stack (last hand)"
