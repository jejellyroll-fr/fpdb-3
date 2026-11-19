"""HUD layouts, stat sets, aux windows, popups and HUD profile and panel rules."""

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

import re
from typing import Any

from fpdb_3_legacy import config_xml as cx
from fpdb_3_legacy.config_common import (
    LAYOUT_REFERENCE_UNDERHANG,
    layout_reference_fits,
)
from fpdb_3_legacy.config_sites import ConfigSitesMixin
from fpdb_3_legacy.hud_profiles import HudProfileRule
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("configuration")


class Layout:
    def __init__(self, node) -> None:
        self.max = int(cx.attr(node, "max"))
        self.width = int(cx.attr(node, "width"))
        self.height = int(cx.attr(node, "height"))

        self.location: list[Any] = []
        self.hh_seats: list[Any] = []
        self.location = [None for x in range(self.max + 1)]  # fill array with max seats+1 empty entries
        # hh_seats is used to map the seat numbers specified in hand history files (and stored in db) onto
        #   the contiguous integerss, 1 to self.max, used to index hud stat_windows (and aw seat_windows) for display
        #   For most sites these numbers are the same, but some sites (e.g. iPoker) omit seat numbers in hand histories
        #   for tables smaller than 10-max.
        self.hh_seats = [None for x in range(self.max + 1)]  # fill array with max seats+1 empty entries

        for location_node in cx.find_all(node, "location"):
            hud_seat = cx.attr(location_node, "seat")
            if hud_seat != "":
                # if hist_seat for this seat number is specified in the layout, then store it in the hh_seats list
                hist_seat = cx.attr(location_node, "hist_seat")  # XXX
                if hist_seat:
                    self.hh_seats[int(hud_seat)] = int(hist_seat)
                else:
                    # .. otherwise just store the original seat number in the hh_seats list
                    self.hh_seats[int(hud_seat)] = int(hud_seat)
                self.location[int(hud_seat)] = (
                    int(cx.attr(location_node, "x")),
                    int(cx.attr(location_node, "y")),
                )
            elif cx.attr(location_node, "common"):
                self.common = (
                    int(cx.attr(location_node, "x")),
                    int(cx.attr(location_node, "y")),
                )

        self._repair_reference_size()

    def _repair_reference_size(self) -> None:
        """Widen a reference size that cannot possibly frame this layout's positions.

        Configs in the wild carry layouts whose width/height were saved from the
        wrong window (a stray HUD label, a rolled-up client), leaving positions
        several times larger than the frame they are scaled against. Loading such
        a layout as-is multiplies every block position by table/reference and
        scatters the HUD far off the table, which reads as "no HUD". Growing the
        reference to the bounding box keeps the user's own positions and puts
        them back inside the table window; the layout is not the intended one,
        but it is visible and can be dragged and re-saved.
        """
        positions = [p for p in self.location if p is not None]
        if getattr(self, "common", None) is not None:
            positions.append(self.common)
        if layout_reference_fits(self.width, self.height, positions):
            return
        old_width, old_height = self.width, self.height
        if positions:
            # At least 1: a zero reference whose coordinates are all zero or
            # negative would otherwise survive the widening unchanged, and
            # Aux_Base.create_scale_position() refuses to divide by it -- the HUD
            # would be no more available than before the repair.
            self.width = max(1, self.width, max(x for x, _y in positions))
            self.height = max(1, self.height, max(y for _x, y in positions))
        # Growing the reference cannot rescue a position that sits *before* the
        # table's origin: scaling only pushes it further off. Such a block is
        # lifted back to the edge instead, which is the same bargain the widening
        # makes -- not the layout the user drew, but one they can see and re-drag.
        lifted = self._lift_positions_into_view()
        log.warning(
            "Layout %d-max declares a %dx%d reference that cannot contain its own positions; "
            "using %dx%d instead%s so the HUD stays on the table",
            self.max,
            old_width,
            old_height,
            self.width,
            self.height,
            f" and lifting {lifted} block(s) back onto it" if lifted else "",
        )

    def _lift_positions_into_view(self) -> int:
        """Clamp positions that sit far before the table origin; return how many."""
        floor_x = -int(self.width * LAYOUT_REFERENCE_UNDERHANG)
        floor_y = -int(self.height * LAYOUT_REFERENCE_UNDERHANG)

        def lift(point):
            x, y = point
            return (max(x, floor_x), max(y, floor_y))

        lifted = 0
        for seat, point in enumerate(self.location):
            if point is None:
                continue
            raised = lift(point)
            if raised != point:
                self.location[seat] = raised
                lifted += 1
        common = getattr(self, "common", None)
        if common is not None:
            raised = lift(common)
            if raised != common:
                self.common = raised
                lifted += 1
        return lifted

    def __str__(self) -> str:
        if hasattr(self, "name"):
            name = str(self.name)
            log.info(f"attribut {name} exists")
        temp = "    Layout = %d max, width= %d, height = %d" % (
            self.max,
            self.width,
            self.height,
        )
        temp = temp + ", fav_seat = %d\n" % self.fav_seat if hasattr(self, "fav_seat") else temp + "\n"
        if hasattr(self, "common"):
            temp = temp + "        Common = (%d, %d)\n" % (
                self.common[0],
                self.common[1],
            )
        temp = temp + "        Locations = "
        for i in range(1, len(self.location)):
            temp = temp + "%s:(%d,%d) " % (
                self.hh_seats[i],
                self.location[i][0],
                self.location[i][1],
            )
        return temp + "\n"


