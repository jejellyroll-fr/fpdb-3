"""Tournament stack statistics extracted from the legacy catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_context import get_hand_instance
from fpdb_3_legacy.stats_formatting import StatTuple


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
