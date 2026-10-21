"""Bringing hands over from PokerTracker 4 or Holdem Manager 3 (#612).

Both trackers keep the hand histories they import in each room's own format,
which fpdb's room parsers already read, so moving over is a bulk import of the
right folder. What the user needs from fpdb is the route to that folder, a look
at what it holds before anything is written, and an account afterwards of what
came over, room by room. This module is that, without Qt: the wizard in
``GuiTrackerMigration`` only renders it.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from fpdb_3_legacy.i18n import N_

__all__ = [
    "TRACKERS",
    "ExportScan",
    "RoomSummary",
    "Tracker",
    "configured_hero",
    "scan_folder",
    "summarize",
]

# The values the shipped configurations hold until the user enters their name.
_PLACEHOLDER_SCREEN_NAMES = {"YOUR SCREEN NAME HERE", "YOUR_SCREEN_NAME"}


@dataclass(frozen=True)
class Tracker:
    """A tracker to migrate from, and where its hand histories are found."""

    key: str
    name: str
    steps: tuple[str, ...]  # N_-marked; translated when shown


TRACKERS: tuple[Tracker, ...] = (
    Tracker(
        "pt4",
        "PokerTracker 4",
        (
            N_(
                "PokerTracker 4 archives every hand history it imports, in the room's own format. "
                "Its archive folder is set in Configure > Site & Import Options > Preferences."
            ),
            N_("Choose that folder below: fpdb reads those files as they are, room by room."),
            N_(
                "Without the archive, Database > Export Hands writes the hands out again. "
                "Check the summary afterwards for any file fpdb could not read."
            ),
        ),
    ),
    Tracker(
        "hm3",
        "Holdem Manager 3",
        (
            N_(
                "Holdem Manager 3 can move the hand histories it imports to an archive folder, "
                "in the room's own format. Its import settings show where that folder is."
            ),
            N_("Choose that folder below: fpdb reads those files as they are, room by room."),
            N_(
                "Without the archive, export the hands from Holdem Manager 3 to a folder. "
                "Check the summary afterwards for any file fpdb could not read."
            ),
        ),
    ),
)


@dataclass
class ExportScan:
    """What a folder holds, before anything is imported."""

    rooms: dict[str, list[str]] = field(default_factory=dict)  # room -> files
    heroes: dict[str, set[str]] = field(default_factory=dict)  # room -> hero names seen in the files
    unsupported: list[str] = field(default_factory=list)  # files no parser recognises

    @property
    def file_count(self) -> int:
        return sum(len(files) for files in self.rooms.values())


def _candidate_files(folder: str) -> Iterable[str]:
    from fpdb_3_legacy.Importer import is_valid_import_file

    for directory, _dirs, files in os.walk(folder):
        for name in sorted(files):
            path = os.path.join(directory, name)
            if not os.path.islink(path) and is_valid_import_file(path):
                yield path


def scan_folder(config: Any, folder: str, identifier: Any = None) -> ExportScan:
    """Sort the files under ``folder`` by room, as the bulk import will.

    ``identifier`` is an ``IdentifySite``; one is built from ``config`` when not
    given. Empty files are left out: a tracker can leave one behind and it holds
    nothing to lose. Every other file is either a room's or unsupported -- none
    is dropped without being listed.
    """
    if identifier is None:
        from fpdb_3_legacy.IdentifySite import IdentifySite

        identifier = IdentifySite(config)
    scan = ExportScan()
    for path in _candidate_files(folder):
        try:
            if os.path.getsize(path) == 0:
                continue
        except OSError:
            scan.unsupported.append(path)
            continue
        identifier.processFile(path)
        found = identifier.get_fobj(path)
        site = getattr(getattr(found, "site", None), "name", None) if found else None
        if site is None:
            scan.unsupported.append(path)
            continue
        scan.rooms.setdefault(site, []).append(path)
        hero = getattr(found, "hero", "-")
        if hero and hero not in ("-", "Hero"):
            scan.heroes.setdefault(site, set()).add(hero)
    return scan


def configured_hero(config: Any, site: str) -> str | None:
    """The screen name fpdb counts as the hero on ``site``, or None while it is not set."""
    site_config = getattr(config, "supported_sites", {}).get(site)
    name = str(getattr(site_config, "screen_name", "") or "").strip()
    return name if name and name not in _PLACEHOLDER_SCREEN_NAMES else None


@dataclass(frozen=True)
class RoomSummary:
    """What one room's files gave once imported."""

    site: str
    hero: str | None
    files: int
    stored: int
    duplicates: int
    partial: int
    errors: int


def summarize(file_results: Mapping[str, Any], config: Any) -> list[RoomSummary]:
    """Group an import's per-file results (``Importer.file_results``) by room, busiest room first."""
    totals: dict[str, list[int]] = {}
    for result in file_results.values():
        room = result.site or "?"
        row = totals.setdefault(room, [0, 0, 0, 0, 0])
        row[0] += 1
        row[1] += result.stored
        row[2] += result.duplicates
        row[3] += result.partial
        row[4] += result.errors
    summaries = [
        RoomSummary(site, configured_hero(config, site), files, stored, dups, partial, errors)
        for site, (files, stored, dups, partial, errors) in totals.items()
    ]
    return sorted(summaries, key=lambda room: (-room.stored, room.site))
