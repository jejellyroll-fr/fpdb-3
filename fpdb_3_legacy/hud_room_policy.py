"""What each poker room lets the HUD do at its tables (#756).

The HUD can do four things that rooms rule on separately:

* a **static** HUD: a player's historical statistics, the same whatever the
  hand being played;
* a **positional** HUD: panels bound to a position, shown or hidden as the
  seat's position changes from one hand to the next;
* **dynamic** panels (#298): which statistics show changes with the hand being
  played -- preflop panels preflop, c-bet panels when a c-bet is made;
* **live context** (#336): using what is happening in the current hand, from a
  live source, to pick those panels.

This module is the policy only: what a room *permits*. Whether a source can
*deliver* the current hand is the source's business -- no action-by-action
source is wired in since CoinPoker's capture, the only one, was removed (#732)
-- and whether the user said yes to dynamic panels is
:mod:`fpdb_3_legacy.dynamic_panels_consent`'s. A yes never overrides a room.

Rooms are identified by network, not by site name: an iPoker skin reaches the
HUD under its own name (``Betclic Poker``, ``PMU Poker``, ``Unibet Poker``...),
and a regional PokerStars site under ``PokerStars.FR`` and the like. A room
nobody has reviewed gets :data:`CONSERVATIVE`: the static HUD, nothing that
changes with the hand. Today no room has been reviewed as allowing more, so
every live table gets the static HUD; a room is added to
:data:`ROOM_POLICIES` with its capabilities once its rules have been read and,
where they are unclear, confirmed by the room itself.

Nothing in the configuration can loosen this: ``HUD_config.xml``'s ``network``
attribute can only make a site *more* restricted, never less.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Final, Literal

Capability = Literal["static_hud", "positional_hud", "dynamic_hud", "live_context"]


@dataclass(frozen=True)
class HudCapabilities:
    """What a room permits the HUD to do at its tables."""

    static_hud: bool
    positional_hud: bool
    dynamic_hud: bool
    #: The room permits using the current hand's context from a live source.
    live_context: bool

    def __post_init__(self) -> None:
        # Each step changes more with the hand than the one before: dynamic
        # panels pick position panels too, and live context only feeds them.
        if self.dynamic_hud and not self.positional_hud:
            raise ValueError("a room that allows dynamic panels must allow a positional HUD")
        if self.live_context and not self.dynamic_hud:
            raise ValueError("live context is only used by dynamic panels")

    def __and__(self, other: HudCapabilities) -> HudCapabilities:
        """The capabilities both allow: the stricter of two policies."""
        return HudCapabilities(**{f.name: getattr(self, f.name) and getattr(other, f.name) for f in fields(self)})


#: Every capability: offline use, where no room's rules apply.
UNRESTRICTED: Final = HudCapabilities(static_hud=True, positional_hud=True, dynamic_hud=True, live_context=True)

#: A room whose rules were not reviewed, or that forbids anything changing
#: with the hand: the static HUD only.
CONSERVATIVE: Final = HudCapabilities(static_hud=True, positional_hud=False, dynamic_hud=False, live_context=False)


@dataclass(frozen=True)
class RoomPolicy:
    """A network's reviewed policy, and why it is what it is."""

    network: str
    capabilities: HudCapabilities
    #: Said to the user (and logged) when a capability is refused.
    reason: str
    #: The room allows HUD statistics only from hands the user played (#719):
    #: a hand imported without the hero at the table does not feed the HUD.
    hero_hands_only: bool = False


#: The networks whose rules were read. Keyed by network, casefolded.
ROOM_POLICIES: dict[str, RoomPolicy] = {
    "pokerstars": RoomPolicy(
        "PokerStars",
        CONSERVATIVE,
        "PokerStars forbids in-game statistics that change automatically with the game state",
    ),
    "winamax": RoomPolicy(
        "Winamax",
        CONSERVATIVE,
        "Winamax prohibits dynamic range software and certain dynamic HUD features; "
        "fpdb keeps them off until its integrity team approves them",
    ),
    "ipoker": RoomPolicy(
        "iPoker",
        CONSERVATIVE,
        "positional and dynamic HUDs are documented as not allowed on the iPoker network",
    ),
    # ACR Poker's Security & Game Integrity Policies (read 2026-11-06), §4.1.3:
    # numeric HUD statistics only from hands the player took part in, and
    # nothing from the hand in play (#719).
    "wpn": RoomPolicy(
        "WPN",
        CONSERVATIVE,
        "ACR/WPN allows HUD statistics only from your own completed hands, "
        "with nothing from the hand in play (ACR security policy, section 4.1.3)",
        hero_hands_only=True,
    ),
}

#: Site names of the Winning Poker Network: every ``'WP'`` row of the Sites
#: table (``database_schema``) and the names its clients go by.
WPN_SKINS: Final = frozenset(
    name.casefold()
    for name in (
        "WinningPoker",
        "Winning Poker",
        "Americas Cardroom",
        "ACR Poker",
        "ACR",
        "BlackChipPoker",
        "BlackChip Poker",
        "TruePoker",
        "True Poker",
        "Ya Poker",
        "WPN",
    )
)

