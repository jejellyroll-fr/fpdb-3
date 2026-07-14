"""Preflop frequency statistics extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_formatting import StatTuple, format_no_data_stat
from fpdb_3_legacy.stats_postflop import postflop_ratio


def face_limpers(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the average number of limpers faced before acting preflop."""
    try:
        hands = float(stat_dict[player].get("n", 0))
        total = float(stat_dict[player].get("face_limpers", 0))
        if hands == 0:
            return format_no_data_stat("FLmp", "avg limpers faced preflop")
        stat = total / hands
        return (
            stat,
            f"{stat:3.1f}",
            f"FLmp={stat:3.1f}",
            f"FLmp={stat:3.1f}",
            f"({int(total)}/{int(hands)})",
            "avg limpers faced preflop",
        )
    except (KeyError, TypeError, ValueError):
        return format_no_data_stat("FLmp", "avg limpers faced preflop")


def straddle(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of voluntarily posting a straddle."""
    return postflop_ratio(stat_dict, player, "n", "straddle_done", "Str", "% straddle")


def gp_2x(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of opening for less than 40 percent of the stack."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_2x", "2X", "% open-raise (<40% stack)")


def gp_os(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of open-shoving at least 40 percent of the stack."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_os", "OS", "% open-shove (>=40% stack)")


def gp_limp(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of open-limping."""
    return postflop_ratio(stat_dict, player, "gp_open_opp", "gp_limp", "Limp", "% open-limp")


def fold_to_allin(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return the frequency of folding when facing an all-in."""
    return postflop_ratio(stat_dict, player, "faced_allin", "fold_allin", "FvAI", "% fold to all-in")
