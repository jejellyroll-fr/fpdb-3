#    Copyright 2011-2012,  Ray E. Barker
from __future__ import annotations

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
"""A simple HUD display for FreePokerTools/fpdb HUD."""

########################################################################

#    Standard Library modules
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

#    FreePokerTools modules
from fpdb_3_legacy import Aux_Base, Configuration, Popup, Stats
from fpdb_3_legacy.i18n import gettext as _t
from fpdb_3_legacy.loggingFpdb import get_logger, hud_trace

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("hud_main")

import json
import logging
import os


class HUDLayoutPositionsStore:
    def __init__(self) -> None:
        self.path = os.path.join(os.path.expanduser("~"), ".fpdb", "HUD_layout_positions.json")
        self.data = {"version": 1, "positions": {}}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                log.exception("Error loading HUD layout positions JSON")

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            temp_path = self.path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(temp_path, self.path)
        except Exception:
            log.exception("Error saving HUD layout positions JSON")

    def get_position(self, site: str, layout: str, stat_set: str, max_seats: int, seat: str | int, block_id: str | int) -> tuple[int, int] | None:
        key = f"{site}/{layout}/{stat_set}/{max_seats}/{seat}/{block_id}"
        pos = self.data.setdefault("positions", {}).get(key)
        if pos:
            return int(pos.get("x", 0)), int(pos.get("y", 0))
        return None

    def set_position(self, site: str, layout: str, stat_set: str, max_seats: int, seat: str | int, block_id: str | int, x: int, y: int) -> None:
        key = f"{site}/{layout}/{stat_set}/{max_seats}/{seat}/{block_id}"
        self.data.setdefault("positions", {})[key] = {"x": x, "y": y}
        self.save()

_positions_store = None
def get_positions_store():
    global _positions_store
    if _positions_store is None:
        _positions_store = HUDLayoutPositionsStore()
    return _positions_store

# PT4-style item alignment names -> Qt flags.
_ALIGN = {
    "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    "center": Qt.AlignmentFlag.AlignCenter,
    "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
}


def normalize_position(raw: Any) -> str:
    """Map a stored/labelled position to a canonical panel code.

    Accepts the values DerivedStats stores in HandsPlayers.position (0 = button,
    "S" = small blind, "B" = big blind, 1.. = seats after the BB) and the panel
    labels used in configs ("BU"/"SB"/"BB"/...). Returns one of
    BTN/SB/BB/CO/MP/EP (or "" when unknown/empty).
    """
    if raw is None or raw == "":
        return ""
    s = str(raw).strip().upper()
    if s in ("0", "BTN", "BU", "D", "BUTTON"):
        return "BTN"
    if s in ("S", "SB"):
        return "SB"
    if s in ("B", "BB"):
        return "BB"
    after_bb = {"1": "CO", "2": "MP", "3": "MP", "4": "EP", "5": "EP", "6": "EP", "7": "EP", "8": "EP", "9": "EP"}
    return after_bb.get(s, s)


def block_visible(block_position: str, player_position: Any) -> bool:
    """Whether a panel bound to ``block_position`` shows for ``player_position``.

    A block with no position binding is always visible; otherwise the player's
    normalized position must match the block's.
    """
    if not block_position:
        return True
    return normalize_position(block_position) == normalize_position(player_position)


def false_attr(value: Any) -> bool:
    """Return True for XML/config values that explicitly mean false."""
    return str(value).strip().lower() in ("false", "no", "0", "off")


def true_attr(value: Any) -> bool:
    """Return True for XML/config values that explicitly mean true."""
    return str(value).strip().lower() in ("true", "yes", "1", "on")


