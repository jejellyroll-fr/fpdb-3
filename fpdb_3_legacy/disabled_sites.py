"""Rooms whose support is switched off, without their code being removed.

A disabled room keeps everything it ever had in the tree -- converter, live
capture, table detection, tests -- but the application never offers it:

* :class:`Configuration.Site` forces ``enabled = False`` whatever the user's
  ``HUD_config.xml`` says, so the room disappears from the site preferences,
  the report filters, auto-import and the HUD;
* the ``<hhc>`` converter binding is dropped at config load, so bulk import and
  :mod:`IdentifySite` no longer recognise the room's hand histories;
* the main window hides the menu entries that open the room's own tabs.

Re-enabling a room is therefore a one-line change here, not a revert.
"""

from __future__ import annotations

DISABLED_SITES: frozenset[str] = frozenset({"CoinPoker"})


def is_site_disabled(site_name: str) -> bool:
    """True when support for ``site_name`` is switched off in this build."""
    return site_name in DISABLED_SITES
