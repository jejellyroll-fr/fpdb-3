"""The <general> section and the cash / tournament stat-table column layouts."""

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

from typing import Any

from fpdb_3_legacy.config_common import (
    ConfigBase,
    string_to_bool,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("configuration")


class General(dict):
    def __init__(self) -> None:
        super().__init__()

    def add_elements(self, node) -> None:
        # day_start    - number n where 0.0 <= n < 24.0 representing start of day for user
        #                e.g. user could set to 4.0 for day to start at 4am local time
        # [ HH_bulk_path was here - now moved to import section ]
        for name, value in list(node.attributes.items()):
            log.debug(f"config.general: adding {name} = {value}")
            self[name] = value

        try:
            self["version"] = int(self["version"])
        except (KeyError, ValueError):
            self["version"] = 0
            self["ui_language"] = "system"
            self["config_difficulty"] = "expert"

    def get_defaults(self) -> None:
        self["version"] = 0
        self["ui_language"] = "system"
        self["config_difficulty"] = "expert"
        self["config_wrap_len"] = "-1"
        self["day_start"] = "5"
        # Theme settings for global theme persistence
        self["qt_material_theme"] = "dark_purple.xml"
        self["popup_theme"] = "material_dark"

    def __str__(self) -> str:
        s = ""
        for k in self:
            s = s + f"    {k} = {self[k]}\n"
        return s


class GUICashStats(list):
    """<gui_cash_stats>
        <col col_name="game" col_title="Game" disp_all="True" disp_posn="True" field_format="%s" field_type="str" xalignment="0.0" />
        ...
    </gui_cash_stats>.
    """

    DEFAULTS = [
        ["game", "Game", True, True, "%s", "str", 0.0],
        ["hand", "Hand", False, False, "%s", "str", 0.0],
        ["plposition", "Posn", False, False, "%s", "str", 1.0],
        ["pname", "Name", False, False, "%s", "str", 0.0],
        ["n", "Hds", True, True, "%1.0f", "str", 1.0],
        ["avgseats", "Seats", False, False, "%3.1f", "str", 1.0],
        ["vpip", "VPIP", True, True, "%3.1f", "str", 1.0],
        ["pfr", "PFR", True, True, "%3.1f", "str", 1.0],
        ["pf3", "PF3", True, True, "%3.1f", "str", 1.0],
        ["fl3", "Flop3B", False, False, "%3.1f", "str", 1.0],
        ["tn3", "Turn3B", False, False, "%3.1f", "str", 1.0],
        ["rv3", "Rivr3B", False, False, "%3.1f", "str", 1.0],
        ["ff3", "FFlop3B", False, False, "%3.1f", "str", 1.0],
        ["ft3", "FTurn3B", False, False, "%3.1f", "str", 1.0],
        ["fr3", "FRivr3B", False, False, "%3.1f", "str", 1.0],
        ["fl4", "Flop4B", False, False, "%3.1f", "str", 1.0],
        ["tn4", "Turn4B", False, False, "%3.1f", "str", 1.0],
        ["rv4", "Rivr4B", False, False, "%3.1f", "str", 1.0],
        ["flopen", "FOpen", False, False, "%3.1f", "str", 1.0],
        ["tnopen", "TOpen", False, False, "%3.1f", "str", 1.0],
        ["rvopen", "ROpen", False, False, "%3.1f", "str", 1.0],
        ["pf4", "PF4", True, True, "%3.1f", "str", 1.0],
        ["pff3", "PFF3", True, True, "%3.1f", "str", 1.0],
        ["pff4", "PFF4", True, True, "%3.1f", "str", 1.0],
        ["aggfac", "AggFac", True, True, "%2.2f", "str", 1.0],
        ["aggfrq", "AggFreq", True, True, "%3.1f", "str", 1.0],
        ["conbet", "ContBet", True, True, "%3.1f", "str", 1.0],
        ["rfi", "RFI", True, True, "%3.1f", "str", 1.0],
        ["raisetosteal", "RST", True, True, "%3.1f", "str", 1.0],
        ["steals", "Steals", True, True, "%3.1f", "str", 1.0],
        ["suc_steal", "SucSt", False, False, "%3.1f", "str", 1.0],
        ["foldsbtosteal", "fSB", True, True, "%3.1f", "str", 1.0],
        ["foldbbtosteal", "fBB", True, True, "%3.1f", "str", 1.0],
        ["car0", "CARpre", True, True, "%3.1f", "str", 1.0],
        ["saw_f", "Saw_F", True, True, "%3.1f", "str", 1.0],
        ["sawsd", "SawSD", True, True, "%3.1f", "str", 1.0],
        ["wmsf", "W$wsF", True, True, "%3.1f", "str", 1.0],
        ["wtsdwsf", "WtSDwsF", True, True, "%3.1f", "str", 1.0],
        ["wmsd", "W$SD", True, True, "%3.1f", "str", 1.0],
        ["flafq", "FlAFq", True, True, "%3.1f", "str", 1.0],
        ["tuafq", "TuAFq", True, True, "%3.1f", "str", 1.0],
        ["rvafq", "RvAFq", True, True, "%3.1f", "str", 1.0],
        ["pofafq", "PoFAFq", False, False, "%3.1f", "str", 1.0],
        ["net", "Net($)", True, True, "%6.2f", "cash", 1.0],
        ["bbper100", "bb/100", True, True, "%4.2f", "str", 1.0],
        ["profitperhand", "Profit/Hnd", False, False, "%6.2f", "cash", 1.0],
        ["rake", "Rake($)", True, True, "%6.2f", "cash", 1.0],
        ["bb100xr", "bbxr/100", True, True, "%4.2f", "str", 1.0],
        ["profhndxr", "ProfitHndXR", False, False, "%6.2f", "cash", 1.0],
        ["variance", "Variance", False, False, "%5.2f", "str", 1.0],
        ["stddev", "Standard Deviation", True, True, "%5.2f", "str", 1.0],
    ]

    def __init__(self) -> None:
        super().__init__()

    def add_elements(self, node) -> None:
        # is this needed?
        for child in node.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                (
                    col_name,
                    col_title,
                    disp_all,
                    disp_posn,
                    field_format,
                    field_type,
                    xalignment,
                ) = (
                    None,
                    None,
                    True,
                    True,
                    "%s",
                    "str",
                    0.0,
                )

                if child.hasAttribute("col_name"):
                    col_name = child.getAttribute("col_name")
                if child.hasAttribute("col_title"):
                    col_title = child.getAttribute("col_title")
                if child.hasAttribute("disp_all"):
                    disp_all = string_to_bool(child.getAttribute("disp_all"))
                if child.hasAttribute("disp_posn"):
                    disp_posn = string_to_bool(child.getAttribute("disp_posn"))
                if child.hasAttribute("field_format"):
                    field_format = child.getAttribute("field_format")
                if child.hasAttribute("field_type"):
                    field_type = child.getAttribute("field_type")
                try:
                    if child.hasAttribute("xalignment"):
                        xalignment = float(child.getAttribute("xalignment"))
                except ValueError:
                    log.exception("bad number in xalignment was ignored")

                self.append(
                    [
                        col_name,
                        col_title,
                        disp_all,
                        disp_posn,
                        field_format,
                        field_type,
                        xalignment,
                    ],
                )

    def get_defaults(self) -> None:
        """A list of defaults to be called, should there be no entry in config."""
        # SQL column name, display title, display all, display positional, format, type, alignment
        for col in self.DEFAULTS:
            self.append(col[:])

    def add_missing_defaults(self) -> None:
        """Append newer default columns without overwriting user visibility choices."""
        configured_names = {col[0] for col in self}
        for col in self.DEFAULTS:
            if col[0] not in configured_names:
                self.append(col[:])


#    def __str__(self):
#        s = ""
#        for l in self:
#            s = s + "    %s = %s\n" % (k, self[k])
#        return(s)
class GUITourStats(list):
    """<gui_tour_stats>
        <col col_name="game" col_title="Game" disp_all="True" disp_posn="True" field_format="%s" field_type="str" xalignment="0.0" />
        ...
    </gui_tour_stats>.
    """

    def __init__(self) -> None:
        super().__init__()

    def add_elements(self, node) -> None:
        # is this needed?
        for child in node.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                (
                    col_name,
                    col_title,
                    disp_all,
                    disp_posn,
                    field_format,
                    field_type,
                    xalignment,
                ) = (
                    None,
                    None,
                    True,
                    True,
                    "%s",
                    "str",
                    0.0,
                )

                if child.hasAttribute("col_name"):
                    col_name = child.getAttribute("col_name")
                if child.hasAttribute("col_title"):
                    col_title = child.getAttribute("col_title")
                if child.hasAttribute("disp_all"):
                    disp_all = string_to_bool(child.getAttribute("disp_all"))
                if child.hasAttribute("disp_posn"):
                    disp_posn = string_to_bool(child.getAttribute("disp_posn"))
                if child.hasAttribute("field_format"):
                    field_format = child.getAttribute("field_format")
                if child.hasAttribute("field_type"):
                    field_type = child.getAttribute("field_type")
                try:
                    if child.hasAttribute("xalignment"):
                        xalignment = float(child.getAttribute("xalignment"))
                except ValueError:
                    log.exception("bad number in xalignment was ignored")

                self.append(
                    [
                        col_name,
                        col_title,
                        disp_all,
                        disp_posn,
                        field_format,
                        field_type,
                        xalignment,
                    ],
                )

    def get_defaults(self) -> None:
        """A list of defaults to be called, should there be no entry in config."""
        # SQL column name, display title, display all, display positional, format, type, alignment
        defaults = [
            ["game", "Game", True, True, "%s", "str", 0.0],
            ["hand", "Hand", False, False, "%s", "str", 0.0],
        ]
        for col in defaults:
            self.append(col)


class ConfigGuiMixin(ConfigBase):
    """Read and edit the general settings and the stats-table columns."""

    def set_general(self, lang=None) -> None:
        for general_node in self.doc.getElementsByTagName("general"):
            if lang:
                general_node.setAttribute("ui_language", lang)

    def set_preflop_advisor_path(self, path: str | None) -> None:
        """Remember where PreflopAdvisor is, for the solver review (#413); empty forgets it.

        An optional ``preflop_advisor`` attribute on ``<general>``: the shipped templates do
        not carry it, so files without it keep looking for PreflopAdvisor on the PATH.
        """
        value = str(path or "")
        if value:
            self.general["preflop_advisor"] = value
        else:
            self.general.pop("preflop_advisor", None)
        for general_node in self.doc.getElementsByTagName("general"):
            if value:
                general_node.setAttribute("preflop_advisor", value)
            elif general_node.hasAttribute("preflop_advisor"):
                general_node.removeAttribute("preflop_advisor")
        self.save()

    def get_check_for_updates(self) -> bool | None:
        """Whether fpdb looks for a newer release at startup (#445); None until the user has been asked.

        An optional ``check_for_updates`` attribute on ``<general>``, absent from the
        shipped templates so that the first start asks instead of deciding.
        """
        value = self.general.get("check_for_updates")
        if value is None:
            return None
        return str(value).strip().lower() in ("true", "1", "yes")

    def get_update_prereleases(self) -> bool:
        """Whether the update check also announces pre-releases (``update_prereleases``, off by default)."""
        return str(self.general.get("update_prereleases", "")).strip().lower() in ("true", "1", "yes")

    def set_check_for_updates(self, enabled: bool) -> None:
        """Record the user's answer to the update question, and save."""
        value = "True" if enabled else "False"
        self.general["check_for_updates"] = value
        for general_node in self.doc.getElementsByTagName("general"):
            general_node.setAttribute("check_for_updates", value)
        self.save()

    def get_session_guard_defaults(self) -> dict[str, str]:
        """The Session Guard limits saved as defaults (#395), as stored; empty when none."""
        for node in self.doc.getElementsByTagName("session_guard"):
            return dict(node.attributes.items())
        return {}

    def set_session_guard_defaults(self, limits: dict[str, Any] | None) -> None:
        """Save Session Guard limits as defaults, or forget them (``None`` or empty).

        An optional ``<session_guard>`` element of the root: the shipped templates do not
        carry it, so a configuration without one simply has no defaults.
        """
        for node in list(self.doc.getElementsByTagName("session_guard")):
            node.parentNode.removeChild(node)
        if limits:
            node = self.doc.createElement("session_guard")
            for name, value in sorted(limits.items()):
                node.setAttribute(name, str(value))
            self.doc.documentElement.appendChild(node)
        self.save()

    def get_general_params(self):
        return self.general

    def get_gui_cash_stat_params(self):
        # print(type(self.gui_cash_stats))
        return self.gui_cash_stats

    def get_gui_tour_stat_params(self):
        # print(type(self.gui_tour_stats))
        return self.gui_tour_stats

    def save_gui_cash_stats(self):
        """Saves current gui_cash_stats list to the DOM tree."""
        # Find the <gui_cash_stats> node
        gcs_nodes = self.doc.getElementsByTagName("gui_cash_stats")
        if not gcs_nodes:
            # Create if not exists
            root = self.doc.getElementsByTagName("FreePokerToolsConfig")[0]
            gcs_node = self.doc.createElement("gui_cash_stats")
            root.appendChild(gcs_node)
        else:
            gcs_node = gcs_nodes[0]

        # Remove all children
        while gcs_node.firstChild:
            gcs_node.removeChild(gcs_node.firstChild)

        # Add new children
        for col in self.gui_cash_stats:
            # col is [col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment]
            node = self.doc.createElement("col")
            node.setAttribute("col_name", str(col[0]))
            node.setAttribute("col_title", str(col[1]))
            node.setAttribute("disp_all", str(col[2]))
            node.setAttribute("disp_posn", str(col[3]))
            node.setAttribute("field_format", str(col[4]))
            node.setAttribute("field_type", str(col[5]))
            node.setAttribute("xalignment", str(col[6]))
            gcs_node.appendChild(node)