class SimpleHUD(Aux_Base.AuxSeats):
    """A simple HUD class based on the Aux_Window interface."""

    def __init__(self, hud: Any, config: Any, aux_params: Any) -> None:
        """Initializes the SimpleHUD instance for a poker table.

        This constructor sets up the HUD's configuration, layout, and stat window classes for the table.
        It prepares the stat, popup, and tip arrays based on the current game parameters.

        Args:
            hud: The HUD instance associated with the table.
            config: The configuration object for the HUD.
            aux_params: Additional parameters for HUD customization.
        """
        log.debug("=== SIMPLEHUD __INIT__ CALLED ===")
        #    Save everything you need to know about the hud as attrs.
        #    That way a subclass doesn't have to grab them.
        #    Also, the subclass can override any of these attributes
        super().__init__(hud, config, aux_params)
        self.poker_game = self.hud.poker_game
        self.site_params = self.hud.site_parameters
        self.aux_params = aux_params
        self.game_params = self.hud.supported_games_parameters["game_stat_set"]
        self.max = self.hud.max
        self.nrows = self.game_params.rows
        self.ncols = self.game_params.cols
        self.xpad = self.game_params.xpad
        self.ypad = self.game_params.ypad
        self.xshift = self.site_params["hud_menu_xshift"]
        self.yshift = self.site_params["hud_menu_yshift"]
        self.fgcolor = self.aux_params["fgcolor"]
        self.bgcolor = self.aux_params["bgcolor"]
        self.opacity = self.aux_params["opacity"]
        self.font = QFont(self.aux_params["font"], int(self.aux_params["font_size"]))

        # store these class definitions for use elsewhere
        # this is needed to guarantee that the classes in _this_ module
        # are called, and that some other overriding class is not used.

        self.aw_class_window = SimpleStatWindow
        self.aw_class_stat = SimpleStat
        self.aw_class_table_mw = SimpleTableMW
        self.aw_class_label = SimpleLabel

        #    layout is handled by superclass!
        #    retrieve the contents of the stats. popup and tips elements
        #    for future use do this here so that subclasses don't have to bother

        self.stats = [[None] * self.ncols for _ in range(self.nrows)]
        self.popups = [[None] * self.ncols for _ in range(self.nrows)]
        self.tips = [[None] * self.ncols for _ in range(self.nrows)]

        for stat in self.game_params.stats:
            self.stats[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].stat_name
            )
            self.popups[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].popup
            )
            self.tips[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].tip
            )

        self._build_block_layouts()

    def _positional_mode(self) -> str:
        """'all' (show every position panel, stacked) or 'current' (only the
        panel matching the live position). Defaults to 'current'."""
        config_stat_set = getattr(self.config, "stat_sets", {}).get(self.game_params.name)
        for stat_set in (self.game_params, config_stat_set):
            mode = getattr(stat_set, "positional_mode", "") if stat_set is not None else ""
            if mode:
                return str(mode).strip().lower()
        return "current"

    def _show_hero_hud(self) -> bool:
        """Whether this stat-set should display hero stat windows."""
        config_stat_set = getattr(self.config, "stat_sets", {}).get(self.game_params.name)
        for stat_set in (self.game_params, config_stat_set):
            show_hero = getattr(stat_set, "show_hero_hud", "") if stat_set is not None else ""
            if false_attr(show_hero):
                return False
            if true_attr(show_hero):
                return True
        if getattr(self.game_params, "is_multiblock", False):
            return False
        return True

    def _is_hero_player(self, pdata: dict[str, Any] | None) -> bool:
        """Best-effort hero detection across config aliases and loaded hands."""
        if not pdata:
            return False

        screen_name = str(pdata.get("screen_name", "") or "")
        if not screen_name:
            return False
        screen_name_l = screen_name.lower()

        is_hero_name = getattr(self.config, "is_hero_name", None)
        site_name = getattr(self.hud, "site", "")
        if site_name and is_hero_name is not None and is_hero_name(site_name, screen_name):
            return True

        for site_cfg in getattr(self.config, "supported_sites", {}).values():
            if site_cfg.screen_name and screen_name_l == site_cfg.screen_name.lower():
                return True
            if any(alias and screen_name_l == alias.lower() for alias in getattr(site_cfg, "hero_aliases", [])):
                return True

        hand_hero = getattr(self.hud.hand_instance, "hero", None)
        return bool(hand_hero and screen_name_l == str(hand_hero).lower()) or screen_name_l == "hero"

    def _build_block_layouts(self) -> None:
        """Build per-block 2D stat/popup/tip arrays for multi-panel rendering.

        A classic single-grid stat-set yields one block (identical to the legacy
        self.stats arrays); a multi-panel stat-set yields one entry per panel.
        """
        self.block_layouts = []
        blocks = getattr(self.game_params, "blocks", None)
        if not blocks:  # very old config object without blocks -> single grid
            blocks = [type("B", (), {"label": "", "rows": self.nrows, "cols": self.ncols, "stats": self.game_params.stats})()]
        for blk in blocks:
            nr, nc = blk.rows, blk.cols
            stats = [[None] * nc for _ in range(nr)]
            popups = [[None] * nc for _ in range(nr)]
            tips = [[None] * nc for _ in range(nr)]
            hudcolors = [[""] * nc for _ in range(nr)]
            hudbgcolors = [[""] * nc for _ in range(nr)]
            colorranges = [[None] * nc for _ in range(nr)]
            colspans = [[1] * nc for _ in range(nr)]
            aligns = [[""] * nc for _ in range(nr)]
            for (r, c), st in blk.stats.items():
                if 0 <= r < nr and 0 <= c < nc:
                    stats[r][c] = st.stat_name
                    popups[r][c] = st.popup
                    tips[r][c] = st.tip
                    hudcolors[r][c] = getattr(st, "hudcolor", "")
                    hudbgcolors[r][c] = getattr(st, "hudbgcolor", "")
                    colspans[r][c] = getattr(st, "colspan", 1) or 1
                    aligns[r][c] = getattr(st, "align", "") or ""
                    loth, hith = getattr(st, "stat_loth", ""), getattr(st, "stat_hith", "")
                    if loth and hith:
                        colorranges[r][c] = {"loth": loth, "hith": hith,
                                             "locolor": getattr(st, "stat_locolor", ""),
                                             "midcolor": getattr(st, "stat_midcolor", ""),
                                             "hicolor": getattr(st, "stat_hicolor", "")}
            self.block_layouts.append(
                {"label": blk.label, "position": getattr(blk, "position", ""),
                 # scope/audience/id drive create() (a table block gets one window,
                 # not one per seat) and visibility; they MUST be carried through.
                 "scope": getattr(blk, "scope", "player"),
                 "audience": getattr(blk, "audience", "everyone"),
                 "id": getattr(blk, "id", ""),
                 "bgcolor": getattr(blk, "bgcolor", ""), "fgcolor": getattr(blk, "fgcolor", ""),
                 "bordercolor": getattr(blk, "bordercolor", ""),
                 "title_bgcolor": getattr(blk, "title_bgcolor", ""),
                 "title_fgcolor": getattr(blk, "title_fgcolor", ""),
                 "x": getattr(blk, "x", 0), "y": getattr(blk, "y", 0),
                 "nrows": nr, "ncols": nc, "stats": stats, "popups": popups, "tips": tips,
                 "hudcolors": hudcolors, "hudbgcolors": hudbgcolors, "colorranges": colorranges,
                 "colspans": colspans, "aligns": aligns,
                 "texts": list(getattr(blk, "texts", [])), "hlines": list(getattr(blk, "hlines", []))},
            )

    def refresh_stats_layout(self) -> None:
        """Refreshes the stats layout arrays based on the current game parameters.

        This method updates the layout parameters and repopulates the stats, popups, and tips arrays
        to reflect any changes in the stat set configuration.
        """
        # Update layout parameters from new game_params
        self.nrows = self.game_params.rows
        self.ncols = self.game_params.cols
        self.xpad = self.game_params.xpad
        self.ypad = self.game_params.ypad

        # Reinitialize the stats arrays
        self.stats = [[None] * self.ncols for _ in range(self.nrows)]
        self.popups = [[None] * self.ncols for _ in range(self.nrows)]
        self.tips = [[None] * self.ncols for _ in range(self.nrows)]

        # Repopulate with new stat set configuration
        for stat in self.game_params.stats:
            self.stats[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].stat_name
            )
            self.popups[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].popup
            )
            self.tips[self.game_params.stats[stat].rowcol[0]][self.game_params.stats[stat].rowcol[1]] = (
                self.game_params.stats[stat].tip
            )

        self._build_block_layouts()

    def create_contents(self, container: Any, i: int) -> None:
        """Create the contents of the specified container.

        This method delegates the creation of contents to the container's create_contents method.

        Args:
            container: The container object whose contents are to be created.
            i: The index or identifier for the contents to be created.
        """
        # this is a call to whatever is in self.aw_class_window but it isn't obvious
        container.create_contents(i)

    def update_contents(self, container: Any, i: int) -> None:
        """Update the contents of the specified container.

        This method delegates the update of contents to the container's update_contents method.

        Args:
            container: The container object whose contents are to be updated.
            i: The index or identifier for the contents to be updated.
        """
        # this is a call to whatever is in self.aw_class_window but it isn't obvious
        container.update_contents(i)

    def create_common(self, _x: int = 0, _y: int = 0) -> Any:
        """Create the common table menu window for the HUD.

        This method instantiates and returns the main table menu window for the HUD.

        Args:
            _x: The x-coordinate for positioning (unused).
            _y: The y-coordinate for positioning (unused).

        Returns:
            Any: The created table menu window instance.
        """
        # invokes the simple_table_mw class (or similar)
        self.table_mw = self.aw_class_table_mw(self.hud, aw=self)
        return self.table_mw

    def move_windows(self) -> None:
        """Move all HUD windows to their appropriate positions.

        This method moves both the stat windows and the main table menu window to their updated locations.
        """
        if self._uses_block_windows():
            self._move_block_windows()
            self.table_mw.move_windows()
            return
        super().move_windows()
        #
        # tell our mw that an update is needed (normally on table move)
        # custom code here, because we don't use the ['common'] element
        # to control menu position
        self.table_mw.move_windows()

    def get_id_from_seat(self, seat: int | str) -> int | None:
        """Player id (native int) seated at a visual seat, or None if empty.

        Returns an int so callers can index stat_dict[player_id] directly; the
        dict is int-keyed (see Database.get_stats_from_hand).
        """
        if seat == "common" or seat == "table":
            return None
        # Convert visual seat index to physical seat number
        physical_seat = self.hud.layout.hh_seats[seat]
        # Check authoritative seat_players dictionary first
        if hasattr(self.hud, "seat_players") and self.hud.seat_players:
            player_info = self.hud.seat_players.get(physical_seat)
            if player_info:
                return player_info["player_id"]
        # Fallback to stat_dict
        if self.hud.stat_dict:
            for player_id, player_data in list(self.hud.stat_dict.items()):
                if physical_seat == player_data.get("seat"):
                    return player_id
        return None

    def _uses_block_windows(self) -> bool:
        return len(getattr(self, "block_layouts", [])) > 1

    def _block_offset(self, block_index: int) -> tuple[int, int]:
        blk = self.block_layouts[block_index]
        return int(blk.get("x", 0) or 0), int(blk.get("y", 0) or 0)

    def _hero_display_seat(self) -> int | None:
        fav_seat = self.hud.site_parameters["fav_seat"].get(self.hud.max, 0)
        for key in self.hud.stat_dict:
            if self._is_hero_player(self.hud.stat_dict[key]):
                for seat in range(1, self.hud.max + 1):
                    if self.get_id_from_seat(seat) == key:
                        return seat
        if fav_seat and hasattr(self, "adj"):
            for seat in range(1, self.hud.max + 1):
                if self.adj[seat] == fav_seat:
                    return seat
        return None

    def _hide_seat_for_villain_only(self, seat: int, pdata: dict[str, Any] | None) -> bool:
        if self._show_hero_hud():
            return False
        if self._is_hero_player(pdata):
            return True
        return getattr(self, "hero_display_seat", None) == seat

    def _seat_player_debug(self, seat: int) -> tuple[Any, str, Any]:
        try:
            player_id = self.get_id_from_seat(seat)
        except Exception:
            return None, "", ""
        pdata = self.hud.stat_dict.get(player_id, {}) if player_id is not None and self.hud.stat_dict else {}
        return player_id, str(pdata.get("screen_name", "") or ""), pdata.get("position", "")

    def _log_block_window_position(
        self,
        reason: str,
        seat: int | str,
        block_index: int,
        rel_pos: tuple[int, int],
        abs_pos: tuple[int, int],
        visible: bool | None = None,
    ) -> None:
        player_id, screen_name, player_pos = self._seat_player_debug(seat)
        block = self.block_layouts[block_index]
        msg = (
            f"HUD BOX {reason} table={getattr(self.hud.table, 'key', '')} display_seat={seat} "
            f"layout_seat={self.adj[seat] if (hasattr(self, 'adj') and isinstance(seat, int) and seat < len(self.adj)) else seat} "
            f"player_id={player_id} player={screen_name!r} hand_pos={player_pos!r} "
            f"block={block_index} label={block.get('label', '')!r} block_pos={block.get('position', '')!r} "
            f"rel={rel_pos} abs={abs_pos} visible={visible}"
        )
        log.warning(msg)

        # Log to the dedicated trace log if active
        trace_logger = logging.getLogger("hud_trace")
        if trace_logger.handlers:
            trace_logger.info(msg)

    # -- Single coordinate model -------------------------------------------
    #
    # Block windows are stored in ONE space: "canonical" = unscaled coordinates
    # in the reference-layout space, measured from the table's top-left corner.
    # block_positions[key] and the on-disk positions store both hold canonical
    # values. The only scaling happens at display time, through the single
    # converter _canonical_to_screen(); its inverse is _screen_to_canonical().
    # Because the reference dimensions are frozen once (never the live, mutated
    # layout size), a resize A->B->A round-trips a window back to exactly A.

    def _ensure_reference(self) -> None:
        """Freeze the reference layout size once, from the config layout.

        Shared with Hud.resize_windows via hud.ref_layout_*, so both the resize
        path and the block windows divide by the same stable denominator.
        """
        if not getattr(self.hud, "ref_layout_width", None):
            self.hud.ref_layout_width = self.hud.layout.width or 792
            self.hud.ref_layout_height = self.hud.layout.height or 546

    @property
    def scale_factors(self) -> tuple[float, float]:
        self._ensure_reference()
        ref_w = self.hud.ref_layout_width or 792
        ref_h = self.hud.ref_layout_height or 546
        table_w = self.hud.table.width or ref_w
        table_h = self.hud.table.height or ref_h
        return float(table_w) / ref_w, float(table_h) / ref_h

    def _table_origin(self) -> tuple[int, int]:
        table_x = self.hud.table.x if self.hud.table.x is not None else 0
        table_y = self.hud.table.y if self.hud.table.y is not None else 0
        return max(0, table_x), max(0, table_y)

    def _canonical_to_screen(self, canon: tuple[int, int]) -> tuple[int, int]:
        """Convert a canonical block position to an absolute screen position.

        The screen clamp here is display-only and is never fed back into the
        stored canonical value.
        """
        x_scale, y_scale = self.scale_factors
        table_x, table_y = self._table_origin()
        screen_x = int(round(canon[0] * x_scale)) + table_x
        screen_y = int(round(canon[1] * y_scale)) + table_y
        return Aux_Base.clamp_to_screen(screen_x, screen_y)

    def _screen_to_canonical(self, abs_x: int, abs_y: int) -> tuple[int, int]:
        """Inverse of _canonical_to_screen, without the display-only clamp."""
        x_scale, y_scale = self.scale_factors
        table_x, table_y = self._table_origin()
        return (
            int(round((abs_x - table_x) / x_scale)),
            int(round((abs_y - table_y) / y_scale)),
        )

    def _default_canonical(self, key: tuple[int | str, int]) -> tuple[int, int]:
        """Layout-default canonical position for a block that has never moved."""
        seat, block_index = key
        offset_x, offset_y = self._block_offset(block_index)
        if seat == "table":
            return (offset_x, offset_y)
        anchor_x, anchor_y = getattr(self, "_seat_anchor_ref", {}).get(seat, (0, 0))
        if self._positional_mode() == "all":
            # The imported x/y offsets assume one panel is shown at a time. When
            # showing them all, lay the player blocks out as a clean vertical
            # stack instead (a starting layout; the user can drag to fine-tune,
            # and drags persist and override this).
            return (anchor_x, anchor_y + self._stack_offset(block_index))
        return (anchor_x + offset_x, anchor_y + offset_y)

    def _stack_offset(self, block_index: int) -> int:
        """Cumulative height of the player blocks laid out before this one, so
        'all'-mode blocks stack vertically without overlapping. Heights are
        estimated from each block's grid row count (drag corrects any drift)."""
        row_px, title_px, pad_px = 15, 18, 5
        offset = 0
        for i in range(block_index):
            b = self.block_layouts[i]
            if b.get("scope") == "table":
                continue
            offset += int(b.get("nrows", 1) or 1) * row_px + (title_px if b.get("label") else 0) + pad_px
        return offset

    def _canonical_for(self, key: tuple[int | str, int]) -> tuple[int, int]:
        """Canonical position for a block window.

        Priority: a user drag saved to the positions store, then the value
        computed at create time, then the layout default. A saved position for
        one (seat, block) key can never affect another key.
        """
        seat, block_index = key
        stored = get_positions_store().get_position(
            self.hud.site,
            getattr(self.hud.layout, "name", "default"),
            getattr(self.game_params, "name", "default"),
            self.hud.max,
            seat,
            block_index,
        )
        if stored is not None:
            return stored
        if key in self.block_positions:
            return self.block_positions[key]
        return self._default_canonical(key)

    def create(self) -> None:
        """Create classic one-window seats or PT4-style one-window-per-block seats."""
        if not self._uses_block_windows():
            super().create()
            return

        log.debug("=== SIMPLEHUD MULTI-BLOCK CREATE() METHOD CALLED ===")
        self.adj = self.adj_seats()
        self.hero_display_seat = self._hero_display_seat()
        self.m_windows = {}
        self.block_positions = {}
        # Unscaled reference seat anchors, captured once. Kept separate from the
        # live layout.location (which Hud.resize_windows rescales) so canonical
        # defaults stay stable across resizes.
        self._seat_anchor_ref = {}
        self._ensure_reference()

        x, y = self.hud.layout.common
        self.m_windows["common"] = self.create_common(x, y)
        self.hud.layout.common = self.create_scale_position(x, y)

        # Create player seat windows
        for seat in range(1, self.hud.max + 1):
            anchor = self.hud.layout.location[self.adj[seat]]
            self._seat_anchor_ref[seat] = anchor
            self.positions[seat] = self.create_scale_position(*anchor)
            for block_index, blk in enumerate(self.block_layouts):
                if blk.get("scope") == "table":
                    continue
                self._create_block_window((seat, block_index), seat)

        # Create table-scoped windows
        for block_index, blk in enumerate(self.block_layouts):
            if blk.get("scope") != "table":
                continue
            self._create_block_window(("table", block_index), "table")

        self.m_windows["common"].create()
        self.hud.table.topify(self.m_windows["common"])
        if not self.uses_timer:
            self.m_windows["common"].show()

    def _create_block_window(self, key: tuple[int | str, int], seat: int | str) -> None:
        """Create one block window and place it via the single coordinate model."""
        block_index = key[1]
        blk = self.block_layouts[block_index]
        canon = self._canonical_for(key)
        self.block_positions[key] = canon

        window = self.aw_class_window(self, seat)
        window.block_index = block_index
        window.block_key = key
        self.m_windows[key] = window

        screen_x, screen_y = self._canonical_to_screen(canon)
        window.move(screen_x, screen_y)
        window._pos_gen = getattr(self.hud, "geometry_generation", 0)
        reason = "create-table" if seat == "table" else "create"
        self._log_block_window_position(reason, seat, block_index, canon, (screen_x, screen_y))
        if "opacity" in self.params:
            window.setWindowOpacity(float(self.params["opacity"]))
        try:
            self.create_contents(window, seat)
            window.create()
            self.hud.table.topify(window)
            self.update_contents(window, seat)
        except Exception:
            # Isolate a failing block so the other windows still get built.
            log.exception(
                "HUD create: block key=%r label=%r failed; skipping it",
                key,
                blk.get("label", ""),
            )

    def _move_block_windows(self) -> None:
        table_x, table_y = self._table_origin()
        for key, window in list(self.m_windows.items()):
            if key == "common":
                common_x = self.hud.layout.common[0] + table_x
                common_y = self.hud.layout.common[1] + table_y
                clamped_x, clamped_y = Aux_Base.clamp_to_screen(common_x, common_y)
                window.move(clamped_x, clamped_y)
                continue

            seat, block_index = key
            canon = self._canonical_for(key)
            screen_x, screen_y = self._canonical_to_screen(canon)
            window.move(screen_x, screen_y)
            window._pos_gen = getattr(self.hud, "geometry_generation", 0)
            self._log_block_window_position("move", seat, block_index, canon, (screen_x, screen_y))

    def resize_windows(self) -> None:
        if not self._uses_block_windows():
            super().resize_windows()
            return
        for seat in range(1, self.hud.max + 1):
            self.positions[seat] = self.hud.layout.location[self.adj[seat]]
        self.positions["common"] = self.hud.layout.common
        self.move_windows()

    def _block_label(self, key: str | tuple[int | str, int]) -> str:
        """Human-readable name for an m_windows key, for diagnostics."""
        if key == "common":
            return "common"
        with suppress(Exception):
            return self.block_layouts[key[1]].get("label", "") or f"block#{key[1]}"
        return str(key)

    def update_gui(self, _new_hand_id: Any) -> None:
        if not self._uses_block_windows():
            super().update_gui(_new_hand_id)
            return
        windows = list(self.m_windows.items())
        expected = len(windows)
        updated = 0
        failed = 0
        for key, window in windows:
            try:
                self.update_contents(window, key if key == "common" else key[0])
                if key != "common":
                    seat, block_index = key
                    rel_pos = self.block_positions.get(key, self.positions.get(seat, (0, 0)))
                    abs_pos = (window.pos().x(), window.pos().y())
                    self._log_block_window_position("update", seat, block_index, rel_pos, abs_pos, window.isVisible())
                updated += 1
            except Exception:
                # Isolate the failing window: name it, then carry on so one bad
                # block can't stop every other window from refreshing (which is
                # what made stats and names look frozen across the whole table).
                failed += 1
                log.exception(
                    "HUD update_gui: window key=%r label=%r failed for hand %s; skipping it",
                    key,
                    self._block_label(key),
                    _new_hand_id,
                )
        hud_trace(
            "update_gui: %d/%d windows updated (%d failed) for hand %s",
            updated,
            expected,
            failed,
            _new_hand_id,
        )

    def configure_event_cb(self, widget: Aux_Base.SeatWindow, i: int | str | tuple[int, int]) -> None:
        block_index = getattr(widget, "block_index", None)
        if block_index is None:
            super().configure_event_cb(widget, i)
            return
        seat = widget.seat
        new_abs_position = widget.pos()
        # Persist the canonical position derived from the actual (unclamped) drop
        # point, via the single inverse converter. Only this (seat, block) key is
        # written, so dragging one window never disturbs another seat's blocks.
        canonical_x, canonical_y = self._screen_to_canonical(new_abs_position.x(), new_abs_position.y())

        store = get_positions_store()
        layout_name = getattr(self.hud.layout, "name", "default")
        stat_set = getattr(self.game_params, "name", "default")
        store.set_position(
            self.hud.site, layout_name, stat_set, self.hud.max, seat, block_index, canonical_x, canonical_y
        )

        self.block_positions[(seat, block_index)] = (canonical_x, canonical_y)
        self._log_block_window_position("drag-save", seat, block_index, (canonical_x, canonical_y), (new_abs_position.x(), new_abs_position.y()))

    def save_layout(self, *_args: Any) -> None:
        """Save the current HUD layout configuration.

        This method saves the positions of all HUD elements for the current table layout to the configuration.
        """
        new_locs = {self.adj[int(i)]: ((pos[0]), (pos[1])) for i, pos in list(self.positions.items()) if i != "common"}
        log.info("Saving layout for %s-max table: %s", self.hud.max, new_locs)
        self.config.save_layout_set(
            self.hud.layout_set,
            self.hud.max,
            new_locs,
            self.hud.table.width,
            self.hud.table.height,
        )
        self._save_block_offsets()
        log.info("Layout saved successfully")

    def _save_block_offsets(self) -> None:
        if not self._uses_block_windows():
            return
        stat_set_node = self.config.get_stat_set_node(self.game_params.name)
        if stat_set_node is None:
            return
        block_nodes = stat_set_node.getElementsByTagName("block")
        for idx, block_node in enumerate(block_nodes):
            if idx >= len(self.block_layouts):
                break
            block_node.setAttribute("x", str(int(self.block_layouts[idx].get("x", 0) or 0)))
            block_node.setAttribute("y", str(int(self.block_layouts[idx].get("y", 0) or 0)))


