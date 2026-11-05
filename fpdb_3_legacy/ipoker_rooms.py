"""Which room an iPoker hand belongs to when its file does not say (#702).

Every iPoker skin writes the same files. Neither PokerTracker's ``GAME #`` text
nor the room's XML names the skin, and table names are shared across skins, so
the only thing that tells rooms apart is who was playing: a hero is the screen
name of the account they played on, and the configuration says which room that
account belongs to.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = ["GENERIC_ROOM", "is_room", "room_choices", "room_for", "skins_of"]

NETWORK = "iPoker"
# Where a hand goes when nothing tells which skin it was played on.
GENERIC_ROOM = "iPoker"


def skins_of(config: Any) -> list[Any]:
    """Every room the configuration puts on the iPoker network."""
    supported = getattr(config, "supported_sites", None) or {}
    return [site for site in supported.values() if getattr(site, "network", "") == NETWORK]


def _account_names(site: Any) -> set[str]:
    names = getattr(site, "hero_aliases", None) or [getattr(site, "screen_name", "")]
    return {str(name).casefold() for name in names if name}


def is_room(config: Any, name: Any) -> bool:
    """True if the configuration declares ``name`` as a room of the iPoker network."""
    supported = getattr(config, "supported_sites", None) or {}
    return getattr(supported.get(name), "network", "") == NETWORK


def room_for(config: Any, names: Iterable[str], chosen: Mapping[str, str] | None = None) -> str | None:
    """The room of a file naming these players, or None when nothing settles it.

    In order: the room the user chose for one of the names; the one skin that has
    one of them as an account, an enabled skin before a disabled one; the one skin
    enabled. Names pointing at several rooms settle nothing, since any of them could
    be right, so they are not resolved by a later rule either.
    """
    wanted = {name for name in names if name}
    answers = {chosen[name] for name in wanted if name in chosen} if chosen else set()
    if answers:
        return answers.pop() if len(answers) == 1 else None
    folded = {name.casefold() for name in wanted}
    skins = skins_of(config)
    enabled = [site for site in skins if getattr(site, "enabled", False)]
    for pool in (enabled, skins):
        holding = [site for site in pool if _account_names(site) & folded]
        if holding:
            return holding[0].site_name if len(holding) == 1 else None
    return enabled[0].site_name if len(enabled) == 1 else None


def room_choices(config: Any) -> list[str]:
    """The rooms to offer the user: the enabled ones first, each group by name."""
    skins = skins_of(config)
    return sorted(
        (site.site_name for site in skins),
        key=lambda name: (not config.supported_sites[name].enabled, name.casefold()),
    )
