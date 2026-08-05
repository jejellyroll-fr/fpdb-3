"""Shared runtime translation helpers for the GUI.

``L10n.set_locale_translation`` installs the selected gettext catalog as the
builtin ``_`` at startup (see ``i18n_compile`` for how the catalogs are built).
Use :func:`gettext` here to translate a string through that hook — it returns the
text unchanged when no catalog is installed (including in tests), so modules can
mark strings without depending on i18n being set up.

Typical use in a GUI module::

    from fpdb_3_legacy.i18n import gettext as _

    button = QPushButton(_("Create database"))

Use :func:`N_` to *mark* a string for extraction without translating it yet
(e.g. in module-level data that is rendered later).
"""

from __future__ import annotations

import builtins


def gettext(message: str) -> str:
    """Translate ``message`` via the installed builtin ``_`` (identity if none)."""
    func = getattr(builtins, "_", None)
    return func(message) if callable(func) else message


def N_(message: str) -> str:
    """Mark ``message`` for translation extraction without translating it now."""
    return message


CATEGORY_TRANSLATION_MAP: dict[str, str] = {
    "⚡ AGRESSIVITÉ & RENTABILITÉ EV": "⚡ AGGRESSIVENESS & EV PROFIT",
    "⚡ AGRESSIVITÉ &amp; RENTABILITÉ EV": "⚡ AGGRESSIVENESS & EV PROFIT",
    "🃏 STRUCTURE MAINS FAITES": "🃏 MADE HAND STRUCTURE",
    "🎯 TIRAGES (DRAWS)": "🎯 DRAWS",
    "💰 SPLASH POTS & NOTES": "💰 SPLASH POTS & NOTES",
    "💰 SPLASH POTS &amp; NOTES": "💰 SPLASH POTS & NOTES",
}

LABEL_TRANSLATION_MAP: dict[str, str] = {
    "All-ins observés": "Observed All-ins",
    "Weak AI % (Cibles EV+)": "Weak AI % (EV+ Targets)",
    "Air / Aucune main faite": "Air / No Made Hand",
    "1 Paire": "1 Pair",
    "2 Paires": "2 Pair",
    "Trips / Brelan": "Trips",
    "Straight / Quinte": "Straight",
    "Flush / Couleur": "Flush",
    "Total Mains Faites": "Total Made Hands",
    "Flush Draw non-max (fd)": "Flush Draw (fd)",
    "Splash récupéré": "Splash Recovered",
    "Splash fréquence": "Splash Frequency",
    "Notes joueur": "Player Notes",
    "PROFIL ADVERSAIRE : {player}": "OPPONENT PROFILE: {player}",
}


def translate_hud_category(cat: str) -> str:
    """Map legacy or localized HUD category strings to English canonical strings and translate via gettext."""
    if not cat:
        return ""
    canonical = CATEGORY_TRANSLATION_MAP.get(cat, cat)
    return gettext(canonical)


def translate_hud_label(label: str) -> str:
    """Map legacy or localized HUD stat label strings to English canonical strings and translate via gettext."""
    if not label:
        return ""
    canonical = LABEL_TRANSLATION_MAP.get(label, label)
    return gettext(canonical)