class SimpleStatWindow(Aux_Base.SeatWindow):
    """Simple window class for stat windows."""

    def __init__(self, aw: Any | None = None, seat: Any | None = None) -> None:
        """Initializes the SimpleStatWindow for a specific seat.

        This constructor sets up the stat window, initializes the popup count, and sets the window title.

        Args:
            aw: The auxiliary HUD object providing context and configuration.
            seat: The seat number associated with this stat window.
        """
        super().__init__(aw, seat)
        self.popup_count = 0
        self.setWindowTitle(_t("HUD - stats"))

    # button_release_left is inherited from Aux_Base.SeatWindow: it releases the
    # drag grab and, only if the window actually moved, calls configure_event_cb
    # (which resolves the block from widget.block_index). Overriding it here used
    # to persist on every click, filling the position store with stale offsets.

    def button_release_right(self, event: Any) -> None:  # show pop up
        """Show a popup window with detailed statistics when the right mouse button is released.

        This method displays a popup with additional stat information for the widget under the cursor,
        provided the widget contains stats and no other popup is currently active.

        Args:
            event: The mouse event triggering the popup.
        """
        widget = self.childAt(event.pos())

        if (
            widget
            and hasattr(widget, "stat_dict")
            and widget.stat_dict
            and self.popup_count == 0
            and hasattr(widget, "aw_popup")
            and widget.aw_popup
        ):
            # do not popup on empty blocks or if one is already active
            pu = Popup.popup_factory(
                seat=widget.aw_seat,
                stat_dict=widget.stat_dict,
                win=self,
                pop=self.aw.config.popup_windows[widget.aw_popup],
                hand_instance=self.aw.hud.hand_instance,
                config=self.aw.config,
                anchor_widget=widget,
            )
            pu.setStyleSheet(
                f"QWidget{{background:{self.aw.bgcolor};color:{self.aw.fgcolor};}}QToolTip{{}}",
            )

    def create_contents(self, _i: int) -> None:
        """Create and lay out the stat widgets for the stat window.

        This method initializes the grid layout and populates it with stat widgets for each row and column.
        """
        self.setStyleSheet(
            f"QWidget{{background:{self.aw.bgcolor};color:{self.aw.fgcolor};}}QToolTip{{}}",
        )
        # A seat window stacks one grid per PT4-style panel ("block"). The classic
        # single-grid layout is simply a one-block stack, so behaviour is
        # unchanged for existing configs.
        outer = QVBoxLayout()
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(3)
        self.setLayout(outer)

        all_blocks = getattr(self.aw, "block_layouts", None) or [
            {"label": "", "position": "", "nrows": self.aw.nrows, "ncols": self.aw.ncols,
             "bgcolor": "", "fgcolor": "", "bordercolor": "", "title_bgcolor": "", "title_fgcolor": "",
             "hudcolors": [[""] * self.aw.ncols for _ in range(self.aw.nrows)],
             "hudbgcolors": [[""] * self.aw.ncols for _ in range(self.aw.nrows)],
             "stats": self.aw.stats, "popups": self.aw.popups, "tips": self.aw.tips},
        ]
        multi = len(all_blocks) > 1
        block_index = getattr(self, "block_index", None)
        blocks = [all_blocks[block_index]] if block_index is not None else all_blocks
        self.stat_boxes = []  # one 2D array of SimpleStat per block
        self.block_widgets = []  # (container widget, position) per block, for show/hide
        for blk in blocks:
            container = QWidget()
            if multi:
                panel_bg = blk.get("bgcolor") or "rgba(0, 0, 0, 178)"
                panel_fg = blk.get("fgcolor") or self.aw.fgcolor
                border = blk.get("bordercolor") or panel_fg
                container.setStyleSheet(
                    "QWidget{"
                    f"background: {panel_bg};"
                    f"border: 1px solid {border};"
                    "}"
                    "QLabel{"
                    "border: 0;"
                    "background: transparent;"
                    f"color: {panel_fg};"
                    "padding: 0px 3px;"
                    "}"
                )
            cl = QVBoxLayout(container)
            if multi:
                cl.setContentsMargins(2, 1, 2, 2)
            else:
                cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0 if multi else 1)
            if multi and blk["label"]:
                title = self.aw.aw_class_label(blk["label"])
                title.setAlignment(Qt.AlignmentFlag.AlignCenter)
                title_bg = blk.get("title_bgcolor") or blk.get("bordercolor") or panel_fg
                title_fg = blk.get("title_fgcolor") or self.aw.bgcolor
                title.setStyleSheet(
                    f"background: {title_bg};"
                    f"color: {title_fg};"
                    "font-weight: 700;"
                    "padding: 1px 4px;"
                    "border: 0;"
                )
                cl.addWidget(title)
            grid = QGridLayout()
            grid.setHorizontalSpacing(2 if multi else 4)
            grid.setVerticalSpacing(1)
            grid.setContentsMargins(1 if multi else 0, 1 if multi else 0, 1 if multi else 0, 0)
            box = [[None] * blk["ncols"] for _ in range(blk["nrows"])]
            btexts = blk.get("texts", [])
            # When the panel carries explicit PT4 text items (column/row headers,
            # captions) render them at their grid positions; otherwise fall back to
            # the per-stat tip-as-header mode.
            show_headers = multi and not btexts and any(tip for row in blk["tips"] for tip in row)
            for t in btexts:
                tr, tc = t["rowcol"]
                if not (0 <= tr < blk["nrows"] and 0 <= tc < blk["ncols"]):
                    continue
                tlabel = self.aw.aw_class_label(t.get("label", ""))
                tlabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tlabel.setFont(self.aw.font)
                t_fg = t.get("fgcolor") or ""
                t_bg = t.get("bgcolor") or ""
                tlabel.setStyleSheet(
                    "font-weight:700;padding:0px 2px;border:0;"
                    + (f"color:{t_fg};" if t_fg else "")
                    + (f"background:{t_bg};" if t_bg else ""),
                )
                grid.addWidget(tlabel, tr, tc, 1, max(1, int(t.get("colspan", 1))))
            for r in range(blk["nrows"]):
                for c in range(blk["ncols"]):
                    grid_row = r * 2 if show_headers else r
                    if show_headers:
                        label = self.aw.aw_class_label(blk["tips"][r][c] or "")
                        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        label.setFont(self.aw.font)
                        label.setStyleSheet("font-weight: 700; padding: 0px 2px;")
                        grid.addWidget(label, grid_row, c)
                    stat_name = blk["stats"][r][c]
                    if stat_name:
                        cranges = blk.get("colorranges")
                        cr = cranges[r][c] if cranges else None
                        box[r][c] = self.aw.aw_class_stat(
                            stat_name, seat=self.seat, popup=blk["popups"][r][c], aw=self.aw, colors=cr,
                        )
                        if blk["hudcolors"][r][c] or blk["hudbgcolors"][r][c]:
                            box[r][c].set_color(fg=blk["hudcolors"][r][c], bg=blk["hudbgcolors"][r][c])
                        span = max(1, (blk.get("colspans") or [[1]])[r][c] if blk.get("colspans") else 1)
                        align = (blk.get("aligns") or [[""]])[r][c] if blk.get("aligns") else ""
                        if align:
                            box[r][c].widget.setAlignment(_ALIGN.get(align, Qt.AlignmentFlag.AlignCenter))
                        grid.addWidget(box[r][c].widget, grid_row + 1 if show_headers else grid_row, c, 1, span)
                        box[r][c].widget.setFont(self.aw.font)
                        if multi:
                            box[r][c].widget.setMinimumWidth(20)
                    elif not btexts:
                        # Keep empty placeholders only in the legacy (no-text) mode;
                        # with text items the empty cells are intentional spacing.
                        box[r][c] = EmptyStat(aw=self.aw)
                        grid.addWidget(box[r][c].widget, grid_row + 1 if show_headers else grid_row, c)
                        box[r][c].widget.setFont(self.aw.font)
                    else:
                        box[r][c] = EmptyStat(aw=self.aw)
            # Horizontal-line separators (PT4 "Horz Line" items).
            for h in blk.get("hlines", []):
                hr, hc = h["rowcol"]
                if not (0 <= hr < blk["nrows"]):
                    continue
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Plain)
                color = h.get("color") or self.aw.fgcolor
                line.setStyleSheet(f"color: {color}; background: {color};")
                line.setFixedHeight(1)
                hspan = h.get("colspan") or blk["ncols"]
                hrow = hr * 2 if show_headers else hr
                grid.addWidget(line, hrow, hc, 1, max(1, hspan))
            cl.addLayout(grid)
            outer.addWidget(container)
            self.stat_boxes.append(box)
            self.block_widgets.append((container, blk.get("position", "")))
        # Legacy alias: keep self.stat_box pointing at the first block's grid.
        self.stat_box = self.stat_boxes[0] if self.stat_boxes else []

    def update_contents(self, i: int | str) -> None:
        """Update the stat widgets for the specified seat.

        Refreshes all stat widgets and, for position-bound blocks, shows only the
        panel matching the player's position this hand (others are hidden).

        Args:
            i: The seat identifier to update.
        """
        if i == "common":
            return

        if i == "table":
            self.show()
            has_visible_block = False
            for box, (container, block_pos) in zip(self.stat_boxes, self.block_widgets, strict=False):
                container.setVisible(True)
                has_visible_block = True
                for row in box:
                    for stat in row:
                        if stat is not None:
                            stat.update(None, self.aw.hud.stat_dict)
            if not has_visible_block:
                self.hide()
            else:
                self.adjustSize()
            return

        player_id = self.aw.get_id_from_seat(i)
        if player_id is None:
            self.hide()
            return
        pdata = self.aw.hud.stat_dict.get(player_id) if self.aw.hud.stat_dict else None
        if self.aw._hide_seat_for_villain_only(i, pdata):
            self.hide()
            return

        self.show()

        player_pos = ""
        if pdata is not None:
            # Prefer live_position (the current hand, estimated by advancing the
            # button) over the imported last-hand position, so "current" mode
            # shows the panel for where the villain actually sits now.
            player_pos = pdata.get("live_position") or pdata.get("position", "")
        # In "all" mode every position panel is shown (stacked), because an
        # import-driven HUD only knows the *previous* hand's position and would
        # otherwise display a one-hand-stale panel. "current" filters by position.
        show_all_positions = self.aw._positional_mode() == "all"
        has_visible_block = False
        for box, (container, block_pos) in zip(self.stat_boxes, self.block_widgets, strict=False):
            visible = True if show_all_positions else block_visible(block_pos, player_pos)
            container.setVisible(visible)
            if not visible:
                continue
            has_visible_block = True
            for row in box:
                for stat in row:
                    if stat is not None:
                        stat.update(player_id, self.aw.hud.stat_dict)
        if not has_visible_block:
            self.hide()
        else:
            self.adjustSize()