class Stat:
    def __init__(self, node) -> None:
        rowcol = cx.attr(node, "_rowcol")  # human string "(r,c)" values >0)
        self.rows = cx.attr(node, "rows")
        self.cols = cx.attr(node, "cols")
        self.rowcol = tuple(int(s) - 1 for s in rowcol[1:-1].split(","))  # tuple (r-1,c-1)
        self.stat_name = cx.attr(node, "_stat_name")
        self.tip = cx.attr(node, "tip")
        self.display_label = cx.attr(node, "display_label")
        self.click = cx.attr(node, "click")
        self.popup = cx.attr(node, "popup")
        self.hudprefix = cx.attr(node, "hudprefix")
        self.hudsuffix = cx.attr(node, "hudsuffix")
        self.hudcolor = cx.attr(node, "hudcolor")
        self.hudbgcolor = cx.attr(node, "hudbgcolor")
        self.stat_loth = cx.attr(node, "stat_loth")
        self.stat_hith = cx.attr(node, "stat_hith")
        self.stat_locolor = cx.attr(node, "stat_locolor")
        self.stat_hicolor = cx.attr(node, "stat_hicolor")
        self.stat_midcolor = cx.attr(node, "stat_midcolor")
        # PT4-style cell layout: a stat may span several columns and align its text.
        cs = cx.attr(node, "colspan")
        self.colspan = int(cs) if cs else 1
        self.align = cx.attr(node, "align") or "center"
        # Declarative source of the stat, when the editor bound an
        # analytics-backed definition to this cell (#309). Absent for every
        # column-backed stat of Stats.py, which is nearly all of them; kept here
        # so the binding survives a load/save round-trip instead of being
        # rewritten into an anonymous name.
        self.data_source = cx.attr(node, "data_source")
        self.data_definition = cx.attr(node, "data_definition")
        self.data_format = cx.attr(node, "data_format")
        self.data_min_sample = cx.attr(node, "data_min_sample")

    def __str__(self) -> str:
        temp = f"        _rowcol = {self.rowcol}, _stat_name = {self.stat_name}, \n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            if key == "_stat_name":
                continue
            if key == "_rowcol":
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "            " + key + " = " + str(value) + "\n"

        return temp


class StatBlock:
    """One grid panel within a stat-set.

    A stat-set has one block in the classic single-grid layout, or several when
    the HUD shows multiple stacked panels per seat (PT4-style). Built either from
    a ``<block>`` XML node or directly from parameters (for the implicit single
    block of a flat ``<ss>``).
    """

    def __init__(
        self,
        node=None,
        label: str = "",
        rows: int = 0,
        cols: int = 0,
        stats: dict | None = None,
        position: str = "",
        style: dict[str, str] | None = None,
        texts: list | None = None,
    ) -> None:
        style = style or {}
        if node is not None:
            self.label = cx.attr(node, "label")
            self.id = cx.attr(node, "id") or ""
            self.scope = cx.attr(node, "scope") or "player"
            self.audience = cx.attr(node, "audience") or "everyone"
            # Optional position binding: when set, the block is only shown for a
            # player in that position this hand (e.g. "SB"/"BB"/"BTN"); empty
            # means always shown.
            self.position = cx.attr(node, "position")
            self.bgcolor = cx.attr(node, "bgcolor")
            self.fgcolor = cx.attr(node, "fgcolor")
            self.bordercolor = cx.attr(node, "bordercolor")
            self.title_bgcolor = cx.attr(node, "title_bgcolor")
            self.title_fgcolor = cx.attr(node, "title_fgcolor")
            self.title_font_scale = float(cx.attr(node, "title_font_scale")) if cx.attr(node, "title_font_scale") else 0
            self.heading_font_scale = (
                float(cx.attr(node, "heading_font_scale")) if cx.attr(node, "heading_font_scale") else 0
            )
            self.cell_width = int(cx.attr(node, "cell_width")) if cx.attr(node, "cell_width") else 0
            self.x = int(cx.attr(node, "x")) if cx.attr(node, "x") else 0
            self.y = int(cx.attr(node, "y")) if cx.attr(node, "y") else 0
            self.stats = {}
            for stat_node in cx.find_all(node, "stat"):
                stat = Stat(stat_node)
                self.stats[stat.rowcol] = stat
            # Text-label items (column/row headers, section captions like
            # "POST FLOP") — PT4-style group items that are not data cells.
            self.texts = [self._parse_text(t) for t in cx.find_all(node, "text")]
            # Horizontal-line separators (PT4 "Horz Line" group items).
            self.hlines = [self._parse_hline(h) for h in cx.find_all(node, "hline")]
            self.rows = int(cx.attr(node, "rows")) if cx.attr(node, "rows") else 0
            self.cols = int(cx.attr(node, "cols")) if cx.attr(node, "cols") else 0
        else:
            self.label = label
            self.id = style.get("id", "")
            self.scope = style.get("scope", "player")
            self.audience = style.get("audience", "everyone")
            self.position = position
            self.bgcolor = style.get("bgcolor", "")
            self.fgcolor = style.get("fgcolor", "")
            self.bordercolor = style.get("bordercolor", "")
            self.title_bgcolor = style.get("title_bgcolor", "")
            self.title_fgcolor = style.get("title_fgcolor", "")
            self.title_font_scale = float(style.get("title_font_scale", 0) or 0)
            self.heading_font_scale = float(style.get("heading_font_scale", 0) or 0)
            self.cell_width = int(style.get("cell_width", 0) or 0)
            self.x = int(style.get("x", 0) or 0)
            self.y = int(style.get("y", 0) or 0)
            self.stats = stats or {}
            self.texts = texts or []
            self.hlines = []
            self.rows = rows
            self.cols = cols
        # Derive grid size from the items (stats + texts + hlines) if not given explicitly.
        all_rc = list(self.stats) + [t["rowcol"] for t in self.texts] + [h["rowcol"] for h in self.hlines]
        if not self.rows:
            self.rows = max((rc[0] for rc in all_rc), default=-1) + 1
        if not self.cols:
            self.cols = max(
                (
                    rc[1] + t_colspan
                    for rc, t_colspan in [(rc, 1) for rc in self.stats]
                    + [(t["rowcol"], t["colspan"]) for t in self.texts]
                ),
                default=0,
            )
        self.rows = max(self.rows, 1)
        self.cols = max(self.cols, 1)

    @staticmethod
    def _parse_text(node) -> dict:
        """Parse a ``<text>`` label item (header/caption) within a block."""
        rc = cx.attr(node, "_rowcol")
        try:
            rowcol = tuple(int(s) - 1 for s in rc[1:-1].split(",")) if rc else (0, 0)
        except ValueError:
            rowcol = (0, 0)
        cs = cx.attr(node, "colspan")
        return {
            "rowcol": rowcol,
            "label": cx.attr(node, "label"),
            "colspan": int(cs) if cs else 1,
            "align": cx.attr(node, "align") or "center",
            "fgcolor": cx.attr(node, "fgcolor"),
            "bgcolor": cx.attr(node, "bgcolor"),
        }

    @staticmethod
    def _parse_hline(node) -> dict:
        """Parse an ``<hline>`` separator item within a block."""
        rc = cx.attr(node, "_rowcol")
        try:
            rowcol = tuple(int(s) - 1 for s in rc[1:-1].split(",")) if rc else (0, 0)
        except ValueError:
            rowcol = (0, 0)
        cs = cx.attr(node, "colspan")
        return {
            "rowcol": rowcol,
            "colspan": int(cs) if cs else 0,  # 0 -> span the whole block width
            "color": cx.attr(node, "color"),
        }

    def __str__(self) -> str:
        temp = f"        Block '{self.label}' rows={self.rows} cols={self.cols}\n"
        for key in self.stats:
            temp += f"{self.stats[key]}"
        return temp


