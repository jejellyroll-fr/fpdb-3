"""Non-numeric HUD display entries extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fpdb_3_legacy.stats_context import get_hand_instance
from fpdb_3_legacy.stats_formatting import StatTuple

DisplayTuple = tuple[str, str, str, str, str, str]

GAME_ABBREVIATIONS = {
    "holdem.fl": "H", "studhilo.fl": "E", "omahahi.pl": "P", "27_3draw.fl": "T", "razz.fl": "R",
    "holdem.nl": "N", "omahahilo.fl": "O", "studhi.fl": "S", "27_1draw.nl": "K", "badugi.fl": "B",
    "fivedraw.fl": "F", "fivedraw.pl": "Fp", "fivedraw.nl": "Fn", "27_3draw.pl": "Tp", "27_3draw.nl": "Tn",
    "badugi.pl": "Bp", "badugi.hp": "Bh", "omahahilo.pl": "Op", "omahahilo.nl": "On", "holdem.pl": "Hp", "studhi.nl": "Sn",
}


def blank(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return an empty HUD grid cell."""
    return "", "", "", "", "", "<blank>"


def player_note(stat_dict: Mapping[int, Mapping[str, Any]], player: int | str) -> DisplayTuple:
    """Return the note icon; its color is resolved by the HUD display layer."""
    try:
        for data in stat_dict.values():
            if data.get("screen_name") == player:
                break
        return "📝", "📝", "📝", "📝", "📝", "Player note icon"
    except (AttributeError, KeyError, TypeError, ValueError):
        return "📝", "📝", "📝", "📝", "📝", "Player note icon"


def game_abbr(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return the abbreviation for the current hand's game and limit."""
    hand = get_hand_instance()
    try:
        if hand is None or "gametype" not in hand:
            return "NA", "NA", "game=NA", "game_abbr=NA", "(NA)", "Game abbreviation"
        game_type = hand.gametype
        value = GAME_ABBREVIATIONS.get(f"{game_type['category']}.{game_type['limitType']}", "Unknown")
        return value, value, f"game={value}", f"game_abbr={value}", f"({value})", "Game abbreviation"
    except (KeyError, TypeError, ValueError):
        return "NA", "NA", "game=NA", "game_abbr=NA", "(NA)", "Game abbreviation"


def n(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> StatTuple:
    """Format the number of observed hands, using compact notation for large samples."""
    try:
        hands = stat_dict[player]["n"]
        display = f"{int(hands)}"
        if hands >= 10000:
            thousands = hands / 1000
            remainder = hands % 1000
            decimal = round(float(remainder) / 100.0)
            if decimal == 10:
                thousands += 1
                decimal = 0
            display = f"{int(thousands)}.{decimal}k"
        return hands, display, f"n={int(hands)}", f"n={int(hands)}", f"({int(hands)})", "Number of hands seen"
    except (KeyError, TypeError, ValueError):
        return 0, "0", "n=0", "n=0", "(0)", "Number of hands seen"


def playername(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return the player's full screen name."""
    try:
        name = str(stat_dict[player]["screen_name"])
        return name, name, name, name, name, "Player name"
    except (KeyError, TypeError, ValueError):
        return "", "", "", "", "", "Player name"


def playershort(stat_dict: Mapping[int, Mapping[str, Any]], player: int) -> DisplayTuple:
    """Return the screen name truncated to the historical six-character cell width."""
    try:
        full_name = str(stat_dict[player]["screen_name"])
    except (KeyError, TypeError, ValueError):
        return "", "", "", "", "", "Player Name 1-5"
    short_name = full_name[:5] + "." if len(full_name) > 6 else full_name
    return short_name, short_name, short_name, short_name, full_name, "Player Name 1-5"


def playerprofile(stat_dict: Mapping[int, Mapping[str, Any]] | None, player: int | None) -> DisplayTuple:
    """Return the dynamically classified player profile."""
    try:
        if stat_dict is None or player is None:
            raise TypeError("None parameter")
        from fpdb_3_legacy.PlayerProfiler import classify_player

        profile, icon, _color = classify_player(stat_dict, player)
        return profile, icon, f"p={profile}", f"playerprofile={profile}", profile, "Player Profile"
    except Exception:  # intentional broad catch: the profile is optional display data
        return "unknown", "❓", "p=unknown", "playerprofile=unknown", "unknown", "Player Profile"