class SimpleStat:
    """A simple class for displaying a single stat."""

    def __init__(self, stat: str, seat: int | str, popup: str, aw: Any, colors: dict | None = None) -> None:
        """Initializes a SimpleStat instance for displaying a single statistic.

        This constructor sets up the label, associates it with the correct seat and popup,
        and stores relevant HUD context.

        Args:
            stat: The name of the statistic to display.
            seat: The seat number associated with the statistic.
            popup: The popup configuration or identifier for the stat.
            aw: The auxiliary HUD object providing context and configuration.
            colors: Optional PT4-style colour-range config (loth/hith/locolor/
                midcolor/hicolor) applied to the value at update time.
        """
        self.stat = stat
        self.lab = aw.aw_class_label(
            "---",
        )  # --- is used as initial value because longer labels don't shrink
        self.lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if seat == "table" or seat == "common":
            self.lab.aw_seat = seat
        else:
            try:
                self.lab.aw_seat = aw.hud.layout.hh_seats[seat]
            except (KeyError, IndexError, TypeError):
                self.lab.aw_seat = seat
        self.lab.aw_popup = popup
        self.lab.stat_dict = None
        self.widget = self.lab
        self.stat_dict = None
        self.hud = aw.hud
        self.aux_params = aw.aux_params
        self.colors = colors or {}
        self._bg = ""

    def update(self, player_id: str | None, stat_dict: dict) -> None:
        """Update the statistic display for a given player.

        This method recalculates the statistic value and updates the label text for the specified player.

        Args:
            player_id: The unique identifier of the player.
            stat_dict: A dictionary containing statistics for all players.
        """
        self.stat_dict = stat_dict  # So the Simple_stat obj always has a fresh stat_dict
        self.lab.stat_dict = stat_dict

        # Two scopes, both computed in Stats (the single source of truth), never
        # with inline SQL here (this runs on the UI thread, once per label).
        #  - player scope: do_stat, indexed by player id.
        #  - table scope (player_id is None): do_table_stat, reading the value
        #    HUD_main precomputed once for this hand onto hud.table_stats.
        # Earlier revisions inlined SQL/name-shortening here; that duplicated
        # logic, broke the 6-tuple contract (ClassicStat's number[5] tooltip),
        # and hard-coded a %s placeholder that fails on SQLite.
        if player_id is None:
            self.number = Stats.do_table_stat(getattr(self.hud, "table_stats", {}), self.stat)
        else:
            self.number = Stats.do_stat(
                stat_dict,
                player_id,
                self.stat,
                self.hud.hand_instance,
            )
        if self.number:
            self.lab.setText(str(self.number[1]))
        self._apply_color_range()

    def _apply_color_range(self) -> None:
        """Colour the label by value using the PT4-style thresholds (if any).

        Mirrors Aux_Classic_Hud: value < loth -> locolor, < hith -> midcolor,
        else hicolor. Keeps the configured static background.
        """
        cr = self.colors
        if not cr or not cr.get("loth") or not cr.get("hith") or not self.number:
            return
        try:
            value = float(str(self.number[1]).replace("%", "").replace(",", ".").strip())
            loth, hith = float(cr["loth"]), float(cr["hith"])
        except (TypeError, ValueError):
            return
        if value < loth:
            fg = cr.get("locolor")
        elif value < hith:
            fg = cr.get("midcolor") or cr.get("hicolor")
        else:
            fg = cr.get("hicolor")
        if fg:
            self.set_color(fg=fg, bg=self._bg or None)

    def set_color(self, fg: str | None = None, bg: str | None = None) -> None:
        """Set the foreground and background color of the stat label.

        This method updates the label's stylesheet to apply the specified font, foreground, and background colors.

        Args:
            fg: The foreground (text) color to apply.
            bg: The background color to apply.
        """
        if bg:
            self._bg = bg
        ss = f"QLabel{{font-family: {self.aux_params['font']};font-size: {self.aux_params['font_size']}pt;"
        if fg:
            ss += f"color: {fg};"
        if bg:
            ss += f"background: {bg};"
        self.lab.setStyleSheet(ss + "}")


