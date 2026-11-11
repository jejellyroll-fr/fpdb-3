"""What the HUD Preferences editor decides without a window.

Four questions the dialog asks, answered on plain data so they can be tested
without Qt:

* can this text name a profile (:func:`name_problem`);
* what follows a profile when it is renamed: the profile and panel rules that
  name it, the ``<ss>`` that holds it in the file, and the ``stat_set=``
  bindings of the game defaults (:func:`rename_profile`, :func:`rename_in_rules`,
  :func:`record_rename`, :func:`file_name_for`, :func:`follow_renames`);
* what the editor has changed since it was opened or saved (:class:`EditorState`,
  :func:`differences`);
* where an item is, so a refresh can select it again (:func:`locate`), and what
  the Panels list calls each panel (:func:`panel_labels`).
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass, replace
from typing import Any

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.modern_hud_preferences import layout_model


# --- Profile names -----------------------------------------------------------
def name_problem(name: str, existing: Iterable[str], *, current: str | None = None) -> str | None:
    """Why ``name`` cannot name a profile, or ``None`` when it can.

    ``current`` is the profile being renamed: keeping its own name is not a
    clash. Surrounding spaces do not count; the caller stores the stripped name.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        return _("A profile needs a name.")
    if cleaned != current and cleaned in set(existing):
        return _('A profile named "{name}" already exists. Choose another name.').format(name=cleaned)
    return None


# --- Renaming ----------------------------------------------------------------
def rename_profile(profiles: MutableMapping[str, Any], old: str, new: str) -> None:
    """Rename ``old`` to ``new`` in place, keeping the order of the profiles."""
    entries = list(profiles.items())
    profiles.clear()
    for key, value in entries:
        profiles[new if key == old else key] = value


def rename_in_rules(rules: Iterable[Any], old: str, new: str) -> list[Any]:
    """The rules, with every one that names ``old`` naming ``new`` instead.

    Profile rules and panel rules are frozen dataclasses with a ``profile``
    field; a panel rule for "all" profiles names none and is left alone.
    """
    return [replace(rule, profile=new) if getattr(rule, "profile", None) == old else rule for rule in rules]


def record_rename(renames: dict[str, str], old: str, new: str) -> None:
    """Note that ``old`` is now called ``new``.

    ``renames`` maps a profile's current name to the name of the ``<ss>`` that
    holds it in the file. A chain of renames keeps the first name, and renaming
    back to it forgets the entry.
    """
    source = renames.pop(old, old)
    if source != new:
        renames[new] = source


def forget_profile(renames: dict[str, str], name: str) -> None:
    """A deleted profile no longer claims the ``<ss>`` it was renamed from."""
    renames.pop(name, None)


def file_name_for(name: str, renames: Mapping[str, str]) -> str | None:
    """The ``<ss>`` name that holds profile ``name``, or ``None`` for a new one.

    A profile that took over the name another profile was renamed from must not
    reuse that profile's ``<ss>``: it gets a node of its own.
    """
    if name in renames:
        return renames[name]
    if name in renames.values():
        return None
    return name


def follow_renames(doc: Any, renames: Mapping[str, str]) -> int:
    """Point every ``stat_set="..."`` binding of ``doc`` at the new names.

    The game defaults (``<game_stat_set stat_set="...">``) name a profile by
    its ``<ss>`` name; without this a renamed profile would leave them naming a
    stat-set that no longer exists. Returns how many bindings moved.
    """
    new_for = {source: new for new, source in renames.items()}
    moved = 0
    for node in doc.getElementsByTagName("*"):
        if node.hasAttribute("stat_set") and node.getAttribute("stat_set") in new_for:
            node.setAttribute("stat_set", new_for[node.getAttribute("stat_set")])
            moved += 1
    return moved


def follow_renames_in_games(supported_games: Any, renames: Mapping[str, str]) -> None:
    """The same as :func:`follow_renames`, on the parsed ``Supported_games`` of a config."""
    new_for = {source: new for new, source in renames.items()}
    for game in (supported_games or {}).values():
        for binding in (getattr(game, "game_stat_set", None) or {}).values():
            if getattr(binding, "stat_set", None) in new_for:
                binding.stat_set = new_for[binding.stat_set]


# --- Unsaved changes ---------------------------------------------------------
@dataclass(frozen=True)
class EditorState:
    """Everything the editor writes on Save, as comparable data."""

    profiles: Any = None
    popups: Any = None
    settings: tuple[Any, ...] = ()
    profile_rules: tuple[Any, ...] = ()
    panel_rules: tuple[Any, ...] = ()
    panel_rules_enabled: bool = False
    panel_fallback: str = ""

    @classmethod
    def capture(
        cls,
        *,
        profiles: Any = None,
        popups: Any = None,
        settings: Iterable[Any] = (),
        profile_rules: Iterable[Any] = (),
        panel_rules: Iterable[Any] = (),
        panel_rules_enabled: bool = False,
        panel_fallback: str = "",
        keep: bool = True,
    ) -> EditorState:
        """The state now; ``keep`` copies the mutable parts so later edits do not reach it."""
        return cls(
            profiles=copy.deepcopy(profiles) if keep else profiles,
            popups=copy.deepcopy(popups) if keep else popups,
            settings=tuple(settings),
            profile_rules=tuple(profile_rules),
            panel_rules=tuple(panel_rules),
            panel_rules_enabled=bool(panel_rules_enabled),
            panel_fallback=str(panel_fallback or ""),
        )


#: What :func:`differences` names, in the order it names them.
STATE_PARTS = (
    "profiles",
    "popups",
    "settings",
    "profile_rules",
    "panel_rules",
    "panel_rules_enabled",
    "panel_fallback",
)


def differences(saved: EditorState, current: EditorState) -> list[str]:
    """The parts of ``current`` that differ from ``saved``, by their field name."""
    return [name for name in STATE_PARTS if getattr(saved, name) != getattr(current, name)]


def describe_differences(names: Iterable[str]) -> str:
    """The parts that changed, readable: "HUD profiles, panel rules"."""
    labels = {
        "profiles": _("HUD profiles"),
        "popups": _("popup windows"),
        "settings": _("general settings"),
        "profile_rules": _("profile rules"),
        "panel_rules": _("panel rules"),
        "panel_rules_enabled": _("dynamic panels"),
        "panel_fallback": _("panel fallback"),
    }
    return ", ".join(labels.get(name, name) for name in names)


# --- Selection ---------------------------------------------------------------
def locate(profile: Any, ref: Any) -> tuple[int | None, str] | None:
    """``(block index, kind)`` of the item ``ref``, by identity.

    The block index is ``None`` in a flat profile. ``None`` overall when the
    item is not in the profile any more (deleted, or another profile shown).
    """
    if ref is None or profile is None:
        return None
    blocks = profile.get("blocks") if isinstance(profile, dict) else None
    if blocks:
        for index, block in enumerate(blocks):
            found = layout_model.find(block, ref)
            if found is not None:
                return index, found[0]
        return None
    container = profile if isinstance(profile, dict) else {"stats": profile}
    found = layout_model.find(container, ref)
    return (None, found[0]) if found is not None else None


def panel_labels(profile: Any) -> list[str]:
    """What the Panels list shows for each panel of ``profile``.

    A flat profile has one entry, its grid; a panel without a label is
    "(unnamed)". Only a panel can be unnamed: the grid of a flat profile has no
    label to lose.
    """
    blocks = profile.get("blocks") if isinstance(profile, dict) else None
    if blocks:
        return [str(block.get("label") or "") or _("(unnamed)") for block in blocks]
    return [_("(single grid)")]
