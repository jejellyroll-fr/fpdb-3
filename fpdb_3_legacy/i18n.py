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
