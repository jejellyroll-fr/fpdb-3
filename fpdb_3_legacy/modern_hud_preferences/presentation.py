"""How a profile is presented, and which HUD window draws it -- without Qt.

A ``<ss>`` carries a few presentation attributes the live HUD reads:

* ``rich_text`` -- read by ``Aux_Classic_Hud.ClassicStat``; any of ``true``,
  ``yes``, ``1``, ``on`` (case-insensitive) turns the compact rich-text cells
  on. Only the ``ClassicHud`` window class draws them.
* ``font_size`` -- read by ``Aux_Hud.SimpleHUD`` as an integer point size. An
  empty or unreadable value falls back to the ``font_size`` of the ``<aw>`` that
  draws the HUD.
* ``xpad`` / ``ypad`` -- read as integers by ``Stat_sets``.

The editor keeps these as strings in the profile dict (see ``profile_io``) and
writes a cleared one back as a removed attribute. The helpers below read and
change them so that an untouched value keeps its exact spelling: opening and
saving a profile must not rewrite ``rich_text="true"`` as ``"True"``.

Which window handler (``ClassicHud``, ``Simple_HUD``...) draws a profile is not
a property of the profile: each ``<game>`` of ``<supported_games>`` names its
``aux`` windows and the stat-set it uses. :func:`hud_handlers_for` follows that
mapping backwards so the editor can show it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MODE_STANDARD = "standard"
MODE_RICH = "rich"

#: Values of ``rich_text`` the HUD takes as "on" (``Aux_Classic_Hud``).
RICH_TEXT_ON = ("true", "yes", "1", "on")
#: What the editor writes when it turns rich text on.
RICH_TEXT_WRITTEN = "True"

#: Modules whose window class draws the stat grid of a seat.
HUD_MODULES = ("Aux_Hud", "Aux_Classic_Hud")
#: The window class that draws rich-text cells.
RICH_TEXT_CLASS = "ClassicHud"

#: Bounds of the editor's controls. The HUD itself takes any integer.
FONT_SIZE_MAX = 48
PADDING_MAX = 20

#: Profile fields shown for each mode. Both modes use the font size and the
#: padding; the rich-text warning only means something in rich-text mode.
FIELDS_BY_MODE = {
    MODE_STANDARD: ("font_size", "xpad", "ypad"),
    MODE_RICH: ("font_size", "xpad", "ypad", "rich_text_support"),
}


# --- Mode --------------------------------------------------------------------
def _attr(profile: Any, name: str) -> str:
    if not isinstance(profile, dict):
        return ""
    value = profile.get(name)
    return "" if value is None else str(value).strip()


def mode_of(profile: Any) -> str:
    """``MODE_RICH`` when the HUD would draw this profile in rich text."""
    return MODE_RICH if _attr(profile, "rich_text").lower() in RICH_TEXT_ON else MODE_STANDARD


def set_mode(profile: dict[str, Any], mode: str) -> None:
    """Switch the profile's mode, leaving an unchanged value as it was spelled."""
    if mode == mode_of(profile):
        return
    profile["rich_text"] = RICH_TEXT_WRITTEN if mode == MODE_RICH else ""


def visible_fields(mode: str) -> tuple[str, ...]:
    """The presentation fields that have an effect in ``mode``."""
    return FIELDS_BY_MODE.get(mode, FIELDS_BY_MODE[MODE_STANDARD])


# --- Font size and padding ---------------------------------------------------
def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        return 0
    return max(value, 0)


def font_size_of(profile: Any) -> int:
    """The profile's own point size; ``0`` when it uses the window's size.

    The HUD reads the attribute with ``int()`` and falls back to the window's
    size when that fails, so a value like ``"9.5"`` counts as unset.
    """
    return _positive_int(_attr(profile, "font_size"))


def set_font_size(profile: dict[str, Any], size: int) -> None:
    """Set the profile's point size; ``0`` clears it."""
    if int(size) == font_size_of(profile):
        return
    profile["font_size"] = str(int(size)) if int(size) > 0 else ""


def padding_of(profile: Any, axis: str) -> int:
    """``xpad`` or ``ypad`` as the HUD reads it (an empty value is 0)."""
    return _positive_int(_attr(profile, axis) or "0")


def set_padding(profile: dict[str, Any], axis: str, value: int) -> None:
    """Set ``xpad`` or ``ypad``, leaving an unchanged value untouched."""
    if axis not in ("xpad", "ypad"):
        raise ValueError(axis)
    if int(value) == padding_of(profile, axis):
        return
    profile[axis] = int(value)


# --- Window handlers ---------------------------------------------------------
@dataclass
class HandlerUse:
    """One HUD window handler and the games that draw a profile with it."""

    name: str
    module: str = ""
    cls: str = ""
    font_size: int = 0
    games: list[str] = field(default_factory=list)

    @property
    def draws_rich_text(self) -> bool:
        return self.cls == RICH_TEXT_CLASS


def _aux_parameters(config: Any, name: str) -> dict[str, Any] | None:
    getter = getattr(config, "get_aux_parameters", None)
    if callable(getter):
        params = getter(name)
        return params if isinstance(params, dict) else None
    aw = (getattr(config, "aux_windows", None) or {}).get(name)
    return None if aw is None else dict(vars(aw))


def _games_using(config: Any, profile_name: str) -> list[tuple[str, str]]:
    """``(game name, aux list)`` of every game that uses ``profile_name``."""
    found = []
    for game_name, game in (getattr(config, "supported_games", None) or {}).items():
        stat_sets = getattr(game, "game_stat_set", None) or {}
        if any(getattr(gss, "stat_set", None) == profile_name for gss in stat_sets.values()):
            found.append((str(game_name), str(getattr(game, "aux", "") or "")))
    return found


def hud_handlers_for(config: Any, profile_name: str) -> list[HandlerUse]:
    """The HUD window handlers that draw ``profile_name``, in first-seen order.

    Only aux windows whose module draws the stat grid count: a ``mucked`` cards
    window is not a HUD handler. An aux name no ``<aw>`` defines is skipped, as
    the HUD skips it.
    """
    uses: dict[str, HandlerUse] = {}
    for game_name, aux in _games_using(config, profile_name):
        for raw in aux.split(","):
            name = raw.strip()
            if not name:
                continue
            params = _aux_parameters(config, name)
            if params is None or params.get("module") not in HUD_MODULES:
                continue
            use = uses.get(name)
            if use is None:
                use = HandlerUse(
                    name=name,
                    module=str(params.get("module", "")),
                    cls=str(params.get("class", "")),
                    font_size=_positive_int(str(params.get("font_size", "") or "")),
                )
                uses[name] = use
            if game_name not in use.games:
                use.games.append(game_name)
    return list(uses.values())


def handler_font_size(uses: list[HandlerUse], fallback: int) -> int:
    """The size an unset ``font_size`` falls back to, when every handler agrees."""
    sizes = {use.font_size for use in uses if use.font_size > 0}
    return sizes.pop() if len(sizes) == 1 else fallback


def handlers_without_rich_text(uses: list[HandlerUse]) -> list[str]:
    """Names of the handlers that would draw a rich-text profile as plain text."""
    return [use.name for use in uses if not use.draws_rich_text]
