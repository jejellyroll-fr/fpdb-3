"""Rooms whose support is switched off or cut down, without their code being removed.

Two levels, each a single switch here:

**Disabled** (:data:`DISABLED_SITES`). The room keeps everything it ever had in
the tree -- converter, live capture, table detection, tests -- but the
application never offers it:

* :class:`Configuration.Site` forces ``enabled = False`` whatever the user's
  ``HUD_config.xml`` says, so the room disappears from the site preferences,
  the report filters, auto-import and the HUD;
* the ``<hhc>`` converter binding is dropped at config load, so bulk import and
  :mod:`IdentifySite` no longer recognise the room's hand histories;
* the main window hides the menu entries that open the room's own tabs.

**Import-only** (:data:`IMPORT_ONLY_SITES`). The room's exported hand
histories can be bulk-imported for review after the session, and nothing else
runs while it is being played:

* :class:`Configuration.Site` forces ``aux_enabled = False``, and the HUD
  refuses the room's tables outright;
* auto-import does not watch the room's hand-history folder (it is the HUD's
  feed, and runs beside the poker client);
* no live capture is offered for it.

CoinPoker is import-only (#732): its 2026 text export is supported, but given
the room's stance on third-party tools fpdb runs nothing beside its client.

Changing a room's level is a one-line change here, not a revert.
"""

from __future__ import annotations

DISABLED_SITES: frozenset[str] = frozenset()

IMPORT_ONLY_SITES: frozenset[str] = frozenset({"CoinPoker"})


def is_site_disabled(site_name: str) -> bool:
    """True when support for ``site_name`` is switched off in this build."""
    return site_name in DISABLED_SITES


def is_site_import_only(site_name: str) -> bool:
    """True when ``site_name``'s files may be bulk-imported, and nothing more."""
    return site_name in IMPORT_ONLY_SITES


def allows_live_use(site_name: str) -> bool:
    """Whether fpdb may run beside the room's client: HUD, auto-import, live capture."""
    return not (is_site_disabled(site_name) or is_site_import_only(site_name))
