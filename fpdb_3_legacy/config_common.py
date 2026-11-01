"""Helpers shared by the configuration sections, and ConfigBase, the state they work on."""

# Handles fpdb/fpdb-hud configuration files.
#    Copyright 2008-2012,  Ray E. Barker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
########################################################################
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.hud_profiles import HudProfileRule
from fpdb_3_legacy.loggingFpdb import get_logger

if TYPE_CHECKING:
    from fpdb_3_legacy.config_databases import Database
    from fpdb_3_legacy.config_gui import General, GUICashStats, GUITourStats
    from fpdb_3_legacy.config_hud_layouts import Aux_window, Layout_set
    from fpdb_3_legacy.config_hud_ui import HudUI
    from fpdb_3_legacy.config_import import Import, RawHands, RawTourneys
    from fpdb_3_legacy.config_sites import DataSource, HeroProfile, Supported_games

log = get_logger("configuration")


def normalizePath(path):
    """Normalized existing pathes."""
    if os.path.exists(path):
        return os.path.abspath(path)
    return path


########################################################################
def string_to_bool(string, default=True):
    """Converts a string representation of a boolean value to boolean True or False
    @param string: (str) the string to convert
    @param default: value to return if the string can not be converted to a boolean value.
    """
    string = string.lower()
    if string in ("1", "true", "t"):
        return True
    if string in ("0", "false", "f"):
        return False
    return default


#: A saved layout's width/height is the size of the table window the positions
#: were captured on, so every position must sit inside it (a block parked just
#: off the table edge overhangs a little, hence the tolerance). A reference much
#: smaller than the positions it frames is not a layout, it is a corrupted one:
#: Aux_Base.create_scale_position() scales by table/reference, so a 336x103
#: reference framing a position at (1225, 737) throws the HUD blocks thousands
#: of pixels off a real table and the user sees no HUD at all.
LAYOUT_REFERENCE_TOLERANCE = 1.5


#: How far a position may sit *before* the table's origin, as a fraction of the
#: reference. A block parked just above or left of the table is a real user
#: choice (the shipped layouts contain x="-4"), so the allowance mirrors the
#: overhang the tolerance above grants on the right and bottom.
LAYOUT_REFERENCE_UNDERHANG = LAYOUT_REFERENCE_TOLERANCE - 1.0


def layout_reference_fits(width, height, positions) -> bool:
    """Whether ``width``x``height`` can plausibly be the reference for ``positions``.

    ``positions`` is any iterable of (x, y). Missing or non-positive dimensions
    are rejected outright: they would make the scale factor meaningless (or
    raise) rather than merely wrong.

    Both directions are checked. Looking only at the maxima accepted a layout
    whose blocks all sit far above and left of the table -- (-5000, -5000) is as
    unusable as (5000, 5000), and the corrupt ipoker layout this guard was
    written for carried y="-395" alongside its oversized x.
    """
    points = [p for p in positions if p is not None]
    if not width or not height or int(width) <= 0 or int(height) <= 0:
        return False
    if not points:
        return True
    width, height = int(width), int(height)
    xs = [int(x) for x, _y in points]
    ys = [int(y) for _x, y in points]
    return (
        max(xs) <= width * LAYOUT_REFERENCE_TOLERANCE
        and max(ys) <= height * LAYOUT_REFERENCE_TOLERANCE
        and min(xs) >= -width * LAYOUT_REFERENCE_UNDERHANG
        and min(ys) >= -height * LAYOUT_REFERENCE_UNDERHANG
    )


class ConfigBase:
    """The state every Config section mixin works on."""

    appdata_path: str
    aux_windows: dict[str, Aux_window]
    config_path: str
    config_reference_errors: list[str]
    data_sources: dict[str, DataSource]
    db_selected: str | None
    dir_database: Any
    dir_log: str
    doc: Any
    emails: dict[str, Any]
    example_copy: bool
    file: Any
    file_error: str | None
    fpdb_root_path: str
    general: General
    graphics_path: str
    gui_cash_stats: GUICashStats
    gui_tour_stats: GUITourStats
    hero_profiles: dict[str, HeroProfile]
    hhcs: dict[str, Any]
    hud_panel_fallback: str
    hud_panel_rules: list[Any]
    hud_panel_rules_enabled: bool
    hud_profile_rules: list[HudProfileRule]
    imp: Import
    install_method: str
    layout_sets: dict[str, Layout_set]
    log_file: str
    os_family: str
    pack_popups: dict[str, str]
    popup_windows: dict[str, Any]
    posix: bool
    pyfpdb_path: str
    python_version: str
    raw_hands: RawHands
    raw_tourneys: RawTourneys
    site_ids: dict[str, int]
    stat_sets: dict[str, Any]
    supported_databases: dict[str, Database]
    supported_games: dict[str, Supported_games]
    supported_sites: dict[str, Any]
    ui: HudUI
    wrongConfigVersion: bool

    if TYPE_CHECKING:

        def save(self, file=None) -> None: ...