#: The Sites ids of those skins, for the SQL that rebuilds the HUD cache.
WPN_SITE_IDS: Final = (24, 115, 116, 117, 118, 119)

#: Appended to the HUD cache rebuild's WHERE clause: a hand of a room that
#: allows statistics from the user's own hands only, stored without the hero
#: at the table (``Hands.heroSeat = 0``), is left out. The ids are spelled out
#: so the statement is a constant; a test keeps them equal to WPN_SITE_IDS.
HERO_HANDS_ONLY_REBUILD_FILTER: Final = " AND NOT (h.heroSeat = 0 AND g.siteId IN (24, 115, 116, 117, 118, 119))"

#: Site names that belong to the iPoker network: every ``'IP'`` row of the
#: Sites table (``database_schema``), and the names its clients and
#: ``DetectInstalledSites`` use. ``Unibet Poker`` is the historical iPoker skin;
#: ``Unibet`` (the 2026 Relax Gaming client) is not one.
IPOKER_SKINS: Final = frozenset(
    name.casefold()
    for name in (
        "iPoker",
        "PMU Poker",
        "FDJ Poker",
        "FDJPoker",
        "En ligne",
        "Parions Sport en ligne",
        "Poker770",
        "Betclic Poker",
        "Betclic PokerX",
        "BetclicPoker",
        "Bet365.fr Poker",
        "Bwin.fr Poker",
        "PartyPoker.fr",
        "NetBet Poker",
        "Barrière Poker",
        "Red Star Poker",
        "Titan Poker",
        "Bet365 Poker",
        "William Hill Poker",
        "Paddy Power Poker",
        "Betfair Poker",
        "Coral Poker",
        "Genting Poker",
        "Mansion Poker",
        "Winner Poker",
        "Ladbrokes Poker",
        "Sky Poker",
        "Sisal Poker",
        "Lottomatica Poker",
        "Eurobet Poker",
        "Snai Poker",
        "Goldbet Poker",
        "Casino Barcelona Poker",
        "Sportium Poker",
        "Marca Apuestas Poker",
        "Everest Poker",
        "Bet-at-home Poker",
        "Mybet Poker",
        "Betsson Poker",
        "Betsafe Poker",
        "NordicBet Poker",
        "Unibet Poker",
        "Maria Casino Poker",
        "LeoVegas Poker",
        "Mr Green Poker",
        "Redbet Poker",
    )
)


def network_of(site: str | None) -> str:
    """The network ``site`` belongs to, casefolded; the site itself when unknown.

    PokerStars is matched as a prefix, so every regional site counts
    (``PokerStars.FR``, ``PokerStarsES``...). iPoker skins are matched by their
    exact name: ``Unibet`` and ``Unibet Poker`` are different rooms.
    """
    name = " ".join(str(site or "").split()).casefold()
    if name.startswith("pokerstars"):
        return "pokerstars"
    if name in IPOKER_SKINS:
        return "ipoker"
    if name in WPN_SKINS:
        return "wpn"
    return name


def policy_for(site: str | None) -> RoomPolicy:
    """The reviewed policy of ``site``'s network, or the conservative one."""
    network = network_of(site)
    policy = ROOM_POLICIES.get(network)
    if policy is not None:
        return policy
    shown = str(site or "").strip() or "this room"
    return RoomPolicy(
        network or "unknown",
        CONSERVATIVE,
        f"{shown}'s rules on HUDs that change with the hand have not been reviewed",
    )


def hero_hands_only(site: str | None) -> bool:
    """Whether ``site``'s HUD statistics may come only from hands the user played (#719)."""
    return policy_for(site).hero_hands_only


def network_hint(config: Any, site: str | None) -> str:
    """The ``network`` attribute ``HUD_config.xml`` gives ``site``, or ``""``."""
    try:
        site_config = getattr(config, "supported_sites", {}).get(site)
    except Exception:  # intentional broad catch: a malformed config must not break the HUD
        return ""
    hint = str(getattr(site_config, "network", "") or "")
    return "" if hint.casefold() in ("", "unknown") else hint


def capabilities_at(site: str | None, network: str | None = None) -> HudCapabilities:
    """What the HUD may do at a table of ``site``.

    ``network`` is the configuration's hint: it can only restrict, so a site
    configured under a stricter network gets the stricter policy, and an edited
    configuration never loosens a room's.
    """
    capabilities = policy_for(site).capabilities
    if network:
        capabilities &= policy_for(network).capabilities
    return capabilities


def capabilities_for_table(site: str | None, config: Any = None) -> HudCapabilities:
    """:func:`capabilities_at` with the configuration's network hint."""
    return capabilities_at(site, network_hint(config, site))


def why_not(capability: Capability, site: str | None, network: str | None = None) -> str | None:
    """Why ``capability`` is refused at a table of ``site``, or None when it is allowed."""
    if getattr(capabilities_at(site, network), capability):
        return None
    for candidate in (site, network):
        policy = policy_for(candidate)
        if candidate and not getattr(policy.capabilities, capability):
            return policy.reason
    return policy_for(site).reason