# Gaps between the cells of a seat's stat grid, in pixels, for a profile whose
# ``xpad`` and ``ypad`` are 0. A multi-panel profile draws a frame around each
# panel, so its columns sit closer.
GRID_COLUMN_GAP = 4
GRID_COLUMN_GAP_MULTI_PANEL = 2
GRID_ROW_GAP = 1


def _padding(value: Any) -> int:
    """A padding as the HUD applies it: a whole number of pixels, never negative."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return 0
    try:
        return max(int(value), 0)
    except ValueError:
        return 0


def grid_spacing(xpad: Any, ypad: Any, *, multi_panel: bool) -> tuple[int, int]:
    """The (column, row) gaps of a seat's stat grid (#770).

    A profile's ``xpad`` and ``ypad`` add to the default gaps: 0 draws the grid
    as it always was, 3 adds 3 pixels between columns (``xpad``) or rows
    (``ypad``). A negative or unreadable value counts as 0.
    """
    column = GRID_COLUMN_GAP_MULTI_PANEL if multi_panel else GRID_COLUMN_GAP
    return column + _padding(xpad), GRID_ROW_GAP + _padding(ypad)


class Stat_sets:
    """Representation of a HUD display configuration.

    Attributes:
        stats: Dict of Tuples (position in HUD) -> Configuration.Stat.

            Exemple::

                {
                    (0,0): Stat(stat_name = 'vpip', stat_hicolor ='#F44336', ...),
                    (0,1): Stat(stat_name = 'pfr', stat_hicolor ='#F44336', ...),
                    ...
                }

        rows: Size of the HUD rows.
        cols: Size of the HUD columns.
    """

    def __init__(self, node) -> None:
        self.name = cx.attr(node, "name")
        self.show_hero_hud = cx.attr(node, "show_hero_hud")
        # Opt-in compact rich-text rendering for the permanent HUD cells.
        # This belongs to the stat-set (rather than a poker variant) so any
        # current or future game profile can reuse the presentation mode.
        self.rich_text = cx.attr(node, "rich_text")
        # Optional profile-specific font size. An empty value keeps the global
        # HUD font setting, while a profile can opt into a larger compact grid.
        self.font_size = cx.attr(node, "font_size")
        self.title_font_scale = cx.attr(node, "title_font_scale")
        self.heading_font_scale = cx.attr(node, "heading_font_scale")
        # How position-bound panels (SB/BB/BU) display in a multi-block HUD:
        #   "current" -> show only the panel matching the estimated live position
        #                (the positional HUD's expected behaviour and default);
        #   "all"     -> show every position panel at once, stacked.
        self.positional_mode = cx.attr(node, "positional_mode") or "current"
        self.rows = int(cx.attr(node, "rows"))
        self.cols = int(cx.attr(node, "cols"))
        xpad = cx.attr(node, "xpad")
        self.xpad = int(xpad) if xpad else 0
        ypad = cx.attr(node, "ypad")
        self.ypad = int(ypad) if ypad else 0
        self.stats = None

        # A stat-set may either list <stat> elements directly (a single grid, the
        # classic layout) or group them into <block> elements (several stacked
        # panels per seat — the PT4-style multi-panel layout). Either way it is
        # normalised into self.blocks; self.stats keeps the flat union so legacy
        # readers keep working.
        self.blocks = []
        block_nodes = cx.find_all(node, "block")
        # A single <block> is still a block layout: it can carry a title,
        # colours, text labels and lines that a flat grid has no place for.
        self.has_block_nodes = bool(block_nodes)
        if block_nodes:
            self.blocks = [StatBlock(bn) for bn in block_nodes]
        else:
            stats = {}
            for stat_node in cx.find_all(node, "stat"):
                stat = Stat(stat_node)
                stats[stat.rowcol] = stat
            self.blocks = [StatBlock(label="", rows=self.rows, cols=self.cols, stats=stats)]

        self.stats = {}
        for blk in self.blocks:
            self.stats.update(blk.stats)

    @property
    def is_multiblock(self) -> bool:
        return len(self.blocks) > 1

    def __str__(self) -> str:
        temp = "Name = " + self.name + "\n"
        temp = temp + "    rows = %d" % self.rows
        temp = temp + " cols = %d" % self.cols
        temp = temp + "    xpad = %d" % self.xpad
        temp = temp + " ypad = %d\n" % self.ypad

        for stat in list(self.stats.keys()):
            temp = temp + f"{self.stats[stat]}"

        return temp


class Aux_window:
    def __init__(self, node) -> None:
        self.name = ""
        for name, value in cx.attributes(node).items():
            setattr(self, name, value)

    def __str__(self) -> str:
        temp = "Aux = " + self.name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + value + "\n"

        return temp


class Layout_set:
    def __init__(self, node) -> None:
        self.name = ""
        for name, value in cx.attributes(node).items():
            setattr(self, name, value)

        self.layout = {}
        for layout_node in cx.find_all(node, "layout"):
            lo = Layout(layout_node)
            self.layout[lo.max] = lo

    def __str__(self) -> str:
        temp = "Layout set = " + self.name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            if key == "layout":
                continue
            if key == "name":
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + value + "\n"

        for layout in self.layout:
            temp = temp + f"{self.layout[layout]}"
        return temp


class Popup:
    def __init__(self, node) -> None:
        self.name = cx.attr(node, "pu_name")
        self.pu_class = cx.attr(node, "pu_class")
        self.pu_stats = []
        self.pu_stats_submenu = []
        self.pu_stats_category = []
        self.pu_stats_label = []
        self.pu_stats_color = []
        # Optional free-form params for custom popup classes (e.g. the
        # RangeChartPopup chart source); kept generic so new popup types can
        # carry their own attributes without changing the schema.
        self.pu_class_params = {}
        for xml_name, param_name in {
            "pu_source": "source",
            "pu_group": "group",
            "pu_theme": "theme",
            "pu_icon_provider": "icon_provider",
            "pu_title": "title",
            "pu_width": "width",
            "pu_max_height": "max_height",
        }.items():
            if cx.attr(node, xml_name):
                self.pu_class_params[param_name] = cx.attr(node, xml_name)

        for stat_node in cx.find_all(node, "pu_stat"):
            self.pu_stats.append(cx.attr(stat_node, "pu_stat_name"))
            self.pu_stats_category.append(cx.attr(stat_node, "pu_stat_category"))
            self.pu_stats_label.append(cx.attr(stat_node, "pu_stat_label"))
            self.pu_stats_color.append(cx.attr(stat_node, "pu_stat_color"))
            # if stat_node.getAttribute("pu_stat_submenu"):
            self.pu_stats_submenu.append(
                (
                    cx.attr(stat_node, "pu_stat_name"),
                    cx.attr(stat_node, "pu_stat_submenu"),
                ),
            )

    def __str__(self) -> str:
        temp = "Popup = " + self.name + "  Class = " + self.pu_class + "\n"
        for stat in self.pu_stats:
            temp = temp + " " + stat
        return temp + "\n"


def parse_hud_profile_rules(doc: Any) -> list[HudProfileRule]:
    """Read the <hud_profile_rules> section of a configuration document.

    Shared by the initial load and by ``Config.reload()``: a rule the user has
    just saved has to reach the running HUD, and reload was the one path that
    did not re-read this section.
    """
    rules = []
    for order, rule_node in enumerate(cx.find_all(doc, "hud_profile_rule")):
        values = cx.attributes(rule_node)
        rule = HudProfileRule.from_mapping(values, order)
        if rule.profile:
            rules.append(rule)
    return rules


def parse_hud_panel_rules(doc: Any) -> tuple[list[Any], str, bool]:
    """Read the <hud_panel_rules> section of a configuration document (#298).

    Returns ``(rules, fallback_panel, enabled)``. The section is optional and
    absent by default, which is what keeps a static HUD static: no rules means
    the HUD behaves exactly as it always has. ``source="builtin"`` prepends the
    shipped rule library, so enabling dynamic panels is one attribute rather
    than a copy of nineteen rules into the user's configuration.

    A section-level ``profile`` scopes that library to one HUD profile, which
    is how the Dynamic reference HUD (#332) turns the panels on for its own
    profile without changing what every other profile does: a table using
    another profile resolves no rules and keeps its static grid.

    Shared by the initial load and by ``Config.reload()``, for the same reason
    the profile rules are: a change the user has just saved has to reach the
    running HUD.
    """
    from fpdb_3_legacy import hud_situation

    sections = cx.find_all(doc, "hud_panel_rules")
    if not sections:
        return [], "", False
    rules: list[Any] = []
    fallback = ""
    enabled = False
    for section in sections:
        section_enabled = str(cx.attr(section, "enabled") or "true").strip().lower() not in ("false", "no", "0", "off")
        if not section_enabled:
            continue
        enabled = True
        fallback = fallback or str(cx.attr(section, "fallback") or "").strip()
        section_rules: list[Any] = []
        source = str(cx.attr(section, "source") or "").strip()
        if source:
            loaded, loaded_fallback = hud_situation.load_source(source)
            section_rules.extend(loaded)
            fallback = fallback or loaded_fallback
        for node in cx.find_all(section, "hud_panel_rule"):
            values = cx.attributes(node)
            section_rules.append(hud_situation.panel_rule_from_attributes(values, len(rules) + len(section_rules)))
        scope = str(cx.attr(section, "profile") or "").strip()
        if scope and scope.casefold() != "all":
            section_rules = hud_situation.scope_rules(section_rules, scope)
        rules.extend(section_rules)
    return hud_situation.number_rules(rules), fallback, enabled


class ConfigHudLayoutsMixin(ConfigSitesMixin):
    """Read and edit HUD layouts, stat sets, aux windows and HUD rules."""

    def getStatSetNode(self, statsetName):
        """Returns DOM game node for a given game."""
        for statset_node in cx.find_all(self.doc, "ss"):
            # print "getStatSetNode statset_node:",statset_node
            if cx.attr(statset_node, "name") == statsetName:
                return statset_node
        return None

    def get_aux_node(self, aux):
        for aux_node in cx.find_all(self.doc, "aw"):
            if cx.attr(aux_node, "name") == aux:
                return aux_node
        return None

    def get_layout_set_node(self, ls):
        for layout_set_node in cx.find_all(self.doc, "ls"):
            if cx.attr(layout_set_node, "name") == ls:
                return layout_set_node
        return None

    def get_layout_node(self, ls, max):
        for layout_node in cx.find_all(ls, "layout"):
            if cx.attr(layout_node, "max") == str(max):
                return layout_node
        return None

    def get_stat_set_node(self, ss):
        for stat_set_node in cx.find_all(self.doc, "ss"):
            if cx.attr(stat_set_node, "name") == ss:
                return stat_set_node
        return None

    def get_location_node(self, layout_node, seat):
        if seat == "common":
            for location_node in cx.find_all(layout_node, "location"):
                if cx.has_attr(location_node, "common"):
                    return location_node
            return None
        for location_node in cx.find_all(layout_node, "location"):
            if int(cx.attr(location_node, "seat")) == int(seat):
                return location_node
        return None

    def edit_fav_seat(
        self,
        site_name,
        enabled,
        seat2_dict,
        seat3_dict,
        seat4_dict,
        seat5_dict,
        seat6_dict,
        seat7_dict,
        seat8_dict,
        seat9_dict,
        seat10_dict,
    ) -> None:
        site_node = self.get_site_node(site_name)
        cx.set_attr(site_node, "enabled", enabled)

        values = {
            "2": seat2_dict,
            "3": seat3_dict,
            "4": seat4_dict,
            "5": seat5_dict,
            "6": seat6_dict,
            "7": seat7_dict,
            "8": seat8_dict,
            "9": seat9_dict,
            "10": seat10_dict,
        }
        existing = {cx.attr(fav, "max"): fav for fav in cx.find_all(site_node, "fav")}
        for max_seats, value in values.items():
            fav_seat = existing.get(max_seats)
            if fav_seat is None:
                # A site's config may ship without a <fav> node for every table
                # size (e.g. CoinPoker only had 2/6/9/10). Without this, editing a
                # preferred seat for a missing size (a 5-max table) was silently
                # dropped -- create the node so the choice is actually persisted.
                fav_seat = cx.append(self.doc, site_node, cx.create_element(self.doc, "fav", {"max": max_seats}))
            cx.set_attr(fav_seat, "fav_seat", value)

    # end def

    @staticmethod
    def increment_position(position: str) -> str:
        """Convert a zero-based HUD grid position to the one-based XML format.

        >>> Config.increment_position('(0,0)')
        "(1,1)"
        >>> Config.increment_position('(0, 0)')
        "(1,1)"
        >>> Config.increment_position('(2,3)')
        "(3,4)".
        """
        match = re.fullmatch(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", position)
        if match is None:
            raise AssertionError(f"Invalid HUD grid position: {position!r}")
        row, col = map(int, match.groups())
        return f"({row + 1},{col + 1})"

    def edit_hud(
        self,
        hud_name,
        position,
        stat_name,
        click,
        hudcolor,
        hudprefix,
        hudsuffix,
        popup,
        stat_hicolor,
        stat_hith,
        stat_locolor,
        stat_loth,
        tip,
    ) -> None:
        """Replace given values onto self.doc (XML root node)."""
        for statset_node in cx.find_all(self.doc, "ss"):
            if cx.attr(statset_node, "name") == hud_name:
                for fav_stat in cx.find_all(statset_node, "stat"):
                    if cx.attr(fav_stat, "_rowcol") == self.increment_position(position):
                        cx.set_attr(fav_stat, "_stat_name", stat_name)
                        cx.set_attr(fav_stat, "click", click)
                        cx.set_attr(fav_stat, "hudcolor", hudcolor)
                        cx.set_attr(fav_stat, "hudprefix", hudprefix)
                        cx.set_attr(fav_stat, "hudsuffix", hudsuffix)
                        cx.set_attr(fav_stat, "popup", popup)
                        cx.set_attr(fav_stat, "stat_hicolor", stat_hicolor)
                        cx.set_attr(fav_stat, "stat_hith", stat_hith)
                        cx.set_attr(fav_stat, "stat_locolor", stat_locolor)
                        cx.set_attr(fav_stat, "stat_loth", stat_loth)
                        cx.set_attr(fav_stat, "tip", tip)
                        # fav_stat.setAttribute("stat_midcolor", stat_midcolor)  # not returned by UI

    # end def

    def install_popup_packs(self) -> None:
        """Merge the packaged popup packs (#299) into the popup registry.

        Best-effort: a pack library that fails to load is logged and the popups
        the configuration file defines are left in place, so the HUD always has
        the classic popups even when the packs are broken.
        """
        try:
            from fpdb_3_legacy import popup_packs

            registry = popup_packs.load_default_registry()
            report = popup_packs.install_packs(self, [registry.packs[name] for name in registry.names()])
        except Exception:  # intentional broad catch: a broken pack must not break the HUD
            log.exception("popup packs could not be installed")
            return
        for warning in report.warnings:
            log.debug("popup pack: %s", warning)
        log.info("popup packs: %s", report.summary())

    def editStats(self, statsetName, statArray) -> None:
        """Replaces stat selection for the given gameName with the given statArray."""
        statset_node = self.getStatSetNode(statsetName)
        if statset_node is None:
            # Saying so beats the AttributeError on None this used to raise:
            # replacing a whole grid must not look like a bug in the caller.
            msg = f"No stat set named {statsetName!r}"
            raise ValueError(msg)
        stat_nodes = cx.find_all(statset_node, "stat")

        # Store existing stat attributes before removing
        existing_stats = {}
        for node in stat_nodes:
            rowcol = cx.attr(node, "_rowcol")
            existing_stats[rowcol] = {
                "click": cx.attr(node, "click"),
                "popup": cx.attr(node, "popup"),
                "tip": cx.attr(node, "tip"),
                "hudprefix": cx.attr(node, "hudprefix"),
                "hudsuffix": cx.attr(node, "hudsuffix"),
                "hudcolor": cx.attr(node, "hudcolor"),
                "stat_locolor": cx.attr(node, "stat_locolor"),
                "stat_loth": cx.attr(node, "stat_loth"),
                "stat_midcolor": cx.attr(node, "stat_midcolor"),
                "stat_hicolor": cx.attr(node, "stat_hicolor"),
                "stat_hith": cx.attr(node, "stat_hith"),
            }

        # Remove all child nodes (stats and text nodes)
        cx.clear(self.doc, statset_node)

        cx.set_attr(statset_node, "rows", str(len(statArray)))
        # A grid with no rows at all has no width either. Reading it off the
        # first row raised IndexError, even though the last step of this same
        # function guards for an empty grid -- so emptying a stat set worked
        # with [[]] and not with [].
        cx.set_attr(statset_node, "cols", str(len(statArray[0]) if statArray else 0))

        for _idx, (rowNumber, columnNumber) in enumerate(
            [(r, c) for r in range(len(statArray)) for c in range(len(statArray[r]))],
        ):
            # Add newline and indentation before each stat
            cx.append_text(self.doc, statset_node, "\n            ")

            rowcol_str = f"({rowNumber + 1},{columnNumber + 1})"

            # Default attributes
            attributes = {
                "_stat_name": statArray[rowNumber][columnNumber],
                "_rowcol": rowcol_str,
                "click": "",
                "popup": "default",
                "tip": "",
                "hudprefix": "",
                "hudsuffix": "",
                "hudcolor": "",
                "stat_locolor": "",
                "stat_loth": "",
                "stat_midcolor": "",
                "stat_hicolor": "",
                "stat_hith": "",
            }

            # Restore existing attributes if they exist
            if rowcol_str in existing_stats:
                for attr, value in existing_stats[rowcol_str].items():
                    if value:  # Only set non-empty values
                        attributes[attr] = value

            cx.append(self.doc, statset_node, cx.create_element(self.doc, "stat", attributes))

        # Add final newline and indentation
        if len(statArray) > 0:
            cx.append_text(self.doc, statset_node, "\n        ")

    def save_layout_set(self, ls, max, locations, width=None, height=None) -> None:
        # wid/height normally not specified when saving common from the mucked display

        log.debug(f"saving layout = {ls.name} {max}Max {locations} size: {width}x{height}")
        # A dimension that is present is a measurement; only None means "not
        # specified", which is how the mucked display saves its common position.
        # The difference matters because a minimized, rolled-up or not yet
        # realized window measures exactly 0, and the truthiness test this used
        # to be read that as "not specified": the guard was skipped, the
        # positions were written, and `if width:` below left the previous
        # width/height on the node for them to be scaled against -- the
        # mismatched reference this guard exists to prevent, reached through the
        # one path that bypassed it.
        measured = [value for value in (width, height) if value is not None]
        broken_measurement = any(int(value) <= 0 for value in measured)
        # A pair can be checked against the positions it is supposed to frame;
        # a single dimension cannot (the other one stays whatever the node
        # already held), so it is only checked for being a real measurement.
        pair_does_not_fit = len(measured) == 2 and not layout_reference_fits(width, height, locations.values())
        if broken_measurement or pair_does_not_fit:
            # The reference is the table the positions were just read from, so
            # positions far outside it mean the HUD was measuring the wrong
            # window (a stray label, a rolled-up client). Persisting that pair
            # is what corrupts a layout set permanently: on the next real table
            # the blocks get scaled by table/reference and land off-screen.
            log.error(
                "Refusing to save layout %s %d-max: positions %s cannot come from a %sx%s table",
                ls.name,
                max,
                locations,
                width,
                height,
            )
            return
        ls_node = self.get_layout_set_node(ls.name)
        layout_node = self.get_layout_node(ls_node, max)
        if width:
            cx.set_attr(layout_node, "width", str(width))
        if height:
            cx.set_attr(layout_node, "height", str(height))

        for i, _pos in list(locations.items()):
            location_node = self.get_location_node(layout_node, i)
            cx.set_attr(location_node, "x", str(locations[i][0]))
            cx.set_attr(location_node, "y", str(locations[i][1]))
            # now refresh the live instance of the layout set with the new locations
            # this is needed because any future windows created after a save layout
            # MUST pickup the new layout
            # fixme - this is horrid
            if i == "common":
                self.layout_sets[ls.name].layout[max].common = (
                    locations[i][0],
                    locations[i][1],
                )
            else:
                self.layout_sets[ls.name].layout[max].location[i] = (
                    locations[i][0],
                    locations[i][1],
                )
        # more horridness below, fixme
        if height:
            self.layout_sets[ls.name].layout[max].height = height
        if width:
            self.layout_sets[ls.name].layout[max].width = width

    def get_layout_set_locations(self, set="mucked", max="9"):
        try:
            locations = self.layout_sets[set].layout[max].location
        except (KeyError, AttributeError) as e:
            log.exception(f"Error retrieving layout set locations for set='{set}', max='{max}': {e}")
            locations = [
                (0, 0),
                (684, 61),
                (689, 239),
                (692, 346),
                (586, 393),
                (421, 440),
                (267, 440),
                (0, 361),
                (0, 280),
                (121, 280),
                (46, 30),
            ]
        return locations

    def get_layout(self, site, game_type):
        # find layouts used at site
        # locate the one used for this game_type
        # return that Layout-set() instance

        site_layouts = self.get_site_parameters(site)["layout_set"]

        if game_type in site_layouts:
            return self.layout_sets[site_layouts[game_type]]
        if "all" in site_layouts:
            return self.layout_sets[site_layouts["all"]]
        return None

    #    def set_site_parameters(self, site_name, converter = None, decoder = None,
    #                            hudbgcolor = None, hudfgcolor = None,
    #                            hudopacity = None, screen_name = None,
    #                            site_path = None, table_finder = None,
    #                            HH_path = None, enabled = None,
    #                            font = None, font_size = None):
    #        """Sets the specified site parameters for the specified site."""
    #        site_node = self.get_site_node(site_name)
    #        if db_node is not None:
    #            if converter      is not None: site_node.setAttribute("converter", converter)
    #            if decoder        is not None: site_node.setAttribute("decoder", decoder)
    #            if hudbgcolor     is not None: site_node.setAttribute("hudbgcolor", hudbgcolor)
    #            if hudfgcolor     is not None: site_node.setAttribute("hudfgcolor", hudfgcolor)
    #            if hudopacity     is not None: site_node.setAttribute("hudopacity", hudopacity)
    #            if screen_name    is not None: site_node.setAttribute("screen_name", screen_name)
    #            if site_path      is not None: site_node.setAttribute("site_path", site_path)
    #            if table_finder   is not None: site_node.setAttribute("table_finder", table_finder)
    #            if HH_path        is not None: site_node.setAttribute("HH_path", HH_path)
    #            if enabled        is not None: site_node.setAttribute("enabled", enabled)
    #            if font           is not None: site_node.setAttribute("font", font)
    #            if font_size      is not None: site_node.setAttribute("font_size", font_size)
    #        return

    def get_aux_windows(self):
        """Gets the list of mucked window formats in the configuration."""
        return list(self.aux_windows.keys())

    @staticmethod
    def _aux_name_key(name):
        """A form of an aux window name that survives a rename of its spelling.

        Aux windows have been respelled over the years -- "Classic_HUD" became
        "ClassicHud" -- and a user configuration written before a rename keeps
        the old spelling in its ``aux=`` references while its ``<aw>`` blocks
        carry the new one. Comparing on this key lets the reference still find
        its definition, so a configuration that has simply aged does not cost
        the player their HUD.
        """
        return str(name).replace("_", "").replace("-", "").replace(" ", "").casefold()

    def _resolve_aux_name(self, name):
        """The configured aux window this name refers to, or None.

        An exact name always wins; only a name no ``<aw>`` block defines falls
        back to the respelling match, so a valid configuration resolves exactly
        as it always did.
        """
        if name in self.aux_windows:
            return name
        wanted = self._aux_name_key(name)
        matches = [defined for defined in self.aux_windows if self._aux_name_key(defined) == wanted]
        if len(matches) != 1:
            # No match, or an ambiguous one: refuse to guess which was meant.
            return None
        # Said once per name: this is asked again for every aux window of every
        # HUD built, so logging each time would bury the rest of a busy session.
        warned = self.__dict__.setdefault("_respelled_aux_warned", set())
        if name not in warned:
            warned.add(name)
            log.warning(
                "Configuration asks for aux window %r, which no <aw> defines; using %r, "
                "which differs only in spelling. Update %s to silence this.",
                name,
                matches[0],
                self.file,
            )
        return matches[0]

    def get_aux_parameters(self, name):
        """Gets a dict of mucked window parameters from the named mw."""
        param = {}
        resolved = self._resolve_aux_name(name)
        if resolved is not None:
            for key in dir(self.aux_windows[resolved]):
                if key.startswith("__"):
                    continue
                value = getattr(self.aux_windows[resolved], key)
                if callable(value):
                    continue
                param[key] = value

            return param
        return None

    def get_stat_sets(self):
        """Gets the list of stat block contents in the configuration."""
        return list(self.stat_sets.keys())

    def get_layout_sets(self):
        """Gets the list of block layouts in the configuration."""
        return list(self.layout_sets.keys())

    def get_layout_set_parameters(self, name):
        """Gets a dict of parameters from the named ls."""
        param = {}
        if name in self.layout_sets:
            for key in dir(self.layout_sets[name]):
                if key.startswith("__"):
                    continue
                value = getattr(self.layout_sets[name], key)
                if callable(value):
                    continue
                param[key] = value

            return param
        return None

    def get_hud_profile_rules(self) -> list[HudProfileRule]:
        """Return a copy of the persistent PT-style profile selection rules."""
        return list(self.hud_profile_rules)

    def get_hud_panel_rules(self) -> list[Any]:
        """The dynamic panel rules (#298), or ``[]`` when they are disabled.

        An empty list is what the HUD reads as "keep the static grid", so the
        disabled case and the unconfigured case are the same code path: turning
        dynamic panels off cannot change what a table draws.
        """
        if not self.hud_panel_rules_enabled:
            return []
        return list(self.hud_panel_rules)

    def set_hud_panel_rules(
        self,
        rules: list[Any],
        *,
        fallback: str = "",
        enabled: bool = True,
    ) -> None:
        """Replace the dynamic panel rules in memory and in the DOM.

        Each rule is validated on the way in by being rebuilt from its own XML
        attributes, so what is written is what a reload can read back.
        """
        from fpdb_3_legacy import hud_situation

        self.hud_panel_rules = hud_situation.number_rules(
            hud_situation.panel_rule_from_attributes(rule.as_xml_attributes(), order)
            for order, rule in enumerate(rules)
        )
        self.hud_panel_fallback = str(fallback or "")
        self.hud_panel_rules_enabled = bool(enabled)
        if self.doc is None:
            return

        sections = cx.find_all(self.doc, "hud_panel_rules")
        if sections:
            section = sections[0]
            cx.set_attr(section, "enabled", "true" if enabled else "false")
            cx.set_attr(section, "fallback", self.hud_panel_fallback)
            # These rules are already materialized; retaining the source would
            # make reload append the source rules again.
            cx.del_attr(section, "source")
            cx.clear(self.doc, section)
            for duplicate in sections[1:]:
                cx.remove(self.doc, duplicate)
        else:
            section = cx.create_element(
                self.doc,
                "hud_panel_rules",
                {"enabled": "true" if enabled else "false", "fallback": self.hud_panel_fallback},
            )
            cx.append_text(self.doc, self.doc, "\n    ")
            cx.append(self.doc, self.doc, section)

        for rule in self.hud_panel_rules:
            cx.append_text(self.doc, section, "\n        ")
            cx.append(self.doc, section, cx.create_element(self.doc, "hud_panel_rule", rule.as_xml_attributes()))
        if self.hud_panel_rules:
            cx.append_text(self.doc, section, "\n    ")

    def set_hud_profile_rules(self, rules: list[HudProfileRule]) -> None:
        """Replace profile rules in memory and in the configuration DOM."""
        self.hud_profile_rules = [
            HudProfileRule.from_mapping(rule.as_xml_attributes(), order)
            for order, rule in enumerate(rules)
            if rule.profile
        ]
        if self.doc is None:
            return

        sections = cx.find_all(self.doc, "hud_profile_rules")
        if sections:
            section = sections[0]
            cx.clear(self.doc, section)
        else:
            section = cx.create_element(self.doc, "hud_profile_rules")
            cx.append_text(self.doc, self.doc, "\n    ")
            cx.append(self.doc, self.doc, section)

        for rule in self.hud_profile_rules:
            cx.append_text(self.doc, section, "\n        ")
            attributes = {name: value for name, value in rule.as_xml_attributes().items() if value or name != "id"}
            cx.append(self.doc, section, cx.create_element(self.doc, "hud_profile_rule", attributes))
        if self.hud_profile_rules:
            cx.append_text(self.doc, section, "\n    ")
