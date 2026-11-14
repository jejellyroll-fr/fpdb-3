"""Dynamic HUD panels run only once their user has read what rooms say about them (#647).

A dynamic panel changes which statistics a seat shows with the hand being
played. That is exactly what some rooms address: PokerStars bans in-game
statistics that change automatically with the game state, and Winamax lists
dynamic range software among the tools it prohibits. Which rooms allow them is
:mod:`fpdb_3_legacy.hud_room_policy`'s decision (#756), and a yes never
overrides it.

The panels stay off until the user says yes after reading that, and the yes is
kept beside the configuration with the version of what it was given for, the
way the live-capture answers are (:mod:`fpdb_3_legacy.live_capture_consent`).
Whatever wrote the panel rules -- Preferences, a HUD package, the pack gallery
or a hand edit of HUD_config.xml -- the HUD resolves them only with that yes,
and only at a table of a room whose reviewed rules allow them.

This module is data and checks only; the question is asked by the Dynamic
Panels tab of the HUD preferences.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from fpdb_3_legacy import hud_room_policy, live_capture_consent
from fpdb_3_legacy.i18n import N_
from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.live_capture_consent import Mechanism

#: Where the answer is kept, beside HUD_config.xml.
CONSENT_NAME: Final = "dynamic-panels-consent.json"

DYNAMIC_PANELS: Final = Mechanism(
    key="dynamic_panels",
    version=1,
    title=N_("Dynamic HUD panels"),
    what_happens=N_(
        "With dynamic panels on, the HUD changes which of a player's statistics it shows with the "
        "hand being played: preflop panels preflop, c-bet panels when a c-bet is made. The "
        "statistics are still the player's history; fpdb never shows a recommended action."
    ),
)

#: ``(path, version, mtime, size) -> answer``: the HUD asks on every update,
#: and the file changes only when the user answers.
_confirmed_cache: dict[tuple[str, int, int, int], bool] = {}


def consent_path(config_file: str | os.PathLike[str] | None = None) -> Path:
    """The answer file beside ``config_file``, or in fpdb's configuration folder."""
    return live_capture_consent.consent_path(config_file).with_name(CONSENT_NAME)


def statement() -> str:
    """Everything the user reads before saying yes, translated."""
    return "\n\n".join(
        (
            _(DYNAMIC_PANELS.what_happens),
            _(
                "fpdb shows dynamic panels only at tables of rooms whose rules were reviewed and allow "
                "them, and your yes does not change that. PokerStars forbids in-game statistics that "
                "change automatically with the game state. Winamax lists dynamic range software and "
                "certain dynamic features of Hand2Note as prohibited, so the panels stay off there until "
                "its integrity team approves them. They stay off on the iPoker network, whose skins "
                "are documented as allowing neither positional nor dynamic HUDs, and in every room "
                "not reviewed yet. Until then, the panels can be set up and previewed in Preferences."
            ),
            _(
                "Your room's terms prevail. Read them, and turn this on only if they allow it. "
                "Help ▸ What fpdb does while you play says what each room's page says."
            ),
        )
    )


def is_confirmed(path: Path | None = None) -> bool:
    """Whether the user said yes to this version of dynamic panels."""
    target = path or consent_path()
    try:
        stat = target.stat()
    except OSError:
        return False
    key = (str(target), DYNAMIC_PANELS.version, stat.st_mtime_ns, stat.st_size)
    if key not in _confirmed_cache:
        _confirmed_cache.clear()
        _confirmed_cache[key] = live_capture_consent.is_accepted(DYNAMIC_PANELS, target)
    return _confirmed_cache[key]


def forbids_them(site: str | None, network: str | None = None) -> bool:
    """Whether dynamic panels are refused at a table of ``site`` -- any regional site or skin of it."""
    return not hud_room_policy.capabilities_at(site, network).dynamic_hud


def confirm(path: Path | None = None) -> None:
    """Record the user's yes."""
    live_capture_consent.accept(DYNAMIC_PANELS, path or consent_path())


def withdraw(path: Path | None = None) -> None:
    """Forget the yes: the HUD keeps its static grid again."""
    live_capture_consent.withdraw(DYNAMIC_PANELS, path or consent_path())


def why_not_at(site: str | None, path: Path | None = None, network: str | None = None) -> str | None:
    """Why the HUD keeps the static grid at a table of ``site``, or None when it need not.

    The room is asked first: no answer file can turn the panels on where the
    room's policy refuses them.
    """
    refused = hud_room_policy.why_not("dynamic_hud", site, network)
    if refused:
        return refused
    if not is_confirmed(path):
        return "they were not turned on in Preferences ▸ HUD ▸ Dynamic Panels after reading what rooms say"
    return None
