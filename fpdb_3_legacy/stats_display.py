"""Non-numeric HUD display entries extracted from the legacy stat catalogue."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DisplayTuple = tuple[str, str, str, str, str, str]


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
