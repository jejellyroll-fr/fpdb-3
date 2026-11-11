"""What an edit of a stat in the HUD Preferences editor writes back.

No Qt here: the rules that decide what an edit writes back live in plain
functions the default test suite covers. An edit writes only what the user
changed (:func:`changes`), and leaves every other attribute of the stat as it
was -- including attributes the form does not show.

The HUD colours a stat only when both ``stat_loth`` and ``stat_hith`` are set
(``Aux_Classic_Hud``): below the low one it uses ``stat_locolor``, between the
two ``stat_midcolor``, above the high one ``stat_hicolor``. The thresholds are
plain numbers -- a decimal (``12.5``), a negative (``-5`` bb/100) or a value
above 100 (``140`` hands) are all valid -- and they are stored as the strings
the user wrote. An edit therefore writes a threshold back only when the user
changed the number shown, and otherwise keeps the stored string as it was.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from fpdb_3_legacy.i18n import gettext as _

#: Digits after the decimal point the threshold inputs offer.
DECIMALS = 2
#: Bounds of the threshold inputs: wide enough for any stat, not capped at 100.
MINIMUM = -1_000_000.0
MAXIMUM = 1_000_000.0
#: What a new range starts from when the user turns thresholds on.
DEFAULT_LOW = 20.0
DEFAULT_HIGH = 60.0
DEFAULT_LOW_COLOR = "#ff0000"
DEFAULT_MID_COLOR = "#ffff00"
DEFAULT_HIGH_COLOR = "#00ff00"

THRESHOLD_KEYS = ("stat_loth", "stat_hith")
COLOR_KEYS = ("stat_locolor", "stat_midcolor", "stat_hicolor")


def parse(text: Any) -> float | None:
    """The number a stored threshold holds, or None when it holds none."""
    if text is None:
        return None
    try:
        value = float(str(text).strip())
    except ValueError:
        return None
    return value if math.isfinite(value) else None  # not NaN or an infinity


def format_value(value: float, decimals: int = DECIMALS) -> str:
    """``12.5`` -> ``"12.5"``, ``140.0`` -> ``"140"``: no trailing zeros."""
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def shown_value(text: Any, default: float) -> float:
    """The number an input shows for a stored threshold, clamped to its range."""
    value = parse(text)
    if value is None:
        return default
    return min(MAXIMUM, max(MINIMUM, value))


def has_thresholds(stat: Mapping[str, Any]) -> bool:
    """Whether the stat holds any threshold the editor should show as in use."""
    return any(str(stat.get(key) or "").strip() for key in THRESHOLD_KEYS)


def stored_text(stored: Any, shown_at_load: float, shown_now: float) -> str:
    """The string to store for a threshold input that now shows ``shown_now``.

    An input the user left alone keeps the stored string character for
    character, even one the input cannot show exactly (``12.345``, ``1e3``);
    a changed one, or one that had nothing stored, stores the number shown.
    """
    text = "" if stored is None else str(stored)
    if text.strip() and shown_now == shown_at_load:
        return text
    return format_value(shown_now)


def threshold_values(
    stored: Mapping[str, Any],
    use: bool,
    shown_at_load: tuple[float, float],
    shown_now: tuple[float, float],
) -> dict[str, str]:
    """``stat_loth`` and ``stat_hith`` as a threshold form now reads.

    ``stored`` is the stat as it was when the form loaded it; with thresholds
    turned off both are empty, which the HUD reads as "no colour range".
    """
    if not use:
        return dict.fromkeys(THRESHOLD_KEYS, "")
    return {
        key: stored_text(stored.get(key), at_load, now)
        for key, at_load, now in zip(THRESHOLD_KEYS, shown_at_load, shown_now, strict=True)
    }


def edit_target(original: Mapping[str, Any], at_load: Mapping[str, Any], now: Mapping[str, Any]) -> dict[str, Any]:
    """What each attribute a live form shows should hold after its latest edit.

    A form that writes on every change (the Item Properties tabs) cannot diff
    against the stat itself, which its previous edits already changed: an
    attribute the form shows as it showed it at load goes back to its
    ``original`` value, any other takes the form's value.
    """
    return {key: original.get(key, "") if value == at_load.get(key) else value for key, value in now.items()}


def changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """The entries of ``after`` whose value differs from ``before``.

    The editor reads its form once when it opens and again when it closes:
    only what differs is what the user set, and only that is written back.
    """
    return {key: value for key, value in after.items() if before.get(key) != value}


def apply_changes(stat: dict[str, Any], updates: Mapping[str, Any]) -> bool:
    """Write ``updates`` into ``stat`` without adding empty attributes it lacked.

    Returns whether anything in ``stat`` changed.
    """
    changed = False
    for key, value in updates.items():
        if stat.get(key, "") == value and (key in stat or value == ""):
            continue
        stat[key] = value
        changed = True
    return changed


def preview_span(low: float, high: float) -> tuple[float, float]:
    """The value range a colour preview draws so both thresholds fit on it.

    Percentages keep the familiar 0-100 bar; a threshold outside it widens the
    bar instead of falling off its edge.
    """
    lo, hi = min(low, high), max(low, high)
    start = min(0.0, lo)
    end = max(100.0, hi)
    if lo < 0.0 or hi > 100.0:
        margin = (end - start) * 0.1
        start = start - margin if lo < 0.0 else start
        end = end + margin if hi > 100.0 else end
    return start, end


def popup_options(names: Iterable[str], current: str = "") -> list[tuple[str, str]]:
    """``(label, value)`` of the popups a stat can open, for a list to pick from (B15).

    "No popup" comes first. A *current* popup the configuration does not define
    is listed too, marked as missing, so showing a stat never changes it.
    """
    known = sorted({str(name) for name in names if str(name)}, key=str.casefold)
    options = [(_("(no popup)"), "")] + [(name, name) for name in known]
    if current and current not in known:
        options.append((_("{popup} (missing)").format(popup=current), current))
    return options