class EmptyStat:
    """A non-interactive placeholder for intentionally empty HUD grid cells."""

    def __init__(self, aw: Any) -> None:
        self.stat = None
        self.widget = aw.aw_class_label("")
        self.widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.widget.stat_dict = None
        self.widget.aw_popup = None

    def update(self, _player_id: str, _stat_dict: dict) -> None:
        return


class SimpleLabel(QLabel):
    """A simple label class."""


class SimpleTableMW(Aux_Base.SeatWindow):
    """Create a default table hud menu label."""

    #    This is a recreation of the table main window from the default HUD
    #    in the old Hud.py. This has the menu options from that hud.

    #    BTW: It might be better to do this with a different AW.

    def __init__(self, hud: Any, aw: Any | None = None) -> None:
        """Initializes the SimpleTableMW, the main table HUD menu window.

        This constructor sets up the menu label, icon, layout, and positions the menu window relative to the table.

        Args:
            hud: The HUD instance associated with the table.
            aw: The auxiliary HUD object providing context and configuration.
        """
        super().__init__(aw)
        self.hud = hud
        self.aw = aw
        self.menu_is_popped = False

        # self.connect("configure_event", self.configure_event_cb, "auxmenu") base class will deal with this

        try:
            self.menu_label = hud.hud_params["label"]
        except KeyError:
            self.menu_label = "fpdb menu"

        lab = QLabel(self.menu_label)
        logo = Path(Configuration.GRAPHICS_PATH) / "tribal.jpg"
        pixmap = QPixmap(str(logo))
        pixmap = pixmap.scaled(45, 45)
        lab.setPixmap(pixmap)
        lab.setStyleSheet(f"background: {self.aw.bgcolor}; color: {self.aw.fgcolor};")

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(lab)

        table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
        table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50
        pos_x = table_x + self.aw.xshift
        pos_y = table_y + self.aw.yshift
        clamped_x, clamped_y = Aux_Base.clamp_to_screen(pos_x, pos_y, 100, 100)
        self.move(clamped_x, clamped_y)

    def button_press_right(self, _event: Any) -> None:
        """Show the table popup menu when the right mouse button is pressed.

        This method displays the table popup menu if it is not already open.

        Args:
            _event: The mouse event triggering the popup menu.
        """
        if not self.menu_is_popped:
            self.menu_is_popped = True
            SimpleTablePopupMenu(self)

    def move_windows(self) -> None:
        """Move the table menu window to its correct position relative to the table.

        This method repositions the menu window based on the table's current coordinates and configured offsets.
        """
        # force menu to the offset position from table origin (do not use common setting)
        table_x = max(0, self.hud.table.x) if self.hud.table.x is not None else 50
        table_y = max(0, self.hud.table.y) if self.hud.table.y is not None else 50
        pos_x = table_x + self.aw.xshift
        pos_y = table_y + self.aw.yshift
        clamped_x, clamped_y = Aux_Base.clamp_to_screen(pos_x, pos_y)
        self.move(clamped_x, clamped_y)


