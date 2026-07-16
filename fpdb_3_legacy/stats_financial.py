"""Financial and win-rate statistics extracted from the legacy catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.localized_formats import format_currency
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.stats_formatting import StatTuple

log = get_logger("stats")


def totalprofit(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return total profit from the cent-denominated net counter."""
    try:
        display_value = float(stat_dict[player]["net"]) / 100
        currency = str(stat_dict[player].get("currency", "USD"))
        display = format_currency(display_value, currency)
        return display_value / 100.0, display, f"tp={display}", f"tot_prof={display}", str(display_value), "Total Profit"
    except (KeyError, TypeError, ValueError):
        display = format_currency(0, "USD")
        return "0", display, "tp=0", "totalprofit=0", "0", "Total Profit"


def profit100(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return profit per 100 hands, with money stored in cents."""
    stat = 0.0
    try:
        if player not in stat_dict:
            return stat, "NA", "p=NA", "p/100=NA", "(0/0)", "Profit per 100 hands"
        hands = float(stat_dict[player].get("n", 0))
        if hands != 0:
            stat = float(stat_dict[player]["net"]) / hands
        return stat / 100.0, f"{stat:.2f}", f"p={stat:.2f}", f"p/100={stat:.2f}", f"{int(stat_dict[player]['net'])}/{int(hands)}", "Profit per 100 hands"
    except (KeyError, TypeError, ValueError):
        if stat_dict:
            log.exception(f"exception calculating profit100: player {player} not found in stat_dict or missing data")
        return stat, "NA", "p=NA", "p/100=NA", "(0/0)", "Profit per 100 hands"


def bbper100(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return big blinds won per 100 hands."""
    stat = 0.0
    try:
        bigblind = float(stat_dict[player].get("bigblind", 0))
        if bigblind != 0:
            stat = 100.0 * float(stat_dict[player]["net"]) / bigblind
        return stat / 100.0, f"{stat:5.3f}", f"bb100={stat:5.3f}", f"bb100={stat:5.3f}", f"({int(100 * stat_dict[player]['net'])},{int(bigblind)})", "Big blinds won per 100 hands"
    except (KeyError, TypeError, ValueError):
        if stat_dict and player in stat_dict:
            log.info(f"exception calculating bbper100: {stat_dict[player].get('net', 'N/A')} / {stat_dict[player].get('bigblind', 'N/A')}")
        return stat, "NA", "bb100=NA", "bb100=NA", "(--)", "Big blinds won per 100 hands"


def BBper100(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Return big bets won per 100 hands."""
    stat = 0.0
    try:
        bigblind = float(stat_dict[player].get("bigblind", 0))
        if bigblind != 0:
            stat = 50 * float(stat_dict[player]["net"]) / bigblind
        return stat / 100.0, f"{stat:5.3f}", f"BB100={stat:5.3f}", f"BB100={stat:5.3f}", f"({int(100 * stat_dict[player]['net'])},{int(2 * bigblind)})", "Big bets won per 100 hands"
    except (KeyError, TypeError, ValueError):
        if stat_dict:
            log.info(f"exception calculating BBper100: {stat_dict[player]}")
        return stat, "NA", "BB100=NA", "BB100=NA", "(--)", "Big bets won per 100 hands"