class SimpleTablePopupMenu(QWidget):
    """A simple table popup menu."""

    def __init__(self, parentwin: Any) -> None:
        """Initializes the SimpleTablePopupMenu for HUD configuration.

        This constructor sets up the popup menu window, positions it relative to the table, and initializes the UI.

        Args:
            parentwin: The parent window instance that owns this popup menu.
        """
        # WindowStaysOnTopHint is required so the config menu appears ABOVE the
        # always-on-top HUD seat windows; without it the menu is created visible
        # but rendered behind them and the user never sees it.
        super().__init__(
            None,
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.parentwin = parentwin
        table_x = max(0, self.parentwin.hud.table.x) if self.parentwin.hud.table.x is not None else 50
        table_y = max(0, self.parentwin.hud.table.y) if self.parentwin.hud.table.y is not None else 50
        pos_x = table_x + self.parentwin.aw.xshift
        pos_y = table_y + self.parentwin.aw.yshift
        clamped_x, clamped_y = Aux_Base.clamp_to_screen(pos_x, pos_y, 400, 300)  # Larger window size
        self.move(clamped_x, clamped_y)
        self.setWindowTitle(f"{self.parentwin.menu_label} - HUD configuration")
        self._setup_ui()
        self.show()
        self.raise_()

    def _setup_ui(self) -> None:
        """Set up the user interface for the table popup menu.

        This method initializes the combo box dictionaries, creates the main controls and stats configuration boxes,
        and arranges them in the popup menu layout.
        """
        # Dictionaries for combo boxes
        stat_range_combo_dict = self._create_stat_range_dict()
        seats_style_combo_dict = self._create_seats_style_dict()
        multiplier_combo_dict = self._create_multiplier_dict()
        cb_max_dict = self._create_max_seats_dict()

        # Layouts
        grid = QGridLayout()
        self.setLayout(grid)
        vbox1 = self._create_main_controls(cb_max_dict)
        vbox2 = self._create_player_stats_box(
            multiplier_combo_dict,
            seats_style_combo_dict,
            stat_range_combo_dict,
        )
        vbox3 = self._create_opponent_stats_box(
            multiplier_combo_dict,
            seats_style_combo_dict,
            stat_range_combo_dict,
        )

        self.set_spinners_active()

        grid.addLayout(vbox1, 0, 0)
        grid.addLayout(vbox2, 0, 1)
        grid.addLayout(vbox3, 0, 2)
        grid.addWidget(QLabel(f"Stat set: {self.parentwin.aw.game_params.name}"), 1, 0)

    def _create_main_controls(self, cb_max_dict: dict) -> QVBoxLayout:
        """Create the main control buttons and selectors for the popup menu.

        This method adds buttons for HUD control actions and, if available, a stat set selector and max seats combo box.

        Args:
            cb_max_dict: The dictionary for the max seats combo box.

        Returns:
            QVBoxLayout: The vertical layout containing all main controls.
        """
        vbox = QVBoxLayout()
        vbox.addWidget(self.build_button("Restart This HUD", "kill"))
        vbox.addWidget(self.build_button("Save HUD Layout", "save"))
        vbox.addWidget(self.build_button("Stop this HUD", "blacklist"))
        vbox.addWidget(self.build_button("Close", "close"))
        vbox.addWidget(QLabel(""))

        # Add stat set selector
        stat_sets_dict = self._create_stat_sets_dict()
        if len(stat_sets_dict) > 1:  # Only show if there are multiple stat sets
            vbox.addWidget(QLabel(_t("Stat Set (HUD):")))
            self.stat_set_combo = self.build_stat_set_combo(stat_sets_dict)
            vbox.addWidget(self.stat_set_combo)
            vbox.addWidget(QLabel(""))

        vbox.addWidget(self.build_combo_and_set_active("new_max_seats", cb_max_dict))
        return vbox

    def _create_player_stats_box(
        self,
        multiplier_dict: dict,
        seats_style_dict: dict,
        stat_range_dict: dict,
    ) -> QVBoxLayout:
        """Create the player stats configuration box for the popup menu.

        This method builds and arranges the controls for configuring player stats display,
        including combo boxes and spinners.

        Args:
            multiplier_dict: The dictionary for the multiplier combo box.
            seats_style_dict: The dictionary for the seats style combo box.
            stat_range_dict: The dictionary for the stat range combo box.

        Returns:
            QVBoxLayout: The vertical layout containing all player stats controls.
        """
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel(_t("Show Player Stats for")))
        vbox.addWidget(
            self.build_combo_and_set_active("h_agg_bb_mult", multiplier_dict),
        )
        vbox.addWidget(
            self.build_combo_and_set_active("h_seats_style", seats_style_dict),
        )
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_t("Custom")))
        self.h_nums_low_spinner = self.build_spinner("h_seats_cust_nums_low", 1, 9)
        hbox.addWidget(self.h_nums_low_spinner)
        hbox.addWidget(QLabel(_t("To")))
        self.h_nums_high_spinner = self.build_spinner("h_seats_cust_nums_high", 2, 10)
        hbox.addWidget(self.h_nums_high_spinner)
        vbox.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(
            self.build_combo_and_set_active("h_stat_range", stat_range_dict),
        )
        self.h_hud_days_spinner = self.build_spinner("h_hud_days", 1, 9999)
        hbox.addWidget(self.h_hud_days_spinner)
        vbox.addLayout(hbox)
        return vbox

    def _create_opponent_stats_box(
        self,
        multiplier_dict: dict,
        seats_style_dict: dict,
        stat_range_dict: dict,
    ) -> QVBoxLayout:
        """Create the opponent stats configuration box for the popup menu.

        This method builds and arranges the controls for configuring opponent stats display,
        including combo boxes and spinners.

        Args:
            multiplier_dict: The dictionary for the multiplier combo box.
            seats_style_dict: The dictionary for the seats style combo box.
            stat_range_dict: The dictionary for the stat range combo box.

        Returns:
            QVBoxLayout: The vertical layout containing all opponent stats controls.
        """
        vbox = QVBoxLayout()
        vbox.addWidget(QLabel(_t("Show Opponent Stats for")))
        vbox.addWidget(self.build_combo_and_set_active("agg_bb_mult", multiplier_dict))
        vbox.addWidget(
            self.build_combo_and_set_active("seats_style", seats_style_dict),
        )
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(_t("Custom")))
        self.nums_low_spinner = self.build_spinner("seats_cust_nums_low", 1, 9)
        hbox.addWidget(self.nums_low_spinner)
        hbox.addWidget(QLabel(_t("To")))
        self.nums_high_spinner = self.build_spinner("seats_cust_nums_high", 2, 10)
        hbox.addWidget(self.nums_high_spinner)
        vbox.addLayout(hbox)
        hbox = QHBoxLayout()
        hbox.addWidget(self.build_combo_and_set_active("stat_range", stat_range_dict))
        self.hud_days_spinner = self.build_spinner("hud_days", 1, 9999)
        hbox.addWidget(self.hud_days_spinner)
        vbox.addLayout(hbox)
        return vbox

    def _create_stat_range_dict(self) -> dict:
        """Create the dictionary for the stat range combo box.

        This method returns a dictionary mapping stat range options to their display labels and codes.

        Returns:
            dict: The dictionary for the stat range combo box.
        """
        return {
            0: ("Since: All Time", "A"),
            1: ("Since: Session", "S"),
            2: ("Since: n Days" + " - - >", "T"),
        }

    def _create_seats_style_dict(self) -> dict:
        """Create the dictionary for the seats style combo box.

        This method returns a dictionary mapping seat style options to their display labels and codes.

        Returns:
            dict: The dictionary for the seats style combo box.
        """
        return {
            0: ("Number of Seats: Any Number", "A"),
            1: ("Number of Seats: Custom", "C"),
            2: ("Number of Seats: Exact", "E"),
        }

    def _create_multiplier_dict(self) -> dict:
        """Create the dictionary for the multiplier combo box.

        This method returns a dictionary mapping multiplier options to their display labels and values.

        Returns:
            dict: The dictionary for the multiplier combo box.
        """
        return {
            0: ("For This Blind Level Only", 1),
            1: ("  0.5 to 2 * Current Blinds", 2),
            2: ("  0.33 to 3 * Current Blinds", 3),
            3: ("  0.1 to 10 * Current Blinds", 10),
            4: ("All Levels", 10000),
        }

    def _create_max_seats_dict(self) -> dict:
        """Create the dictionary for the max seats combo box.

        This method returns a dictionary mapping available table layouts to their display labels and values.

        Returns:
            dict: The dictionary for the max seats combo box.
        """
        cb_max_dict = {0: ("Force layout...", None)}
        for pos, i in enumerate(
            sorted(self.parentwin.hud.layout_set.layout),
            start=1,
        ):
            cb_max_dict[pos] = (f"{i}-max", i)
        return cb_max_dict

    def _create_stat_sets_dict(self) -> dict:
        """Create the dictionary for the stat set combo box.

        This method returns a dictionary mapping available stat sets to their display labels and values.

        Returns:
            dict: The dictionary for the stat set combo box.
        """
        stat_sets = self.parentwin.hud.config.get_stat_sets()
        return {i: (stat_set_name, stat_set_name) for i, stat_set_name in enumerate(stat_sets)}

    def delete_event(self) -> None:
        """Handle the event to close and destroy the popup menu.

        This method resets the menu state in the parent window and destroys the popup menu instance.
        """
        self.parentwin.menu_is_popped = False
        self.destroy()

    def callback(self, _check_state: Any, data: str | None = None) -> None:
        """Handle button callbacks for popup menu actions.

        This method processes actions such as killing the HUD, blacklisting, saving the layout, and closing the popup.

        Args:
            _check_state: The state of the triggering event (unused).
            data: The action keyword indicating which operation to perform.
        """
        if data == "kill":
            self.parentwin.hud.parent.kill_hud("kill", self.parentwin.hud.table.key)
        if data == "blacklist":
            self.parentwin.hud.parent.blacklist_hud(
                "kill",
                self.parentwin.hud.table.key,
            )
        if data == "save":
            # This calls the save_layout method of the Hud object. The Hud object
            # then calls the save_layout method in each installed AW.
            self.parentwin.hud.save_layout()
        self.delete_event()

    def build_button(self, labeltext: str, cbkeyword: str) -> QPushButton:
        """Build a QPushButton with a connected callback for the popup menu.

        This method creates a button with the specified label and connects it
        to the callback using the provided keyword.

        Args:
            labeltext: The text to display on the button.
            cbkeyword: The keyword to pass to the callback when the button is clicked.

        Returns:
            QPushButton: The created button instance.
        """
        button = QPushButton(labeltext)
        button.clicked.connect(partial(self.callback, data=cbkeyword))
        return button

    def build_spinner(self, field: str, low: int, high: int) -> QSpinBox:
        """Build a QSpinBox for numeric input in the popup menu.

        This method creates a spin box with the specified range and initial value,
        and connects it to update the HUD parameter.

        Args:
            field: The HUD parameter field to bind to the spin box.
            low: The minimum value for the spin box.
            high: The maximum value for the spin box.

        Returns:
            QSpinBox: The created spin box instance.
        """
        spin_box = QSpinBox()
        spin_box.setRange(low, high)
        spin_box.setValue(self.parentwin.hud.hud_params[field])
        spin_box.valueChanged.connect(partial(self.change_spin_field_value, field=field))
        return spin_box

    def build_combo_and_set_active(self, field: str, combo_dict: dict) -> QComboBox:
        """Build a QComboBox for selection in the popup menu and set the active value.

        This method creates a combo box with the specified options, sets the current value based on the HUD parameter,
        and connects it to update the parameter when changed.

        Args:
            field: The HUD parameter field to bind to the combo box.
            combo_dict: The dictionary of options for the combo box.

        Returns:
            QComboBox: The created combo box instance.
        """
        widget = QComboBox()
        for pos in combo_dict:
            widget.addItem(combo_dict[pos][0])
            if combo_dict[pos][1] == self.parentwin.hud.hud_params[field]:
                widget.setCurrentIndex(pos)
        widget.currentIndexChanged.connect(
            partial(self.change_combo_field_value, field=field, combo_dict=combo_dict),
        )
        return widget

    def build_stat_set_combo(self, stat_sets_dict: dict) -> QComboBox:
        """Build a QComboBox for selecting the stat set in the popup menu.

        This method creates a combo box with available stat sets, sets the current value,
        and connects it to update the stat set.

        Args:
            stat_sets_dict: The dictionary of available stat sets.

        Returns:
            QComboBox: The created combo box instance for stat set selection.
        """
        combo = QComboBox()
        for pos in stat_sets_dict:
            combo.addItem(stat_sets_dict[pos][0])
            # Get current stat set name
            current_stat_set = self._get_current_stat_set()
            if stat_sets_dict[pos][1] == current_stat_set:
                combo.setCurrentIndex(pos)
        combo.currentIndexChanged.connect(
            partial(self.change_stat_set, stat_sets_dict=stat_sets_dict),
        )
        return combo

    def _get_current_stat_set(self) -> str:
        """Get the name of the currently active stat set.

        This method retrieves the stat set name from the current game parameters.

        Returns:
            str: The name of the current stat set.
        """
        # The stat set is available in the game parameters
        return self.parentwin.aw.game_params.name

    def change_stat_set(self, sel: int, stat_sets_dict: dict) -> None:
        """Change the active stat set for the HUD and refresh the display.

        This method updates the configuration to use the selected stat set, saves the configuration,
        closes the popup menu, and attempts to refresh the HUD with the new stat set. If refreshing fails,
        the HUD is restarted to apply the new stat set.

        Args:
            sel: The index of the selected stat set in the combo box.
            stat_sets_dict: The dictionary of available stat sets.
        """
        new_stat_set = stat_sets_dict[sel][1]

        # Update the configuration to use the new stat set
        self._update_stat_set_in_config(new_stat_set)

        # Save the configuration
        self.parentwin.hud.config.save()

        # Close the popup menu
        self.delete_event()

        try:
            self.parentwin.aw.game_params = self.parentwin.hud.config.get_supported_games_parameters(
                self.parentwin.hud.poker_game,
                self.parentwin.hud.game_type,
            )["game_stat_set"]
            self.parentwin.aw.destroy()
            self.parentwin.aw.refresh_stats_layout()
            self.parentwin.aw.create()
            if hasattr(self.parentwin.hud, "stat_dict"):
                self.parentwin.aw.update_gui(None)
            log.info("HUD rebuilt with new stat set: %s", new_stat_set)
        except Exception as e:  # intentional broad catch: switch fallback must leave no duplicate windows.
            log.info("Rebuilding HUD failed, restarting to apply stat set '%s': %s", new_stat_set, e)
            self.parentwin.hud.parent.kill_hud("kill", self.parentwin.hud.table.key)

    def _update_stat_set_in_config(self, new_stat_set: str) -> None:
        """Update the stat set in the configuration and XML for the current game.

        This method updates the stat set for the current poker game and game type in both the in-memory configuration
        and the XML configuration file.

        Args:
            new_stat_set: The name of the new stat set to apply.
        """
        # Update the game_stat_set configuration
        poker_game = self.parentwin.hud.poker_game
        if poker_game in self.parentwin.hud.config.supported_games:
            game_config = self.parentwin.hud.config.supported_games[poker_game]

            # game_stat_set is a dictionary indexed by game_type
            game_type = self.parentwin.hud.game_type
            if game_type in game_config.game_stat_set:
                game_config.game_stat_set[game_type].stat_set = new_stat_set

            # Also update the XML directly
            self._update_xml_stat_set(poker_game, game_type, new_stat_set)

    def _update_xml_stat_set(self, poker_game: str, game_type: str, new_stat_set: str) -> None:
        """Update the stat set attribute in the XML configuration for a specific game and game type.

        This method locates the relevant game and game_stat_set nodes in the XML document and updates
        the stat_set attribute to the new value.

        Args:
            poker_game: The name of the poker game to update.
            game_type: The type of the game to update.
            new_stat_set: The new stat set name to assign in the XML.
        """
        # Find the game node in the XML document
        game_nodes = self.parentwin.hud.config.doc.getElementsByTagName("game")
        for game_node in game_nodes:
            if game_node.getAttribute("game_name") == poker_game:
                # Find the game_stat_set node for this game type
                game_stat_set_nodes = game_node.getElementsByTagName("game_stat_set")
                for gss_node in game_stat_set_nodes:
                    if gss_node.getAttribute("game_type") == game_type:
                        # Update the stat_set attribute
                        gss_node.setAttribute("stat_set", new_stat_set)
                        break
                break

    def change_combo_field_value(self, sel: int, field: str, combo_dict: dict) -> None:
        """Update the HUD parameter value based on the selected combo box option.

        This method sets the specified HUD parameter to the value associated with the selected combo box item
        and updates the enabled state of related spinners.

        Args:
            sel: The index of the selected item in the combo box.
            field: The HUD parameter field to update.
            combo_dict: The dictionary of options for the combo box.
        """
        self.parentwin.hud.hud_params[field] = combo_dict[sel][1]
        self.set_spinners_active()

    def change_spin_field_value(self, value: int, field: str) -> None:
        """Update the HUD parameter value based on the spin box input.

        This method sets the specified HUD parameter to the value provided by the spin box.

        Args:
            value: The new value selected in the spin box.
            field: The HUD parameter field to update.
        """
        self.parentwin.hud.hud_params[field] = value

    def set_spinners_active(self) -> None:
        """Enable or disable spinner controls based on current HUD parameter selections.

        This method updates the enabled state of various spinner widgets in the popup menu
        according to the current values of the HUD's parameter fields.
        """
        if self.parentwin.hud.hud_params["h_stat_range"] == "T":
            self.h_hud_days_spinner.setEnabled(True)
        else:
            self.h_hud_days_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params["stat_range"] == "T":
            self.hud_days_spinner.setEnabled(True)
        else:
            self.hud_days_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params["h_seats_style"] == "C":
            self.h_nums_low_spinner.setEnabled(True)
            self.h_nums_high_spinner.setEnabled(True)
        else:
            self.h_nums_low_spinner.setEnabled(False)
            self.h_nums_high_spinner.setEnabled(False)
        if self.parentwin.hud.hud_params["seats_style"] == "C":
            self.nums_low_spinner.setEnabled(True)
            self.nums_high_spinner.setEnabled(True)
        else:
            self.nums_low_spinner.setEnabled(False)
            self.nums_high_spinner.setEnabled(False)
