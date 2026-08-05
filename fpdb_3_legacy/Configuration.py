# Configuration####
from __future__ import annotations

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
#    Standard Library modules
import codecs
import inspect
import json
import locale
import os
import platform
import re
import shutil
import sys
import traceback
import xml.parsers.expat
from pathlib import Path
from typing import Any

import defusedxml.minidom
from defusedxml.common import DefusedXmlException

# A configuration file is read from disk, so it can carry whatever an attacker
# who reached the disk put there. defusedxml refuses the two constructs that
# turn parsing into a weapon -- external entities, which read other files, and
# nested entity definitions, which expand until memory runs out -- and it does
# so by raising DefusedXmlException, which is a ValueError rather than the
# ExpatError a malformed file raises. Both have to be caught wherever a
# rejected file must not take fpdb down with it.
XML_PARSE_ERRORS = (OSError, xml.parsers.expat.ExpatError, DefusedXmlException)

if platform.system() == "Windows":
    import os

    winpaths_appdata = (os.getenv("APPDATA") or os.path.expanduser("~")).replace("\\", "/")
else:
    winpaths_appdata = ""

from fpdb_3_legacy.autonotes_aof import AOF_CATEGORIES
from fpdb_3_legacy.hud_profiles import HudContext, HudProfileResolver, HudProfileRule
from fpdb_3_legacy.loggingFpdb import get_logger

# config version is used to flag a warning at runtime if the users config is
#  out of date.
# The CONFIG_VERSION should be incremented __ONLY__ if the add_missing_elements()
#  method cannot update existing standard configurations
CONFIG_VERSION = 83
SOURCE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT_PATH = SOURCE_DIR.parent

#
# Setup constants
# code is centralised here to ensure uniform handling of path names
# especially important when user directory includes non-ascii chars
#
#
# FPDB_ROOT_PATH (path to the root fpdb installation dir root (normally ...../fpdb)
# APPDATA_PATH (root path for appdata eg /~ or appdata)
# CONFIG_PATH (path to the directory holding logs, sqlite db's and config)
# GRAPHICS_PATH (path to graphics assets (normally .gfx)
# PYFPDB_PATH (path to py's)
# OS_FAMILY (OS Family for installed system (Linux, Mac, XP, Win7)
# POSIX (True=Linux or Mac platform, False=Windows platform)


def _frozen_resource_root() -> str:
    """Return the directory containing data bundled with a frozen executable."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return os.path.abspath(os.fspath(bundle_dir))
    return os.path.dirname(os.path.abspath(sys.executable))


if hasattr(sys, "frozen"):
    if platform.system() == "Windows":
        INSTALL_METHOD = "exe"
    elif platform.system() == "Darwin":
        INSTALL_METHOD = "app"
    elif "APPDIR" in os.environ:
        INSTALL_METHOD = "appimage"
    else:
        INSTALL_METHOD = "unknown"
else:
    INSTALL_METHOD = "source"

if INSTALL_METHOD == "exe":
    FPDB_ROOT_PATH = _frozen_resource_root()

    FPDB_ROOT_PATH = FPDB_ROOT_PATH.replace("\\", "/")
# should be exe path to \fpdbroot\pyfpdb
elif INSTALL_METHOD == "app":
    FPDB_ROOT_PATH = _frozen_resource_root()
elif INSTALL_METHOD == "appimage":
    FPDB_ROOT_PATH = os.environ["APPDIR"]
elif sys.path[0] == "":  # we are probably running directly (>>>import Configuration)
    temp = os.getcwd()  # should be ./pyfpdb
    FPDB_ROOT_PATH = os.path.join(temp, os.pardir)  # go up one level (to fpdbroot)
else:  # all other cases
    FPDB_ROOT_PATH = os.getcwd()

if INSTALL_METHOD == "source":
    FPDB_ROOT_PATH = str(SOURCE_ROOT_PATH)

sysPlatform = platform.system()  # Linux, Windows, Darwin
if sysPlatform[0:5] == "Linux":
    OS_FAMILY = "Linux"
elif sysPlatform == "Darwin":
    OS_FAMILY = "Mac"
elif sysPlatform == "Windows":
    if platform.release() != "XP":
        OS_FAMILY = "Win7"  # Vista and win7
    else:
        OS_FAMILY = "XP"
else:
    OS_FAMILY = ""

# Where each client actually writes its hand histories, per platform.System().
# Used by Config.detect_hh_path() when the configured HH_path does not exist:
# the shipped defaults are Windows-only, and a config moved between machines
# keeps the previous home directory. Paths are tried in order; "~" is expanded.
HH_PATH_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "SealsWithClubs": {
        # The client's own setting, "Hand History Folder", defaults to Documents.
        "Darwin": ("~/Documents/SwC Poker/Hand History",),
        "Linux": ("~/Documents/SwC Poker/Hand History",),
        "Windows": (
            "~/Documents/SwC Poker/Hand History",
            "C:/Program Files/SealsWithClubs/handhistories",
        ),
    },
    # All WinningPoker Network skins share the same ACR client / paths.
    "Americas Cardroom": {
        "Darwin": ("~/Downloads/AmericasCardroom/handHistory",),
        "Windows": (
            "C:/ACR Poker/handHistory",
            "~/Documents/AmericasCardroom/handHistory",
        ),
    },
    "ACR Poker": {
        "Darwin": ("~/Downloads/AmericasCardroom/handHistory",),
        "Windows": (
            "C:/ACR Poker/handHistory",
            "~/Documents/AmericasCardroom/handHistory",
        ),
    },
    "WinningPoker": {
        "Darwin": ("~/Downloads/AmericasCardroom/handHistory",),
        "Windows": (
            "C:/ACR Poker/handHistory",
            "~/Documents/AmericasCardroom/handHistory",
        ),
    },
    "BlackChipPoker": {
        "Darwin": ("~/Downloads/AmericasCardroom/handHistory",),
        "Windows": (
            "C:/ACR Poker/handHistory",
            "~/Documents/AmericasCardroom/handHistory",
        ),
    },
    "TruePoker": {
        "Darwin": ("~/Downloads/AmericasCardroom/handHistory",),
        "Windows": (
            "C:/ACR Poker/handHistory",
            "~/Documents/AmericasCardroom/handHistory",
        ),
    },
    "Ya Poker": {
        "Darwin": ("~/Downloads/AmericasCardroom/handHistory",),
        "Windows": (
            "C:/ACR Poker/handHistory",
            "~/Documents/AmericasCardroom/handHistory",
        ),
    },
}

# Sites whose HH/TS paths can be read from the ACR macOS Electron client's
# local storage.  Maps site name -> JSON config key used in the filename
# ``~/Library/Application Support/Loading/storage/hhDirPath_{key}.json``.
_ACR_JSON_CONFIG_SITES: dict[str, str] = {
    "Americas Cardroom": "AmericasCardroom",
    "ACR Poker": "AmericasCardroom",
    "WinningPoker": "AmericasCardroom",
    "BlackChipPoker": "AmericasCardroom",
    "TruePoker": "AmericasCardroom",
    "Ya Poker": "AmericasCardroom",
}


if OS_FAMILY in ["XP", "Win7"]:
    APPDATA_PATH = winpaths_appdata
    CONFIG_PATH = os.path.join(APPDATA_PATH, "fpdb")
    CONFIG_PATH = CONFIG_PATH.replace("\\", "/")
    if INSTALL_METHOD == "source":
        # gfx/ lives at the repository root (SOURCE_ROOT_PATH), i.e. the parent
        # of this module's fpdb_3_legacy/ directory — not next to this file.
        GRAPHICS_PATH = (str(SOURCE_ROOT_PATH) + "/gfx").replace("\\", "/")
    else:
        FPDB_ROOT_PATH = _frozen_resource_root().replace("\\", "/")
        GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
        GRAPHICS_PATH = GRAPHICS_PATH.replace("\\", "/")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")
    PYFPDB_PATH = PYFPDB_PATH.replace("\\", "/")
elif OS_FAMILY == "Mac":
    APPDATA_PATH = os.getenv("HOME") or os.path.expanduser("~")
    CONFIG_PATH = os.path.join(APPDATA_PATH, ".fpdb")
    GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
    PYFPDB_PATH = str(SOURCE_DIR) if INSTALL_METHOD == "source" else os.path.join(FPDB_ROOT_PATH, "pyfpdb")
elif OS_FAMILY == "Linux":
    APPDATA_PATH = os.path.expanduser("~")
    CONFIG_PATH = os.path.join(APPDATA_PATH, ".fpdb")
    GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
    PYFPDB_PATH = str(SOURCE_DIR) if INSTALL_METHOD == "source" else os.path.join(FPDB_ROOT_PATH)
else:
    APPDATA_PATH = ""
    CONFIG_PATH = ""

POSIX = os.name == "posix"

PYTHON_VERSION = sys.version[:3]

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("configuration")


def _find_example_config(file_name: str) -> str:
    """Return the first existing example config, or its user-config fallback."""
    example_name = f"{file_name}.example"
    candidates = [
        os.path.join("/usr/share/python-fpdb", example_name),
        example_name,
        os.path.join(str(SOURCE_ROOT_PATH), example_name),
        os.path.join(str(SOURCE_DIR), example_name),
        os.path.join(FPDB_ROOT_PATH, example_name),
        os.path.join(PYFPDB_PATH, example_name),
    ]
    for candidate in candidates:
        normalized = candidate.replace("\\", "/")
        if os.path.exists(normalized):
            return normalized
    return os.path.join(CONFIG_PATH, example_name).replace("\\", "/")


def get_config(file_name, fallback=True):
    """Resolve a user config and optionally bootstrap it from an example file."""
    config_path = os.path.join(CONFIG_PATH, file_name).replace("\\", "/")
    config_found = os.path.exists(config_path)
    example_copy = False
    example_path = _find_example_config(file_name)

    if not config_found and fallback:
        if os.path.exists(example_path):
            try:
                shutil.copyfile(example_path, config_path)
                example_copy = True
                log.info(f"Config file has been created at {config_path} from {example_path}.")
            except OSError:
                log.exception("Error copying .example config file, cannot fall back. Exiting.")
                sys.stderr.write("Error copying .example config file, cannot fall back. Exiting.\n")
                sys.stderr.write(str(sys.exc_info()))
                sys.exit()
        else:
            sys.stderr.write(f"No {file_name} found, cannot fall back. Exiting.\n")
            sys.exit()

    return (config_path, example_copy, example_path)


def set_logfile(file_name) -> None:
    log_dir = os.path.join(CONFIG_PATH, "log").replace("\\", "/")
    check_dir(log_dir)
    log_file = os.path.join(log_dir, file_name).replace("\\", "/")

    try:
        log.info(f"Logging initialized to file: {log_file}")
    except Exception as e:  # intentional broad catch: startup logging best-effort, fall back to stderr
        if not sys.stderr:
            sys.stderr = open(os.devnull, "w")
        sys.stderr.write(f"Could not setup log file {file_name}: {e}\n")


def check_dir(path, create=True):
    """Check if a dir exists, optionally creates if not."""
    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        return False
    if create:
        path = path.replace("\\", "/")
        msg = f"Creating directory: '{path}'"

        log.info(f"Directory: {msg}")
        os.makedirs(path)  # , "utf-8"))
        return None
    return False


def normalizePath(path):
    """Normalized existing pathes."""
    if os.path.exists(path):
        return os.path.abspath(path)
    return path


########################################################################
# application wide consts

APPLICATION_NAME_SHORT = "fpdb"
APPLICATION_VERSION = "xx.xx.xx"

DATABASE_TYPE_POSTGRESQL = "postgresql"
DATABASE_TYPE_SQLITE = "sqlite"
DATABASE_TYPE_MYSQL = "mysql"
DATABASE_TYPES = (
    DATABASE_TYPE_POSTGRESQL,
    DATABASE_TYPE_SQLITE,
    DATABASE_TYPE_MYSQL,
)

LOCALE_ENCODING = locale.getpreferredencoding()
if LOCALE_ENCODING in ("US-ASCII", "", None):
    LOCALE_ENCODING = "cp1252"
    if os.uname()[0] != "Darwin":
        log.warning(
            (
                ("Default encoding set to US-ASCII, defaulting to CP1252 instead."),
                ("Please report this problem."),
            ),
        )

# needs LOCALE_ENCODING (above), imported for sqlite setup in Config class below


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


class Layout:
    def __init__(self, node) -> None:
        self.max = int(node.getAttribute("max"))
        self.width = int(node.getAttribute("width"))
        self.height = int(node.getAttribute("height"))

        self.location: list[Any] = []
        self.hh_seats: list[Any] = []
        self.location = [None for x in range(self.max + 1)]  # fill array with max seats+1 empty entries
        # hh_seats is used to map the seat numbers specified in hand history files (and stored in db) onto
        #   the contiguous integerss, 1 to self.max, used to index hud stat_windows (and aw seat_windows) for display
        #   For most sites these numbers are the same, but some sites (e.g. iPoker) omit seat numbers in hand histories
        #   for tables smaller than 10-max.
        self.hh_seats = [None for x in range(self.max + 1)]  # fill array with max seats+1 empty entries

        for location_node in node.getElementsByTagName("location"):
            hud_seat = location_node.getAttribute("seat")
            if hud_seat != "":
                # if hist_seat for this seat number is specified in the layout, then store it in the hh_seats list
                hist_seat = location_node.getAttribute("hist_seat")  # XXX
                if hist_seat:
                    self.hh_seats[int(hud_seat)] = int(hist_seat)
                else:
                    # .. otherwise just store the original seat number in the hh_seats list
                    self.hh_seats[int(hud_seat)] = int(hud_seat)
                self.location[int(hud_seat)] = (
                    int(location_node.getAttribute("x")),
                    int(location_node.getAttribute("y")),
                )
            elif location_node.getAttribute("common") != "":
                self.common = (
                    int(location_node.getAttribute("x")),
                    int(location_node.getAttribute("y")),
                )

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


class Email:
    def __init__(self, node) -> None:
        self.node = node
        self.host = node.getAttribute("host")
        self.username = node.getAttribute("username")
        self.password = node.getAttribute("password")
        self.useSsl = node.getAttribute("useSsl")
        self.folder = node.getAttribute("folder")
        self.fetchType = node.getAttribute("fetchType")

    def __str__(self) -> str:
        return f"    email\n        fetchType = {self.fetchType}  host = {self.host}\n        username = {self.username} password = {self.password}\n        useSsl = {self.useSsl} folder = {self.folder}"


class Site:
    def __init__(self, node) -> None:
        self.site_name = node.getAttribute("site_name")
        self.screen_name = node.getAttribute("screen_name")
        self.site_path = normalizePath(node.getAttribute("site_path"))
        self.HH_path = normalizePath(node.getAttribute("HH_path"))
        self.TS_path = normalizePath(node.getAttribute("TS_path"))
        self.enabled = string_to_bool(node.getAttribute("enabled"), default=True)
        self.aux_enabled = string_to_bool(node.getAttribute("aux_enabled"), default=True)
        self.hud_menu_xshift = node.getAttribute("hud_menu_xshift")
        self.hud_menu_xshift = 1 if self.hud_menu_xshift == "" else int(self.hud_menu_xshift)
        self.hud_menu_yshift = node.getAttribute("hud_menu_yshift")
        self.hud_menu_yshift = 1 if self.hud_menu_yshift == "" else int(self.hud_menu_yshift)
        if node.hasAttribute("TS_path"):
            self.TS_path = normalizePath(node.getAttribute("TS_path"))
        else:
            self.TS_path = ""

        # Support for the network attribute (configuration by skins)
        self.network = node.getAttribute("network") if node.hasAttribute("network") else "Unknown"

        # Hero aliases: a room can recognise several screen names as the hero
        # (nickname changes, multiple accounts). The primary ``screen_name`` is
        # always the first alias; additional ones come from <hero_alias> child
        # elements. Backward compatible: no <hero_alias> => [screen_name].
        self.hero_aliases = []
        _seen_aliases = set()
        for _alias in [self.screen_name] + [n.getAttribute("name") for n in node.getElementsByTagName("hero_alias")]:
            if _alias and _alias not in _seen_aliases:
                _seen_aliases.add(_alias)
                self.hero_aliases.append(_alias)

        self.fav_seat = {}
        for fav_node in node.getElementsByTagName("fav"):
            max = int(fav_node.getAttribute("max"))
            fav = int(fav_node.getAttribute("fav_seat"))
            self.fav_seat[max] = fav

        self.layout_set = {}
        for site_layout_node in node.getElementsByTagName("layout_set"):
            gt = site_layout_node.getAttribute("game_type")
            ls = site_layout_node.getAttribute("ls")
            self.layout_set[gt] = ls

        self.emails = {}
        for email_node in node.getElementsByTagName("email"):
            email = Email(email_node)
            self.emails[email.fetchType] = email

    def __str__(self) -> str:
        temp = "Site = " + self.site_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            if key == "layout_set":
                continue
            if key == "fav_seat":
                continue
            if key == "emails":
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + str(value) + "\n"

        for fetchtype in self.emails:
            temp = temp + str(self.emails[fetchtype]) + "\n"

        for game_type in self.layout_set:
            temp = temp + f"    game_type = {game_type}, layout_set = {self.layout_set[game_type]}\n"

        for max in self.fav_seat:
            temp = temp + f"    max = {max}, fav_seat = {self.fav_seat[max]}\n"

        return temp


class HeroProfile:
    """A logical hero identity spanning one or more rooms.

    Links a set of ``(site_name, alias)`` pairs so stats/reports can aggregate a
    player's identity across rooms (e.g. ``jeje`` on Stars + ``jeje76`` on
    Winamax). Parsed from::

        <hero_profile name="Me" default="True">
            <link site_name="PokerStars" alias="jeje"/>
            <link site_name="Winamax"    alias="jeje76"/>
        </hero_profile>
    """

    def __init__(self, node) -> None:
        self.name = node.getAttribute("name")
        self.default = string_to_bool(node.getAttribute("default"), default=False)
        self.links: list[tuple[str, str]] = []
        seen = set()
        for link in node.getElementsByTagName("link"):
            site = link.getAttribute("site_name")
            alias = link.getAttribute("alias")
            if site and alias and (site, alias) not in seen:
                seen.add((site, alias))
                self.links.append((site, alias))

    def aliases_by_site(self):
        """Return ``{site_name: [alias, ...]}`` for this profile."""
        out: dict[str, list[str]] = {}
        for site, alias in self.links:
            out.setdefault(site, []).append(alias)
        return out

    def sites(self):
        """Return the ordered, deduplicated list of sites in this profile."""
        out: list[str] = []
        for site, _alias in self.links:
            if site not in out:
                out.append(site)
        return out

    def __str__(self) -> str:
        links = ", ".join(f"{s}:{a}" for s, a in self.links)
        return f"HeroProfile {self.name} (default={self.default}) [{links}]"


class Stat:
    def __init__(self, node) -> None:
        rowcol = node.getAttribute("_rowcol")  # human string "(r,c)" values >0)
        self.rows = node.getAttribute("rows")
        self.cols = node.getAttribute("cols")
        self.rowcol = tuple(int(s) - 1 for s in rowcol[1:-1].split(","))  # tuple (r-1,c-1)
        self.stat_name = node.getAttribute("_stat_name")
        self.tip = node.getAttribute("tip")
        self.click = node.getAttribute("click")
        self.popup = node.getAttribute("popup")
        self.hudprefix = node.getAttribute("hudprefix")
        self.hudsuffix = node.getAttribute("hudsuffix")
        self.hudcolor = node.getAttribute("hudcolor")
        self.hudbgcolor = node.getAttribute("hudbgcolor")
        self.stat_loth = node.getAttribute("stat_loth")
        self.stat_hith = node.getAttribute("stat_hith")
        self.stat_locolor = node.getAttribute("stat_locolor")
        self.stat_hicolor = node.getAttribute("stat_hicolor")
        self.stat_midcolor = node.getAttribute("stat_midcolor")
        # PT4-style cell layout: a stat may span several columns and align its text.
        cs = node.getAttribute("colspan")
        self.colspan = int(cs) if cs else 1
        self.align = node.getAttribute("align") or "center"

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
            self.label = node.getAttribute("label")
            self.id = node.getAttribute("id") or ""
            self.scope = node.getAttribute("scope") or "player"
            self.audience = node.getAttribute("audience") or "everyone"
            # Optional position binding: when set, the block is only shown for a
            # player in that position this hand (e.g. "SB"/"BB"/"BTN"); empty
            # means always shown.
            self.position = node.getAttribute("position")
            self.bgcolor = node.getAttribute("bgcolor")
            self.fgcolor = node.getAttribute("fgcolor")
            self.bordercolor = node.getAttribute("bordercolor")
            self.title_bgcolor = node.getAttribute("title_bgcolor")
            self.title_fgcolor = node.getAttribute("title_fgcolor")
            self.cell_width = int(node.getAttribute("cell_width")) if node.getAttribute("cell_width") else 0
            self.x = int(node.getAttribute("x")) if node.getAttribute("x") else 0
            self.y = int(node.getAttribute("y")) if node.getAttribute("y") else 0
            self.stats = {}
            for stat_node in node.getElementsByTagName("stat"):
                stat = Stat(stat_node)
                self.stats[stat.rowcol] = stat
            # Text-label items (column/row headers, section captions like
            # "POST FLOP") — PT4-style group items that are not data cells.
            self.texts = [self._parse_text(t) for t in node.getElementsByTagName("text")]
            # Horizontal-line separators (PT4 "Horz Line" group items).
            self.hlines = [self._parse_hline(h) for h in node.getElementsByTagName("hline")]
            self.rows = int(node.getAttribute("rows")) if node.getAttribute("rows") else 0
            self.cols = int(node.getAttribute("cols")) if node.getAttribute("cols") else 0
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
        rc = node.getAttribute("_rowcol")
        try:
            rowcol = tuple(int(s) - 1 for s in rc[1:-1].split(",")) if rc else (0, 0)
        except ValueError:
            rowcol = (0, 0)
        cs = node.getAttribute("colspan")
        return {
            "rowcol": rowcol,
            "label": node.getAttribute("label"),
            "colspan": int(cs) if cs else 1,
            "align": node.getAttribute("align") or "center",
            "fgcolor": node.getAttribute("fgcolor"),
            "bgcolor": node.getAttribute("bgcolor"),
        }

    @staticmethod
    def _parse_hline(node) -> dict:
        """Parse an ``<hline>`` separator item within a block."""
        rc = node.getAttribute("_rowcol")
        try:
            rowcol = tuple(int(s) - 1 for s in rc[1:-1].split(",")) if rc else (0, 0)
        except ValueError:
            rowcol = (0, 0)
        cs = node.getAttribute("colspan")
        return {
            "rowcol": rowcol,
            "colspan": int(cs) if cs else 0,  # 0 -> span the whole block width
            "color": node.getAttribute("color"),
        }

    def __str__(self) -> str:
        temp = f"        Block '{self.label}' rows={self.rows} cols={self.cols}\n"
        for key in self.stats:
            temp += f"{self.stats[key]}"
        return temp


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
        self.name = node.getAttribute("name")
        self.show_hero_hud = node.getAttribute("show_hero_hud")
        # Opt-in compact rich-text rendering for the permanent HUD cells.
        # This belongs to the stat-set (rather than a poker variant) so any
        # current or future game profile can reuse the presentation mode.
        self.rich_text = node.getAttribute("rich_text")
        # Optional profile-specific font size. An empty value keeps the global
        # HUD font setting, while a profile can opt into a larger compact grid.
        self.font_size = node.getAttribute("font_size")
        # How position-bound panels (SB/BB/BU) display in a multi-block HUD:
        #   "current" -> show only the panel matching the estimated live position
        #                (the positional HUD's expected behaviour and default);
        #   "all"     -> show every position panel at once, stacked.
        self.positional_mode = node.getAttribute("positional_mode") or "current"
        self.rows = int(node.getAttribute("rows"))
        self.cols = int(node.getAttribute("cols"))
        self.xpad = node.getAttribute("xpad")
        self.xpad = 0 if self.xpad == "" else int(self.xpad)
        self.ypad = node.getAttribute("ypad")
        self.ypad = 0 if self.ypad == "" else int(self.ypad)
        self.stats = None

        # A stat-set may either list <stat> elements directly (a single grid, the
        # classic layout) or group them into <block> elements (several stacked
        # panels per seat — the PT4-style multi-panel layout). Either way it is
        # normalised into self.blocks; self.stats keeps the flat union so legacy
        # readers keep working.
        self.blocks = []
        block_nodes = node.getElementsByTagName("block")
        if block_nodes:
            self.blocks = [StatBlock(bn) for bn in block_nodes]
        else:
            stats = {}
            for stat_node in node.getElementsByTagName("stat"):
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


class Database:
    def __init__(self, node) -> None:
        self.db_name = node.getAttribute("db_name")
        self.db_desc = node.getAttribute("db_desc")
        self.db_server = node.getAttribute("db_server").lower()
        self.db_ip = node.getAttribute("db_ip")
        self.db_port = node.getAttribute("db_port")
        self.db_user = node.getAttribute("db_user")
        self.db_pass = node.getAttribute("db_pass")
        self.db_path = node.getAttribute("db_path")
        self.db_selected = string_to_bool(node.getAttribute("default"), default=False)
        log.debug(
            f"Database db_name:'{self.db_name}'  db_server:'{self.db_server}'  db_ip:'{self.db_ip}'  db_port:'{self.db_port}' db_user:'{self.db_user}'  db_pass (not logged)  selected:'{self.db_selected}'",
        )

    def __str__(self) -> str:
        temp = "Database = " + self.db_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + repr(value) + "\n"
        return temp


class Aux_window:
    def __init__(self, node) -> None:
        self.name = ""
        for name, value in list(node.attributes.items()):
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


class Supported_games:
    def __init__(self, node) -> None:
        self.game_name = ""
        for name, value in list(node.attributes.items()):
            setattr(self, name, value)

        self.game_stat_set = {}
        for game_stat_set_node in node.getElementsByTagName("game_stat_set"):
            gss = Game_stat_set(game_stat_set_node)
            self.game_stat_set[gss.game_type] = gss

    def __str__(self) -> str:
        temp = "Supported_games = " + self.game_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            if key == "game_stat_set":
                continue
            if key == "game_name":
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + value + "\n"

        for gs in self.game_stat_set:
            temp = temp + f"{self.game_stat_set[gs]!s}"
        return temp


class Layout_set:
    def __init__(self, node) -> None:
        self.name = ""
        for name, value in list(node.attributes.items()):
            setattr(self, name, value)

        self.layout = {}
        for layout_node in node.getElementsByTagName("layout"):
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


class Game_stat_set:
    def __init__(self, node) -> None:
        self.game_type = node.getAttribute("game_type")
        self.stat_set = node.getAttribute("stat_set")

    def __str__(self) -> str:
        return f"      Game Type: '{self.game_type}' Stat Set: '{self.stat_set}'\n"


class HHC:
    def __init__(self, node) -> None:
        self.site = node.getAttribute("site")
        self.converter = node.getAttribute("converter")
        self.summaryImporter = node.getAttribute("summaryImporter")

    def __str__(self) -> str:
        return f"{self.site}:\tconverter: '{self.converter}' summaryImporter: '{self.summaryImporter}'"


class Popup:
    def __init__(self, node) -> None:
        self.name = node.getAttribute("pu_name")
        self.pu_class = node.getAttribute("pu_class")
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
            if node.getAttribute(xml_name):
                self.pu_class_params[param_name] = node.getAttribute(xml_name)

        for stat_node in node.getElementsByTagName("pu_stat"):
            self.pu_stats.append(stat_node.getAttribute("pu_stat_name"))
            self.pu_stats_category.append(stat_node.getAttribute("pu_stat_category"))
            self.pu_stats_label.append(stat_node.getAttribute("pu_stat_label"))
            self.pu_stats_color.append(stat_node.getAttribute("pu_stat_color"))
            # if stat_node.getAttribute("pu_stat_submenu"):
            self.pu_stats_submenu.append(
                (
                    stat_node.getAttribute("pu_stat_name"),
                    stat_node.getAttribute("pu_stat_submenu"),
                ),
            )

    def __str__(self) -> str:
        temp = "Popup = " + self.name + "  Class = " + self.pu_class + "\n"
        for stat in self.pu_stats:
            temp = temp + " " + stat
        return temp + "\n"


class Import:
    def __init__(self, node) -> None:
        self.node = node
        self.interval = node.getAttribute("interval")
        self.sessionTimeout = string_to_bool(node.getAttribute("sessionTimeout"), default=30)
        self.ResultsDirectory = node.getAttribute("ResultsDirectory")
        self.hhBulkPath = node.getAttribute("hhBulkPath")
        self.saveActions = string_to_bool(node.getAttribute("saveActions"), default=False)
        self.cacheSessions = string_to_bool(node.getAttribute("cacheSessions"), default=False)
        self.publicDB = string_to_bool(node.getAttribute("publicDB"), default=False)
        self.callFpdbHud = string_to_bool(node.getAttribute("callFpdbHud"), default=False)
        self.fastStoreHudCache = string_to_bool(node.getAttribute("fastStoreHudCache"), default=False)
        self.saveStarsHH = string_to_bool(node.getAttribute("saveStarsHH"), default=False)
        if node.getAttribute("importFilters"):
            self.importFilters = node.getAttribute("importFilters").split(",")
        else:
            self.importFilters = []
        if node.getAttribute("timezone"):
            self.timezone = node.getAttribute("timezone")
        else:
            self.timezone = "America/New_York"

    def __str__(self) -> str:
        return f"    interval = {self.interval}\n    callFpdbHud = {self.callFpdbHud}\n    saveActions = {self.saveActions}\n   cacheSessions = {self.cacheSessions}\n    publicDB = {self.publicDB}\n    sessionTimeout = {self.sessionTimeout}\n    fastStoreHudCache = {self.fastStoreHudCache}\n    ResultsDirectory = {self.ResultsDirectory}"


class HudUI:
    def __init__(self, node) -> None:
        self.node = node
        self.label = node.getAttribute("label")
        if node.hasAttribute("card_ht"):
            self.card_ht = node.getAttribute("card_ht")
        if node.hasAttribute("card_wd"):
            self.card_wd = node.getAttribute("card_wd")
        if node.hasAttribute("deck_type"):
            self.deck_type = node.getAttribute("deck_type")
        if node.hasAttribute("card_back"):
            self.card_back = node.getAttribute("card_back")
        if node.hasAttribute("stat_range"):
            self.stat_range = node.getAttribute("stat_range")
        if node.hasAttribute("stat_days"):
            self.hud_days = node.getAttribute("stat_days")
        if node.hasAttribute("aggregation_level_multiplier"):
            self.agg_bb_mult = node.getAttribute("aggregation_level_multiplier")
        if node.hasAttribute("seats_style"):
            self.seats_style = node.getAttribute("seats_style")
        if node.hasAttribute("seats_cust_nums_low"):
            self.seats_cust_nums_low = node.getAttribute("seats_cust_nums_low")
        if node.hasAttribute("seats_cust_nums_high"):
            self.seats_cust_nums_high = node.getAttribute("seats_cust_nums_high")
        if node.hasAttribute("hero_stat_range"):
            self.h_stat_range = node.getAttribute("hero_stat_range")
        if node.hasAttribute("hero_stat_days"):
            self.h_hud_days = node.getAttribute("hero_stat_days")
        if node.hasAttribute("hero_aggregation_level_multiplier"):
            self.h_agg_bb_mult = node.getAttribute("hero_aggregation_level_multiplier")
        if node.hasAttribute("hero_seats_style"):
            self.h_seats_style = node.getAttribute("hero_seats_style")
        if node.hasAttribute("hero_seats_cust_nums_low"):
            self.h_seats_cust_nums_low = node.getAttribute("hero_seats_cust_nums_low")
        if node.hasAttribute("hero_seats_cust_nums_high"):
            self.h_seats_cust_nums_high = node.getAttribute("hero_seats_cust_nums_high")

        # Additional HUD positioning attributes
        if node.hasAttribute("xshift"):
            self.xshift = node.getAttribute("xshift")
        if node.hasAttribute("yshift"):
            self.yshift = node.getAttribute("yshift")

        # Aggregation settings
        if node.hasAttribute("aggregate_ring"):
            self.aggregate_ring = node.getAttribute("aggregate_ring")
        if node.hasAttribute("aggregate_tour"):
            self.aggregate_tour = node.getAttribute("aggregate_tour")
        if node.hasAttribute("hud_style"):
            self.hud_style = node.getAttribute("hud_style")
        if node.hasAttribute("hero_stat_aggregation"):
            self.hero_stat_aggregation = node.getAttribute("hero_stat_aggregation")
        if node.hasAttribute("h_hud_style"):
            self.h_hud_style = node.getAttribute("h_hud_style")

        # Player profiling settings
        if node.hasAttribute("player_profiling"):
            self.player_profiling = node.getAttribute("player_profiling")
        if node.hasAttribute("profile_in_name"):
            self.profile_in_name = node.getAttribute("profile_in_name")
        if node.hasAttribute("profile_min_hands"):
            self.profile_min_hands = node.getAttribute("profile_min_hands")

        # Appearance settings
        if node.hasAttribute("bgcolor"):
            self.bgcolor = node.getAttribute("bgcolor")
        if node.hasAttribute("fgcolor"):
            self.fgcolor = node.getAttribute("fgcolor")
        if node.hasAttribute("hudbgcolor"):
            self.hudbgcolor = node.getAttribute("hudbgcolor")
        if node.hasAttribute("hudfgcolor"):
            self.hudfgcolor = node.getAttribute("hudfgcolor")
        if node.hasAttribute("font"):
            self.font = node.getAttribute("font")
        if node.hasAttribute("font_size"):
            self.font_size = node.getAttribute("font_size")

        # HUD opacity
        if node.hasAttribute("opacity"):
            self.opacity = node.getAttribute("opacity")

        # Popup settings
        if node.hasAttribute("popup_style"):
            self.popup_style = node.getAttribute("popup_style")

        # Mucked cards settings
        if node.hasAttribute("mucked_cards"):
            self.mucked_cards = node.getAttribute("mucked_cards")
        if node.hasAttribute("mucked_cards_size"):
            self.mucked_cards_size = node.getAttribute("mucked_cards_size")
        if node.hasAttribute("mucked_cards_opacity"):
            self.mucked_cards_opacity = node.getAttribute("mucked_cards_opacity")

        # Aux windows settings
        if node.hasAttribute("aux_windows"):
            self.aux_windows = node.getAttribute("aux_windows")
        if node.hasAttribute("aux_windows_opacity"):
            self.aux_windows_opacity = node.getAttribute("aux_windows_opacity")

        # HUD menu settings
        if node.hasAttribute("hud_menu_opacity"):
            self.hud_menu_opacity = node.getAttribute("hud_menu_opacity")
        if node.hasAttribute("hud_menu_bgcolor"):
            self.hud_menu_bgcolor = node.getAttribute("hud_menu_bgcolor")
        if node.hasAttribute("hud_menu_fgcolor"):
            self.hud_menu_fgcolor = node.getAttribute("hud_menu_fgcolor")

        # Stat window settings
        if node.hasAttribute("stat_window_opacity"):
            self.stat_window_opacity = node.getAttribute("stat_window_opacity")
        if node.hasAttribute("stat_window_frame"):
            self.stat_window_frame = node.getAttribute("stat_window_frame")

        # Tooltip settings
        if node.hasAttribute("tooltip_delay"):
            self.tooltip_delay = node.getAttribute("tooltip_delay")
        if node.hasAttribute("tooltip_bgcolor"):
            self.tooltip_bgcolor = node.getAttribute("tooltip_bgcolor")
        if node.hasAttribute("tooltip_fgcolor"):
            self.tooltip_fgcolor = node.getAttribute("tooltip_fgcolor")

        # Advanced settings
        if node.hasAttribute("update_interval"):
            self.update_interval = node.getAttribute("update_interval")
        if node.hasAttribute("max_seats"):
            self.max_seats = node.getAttribute("max_seats")
        if node.hasAttribute("debug_level"):
            self.debug_level = node.getAttribute("debug_level")

        # Behaviour settings. set_hud_ui_parameters has always written these
        # seven onto the node, but nothing read them back, so each one reached
        # the file and then lost to the default on the next start.
        if node.hasAttribute("auto_close"):
            self.auto_close = node.getAttribute("auto_close")
        if node.hasAttribute("block_click"):
            self.block_click = node.getAttribute("block_click")
        if node.hasAttribute("on_click"):
            self.on_click = node.getAttribute("on_click")
        if node.hasAttribute("disable_hud"):
            self.disable_hud = node.getAttribute("disable_hud")
        if node.hasAttribute("debug_hud"):
            self.debug_hud = node.getAttribute("debug_hud")
        if node.hasAttribute("save_layout"):
            self.save_layout = node.getAttribute("save_layout")
        if node.hasAttribute("query_limit"):
            self.query_limit = node.getAttribute("query_limit")

    def __str__(self) -> str:
        return f"    label = {self.label}\n"


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
        except KeyError:
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


class RawHands:
    def __init__(self, node=None) -> None:
        if node is None:
            self.save = "error"
            self.compression = "none"
            # print ("missing config section raw_hands")
        else:
            save = node.getAttribute("save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                log.warning(f"Invalid raw_hands save value {save!r}, defaulting to error")
                self.save = "error"

            compression = node.getAttribute("compression")
            if compression in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                log.warning(f"Invalid raw_hands compression value {compression!r}, defaulting to none")
                self.compression = "none"

    # end def __init__

    def __str__(self) -> str:
        return f"        save= {self.save}, compression= {self.compression}\n"


# end class RawHands


class RawTourneys:
    def __init__(self, node=None) -> None:
        if node is None:
            self.save = "error"
            self.compression = "none"
            # print ("missing config section raw_tourneys")
        else:
            save = node.getAttribute("save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                log.warning(f"Invalid raw_tourneys save value {save!r}, defaulting to error")
                self.save = "error"

            compression = node.getAttribute("compression")
            if compression in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                log.warning(f"Invalid raw_tourneys compression value {compression!r}, defaulting to none")
                self.compression = "none"

    # end def __init__

    def __str__(self) -> str:
        return f"        save= {self.save}, compression= {self.compression}\n"


# end class RawTourneys


# Entain France skins that left the PartyPoker network for iPoker in 2026.
# Old user configs still declare them with network="PartyPoker" and the
# PartyPoker converter; Config.__init__ migrates such entries in place.
ENTAIN_FR_IPOKER_SITES = ("Bwin.fr Poker", "PartyPoker.fr")

# Windows data directories of the new Entain France iPoker clients, used to
# repoint HH_path/TS_path during the migration (client/data/<account>/History).
ENTAIN_FR_WINDOWS_DATA_DIRS: dict[str, tuple[str, ...]] = {
    "Bwin.fr Poker": ("bwin Poker France",),
}


def parse_hud_profile_rules(doc: Any) -> list[HudProfileRule]:
    """Read the <hud_profile_rules> section of a configuration document.

    Shared by the initial load and by ``Config.reload()``: a rule the user has
    just saved has to reach the running HUD, and reload was the one path that
    did not re-read this section.
    """
    rules = []
    for order, rule_node in enumerate(doc.getElementsByTagName("hud_profile_rule")):
        values = {name: rule_node.getAttribute(name) for name in rule_node.attributes.keys()}
        rule = HudProfileRule.from_mapping(values, order)
        if rule.profile:
            rules.append(rule)
    return rules


class Config:
    def __init__(
        self,
        file=None,
        dbname: str | None = None,
        custom_log_dir: str | bytes = "",
        lvl="INFO",
    ) -> None:
        self.install_method = INSTALL_METHOD
        self.fpdb_root_path = FPDB_ROOT_PATH
        self.appdata_path = APPDATA_PATH
        self.config_path = CONFIG_PATH
        self.pyfpdb_path = PYFPDB_PATH
        self.graphics_path = GRAPHICS_PATH
        self.os_family = OS_FAMILY
        self.posix = POSIX
        self.python_version = PYTHON_VERSION

        if not os.path.exists(CONFIG_PATH):
            os.makedirs(CONFIG_PATH)

        if custom_log_dir and os.path.exists(custom_log_dir):
            # os.fsdecode leaves a str alone and decodes bytes the way the
            # platform names its files. The previous str(value, "utf8") only
            # accepted bytes, so the str the signature asks for raised
            # TypeError and the parameter could not be used as documented.
            self.dir_log = os.fsdecode(custom_log_dir)
        else:
            self.dir_log = os.path.join(CONFIG_PATH, "log").replace("\\", "/")
        self.log_file = os.path.join(self.dir_log, "fpdb-log.txt")
        log = get_logger("config")

        #    "file" is a path to an xml file with the fpdb/HUD configuration
        #    we check the existence of "file" and try to recover if it doesn't exist

        #        self.default_config_path = self.get_default_config_path()
        self.example_copy = False
        if file is not None:  # config file path passed in
            file = os.path.expanduser(file)
            if not os.path.exists(file):
                log.warning(f"Configuration file {file} not found. Using defaults.")
                sys.stderr.write(f"Configuration file {file} not found. Using defaults.")
                file = None

        uses_default_config = file is None
        self.example_copy, example_file = True, None
        if file is None:
            (file, self.example_copy, example_file) = get_config("HUD_config.xml", True)

        self.file = file

        self.supported_sites: dict[str, Any] = {}
        self.hero_profiles: dict[str, HeroProfile] = {}
        self.supported_games: dict[str, Supported_games] = {}
        self.supported_databases: dict[str, Database] = {}
        self.aux_windows: dict[str, Aux_window] = {}
        self.layout_sets: dict[str, Layout_set] = {}
        self.stat_sets: dict[str, Any] = {}
        self.hhcs: dict[str, Any] = {}
        self.popup_windows: dict[str, Any] = {}
        self.hud_profile_rules: list[HudProfileRule] = []
        self.db_selected = None  # database the user would like to use
        self.general = General()
        self.emails: dict[str, Any] = {}
        self.gui_cash_stats = GUICashStats()
        self.gui_tour_stats = GUITourStats()
        self.site_ids: dict[str, int] = {}
        self.doc: Any = None  # Root of XML tree

        added, n = (
            1,
            0,
        )  # use n to prevent infinite loop if add_missing_elements() fails somehow
        doc: Any = None
        while added > 0 and n < 2:
            n = n + 1
            log.info(f"Reading configuration file {file}")
            try:
                doc = defusedxml.minidom.parse(file)
                self.doc = doc  # Root of XML tree
                self.file_error = None

            except XML_PARSE_ERRORS as e:
                log.exception(f"Error while processing XML: {traceback.format_exc()} Exception: {e}")
                self.file_error = str(e)
                break

            if (not self.example_copy) and (example_file is not None):
                # reads example file and adds missing elements into current config
                added = self.add_missing_elements(doc, example_file)

        if doc is None:
            raise ValueError(f"Unable to load configuration file {file}")

        if doc.getElementsByTagName("general") == []:
            self.general.get_defaults()
        for gen_node in doc.getElementsByTagName("general"):
            self.general.add_elements(node=gen_node)  # add/overwrite elements in self.general

        if int(self.general["version"]) == CONFIG_VERSION:
            self.wrongConfigVersion = False
        else:
            self.wrongConfigVersion = True

        if doc.getElementsByTagName("gui_cash_stats") == []:
            self.gui_cash_stats.get_defaults()
        for gcs_node in doc.getElementsByTagName("gui_cash_stats"):
            self.gui_cash_stats.add_elements(node=gcs_node)  # add/overwrite elements in self.gui_cash_stats
        self.gui_cash_stats.add_missing_defaults()

        if doc.getElementsByTagName("gui_tour_stats") == []:
            self.gui_tour_stats.get_defaults()
        for gcs_node in doc.getElementsByTagName("gui_tour_stats"):
            self.gui_tour_stats.add_elements(node=gcs_node)  # add/overwrite elements in self.gui_cash_stats

        # One-time migration of stale user configs: bwin.fr and partypoker.fr
        # moved from the PartyPoker network to iPoker (Entain France, 2026).
        # Configs written before that migration still carry network="PartyPoker"
        # and converter="PartyPokerToFpdb" for those skins, so their iPoker XML
        # hand histories are never parsed and no HUD ever appears. Runs before
        # the <site>/<hhc> nodes are turned into objects so the migrated values
        # take effect in this very session.
        migrated = self._migrate_entain_fr_sites_to_ipoker(doc)
        # HUD package migration belongs to the user's normal HUD_config.xml.
        # Explicit files are also used for exports, tests and purpose-built
        # minimal configurations; silently enriching those changes their
        # contract and causes an unsolicited save/backup during construction.
        if uses_default_config and self._migrate_aof_omaha_hud(doc):
            migrated = True
        if migrated:
            self.save()  # keeps a .backup of the pre-migration config

        #        s_sites = doc.getElementsByTagName("supported_sites")
        for site_node in doc.getElementsByTagName("site"):
            site = Site(node=site_node)
            self.supported_sites[site.site_name] = site

        # Multiroom hero profiles (optional <hero_profiles> section).
        for hp_node in doc.getElementsByTagName("hero_profile"):
            hp = HeroProfile(node=hp_node)
            if hp.name:
                self.hero_profiles[hp.name] = hp

        # Load site_ids from XML config
        for site_id_node in doc.getElementsByTagName("site_id"):
            site_name = site_id_node.getAttribute("site")
            site_id = site_id_node.getAttribute("id")
            if site_name and site_id:
                self.site_ids[site_name] = int(site_id)

        #        s_games = doc.getElementsByTagName("supported_games")
        for supported_game_node in doc.getElementsByTagName("game"):
            supported_game = Supported_games(supported_game_node)
            self.supported_games[supported_game.game_name] = supported_game

        # parse databases defined by user in the <supported_databases> section
        # the user may select the actual database to use via commandline or by setting the selected="bool"
        # attribute of the tag. if no database is explicitely selected, we use the first one we come across
        #        s_dbs = doc.getElementsByTagName("supported_databases")
        # A <supported_databases> section holds them, and older files put them
        # beside it at the top level instead. The section wins as soon as it
        # holds anything.
        for supported_dbs_node in doc.getElementsByTagName("supported_databases"):
            self._load_databases(supported_dbs_node.getElementsByTagName("database"))
        if not self.supported_databases:
            self._load_databases(
                node for node in doc.documentElement.childNodes if getattr(node, "tagName", None) == "database"
            )
        # ``None`` means that the CLI did not request an override.  An empty
        # string remains a valid explicit key because the XML format has always
        # allowed it as a database name.
        if dbname is not None and dbname in self.supported_databases:
            self.db_selected = dbname
        # NOTE: fpdb can not handle the case when no database is defined in xml, so we throw an exception for now
        if self.db_selected is None:
            msg = "There must be at least one database defined"
            raise ValueError(msg)

        #     s_dbs = doc.getElementsByTagName("mucked_windows")
        for aw_node in doc.getElementsByTagName("aw"):
            aw = Aux_window(node=aw_node)
            self.aux_windows[aw.name] = aw

        for ls_node in doc.getElementsByTagName("ls"):
            ls = Layout_set(node=ls_node)
            self.layout_sets[ls.name] = ls

        for ss_node in doc.getElementsByTagName("ss"):
            ss = Stat_sets(node=ss_node)
            self.stat_sets[ss.name] = ss

        self.hud_profile_rules = parse_hud_profile_rules(doc)

        #     s_dbs = doc.getElementsByTagName("mucked_windows")
        for hhc_node in doc.getElementsByTagName("hhc"):
            hhc = HHC(node=hhc_node)
            self.hhcs[hhc.site] = hhc

        #        s_dbs = doc.getElementsByTagName("popup_windows")
        for pu_node in doc.getElementsByTagName("pu"):
            pu = Popup(node=pu_node)
            self.popup_windows[pu.name] = pu

        for imp_node in doc.getElementsByTagName("import"):
            imp = Import(node=imp_node)
            self.imp = imp

        for hui_node in doc.getElementsByTagName("hud_ui"):
            hui = HudUI(node=hui_node)
            self.ui = hui

        db = self.get_db_parameters()
        # Set the db path if it's defined in HUD_config.xml (sqlite only), otherwise place in config path.
        self.dir_database = db["db-path"] if db["db-path"] else os.path.join(CONFIG_PATH, "database")
        if db["db-password"] == "YOUR MYSQL PASSWORD":
            df_file = self.find_default_conf()
            if df_file is None:  # this is bad
                pass
            else:
                df_parms = self.read_default_conf(df_file)
                self.set_db_parameters(
                    db_name="fpdb",
                    db_ip=df_parms["db-host"],
                    db_user=df_parms["db-user"],
                    db_pass=df_parms["db-password"],
                )
                self.save(file=os.path.join(CONFIG_PATH, "HUD_config.xml"))

        if doc.getElementsByTagName("raw_hands") == []:
            self.raw_hands = RawHands()
        for raw_hands_node in doc.getElementsByTagName("raw_hands"):
            self.raw_hands = RawHands(raw_hands_node)

        if doc.getElementsByTagName("raw_tourneys") == []:
            self.raw_tourneys = RawTourneys()
        for raw_tourneys_node in doc.getElementsByTagName("raw_tourneys"):
            self.raw_tourneys = RawTourneys(raw_tourneys_node)

        # print ""

    # end def __init__

    def _load_databases(self, db_nodes) -> None:
        """Turn <database> nodes into the databases fpdb can connect to.

        The first one read is the selection until a node claims it, so a file
        naming none still ends up with one. That is worked out here and not
        written back: the attribute is for the user's choice, and the writers
        put it there when the choice is made.
        """
        for db_node in db_nodes:
            db = Database(node=db_node)
            if db.db_name in self.supported_databases:
                msg = "Database names must be unique"
                raise ValueError(msg)
            if self.db_selected is None or db.db_selected:
                self.db_selected = db.db_name
            self.supported_databases[db.db_name] = db

    def _migrate_entain_fr_sites_to_ipoker(self, doc) -> bool:
        """Rewrite pre-2026 Entain France skins from PartyPoker to iPoker.

        Returns True when the DOM was modified and the config needs saving.
        Idempotent: entries already on the iPoker network are left untouched.
        """
        changed = False
        has_ipoker_layout = any(
            ls_node.getAttribute("name") == "ipoker_default" for ls_node in doc.getElementsByTagName("ls")
        )
        for site_node in doc.getElementsByTagName("site"):
            name = site_node.getAttribute("site_name")
            if name not in ENTAIN_FR_IPOKER_SITES:
                continue
            if site_node.getAttribute("network") == "PartyPoker":
                site_node.setAttribute("network", "iPoker")
                changed = True
                detected = self._detect_entain_fr_data_dir(name)
                if detected:
                    hh_path, ts_path, hero = detected
                    site_node.setAttribute("HH_path", hh_path)
                    site_node.setAttribute("TS_path", ts_path)
                    if hero and site_node.getAttribute("screen_name") != hero:
                        site_node.setAttribute("screen_name", hero)
                    log.warning(
                        "Migrated site %r from the PartyPoker network to iPoker (hand histories: %s)",
                        name,
                        hh_path,
                    )
                else:
                    log.warning(
                        "Migrated site %r from the PartyPoker network to iPoker "
                        "(client data directory not found; HH_path left unchanged)",
                        name,
                    )
            # Independent of the network attribute (repairs half-migrated
            # configs too): a migrated skin must not keep the PartyPoker HUD
            # layout, or the stat windows are placed for the wrong table
            # geometry. Only rewrite when the target layout set exists.
            if site_node.getAttribute("network") == "iPoker" and has_ipoker_layout:
                for ls_node in site_node.getElementsByTagName("layout_set"):
                    if ls_node.getAttribute("ls") == "party_default":
                        ls_node.setAttribute("ls", "ipoker_default")
                        changed = True
                        log.warning("Switched site %r HUD layout from party_default to ipoker_default", name)
        for hhc_node in doc.getElementsByTagName("hhc"):
            if hhc_node.getAttribute("site") not in ENTAIN_FR_IPOKER_SITES:
                continue
            if hhc_node.getAttribute("converter") != "PartyPokerToFpdb":
                continue
            hhc_node.setAttribute("converter", "iPokerToFpdb")
            hhc_node.setAttribute("summaryImporter", "iPokerSummary")
            changed = True
        return changed

    def _migrate_aof_omaha_hud(self, doc, source_doc=None) -> bool:
        """Install the AoF Omaha profile and game binding when they are absent.

        Existing profiles and mappings are user configuration, so this
        migration only fills gaps. It is deliberately separate from
        ``add_missing_elements()``, which adds missing top-level sections but
        does not merge new children into sections that already exist.
        """
        from fpdb_3_legacy.hud_package import (
            install_missing_hud_package,
            merge_missing_profile_stats,
            upgrade_legacy_popup_presentation,
        )

        if source_doc is None:
            source_path = _find_example_config("HUD_config.xml")
            try:
                source_doc = defusedxml.minidom.parse(source_path)
            except XML_PARSE_ERRORS as exc:
                log.exception("Could not read the shipped AoF Omaha HUD profile from %s: %s", source_path, exc)
                return False

        source_profiles = [
            node
            for node in source_doc.getElementsByTagName("ss")
            if node.getAttribute("name") in {"aof_default", "aof_advanced"}
        ]
        source_popup = next(
            (node for node in source_doc.getElementsByTagName("pu") if node.getAttribute("pu_name") == "aof_profile"),
            None,
        )
        source_games = [
            node
            for node in source_doc.getElementsByTagName("game")
            if node.getAttribute("game_name") in AOF_CATEGORIES
        ]
        if not source_profiles or not source_games:
            return False

        package_doc = defusedxml.minidom.parseString("<fpdb_hud_package/>")
        package_root = package_doc.documentElement
        for source_profile in source_profiles:
            package_root.appendChild(package_doc.importNode(source_profile, True))
        if source_popup is not None:
            package_root.appendChild(package_doc.importNode(source_popup, True))
        for source_game in source_games:
            package_root.appendChild(package_doc.importNode(source_game, True))
        changed = install_missing_hud_package(doc, package_root)
        changed = (
            upgrade_legacy_popup_presentation(
                doc,
                package_root,
                popup_name="aof_profile",
            )
            or changed
        )
        splash_stats = {"aof_splash_won", "aof_splash_freq"}
        changed = (
            merge_missing_profile_stats(
                doc,
                package_root,
                profile_name="aof_default",
                stat_names=splash_stats,
                recognized_dimensions={(3, 4), (4, 4)},
            )
            or changed
        )
        changed = (
            merge_missing_profile_stats(
                doc,
                package_root,
                profile_name="aof_advanced",
                stat_names=splash_stats,
                recognized_dimensions={(5, 4), (6, 4)},
            )
            or changed
        )

        # Lot 4 temporarily replaced the Decision EV placeholder with
        # conditional EV against actual callers. Lot 6 now owns the original
        # cell again. Match both its name and packaged location so a user's
        # unrelated/custom statistic is never replaced.
        advanced = next(
            (node for node in doc.getElementsByTagName("ss") if node.getAttribute("name") == "aof_advanced"),
            None,
        )
        if advanced is not None:
            for stat in advanced.getElementsByTagName("stat"):
                if stat.getAttribute("_stat_name") == "aof_known_ev" and stat.getAttribute("_rowcol") == "(4,3)":
                    stat.setAttribute("_stat_name", "aof_decision_ev")
                    changed = True

        # The named popup belongs to this feature and can be extended
        # idempotently while its class/theme and existing rows remain intact.
        popup = next(
            (node for node in doc.getElementsByTagName("pu") if node.getAttribute("pu_name") == "aof_profile"),
            None,
        )
        if popup is not None and source_popup is not None:
            existing = {node.getAttribute("pu_stat_name") for node in popup.getElementsByTagName("pu_stat")}
            for name in (
                "aof_known_equity",
                "aof_known_ev",
                "aof_range_equity",
                "aof_weak",
                "aof_decision_ev",
                "aof_splash_won",
                "aof_splash_freq",
            ):
                if name in existing:
                    continue
                source_stat = next(
                    (
                        node
                        for node in source_popup.getElementsByTagName("pu_stat")
                        if node.getAttribute("pu_stat_name") == name
                    ),
                    None,
                )
                if source_stat is not None:
                    popup.appendChild(doc.importNode(source_stat, True))
                    changed = True
        return changed

    @staticmethod
    def _detect_entain_fr_data_dir(site_name: str) -> tuple[str, str, str] | None:
        """Locate <client>/data/<account>/History/Data on Windows.

        Returns (HH_path, TS_path, account name) for the first account
        directory that has a History/Data tree, or None when the client is
        not installed (or on other platforms).
        """
        local_appdata = os.getenv("LOCALAPPDATA", "")
        if not local_appdata:
            return None
        for folder in ENTAIN_FR_WINDOWS_DATA_DIRS.get(site_name, ()):
            data_dir = Path(local_appdata) / folder / "data"
            if not data_dir.is_dir():
                continue
            try:
                accounts = sorted(p for p in data_dir.iterdir() if (p / "History" / "Data").is_dir())
            except OSError:
                continue
            for account in accounts:
                history = account / "History" / "Data"
                return (str(history / "Tables"), str(history / "Tournaments"), account.name)
        return None

    @staticmethod
    def _preceding_comment(node):
        """The comment written immediately above ``node``, if there is one."""
        sibling = node.previousSibling
        while sibling is not None and sibling.nodeType == sibling.TEXT_NODE and not sibling.data.strip():
            sibling = sibling.previousSibling
        if sibling is not None and sibling.nodeType == sibling.COMMENT_NODE:
            return sibling
        return None

    def add_missing_elements(self, doc, example_file):
        """Look through example config file and add any elements that are not in the config
        May need to add some 'enabled' attributes to turn things off - can't just delete a
        config section now because this will add it back in.
        """
        nodes_added = 0

        try:
            example_doc = defusedxml.minidom.parse(example_file)
        except XML_PARSE_ERRORS as e:
            log.exception(
                f"Error parsing example configuration file {example_file}. See error log file. Exception: {e}",
            )
            return nodes_added

        for cnode in doc.getElementsByTagName("FreePokerToolsConfig"):
            for example_cnode in example_doc.childNodes:
                if example_cnode.localName == "FreePokerToolsConfig":
                    for example_node in example_cnode.childNodes:
                        # print "nodetype", example_node.nodeType, "name", example_node.localName, "found", len(doc.getElementsByTagName(example_node.localName))
                        if (
                            example_node.nodeType == example_node.ELEMENT_NODE
                            and doc.getElementsByTagName(example_node.localName) == []
                        ):
                            new = doc.importNode(example_node, True)  # True means do deep copy
                            t_node = self.doc.createTextNode("    ")
                            cnode.appendChild(t_node)
                            # A section the user has never seen arrives empty and
                            # unexplained unless the comment documenting it comes
                            # with it. Sections whose whole content is a shipped
                            # default need no comment and have none.
                            comment = self._preceding_comment(example_node)
                            if comment is not None:
                                cnode.appendChild(doc.importNode(comment, True))
                                cnode.appendChild(self.doc.createTextNode("\n    "))
                            cnode.appendChild(new)
                            t_node = self.doc.createTextNode("\r\n\r\n")
                            cnode.appendChild(t_node)
                            log.debug(f"... adding missing config section: {example_node.localName}")
                            nodes_added = nodes_added + 1

        if nodes_added > 0:
            log.debug(f"Added {nodes_added} missing config sections")
            self.save()

        return nodes_added

    def find_default_conf(self):
        config_file = os.path.join(CONFIG_PATH, "default.conf") if CONFIG_PATH else False

        return config_file if config_file and os.path.exists(config_file) else None

    def read_default_conf(self, file_name: str) -> dict[str, str]:
        """Read the legacy ``key=value`` database defaults file."""
        values: dict[str, str] = {}
        with open(file_name, encoding="utf-8") as config_file:
            for raw_line in config_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values

    def get_doc(self):
        return self.doc

    def get_site_node(self, site):
        for site_node in self.doc.getElementsByTagName("site"):
            if site_node.getAttribute("site_name") == site:
                return site_node
        return None

    def getEmailNode(self, siteName, fetchType):
        siteNode = self.get_site_node(siteName)
        for emailNode in siteNode.getElementsByTagName("email"):
            if emailNode.getAttribute("fetchType") == fetchType:
                return emailNode
                break
        return None

    # end def getEmailNode

    def getStatSetNode(self, statsetName):
        """Returns DOM game node for a given game."""
        for statsetNode in self.doc.getElementsByTagName("ss"):
            # print "getStatSetNode statsetNode:",statsetNode
            if statsetNode.getAttribute("name") == statsetName:
                return statsetNode
        return None

    def getGameNode(self, gameName):
        """Returns DOM game node for a given game."""
        for gameNode in self.doc.getElementsByTagName("game"):
            # print "getGameNode gameNode:",gameNode
            if gameNode.getAttribute("game_name") == gameName:
                return gameNode
        return None

    # end def getGameNode

    def get_aux_node(self, aux):
        for aux_node in self.doc.getElementsByTagName("aw"):
            if aux_node.getAttribute("name") == aux:
                return aux_node
        return None

    def get_layout_set_node(self, ls):
        for layout_set_node in self.doc.getElementsByTagName("ls"):
            if layout_set_node.getAttribute("name") == ls:
                return layout_set_node
        return None

    def get_layout_node(self, ls, max):
        for layout_node in ls.getElementsByTagName("layout"):
            if layout_node.getAttribute("max") == str(max):
                return layout_node
        return None

    def get_stat_set_node(self, ss):
        for stat_set_node in self.doc.getElementsByTagName("ss"):
            if stat_set_node.getAttribute("name") == ss:
                return stat_set_node
        return None

    def get_db_node(self, db_name):
        for db_node in self.doc.getElementsByTagName("database"):
            if db_node.getAttribute("db_name") == db_name:
                return db_node
        return None

    #    def get_layout_node(self, site_node, layout):
    #        for layout_node in site_node.getElementsByTagName("layout"):
    #            if layout_node.getAttribute("max") is None:
    #                return None
    #            if int( layout_node.getAttribute("max") ) == int( layout ):
    #                return layout_node

    def get_location_node(self, layout_node, seat):
        if seat == "common":
            for location_node in layout_node.getElementsByTagName("location"):
                if location_node.hasAttribute("common"):
                    return location_node
            return None
        for location_node in layout_node.getElementsByTagName("location"):
            if int(location_node.getAttribute("seat")) == int(seat):
                return location_node
        return None

    def reload(self) -> bool | None:
        """Reload configuration from file without creating a new object.

        Everything is parsed into structures of its own first and only put on
        the object once every section has been read. A section that will not
        parse therefore leaves the configuration already in use untouched,
        rather than emptying it and stopping partway through refilling it --
        none of the callers check the return value, so what they carry on with
        has to be whole either way.
        """
        log.info(f"Reloading configuration from {self.file}")

        try:
            # Parse the XML file again
            doc = defusedxml.minidom.parse(self.file)

            supported_sites = {}
            supported_games = {}
            supported_databases = {}
            aux_windows = {}
            layout_sets = {}
            stat_sets = {}
            hhcs = {}
            popup_windows = {}

            # Re-parse all sections
            # General section. It carries over what the previous load held,
            # which is what reloading onto the live object used to do.
            general = General()
            general.update(self.general)
            if doc.getElementsByTagName("general") == []:
                general.get_defaults()
            for gen_node in doc.getElementsByTagName("general"):
                general.add_elements(node=gen_node)

            # Sites
            for site_node in doc.getElementsByTagName("site"):
                site = Site(node=site_node)
                supported_sites[site.site_name] = site

            # Games
            for supported_game_node in doc.getElementsByTagName("game"):
                supported_game = Supported_games(supported_game_node)
                supported_games[supported_game.game_name] = supported_game

            # Databases
            db_selected = self.db_selected
            for db_node in doc.getElementsByTagName("database"):
                db = Database(node=db_node)
                if db_selected is None or db.db_selected:
                    db_selected = db.db_name
                supported_databases[db.db_name] = db

            # Aux windows
            for aw_node in doc.getElementsByTagName("aw"):
                aw = Aux_window(node=aw_node)
                aux_windows[aw.name] = aw

            # Layout sets
            for ls_node in doc.getElementsByTagName("ls"):
                ls = Layout_set(node=ls_node)
                layout_sets[ls.name] = ls

            # Stat sets
            for ss_node in doc.getElementsByTagName("ss"):
                ss = Stat_sets(node=ss_node)
                stat_sets[ss.name] = ss

            # Profile selection rules
            hud_profile_rules = parse_hud_profile_rules(doc)

            # HHCs
            for hhc_node in doc.getElementsByTagName("hhc"):
                hhc = HHC(node=hhc_node)
                hhcs[hhc.site] = hhc

            # Popup windows
            for pu_node in doc.getElementsByTagName("pu"):
                pu = Popup(node=pu_node)
                popup_windows[pu.name] = pu

            # Import settings. These two are the only sections Config does not
            # always carry -- it grows the attribute when the file has the
            # section -- so a file without one leaves whatever is in use alone
            # rather than replacing it with an empty stand-in.
            imp: Import | None = None
            for imp_node in doc.getElementsByTagName("import"):
                imp = Import(node=imp_node)

            # HUD UI settings - this is the important part for HUD preferences
            ui: HudUI | None = None
            for hui_node in doc.getElementsByTagName("hud_ui"):
                ui = HudUI(node=hui_node)

        except Exception as e:  # intentional broad catch: full XML config reload boundary, return False on any failure
            log.exception(f"Error reloading configuration: {e}")
            return False

        # Every section parsed: swap the lot in.
        self.doc = doc
        self.general = general
        self.supported_sites = supported_sites
        self.supported_games = supported_games
        self.supported_databases = supported_databases
        self.db_selected = db_selected
        self.aux_windows = aux_windows
        self.layout_sets = layout_sets
        self.stat_sets = stat_sets
        self.hud_profile_rules = hud_profile_rules
        self.hhcs = hhcs
        self.popup_windows = popup_windows
        if imp is not None:
            self.imp = imp
        if ui is not None:
            self.ui = ui

        log.info("Configuration reloaded successfully")
        return True

    def save(self, file=None) -> None:
        if file is None:
            file = self.file
            try:
                shutil.move(file, f"{file}.backup")
            except OSError as e:
                log.exception(f"Failed to move file {file} to backup. Exception: {e}")

        with codecs.open(file, "w", "utf-8") as f:
            # self.doc.writexml(f)
            f.write(self.wrap_long_lines(self.doc.toxml()))

    def wrap_long_lines(self, s):
        lines = [self.wrap_long_line(line) for line in s.splitlines()]
        return "\n".join(lines) + "\n"

    def wrap_long_line(self, line):
        if "config_wrap_len" in self.general:
            wrap_len = int(self.general["config_wrap_len"])
        else:
            wrap_len = -1  # < 0 means no wrap

        if wrap_len >= 0 and len(line) > wrap_len:
            m = re.compile(r"\s+\S+\s+")
            mo = m.match(line)
            if mo:
                indent_len = mo.end()
                # print "indent = %s (%s)" % (indent_len, l[0:indent_len])
                indent = "\n" + " " * indent_len
                m = re.compile(r'(\S+="[^"]+"\s+)')
                parts = [x for x in m.split(line[indent_len:]) if x]
                if len(parts) > 1:
                    # print "parts =", parts
                    line = line[0:indent_len] + indent.join(parts)
            return line
        return line

    def editEmail(self, siteName, fetchType, newEmail) -> None:
        emailNode = self.getEmailNode(siteName, fetchType)
        emailNode.setAttribute("host", newEmail.host)
        emailNode.setAttribute("username", newEmail.username)
        emailNode.setAttribute("password", newEmail.password)
        emailNode.setAttribute("folder", newEmail.folder)
        emailNode.setAttribute("useSsl", newEmail.useSsl)

    # end def editEmail

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
        site_node.setAttribute("enabled", enabled)

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
        existing = {fav.getAttribute("max"): fav for fav in site_node.getElementsByTagName("fav")}
        for max_seats, value in values.items():
            fav_seat = existing.get(max_seats)
            if fav_seat is None:
                # A site's config may ship without a <fav> node for every table
                # size (e.g. CoinPoker only had 2/6/9/10). Without this, editing a
                # preferred seat for a missing size (a 5-max table) was silently
                # dropped -- create the node so the choice is actually persisted.
                fav_seat = self.doc.createElement("fav")
                fav_seat.setAttribute("max", max_seats)
                site_node.appendChild(fav_seat)
            fav_seat.setAttribute("fav_seat", value)

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
        for statsetNode in self.doc.getElementsByTagName("ss"):
            if statsetNode.getAttribute("name") == hud_name:
                for fav_stat in statsetNode.getElementsByTagName("stat"):
                    if fav_stat.getAttribute("_rowcol") == self.increment_position(position):
                        fav_stat.setAttribute("_stat_name", stat_name)
                        fav_stat.setAttribute("click", click)
                        fav_stat.setAttribute("hudcolor", hudcolor)
                        fav_stat.setAttribute("hudprefix", hudprefix)
                        fav_stat.setAttribute("hudsuffix", hudsuffix)
                        fav_stat.setAttribute("popup", popup)
                        fav_stat.setAttribute("stat_hicolor", stat_hicolor)
                        fav_stat.setAttribute("stat_hith", stat_hith)
                        fav_stat.setAttribute("stat_locolor", stat_locolor)
                        fav_stat.setAttribute("stat_loth", stat_loth)
                        fav_stat.setAttribute("tip", tip)
                        # fav_stat.setAttribute("stat_midcolor", stat_midcolor)  # not returned by UI

    # end def

    def edit_site(self, site_name, enabled, screen_name, history_path, summary_path) -> None:
        site_node = self.get_site_node(site_name)
        site_node.setAttribute("enabled", enabled)
        site_node.setAttribute("screen_name", screen_name)
        site_node.setAttribute("HH_path", history_path)
        if summary_path:
            site_node.setAttribute("TS_path", summary_path)

    def get_hero_aliases(self, site_name):
        """Return all hero screen names recognised for a site.

        The primary ``screen_name`` is always first, followed by any extra
        ``<hero_alias>`` entries (deduplicated). Returns ``[]`` for an unknown
        site. Backward compatible: a site without aliases yields
        ``[screen_name]``.
        """
        site = self.supported_sites.get(site_name)
        if site is None and site_name:
            for k, v in self.supported_sites.items():
                if k.lower() == site_name.lower():
                    site = v
                    break
        if site is None:
            return []
        return list(getattr(site, "hero_aliases", []) or ([site.screen_name] if site.screen_name else []))

    def set_hero_aliases(self, site_name, aliases) -> None:
        """Persist the hero aliases for a site into the config DOM.

        The first alias becomes the primary ``screen_name``; the remaining ones
        are written as ``<hero_alias name=.../>`` children (replacing existing
        ones). Keeps the in-memory ``Site`` object in sync.
        """
        # Deduplicate while preserving order.
        ordered = []
        seen = set()
        for alias in aliases:
            if alias and alias not in seen:
                seen.add(alias)
                ordered.append(alias)

        site_node = self.get_site_node(site_name)
        primary = ordered[0] if ordered else ""
        site_node.setAttribute("screen_name", primary)

        # Remove existing <hero_alias> children before re-adding.
        for old in list(site_node.getElementsByTagName("hero_alias")):
            site_node.removeChild(old)

        for alias in ordered[1:]:
            alias_node = self.doc.createElement("hero_alias")
            alias_node.setAttribute("name", alias)
            site_node.appendChild(alias_node)

        if site_name in self.supported_sites:
            self.supported_sites[site_name].screen_name = primary
            self.supported_sites[site_name].hero_aliases = ordered

    def is_hero_name(self, site_name, name) -> bool:
        """True if ``name`` is one of the hero aliases configured for a site."""
        if not name:
            return False
        aliases = [a.lower() for a in self.get_hero_aliases(site_name)]
        return name.lower() in aliases

    def get_hero_profiles(self):
        """Return ``{name: HeroProfile}`` for all configured multiroom profiles."""
        return self.hero_profiles

    def get_default_hero_profile(self):
        """Return the default hero profile, or the first one, or ``None``."""
        for hp in self.hero_profiles.values():
            if hp.default:
                return hp
        return next(iter(self.hero_profiles.values()), None)

    def _get_hero_profiles_node(self, create=False):
        """Return the ``<hero_profiles>`` DOM node, optionally creating it."""
        nodes = self.doc.getElementsByTagName("hero_profiles")
        if nodes:
            return nodes[0]
        if not create:
            return None
        root = self.doc.getElementsByTagName("FreePokerToolsConfig")[0]
        node = self.doc.createElement("hero_profiles")
        root.appendChild(node)
        return node

    def save_hero_profile(self, name, links, default=False) -> None:
        """Create or replace a multiroom hero profile in the config DOM.

        ``links`` is an iterable of ``(site_name, alias)`` pairs. Keeps the
        in-memory ``hero_profiles`` dict in sync.
        """
        # Deduplicate links, preserving order.
        ordered_links = []
        seen = set()
        for site, alias in links:
            if site and alias and (site, alias) not in seen:
                seen.add((site, alias))
                ordered_links.append((site, alias))

        profiles_node = self._get_hero_profiles_node(create=True)

        # Remove an existing profile with the same name before re-adding.
        for old in list(profiles_node.getElementsByTagName("hero_profile")):
            if old.getAttribute("name") == name:
                profiles_node.removeChild(old)

        hp_node = self.doc.createElement("hero_profile")
        hp_node.setAttribute("name", name)
        hp_node.setAttribute("default", str(bool(default)))
        for site, alias in ordered_links:
            link_node = self.doc.createElement("link")
            link_node.setAttribute("site_name", site)
            link_node.setAttribute("alias", alias)
            hp_node.appendChild(link_node)
        profiles_node.appendChild(hp_node)

        self.hero_profiles[name] = HeroProfile(node=hp_node)

    def delete_hero_profile(self, name) -> None:
        """Remove a multiroom hero profile from the config DOM and memory."""
        profiles_node = self._get_hero_profiles_node(create=False)
        if profiles_node is not None:
            for old in list(profiles_node.getElementsByTagName("hero_profile")):
                if old.getAttribute("name") == name:
                    profiles_node.removeChild(old)
        self.hero_profiles.pop(name, None)

    def editStats(self, statsetName, statArray) -> None:
        """Replaces stat selection for the given gameName with the given statArray."""
        statsetNode = self.getStatSetNode(statsetName)
        if statsetNode is None:
            # Saying so beats the AttributeError on None this used to raise:
            # replacing a whole grid must not look like a bug in the caller.
            msg = f"No stat set named {statsetName!r}"
            raise ValueError(msg)
        statNodes = statsetNode.getElementsByTagName("stat")

        # Store existing stat attributes before removing
        existing_stats = {}
        for node in statNodes:
            rowcol = node.getAttribute("_rowcol")
            existing_stats[rowcol] = {
                "click": node.getAttribute("click"),
                "popup": node.getAttribute("popup"),
                "tip": node.getAttribute("tip"),
                "hudprefix": node.getAttribute("hudprefix"),
                "hudsuffix": node.getAttribute("hudsuffix"),
                "hudcolor": node.getAttribute("hudcolor"),
                "stat_locolor": node.getAttribute("stat_locolor"),
                "stat_loth": node.getAttribute("stat_loth"),
                "stat_midcolor": node.getAttribute("stat_midcolor"),
                "stat_hicolor": node.getAttribute("stat_hicolor"),
                "stat_hith": node.getAttribute("stat_hith"),
            }

        # Remove all child nodes (stats and text nodes)
        while statsetNode.firstChild:
            statsetNode.removeChild(statsetNode.firstChild)

        statsetNode.setAttribute("rows", str(len(statArray)))
        # A grid with no rows at all has no width either. Reading it off the
        # first row raised IndexError, even though the last step of this same
        # function guards for an empty grid -- so emptying a stat set worked
        # with [[]] and not with [].
        statsetNode.setAttribute("cols", str(len(statArray[0]) if statArray else 0))

        for _idx, (rowNumber, columnNumber) in enumerate(
            [(r, c) for r in range(len(statArray)) for c in range(len(statArray[r]))],
        ):
            # Add newline and indentation before each stat
            indent = self.doc.createTextNode("\n            ")
            statsetNode.appendChild(indent)

            newStat = self.doc.createElement("stat")
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

            for attr_name, attr_value in attributes.items():
                newAttr = self.doc.createAttribute(attr_name)
                newStat.setAttributeNode(newAttr)
                newStat.setAttribute(attr_name, attr_value)

            statsetNode.appendChild(newStat)

        # Add final newline and indentation
        if len(statArray) > 0:
            final_indent = self.doc.createTextNode("\n        ")
            statsetNode.appendChild(final_indent)

    # end def editStats
    def editImportFilters(self, games) -> None:
        self.imp.importFilters = games
        imp_node = self.doc.getElementsByTagName("import")[-1]
        imp_node.setAttribute("importFilters", games)

    def save_layout_set(self, ls, max, locations, width=None, height=None) -> None:
        # wid/height normally not specified when saving common from the mucked display

        log.debug(f"saving layout = {ls.name} {max}Max {locations} size: {width}x{height}")
        ls_node = self.get_layout_set_node(ls.name)
        layout_node = self.get_layout_node(ls_node, max)
        if width:
            layout_node.setAttribute("width", str(width))
        if height:
            layout_node.setAttribute("height", str(height))

        for i, _pos in list(locations.items()):
            location_node = self.get_location_node(layout_node, i)
            location_node.setAttribute("x", str(locations[i][0]))
            location_node.setAttribute("y", str(locations[i][1]))
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

    # NOTE: we got a nice Database class, so why map it again here?
    #            user input validation should be done when initializing the Database class. this allows to give appropriate feddback when something goes wrong
    #            try ..except is evil here. it swallows all kinds of errors. dont do this
    #            naming database types 2, 3, 4 on the fly is no good idea. i see this all over the code. better use some globally defined consts (see DATABASE_TYPE_*)
    #            i would like to drop this method entirely and replace it by get_selected_database() or better get_active_database(), returning one of our Database instances
    #            thus we can drop self.db_selected (holding database name) entirely and replace it with self._active_database = Database, avoiding to define the same
    #            thing multiple times
    def get_db_parameters(self):
        db: dict[str, Any] = {}
        name = self.db_selected

        if name not in self.supported_databases:
            log.error(f"Database {name} not found in supported databases.")
            return db

        # Parameters are retrieved with default values
        db["db-databaseName"] = name

        # use getattr
        db["db-desc"] = getattr(self.supported_databases[name], "db_desc", None)
        db["db-host"] = getattr(self.supported_databases[name], "db_ip", None)
        db["db-port"] = getattr(self.supported_databases[name], "db_port", None)
        db["db-user"] = getattr(self.supported_databases[name], "db_user", None)
        db["db-password"] = getattr(self.supported_databases[name], "db_pass", None)
        db["db-server"] = getattr(self.supported_databases[name], "db_server", None)
        db["db-path"] = getattr(self.supported_databases[name], "db_path", None)

        # add backend
        try:
            db["db-backend"] = self.get_backend(self.supported_databases[name].db_server)
        except (AttributeError, KeyError) as e:
            log.exception(f"Error retrieving backend for {name}: {e!s}")
            db["db-backend"] = None

        return db

    @staticmethod
    def _write_db_attributes(db_node, **values: str | None) -> None:
        """Put on the node every attribute that was actually given.

        None means "leave whatever is there alone", which is not the same as
        the empty string: an empty db_pass is a password that was cleared.
        """
        for name, value in values.items():
            if value is not None:
                db_node.setAttribute(name, value)

    def _write_db_cache(self, db_name: str, *, selected: bool, **values: str | None) -> None:
        """Mirror onto the loaded Database what was just written to the file."""
        database = self.supported_databases[db_name]
        for name, value in values.items():
            if value is not None:
                setattr(database, name, value)
        database.db_selected = selected

    def _mark_db_default(self, db_node, db_name: str, *, wanted: bool) -> None:
        """Carry the default flag on the node, and off every other database.

        The attribute names the one database fpdb opens, so at most one node
        may hold it. A file naming two leaves the choice to whichever comes
        last in the document, which is not a choice anyone made.
        """
        if wanted:
            db_node.setAttribute("default", "True")
            for dbn in self.doc.getElementsByTagName("database"):
                if dbn.getAttribute("db_name") != db_name and dbn.hasAttribute("default"):
                    dbn.removeAttribute("default")
        elif db_node.hasAttribute("default"):
            db_node.removeAttribute("default")

    def set_db_parameters(
        self,
        db_name="fpdb",
        db_ip=None,
        db_port=None,
        db_user=None,
        db_pass=None,
        db_desc=None,
        db_server=None,
        default="False",
    ) -> None:
        db_node = self.get_db_node(db_name)
        defaultb = string_to_bool(default.lower(), False)
        if db_node is not None:
            self._write_db_attributes(
                db_node,
                db_desc=db_desc,
                db_ip=db_ip,
                db_port=db_port,
                db_user=db_user,
                db_pass=db_pass,
                db_server=db_server,
            )
            self._mark_db_default(db_node, db_name, wanted=defaultb or self.db_selected == db_name)
        if db_name in self.supported_databases:
            self._write_db_cache(
                db_name,
                selected=defaultb,
                db_desc=db_desc,
                db_ip=db_ip,
                db_port=db_port,
                db_user=db_user,
                db_pass=db_pass,
                db_server=db_server,
            )
        if defaultb:
            self.db_selected = db_name

    def add_db_parameters(
        self,
        db_name="fpdb",
        db_ip=None,
        db_port=None,
        db_user=None,
        db_pass=None,
        db_desc=None,
        db_server=None,
        default="False",
    ) -> None:
        defaultb = string_to_bool(default.lower(), False)
        if db_name in self.supported_databases:
            msg = "Database names must be unique"
            raise ValueError(msg)

        db_node = self.get_db_node(db_name)
        if db_node is None:
            db_node = self._append_db_node(db_name)
            wanted = defaultb
        else:
            # The node is in the file but never reached supported_databases,
            # which happens when a <supported_databases> section and a
            # top-level <database> both exist: only the section is loaded.
            # Such a node may already be the selection, which keeps the flag.
            wanted = defaultb or self.db_selected == db_name

        self._write_db_attributes(
            db_node,
            db_desc=db_desc,
            db_ip=db_ip,
            db_port=db_port,
            db_user=db_user,
            db_pass=db_pass,
            db_server=db_server,
        )
        self._mark_db_default(db_node, db_name, wanted=wanted)

        # The name is known not to be in supported_databases: the guard above
        # raises when it is, and nothing since has touched the dictionary.
        db = Database(node=db_node)
        self.supported_databases[db.db_name] = db

        if defaultb:
            self.db_selected = db_name

    def _append_db_node(self, db_name: str):
        """Add an empty <database> where this file already keeps its databases.

        Most files hold them in a <supported_databases> section, but the format
        also allows them at the top level, and reading a file falls back to
        those when the section yields nothing. Giving such a file a section to
        put the new database in would hide the ones it already has, since the
        section wins the moment it holds anything -- so the new node joins the
        others where they are.
        """
        parent = None
        for candidate in self.doc.getElementsByTagName("supported_databases"):
            # should only be one supported_databases element, use last one if there are several
            parent = candidate
        if parent is None:
            parent = self.doc.documentElement
        parent.appendChild(self.doc.createTextNode("    "))
        db_node = self.doc.createElement("database")
        parent.appendChild(db_node)
        parent.appendChild(self.doc.createTextNode("\r\n    "))
        db_node.setAttribute("db_name", db_name)
        return db_node

    def del_db_parameters(self, db_name="fpdb") -> None:
        """Remove a database from the config (both the XML node and the cache).

        If the removed database was the selected one, another configured
        database (if any) becomes the selection.
        """
        db_node = self.get_db_node(db_name)
        if db_node is not None and db_node.parentNode is not None:
            db_node.parentNode.removeChild(db_node)
        self.supported_databases.pop(db_name, None)
        if self.db_selected == db_name:
            self.db_selected = next(iter(self.supported_databases), None)

    def get_backend(self, name):
        """Returns the number of the currently used backend."""
        # Map received character strings to expected constants
        name_mapping = {
            "sqlite": "DATABASE_TYPE_SQLITE",
            "mysql": "DATABASE_TYPE_MYSQL",
            "postgresql": "DATABASE_TYPE_POSTGRESQL",
        }

        # Convert the name to uppercase using mapping
        if name in name_mapping:
            name = name_mapping[name]
        else:
            msg = f"Unsupported database backend: {name}"
            raise ValueError(msg)

        # Use of expected constants
        backends = {
            "DATABASE_TYPE_MYSQL": 2,
            "DATABASE_TYPE_POSTGRESQL": 3,
            "DATABASE_TYPE_SQLITE": 4,
        }

        return backends[name]

    def getDefaultSite(self):
        """Returns first enabled site or None."""
        for site_name, site in list(self.supported_sites.items()):
            if site.enabled:
                return site_name
        return None

    # Allow to change the menu appearance
    def get_hud_ui_parameters(self):
        hui = {}

        default_text = "FPDB Menu - Right click\nLeft-Drag to Move"

        try:
            hui["label"] = self.ui.label
            if self.ui.label == "":  # Empty menu label is a big no-no
                hui["label"] = default_text
        except AttributeError as e:
            log.exception(f"Error getting label: {e}")
            hui["label"] = default_text

        try:
            hui["card_ht"] = int(self.ui.card_ht)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting card height: {e}")
            hui["card_ht"] = 42

        try:
            hui["card_wd"] = int(self.ui.card_wd)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting card width: {e}")
            hui["card_wd"] = 30

        try:
            hui["deck_type"] = str(self.ui.deck_type)
        except AttributeError as e:
            log.exception(f"Error getting deck type: {e}")
            hui["deck_type"] = "colour"

        try:
            hui["card_back"] = str(self.ui.card_back)
        except AttributeError as e:
            log.exception(f"Error getting card back: {e}")
            hui["card_back"] = "back04"

        try:
            hui["stat_range"] = self.ui.stat_range
        except AttributeError as e:
            log.exception(f"Error getting stat range: {e}")
            hui["stat_range"] = "A"  # default is show stats for All-time, also S(session) and T(ime)

        try:
            hui["hud_days"] = int(self.ui.hud_days)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting HUD days: {e}")
            hui["hud_days"] = 90

        try:
            hui["agg_bb_mult"] = int(self.ui.agg_bb_mult)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting aggregate BB multiplier: {e}")
            hui["agg_bb_mult"] = 1

        try:
            hui["seats_style"] = self.ui.seats_style
        except AttributeError as e:
            log.exception(f"Error getting seats style: {e}")
            hui["seats_style"] = "A"  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:
            hui["seats_cust_nums_low"] = int(self.ui.seats_cust_nums_low)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting custom seat numbers low: {e}")
            hui["seats_cust_nums_low"] = 1

        try:
            hui["seats_cust_nums_high"] = int(self.ui.seats_cust_nums_high)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting custom seat numbers high: {e}")
            hui["seats_cust_nums_high"] = 10

        # Hero specific
        try:
            hui["h_stat_range"] = self.ui.h_stat_range
        except AttributeError as e:
            log.exception(f"Error getting hero stat range: {e}")
            hui["h_stat_range"] = "S"

        try:
            hui["h_hud_days"] = int(self.ui.h_hud_days)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero HUD days: {e}")
            hui["h_hud_days"] = 30

        try:
            hui["h_agg_bb_mult"] = int(self.ui.h_agg_bb_mult)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero aggregate BB multiplier: {e}")
            hui["h_agg_bb_mult"] = 1

        try:
            hui["h_seats_style"] = self.ui.h_seats_style
        except AttributeError as e:
            log.exception(f"Error getting hero seats style: {e}")
            hui["h_seats_style"] = "A"  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:
            hui["h_seats_cust_nums_low"] = int(self.ui.h_seats_cust_nums_low)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero custom seat numbers low: {e}")
            hui["h_seats_cust_nums_low"] = 1

        try:
            hui["h_seats_cust_nums_high"] = int(self.ui.h_seats_cust_nums_high)
        except (AttributeError, ValueError) as e:
            log.exception(f"Error getting hero custom seat numbers high: {e}")
            hui["h_seats_cust_nums_high"] = 10

        # Additional parameters that might be stored in hud_ui node
        try:
            hui["xshift"] = int(getattr(self.ui, "xshift", 0))
        except (AttributeError, ValueError):
            hui["xshift"] = 0

        try:
            hui["yshift"] = int(getattr(self.ui, "yshift", 0))
        except (AttributeError, ValueError):
            hui["yshift"] = 0

        try:
            hui["aggregate_ring"] = getattr(self.ui, "aggregate_ring", "True")
        except AttributeError:
            hui["aggregate_ring"] = "True"

        try:
            hui["aggregate_tour"] = getattr(self.ui, "aggregate_tour", "True")
        except AttributeError:
            hui["aggregate_tour"] = "True"

        try:
            hui["hud_style"] = getattr(self.ui, "hud_style", "A")
        except AttributeError:
            hui["hud_style"] = "A"

        try:
            hui["hero_stat_aggregation"] = getattr(self.ui, "hero_stat_aggregation", "False")
        except AttributeError:
            hui["hero_stat_aggregation"] = "False"

        try:
            hui["h_hud_style"] = getattr(self.ui, "h_hud_style", "A")
        except AttributeError:
            hui["h_hud_style"] = "A"

        # Appearance parameters
        try:
            hui["bgcolor"] = getattr(self.ui, "bgcolor", "#000000")
        except AttributeError:
            hui["bgcolor"] = "#000000"

        try:
            hui["fgcolor"] = getattr(self.ui, "fgcolor", "#FFFFFF")
        except AttributeError:
            hui["fgcolor"] = "#FFFFFF"

        try:
            hui["hudbgcolor"] = getattr(self.ui, "hudbgcolor", "#000000")
        except AttributeError:
            hui["hudbgcolor"] = "#000000"

        try:
            hui["hudfgcolor"] = getattr(self.ui, "hudfgcolor", "#FFFFFF")
        except AttributeError:
            hui["hudfgcolor"] = "#FFFFFF"

        try:
            hui["font"] = getattr(self.ui, "font", "Sans")
        except AttributeError:
            hui["font"] = "Sans"

        try:
            hui["font_size"] = getattr(self.ui, "font_size", "8")
        except AttributeError:
            hui["font_size"] = "8"

        # Opacity settings
        try:
            hui["opacity"] = getattr(self.ui, "opacity", "1.0")
        except AttributeError:
            hui["opacity"] = "1.0"

        # Mucked cards settings
        try:
            hui["mucked_cards"] = getattr(self.ui, "mucked_cards", "True")
        except AttributeError:
            hui["mucked_cards"] = "True"

        try:
            hui["mucked_cards_size"] = getattr(self.ui, "mucked_cards_size", "100")
        except AttributeError:
            hui["mucked_cards_size"] = "100"

        try:
            hui["mucked_cards_opacity"] = getattr(self.ui, "mucked_cards_opacity", "1.0")
        except AttributeError:
            hui["mucked_cards_opacity"] = "1.0"

        # Aux windows settings
        try:
            hui["aux_windows"] = getattr(self.ui, "aux_windows", "True")
        except AttributeError:
            hui["aux_windows"] = "True"

        try:
            hui["aux_windows_opacity"] = getattr(self.ui, "aux_windows_opacity", "1.0")
        except AttributeError:
            hui["aux_windows_opacity"] = "1.0"

        # HUD menu settings
        try:
            hui["hud_menu_opacity"] = getattr(self.ui, "hud_menu_opacity", "1.0")
        except AttributeError:
            hui["hud_menu_opacity"] = "1.0"

        try:
            hui["hud_menu_bgcolor"] = getattr(self.ui, "hud_menu_bgcolor", "#000000")
        except AttributeError:
            hui["hud_menu_bgcolor"] = "#000000"

        try:
            hui["hud_menu_fgcolor"] = getattr(self.ui, "hud_menu_fgcolor", "#FFFFFF")
        except AttributeError:
            hui["hud_menu_fgcolor"] = "#FFFFFF"

        # Stat window settings
        try:
            hui["stat_window_opacity"] = getattr(self.ui, "stat_window_opacity", "1.0")
        except AttributeError:
            hui["stat_window_opacity"] = "1.0"

        try:
            hui["stat_window_frame"] = getattr(self.ui, "stat_window_frame", "True")
        except AttributeError:
            hui["stat_window_frame"] = "True"

        # Tooltip settings
        try:
            hui["tooltip_delay"] = getattr(self.ui, "tooltip_delay", "1000")
        except AttributeError:
            hui["tooltip_delay"] = "1000"

        try:
            hui["tooltip_bgcolor"] = getattr(self.ui, "tooltip_bgcolor", "#FFFFE0")
        except AttributeError:
            hui["tooltip_bgcolor"] = "#FFFFE0"

        try:
            hui["tooltip_fgcolor"] = getattr(self.ui, "tooltip_fgcolor", "#000000")
        except AttributeError:
            hui["tooltip_fgcolor"] = "#000000"

        # Advanced settings
        try:
            hui["update_interval"] = getattr(self.ui, "update_interval", "10")
        except AttributeError:
            hui["update_interval"] = "10"

        try:
            hui["max_seats"] = getattr(self.ui, "max_seats", "10")
        except AttributeError:
            hui["max_seats"] = "10"

        try:
            hui["debug_level"] = getattr(self.ui, "debug_level", "INFO")
        except AttributeError:
            hui["debug_level"] = "INFO"

        # Behavior parameters
        try:
            hui["update_interval"] = int(getattr(self.ui, "update_interval", 10))
        except (AttributeError, ValueError):
            hui["update_interval"] = 10

        try:
            hui["auto_close"] = getattr(self.ui, "auto_close", "True")
        except AttributeError:
            hui["auto_close"] = "True"

        try:
            hui["block_click"] = getattr(self.ui, "block_click", "False")
        except AttributeError:
            hui["block_click"] = "False"

        try:
            hui["on_click"] = getattr(self.ui, "on_click", "Nothing")
        except AttributeError:
            hui["on_click"] = "Nothing"

        try:
            hui["popup_style"] = getattr(self.ui, "popup_style", "default")
        except AttributeError:
            hui["popup_style"] = "default"

        try:
            hui["stat_range"] = getattr(self.ui, "stat_range", "True")
        except AttributeError:
            hui["stat_range"] = "True"

        # Advanced parameters
        try:
            hui["max_seats"] = int(getattr(self.ui, "max_seats", 10))
        except (AttributeError, ValueError):
            hui["max_seats"] = 10

        try:
            hui["disable_hud"] = getattr(self.ui, "disable_hud", "False")
        except AttributeError:
            hui["disable_hud"] = "False"

        try:
            hui["query_limit"] = int(getattr(self.ui, "query_limit", 1000))
        except (AttributeError, ValueError):
            hui["query_limit"] = 1000

        try:
            hui["debug_hud"] = getattr(self.ui, "debug_hud", "False")
        except AttributeError:
            hui["debug_hud"] = "False"

        try:
            hui["save_layout"] = getattr(self.ui, "save_layout", "True")
        except AttributeError:
            hui["save_layout"] = "True"

        try:
            hui["player_profiling"] = getattr(self.ui, "player_profiling", "True")
        except AttributeError:
            hui["player_profiling"] = "True"

        try:
            hui["profile_in_name"] = getattr(self.ui, "profile_in_name", "True")
        except AttributeError:
            hui["profile_in_name"] = "True"

        try:
            hui["profile_min_hands"] = int(getattr(self.ui, "profile_min_hands", 10))
        except (AttributeError, ValueError):
            hui["profile_min_hands"] = 10

        return hui

    def set_hud_ui_parameters(self, hud_params) -> None:
        """Set HUD UI parameters from a dictionary."""
        # Get the hud_ui node
        hud_ui_nodes = self.doc.getElementsByTagName("hud_ui")
        if not hud_ui_nodes:
            # Create hud_ui node if it doesn't exist
            for config_node in self.doc.getElementsByTagName("FreePokerToolsConfig"):
                hud_ui_node = self.doc.createElement("hud_ui")
                config_node.appendChild(hud_ui_node)
        else:
            hud_ui_node = hud_ui_nodes[0]

        # Update attributes
        if "label" in hud_params:
            hud_ui_node.setAttribute("label", str(hud_params["label"]))
        if "card_ht" in hud_params:
            hud_ui_node.setAttribute("card_ht", str(hud_params["card_ht"]))
        if "card_wd" in hud_params:
            hud_ui_node.setAttribute("card_wd", str(hud_params["card_wd"]))
        if "deck_type" in hud_params:
            hud_ui_node.setAttribute("deck_type", str(hud_params["deck_type"]))
        if "card_back" in hud_params:
            hud_ui_node.setAttribute("card_back", str(hud_params["card_back"]))
        if "stat_range" in hud_params:
            hud_ui_node.setAttribute("stat_range", str(hud_params["stat_range"]))
        if "hud_days" in hud_params:
            hud_ui_node.setAttribute("stat_days", str(hud_params["hud_days"]))
        if "agg_bb_mult" in hud_params:
            hud_ui_node.setAttribute("aggregation_level_multiplier", str(hud_params["agg_bb_mult"]))
        if "seats_style" in hud_params:
            hud_ui_node.setAttribute("seats_style", str(hud_params["seats_style"]))
        if "seats_cust_nums_low" in hud_params:
            hud_ui_node.setAttribute("seats_cust_nums_low", str(hud_params["seats_cust_nums_low"]))
        if "seats_cust_nums_high" in hud_params:
            hud_ui_node.setAttribute("seats_cust_nums_high", str(hud_params["seats_cust_nums_high"]))

        # Hero specific
        if "h_stat_range" in hud_params:
            hud_ui_node.setAttribute("hero_stat_range", str(hud_params["h_stat_range"]))
        if "h_hud_days" in hud_params:
            hud_ui_node.setAttribute("hero_stat_days", str(hud_params["h_hud_days"]))
        if "h_agg_bb_mult" in hud_params:
            hud_ui_node.setAttribute("hero_aggregation_level_multiplier", str(hud_params["h_agg_bb_mult"]))
        if "h_seats_style" in hud_params:
            hud_ui_node.setAttribute("hero_seats_style", str(hud_params["h_seats_style"]))
        if "h_seats_cust_nums_low" in hud_params:
            hud_ui_node.setAttribute("hero_seats_cust_nums_low", str(hud_params["h_seats_cust_nums_low"]))
        if "h_seats_cust_nums_high" in hud_params:
            hud_ui_node.setAttribute("hero_seats_cust_nums_high", str(hud_params["h_seats_cust_nums_high"]))

        # Additional appearance parameters
        if "bgcolor" in hud_params:
            hud_ui_node.setAttribute("bgcolor", str(hud_params["bgcolor"]))
        if "fgcolor" in hud_params:
            hud_ui_node.setAttribute("fgcolor", str(hud_params["fgcolor"]))
        if "hudbgcolor" in hud_params:
            hud_ui_node.setAttribute("hudbgcolor", str(hud_params["hudbgcolor"]))
        if "hudfgcolor" in hud_params:
            hud_ui_node.setAttribute("hudfgcolor", str(hud_params["hudfgcolor"]))
        if "font" in hud_params:
            hud_ui_node.setAttribute("font", str(hud_params["font"]))
        if "font_size" in hud_params:
            hud_ui_node.setAttribute("font_size", str(hud_params["font_size"]))
        if "opacity" in hud_params:
            hud_ui_node.setAttribute("opacity", str(hud_params["opacity"]))

        # Additional behavior parameters
        if "xshift" in hud_params:
            hud_ui_node.setAttribute("xshift", str(hud_params["xshift"]))
        if "yshift" in hud_params:
            hud_ui_node.setAttribute("yshift", str(hud_params["yshift"]))
        if "aggregate_ring" in hud_params:
            hud_ui_node.setAttribute("aggregate_ring", str(hud_params["aggregate_ring"]))
        if "aggregate_tour" in hud_params:
            hud_ui_node.setAttribute("aggregate_tour", str(hud_params["aggregate_tour"]))
        if "hud_style" in hud_params:
            hud_ui_node.setAttribute("hud_style", str(hud_params["hud_style"]))
        if "hero_stat_aggregation" in hud_params:
            hud_ui_node.setAttribute("hero_stat_aggregation", str(hud_params["hero_stat_aggregation"]))
        if "h_hud_style" in hud_params:
            hud_ui_node.setAttribute("h_hud_style", str(hud_params["h_hud_style"]))
        if "update_interval" in hud_params:
            hud_ui_node.setAttribute("update_interval", str(hud_params["update_interval"]))
        if "auto_close" in hud_params:
            hud_ui_node.setAttribute("auto_close", str(hud_params["auto_close"]))
        if "block_click" in hud_params:
            hud_ui_node.setAttribute("block_click", str(hud_params["block_click"]))
        if "on_click" in hud_params:
            hud_ui_node.setAttribute("on_click", str(hud_params["on_click"]))
        if "popup_style" in hud_params:
            hud_ui_node.setAttribute("popup_style", str(hud_params["popup_style"]))
        if "max_seats" in hud_params:
            hud_ui_node.setAttribute("max_seats", str(hud_params["max_seats"]))
        if "disable_hud" in hud_params:
            hud_ui_node.setAttribute("disable_hud", str(hud_params["disable_hud"]))
        if "query_limit" in hud_params:
            hud_ui_node.setAttribute("query_limit", str(hud_params["query_limit"]))
        if "debug_hud" in hud_params:
            hud_ui_node.setAttribute("debug_hud", str(hud_params["debug_hud"]))
        if "save_layout" in hud_params:
            hud_ui_node.setAttribute("save_layout", str(hud_params["save_layout"]))
        if "player_profiling" in hud_params:
            hud_ui_node.setAttribute("player_profiling", str(hud_params["player_profiling"]))
        if "profile_in_name" in hud_params:
            hud_ui_node.setAttribute("profile_in_name", str(hud_params["profile_in_name"]))
        if "profile_min_hands" in hud_params:
            hud_ui_node.setAttribute("profile_min_hands", str(hud_params["profile_min_hands"]))

        # Update the internal ui object
        if hasattr(self, "ui"):
            for key, value in hud_params.items():
                if key == "label":
                    self.ui.label = value
                elif key == "card_ht":
                    self.ui.card_ht = str(value)
                elif key == "card_wd":
                    self.ui.card_wd = str(value)
                elif key == "deck_type":
                    self.ui.deck_type = value
                elif key == "card_back":
                    self.ui.card_back = value
                elif key == "stat_range":
                    self.ui.stat_range = value
                elif key == "hud_days":
                    self.ui.hud_days = str(value)
                elif key == "agg_bb_mult":
                    self.ui.agg_bb_mult = str(value)
                elif key == "seats_style":
                    self.ui.seats_style = value
                elif key == "seats_cust_nums_low":
                    self.ui.seats_cust_nums_low = str(value)
                elif key == "seats_cust_nums_high":
                    self.ui.seats_cust_nums_high = str(value)
                elif key == "h_stat_range":
                    self.ui.h_stat_range = value
                elif key == "h_hud_days":
                    self.ui.h_hud_days = str(value)
                elif key == "h_agg_bb_mult":
                    self.ui.h_agg_bb_mult = str(value)
                elif key == "h_seats_style":
                    self.ui.h_seats_style = value
                elif key == "h_seats_cust_nums_low":
                    self.ui.h_seats_cust_nums_low = str(value)
                elif key == "h_seats_cust_nums_high":
                    self.ui.h_seats_cust_nums_high = str(value)
                elif key == "player_profiling":
                    self.ui.player_profiling = str(value)
                elif key == "profile_in_name":
                    self.ui.profile_in_name = str(value)
                elif key == "profile_min_hands":
                    self.ui.profile_min_hands = str(value)

    def get_import_parameters(self):
        imp = {}

        try:
            imp["callFpdbHud"] = self.imp.callFpdbHud
        except AttributeError as e:
            log.exception(f"Error getting 'callFpdbHud': {e}")
            imp["callFpdbHud"] = True

        try:
            imp["interval"] = self.imp.interval
        except AttributeError as e:
            log.exception(f"Error getting 'interval': {e}")
            imp["interval"] = 10

        # Use if instead of try/except for ResultsDirectory
        if self.imp.ResultsDirectory != "":
            imp["ResultsDirectory"] = self.imp.ResultsDirectory
        else:
            imp["ResultsDirectory"] = "~/.fpdb/Results/"

        try:
            imp["hhBulkPath"] = self.imp.hhBulkPath
        except AttributeError as e:
            log.exception(f"Error getting 'hhBulkPath': {e}")
            imp["hhBulkPath"] = ""

        try:
            imp["saveActions"] = self.imp.saveActions
        except AttributeError as e:
            log.exception(f"Error getting 'saveActions': {e}")
            imp["saveActions"] = False

        try:
            imp["cacheSessions"] = self.imp.cacheSessions
        except AttributeError as e:
            log.exception(f"Error getting 'cacheSessions': {e}")
            imp["cacheSessions"] = False

        try:
            imp["publicDB"] = self.imp.publicDB
        except AttributeError as e:
            log.exception(f"Error getting 'publicDB': {e}")
            imp["publicDB"] = False

        try:
            imp["sessionTimeout"] = self.imp.sessionTimeout
        except AttributeError as e:
            log.exception(f"Error getting 'sessionTimeout': {e}")
            imp["sessionTimeout"] = 30

        try:
            imp["saveStarsHH"] = self.imp.saveStarsHH
        except AttributeError as e:
            log.exception(f"Error getting 'saveStarsHH': {e}")
            imp["saveStarsHH"] = False

        try:
            imp["fastStoreHudCache"] = self.imp.fastStoreHudCache
        except AttributeError as e:
            log.exception(f"Error getting 'fastStoreHudCache': {e}")
            imp["fastStoreHudCache"] = False

        try:
            imp["importFilters"] = self.imp.importFilters
        except AttributeError as e:
            log.exception(f"Error getting 'importFilters': {e}")
            imp["importFilters"] = []

        try:
            imp["timezone"] = self.imp.timezone
        except AttributeError as e:
            log.exception(f"Error getting 'timezone': {e}")
            imp["timezone"] = "America/New_York"

        return imp

    def set_timezone(self, timezone) -> None:
        self.imp.timezone = timezone

    def detect_hh_path(self, site: str) -> str | None:
        """Return an existing hand-history directory for a site, or None.

        A configured HH_path can point nowhere: the shipped defaults are Windows
        paths, and a config copied between machines keeps the other machine's home
        directory. Fall back to where the client actually writes on this platform.

        On macOS, Americas Cardroom (WPN) stores its configured HH path in a
        JSON file written by the Electron client under
        ``~/Library/Application Support/Loading/storage/``.
        We read that first for an authoritative answer, then fall back to the
        static HH_PATH_CANDIDATES list.
        """
        screen_name = getattr(self.supported_sites.get(site), "screen_name", "")

        # --- ACR / WPN: read the Electron client's own JSON config on macOS ---
        if sysPlatform == "Darwin":
            acr_key = _ACR_JSON_CONFIG_SITES.get(site)
            if acr_key:
                detected = self._read_acr_json_path(acr_key, "hh", screen_name)
                if detected:
                    return detected

        # --- Static candidate list ---
        candidates = HH_PATH_CANDIDATES.get(site, {}).get(sysPlatform, ())
        for candidate in candidates:
            base = Path(candidate).expanduser()
            # Clients write under a per-account folder; prefer the hero's own.
            if screen_name and (base / screen_name).is_dir():
                return str(base / screen_name)
            if base.is_dir():
                return str(base)
        return None

    def detect_ts_path(self, site: str) -> str | None:
        """Return an existing tournament-summary directory for a site, or None.

        On macOS, the ACR client stores its TS path in
        ``~/Library/Application Support/Loading/storage/tsDirPath_{key}.json``.
        """
        if sysPlatform == "Darwin":
            acr_key = _ACR_JSON_CONFIG_SITES.get(site)
            if acr_key:
                screen_name = getattr(self.supported_sites.get(site), "screen_name", "")
                detected = self._read_acr_json_path(acr_key, "ts", screen_name)
                if detected:
                    return detected
        return None

    @staticmethod
    def _read_acr_json_path(acr_key: str, kind: str, screen_name: str) -> str | None:
        """Read a path from the ACR Electron client's local-storage JSON.

        Args:
            acr_key: The config key (e.g. ``"AmericasCardroom"``).
            kind: ``"hh"`` for hand histories or ``"ts"`` for tournament summaries.
            screen_name: The player's screen name for per-account sub-folders.

        Returns:
            The resolved directory path, or ``None`` if the file is missing or
            the directory does not exist.
        """
        prefix = "hhDirPath" if kind == "hh" else "tsDirPath"
        json_path = Path(f"~/Library/Application Support/Loading/storage/{prefix}_{acr_key}.json").expanduser()
        if not json_path.is_file():
            return None
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            base = Path(data["path"])
            if screen_name and (base / screen_name).is_dir():
                return str(base / screen_name)
            if base.is_dir():
                return str(base)
        except (json.JSONDecodeError, KeyError, OSError):
            log.debug("Could not read ACR config from %s", json_path)
        return None

    def get_default_paths(self, site=None):
        if site is None:
            site = self.getDefaultSite()
        paths = {}
        try:
            path = os.path.expanduser(self.supported_sites[site].HH_path)
            if not (os.path.isdir(path) or os.path.isfile(path)):
                detected = self.detect_hh_path(site)
                if detected is None:
                    raise AssertionError(path)  # noqa: TRY301 - keep the existing error path
                log.info(
                    "Hand-history path for %s does not exist (%s); using detected path %s",
                    site,
                    path,
                    detected,
                )
                path = detected
            paths["hud-defaultPath"] = paths["bulkImport-defaultPath"] = path
            if self.imp.hhBulkPath:
                paths["bulkImport-defaultPath"] = self.imp.hhBulkPath
            if self.supported_sites[site].TS_path != "":
                tspath = os.path.expanduser(self.supported_sites[site].TS_path)
                if not (os.path.isdir(tspath) or os.path.isfile(tspath)):
                    tspath = self.detect_ts_path(site) or self.detect_hh_path(site) or tspath
                paths["hud-defaultTSPath"] = tspath
        except AssertionError:
            paths["hud-defaultPath"] = paths["bulkImport-defaultPath"] = (
                "** ERROR DEFAULT PATH IN CONFIG DOES NOT EXIST **"
            )
        return paths

    #    def get_frames(self, site = "PokerStars"):
    #        if site not in self.supported_sites: return False
    #        return self.supported_sites[site].use_frames == True

    #    def get_default_colors(self, site = "PokerStars"):
    #        colors = {}
    #        if site not in self.supported_sites or self.supported_sites[site].hudopacity == "":
    #            colors['hudopacity'] = 0.90
    #        else:
    #            colors['hudopacity'] = float(self.supported_sites[site].hudopacity)
    #        if site not in self.supported_sites or self.supported_sites[site].hudbgcolor == "":
    #            colors['hudbgcolor'] = "#FFFFFF"
    #        else:
    #            colors['hudbgcolor'] = self.supported_sites[site].hudbgcolor
    #        if site not in self.supported_sites or self.supported_sites[site].hudfgcolor == "":
    #            colors['hudfgcolor'] = "#000000"
    #        else:
    #            colors['hudfgcolor'] = self.supported_sites[site].hudfgcolor
    #        return colors

    #    def get_default_font(self, site='PokerStars'):
    #        font = "Sans"
    #        font_size = "8"
    #        site = self.supported_sites.get(site, None)
    #        if site is not None:
    #            if site.font:
    #                font = site.font
    #            if site.font_size:
    #                font_size = site.font_size
    #        return font, font_size

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

    def get_supported_sites(self, all=False):
        """Returns the list of supported sites."""
        if all:
            return list(self.supported_sites.keys())
        return [site_name for (site_name, site) in list(self.supported_sites.items()) if site.enabled]

    def get_site_parameters(self, site):
        """Returns a dict of the site parameters for the specified site."""
        parms = {}
        # A site can be enabled under <supported_sites> without a matching <hhc>
        # converter entry (e.g. "BetOnline" vs "BetOnline Poker"). Don't raise
        # KeyError here: callers that iterate every enabled site (auto-import,
        # HUD_main.read_stdin) would otherwise abort on the first such site and
        # the HUD would never create a table window.
        hhc = self.hhcs.get(site)
        if hhc is None:
            log.warning("No <hhc> converter configured for site '%s'; import/HUD disabled for it", site)
        parms["converter"] = hhc.converter if hhc is not None else None
        parms["summaryImporter"] = hhc.summaryImporter if hhc is not None else None
        parms["screen_name"] = self.supported_sites[site].screen_name
        parms["site_path"] = self.supported_sites[site].site_path
        parms["HH_path"] = self.supported_sites[site].HH_path
        parms["TS_path"] = self.supported_sites[site].TS_path
        parms["site_name"] = self.supported_sites[site].site_name
        parms["enabled"] = self.supported_sites[site].enabled
        parms["aux_enabled"] = self.supported_sites[site].aux_enabled
        parms["hud_menu_xshift"] = self.supported_sites[site].hud_menu_xshift
        parms["hud_menu_yshift"] = self.supported_sites[site].hud_menu_yshift
        parms["layout_set"] = self.supported_sites[site].layout_set
        parms["emails"] = self.supported_sites[site].emails
        parms["fav_seat"] = self.supported_sites[site].fav_seat

        return parms

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

    def set_general(self, lang=None) -> None:
        for general_node in self.doc.getElementsByTagName("general"):
            if lang:
                general_node.setAttribute("ui_language", lang)

    def set_site_ids(self, sites) -> None:
        self.site_ids = dict(sites)

    def get_site_id(self, site):
        if not self.site_ids or site not in self.site_ids:
            # Fallback for standalone/testing environments
            fallbacks = {
                "Full Tilt Poker": 1,
                "PokerStars": 2,
                "Everleaf": 3,
                "Boss": 4,
                "OnGame": 5,
                "UltimateBet": 6,
                "Betfair": 7,
                "Absolute": 8,
                "PartyPoker": 9,
                "PacificPoker": 10,
                "Partouche": 11,
                "Merge": 12,
                "PKR": 13,
                "iPoker": 14,
                "BetOnline": 19,
                "Microgaming": 20,
                "Bovada": 21,
                "Enet": 22,
                "SealsWithClubs": 23,
                "WinningPoker": 24,
                "PokerMaster": 25,
                "Run It Once Poker": 26,
                "GGPoker": 27,  # Note: Database.py has GG=27, GGPokerToFpdb has site_id=27. GGPoker=110 in legacy config but matches 27 in db. Let's make sure both/either are supported or match GGPokerToFpdb.
                "KingsClub": 28,
                "PokerBros": 29,
                "Unibet": 30,
                "PokerStars.COM": 32,
                "PokerStars.FR": 33,
                "PokerStars.IT": 34,
                "PokerStars.ES": 35,
                "PokerStars.PT": 36,
                "PokerStars.EU": 37,
                "Party Poker": 38,
                "PMU Poker": 56,
                "FDJ Poker": 57,
                "Poker770": 58,
                "NetBet Poker": 59,
                "Barrière Poker": 60,
                "Red Star Poker": 61,
                "Titan Poker": 62,
                "Bet365 Poker": 63,
                "William Hill Poker": 64,
                "Paddy Power Poker": 65,
                "Betfair Poker": 66,
                "Coral Poker": 67,
                "Genting Poker": 68,
                "Mansion Poker": 69,
                "Winner Poker": 70,
                "Ladbrokes Poker": 71,
                "Sky Poker": 72,
                "Sisal Poker": 73,
                "Lottomatica Poker": 74,
                "Eurobet Poker": 75,
                "Snai Poker": 76,
                "Goldbet Poker": 77,
                "Casino Barcelona Poker": 78,
                "Sportium Poker": 79,
                "Marca Apuestas Poker": 80,
                "Everest Poker": 81,
                "Bet-at-home Poker": 82,
                "Mybet Poker": 83,
                "Betsson Poker": 84,
                "Betsafe Poker": 85,
                "NordicBet Poker": 86,
                "Unibet Poker": 87,
                "Maria Casino Poker": 88,
                "LeoVegas Poker": 89,
                "Mr Green Poker": 90,
                "Redbet Poker": 91,
                "Betclic Poker": 131,
            }
            return fallbacks.get(site, 2)
        return self.site_ids[site]

    def get_aux_windows(self):
        """Gets the list of mucked window formats in the configuration."""
        return list(self.aux_windows.keys())

    def get_aux_parameters(self, name):
        """Gets a dict of mucked window parameters from the named mw."""
        param = {}
        if name in self.aux_windows:
            for key in dir(self.aux_windows[name]):
                if key.startswith("__"):
                    continue
                value = getattr(self.aux_windows[name], key)
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

    def get_supported_games(self):
        """Get the list of supported games."""
        sg = []
        for game in list(self.supported_games.keys()):
            sg.append(self.supported_games[game].game_name)
        return sg

    def get_supported_games_parameters(self, name, game_type, context: HudContext | None = None):
        """Gets a dict of parameters from the named gametype."""
        param = {}
        if name in self.supported_games:
            for key in dir(self.supported_games[name]):
                if key.startswith("__"):
                    continue
                if key == ("game_stat_set"):
                    continue
                value = getattr(self.supported_games[name], key)
                if callable(value):
                    continue
                param[key] = value

            # some gymnastics now to load the correct Stats_sets instance
            # into the game_stat_set key

            game_stat_set = self.supported_games[name].game_stat_set

            if game_type in game_stat_set:
                param["game_stat_set"] = self.stat_sets[game_stat_set[game_type].stat_set]
            elif "all" in game_stat_set:
                param["game_stat_set"] = self.stat_sets[game_stat_set["all"].stat_set]
            else:
                return None

            if context is not None:
                fallback = getattr(param["game_stat_set"], "name", None)
                profile = HudProfileResolver(self.hud_profile_rules).resolve(context, fallback)
                if profile in self.stat_sets:
                    param["game_stat_set"] = self.stat_sets[profile]

            return param

        return None

    def get_hud_profile_rules(self) -> list[HudProfileRule]:
        """Return a copy of the persistent PT-style profile selection rules."""
        return list(self.hud_profile_rules)

    def set_hud_profile_rules(self, rules: list[HudProfileRule]) -> None:
        """Replace profile rules in memory and in the configuration DOM."""
        self.hud_profile_rules = [
            HudProfileRule.from_mapping(rule.as_xml_attributes(), order)
            for order, rule in enumerate(rules)
            if rule.profile
        ]
        if self.doc is None:
            return

        sections = self.doc.getElementsByTagName("hud_profile_rules")
        if sections:
            section = sections[0]
            while section.firstChild:
                section.removeChild(section.firstChild)
        else:
            section = self.doc.createElement("hud_profile_rules")
            self.doc.documentElement.appendChild(self.doc.createTextNode("\n    "))
            self.doc.documentElement.appendChild(section)

        for rule in self.hud_profile_rules:
            section.appendChild(self.doc.createTextNode("\n        "))
            node = self.doc.createElement("hud_profile_rule")
            for name, value in rule.as_xml_attributes().items():
                if value or name != "id":
                    node.setAttribute(name, value)
            section.appendChild(node)
        if self.hud_profile_rules:
            section.appendChild(self.doc.createTextNode("\n    "))

    def execution_path(self, filename):
        """Join the fpdb path to filename."""
        return os.path.join(os.path.dirname(inspect.getfile(sys._getframe(0))), filename)

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


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB Configuration utility")
    parser.add_argument("--validate", action="store_true", help="Validate configuration file")
    parser.add_argument("--show-sites", action="store_true", help="Show configured poker sites")
    parser.add_argument("--show-games", action="store_true", help="Show supported games")
    parser.add_argument("--show-databases", action="store_true", help="Show database configurations")
    parser.add_argument("--show-all", action="store_true", help="Show all configuration sections")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")

    args = parser.parse_args(argv)

    if not any(vars(args).values()):
        parser.print_help()
        return 0

    set_logfile("fpdb-log.txt")

    try:
        c = Config()
    except Exception as e:  # intentional broad catch: CLI top-level config load boundary
        print(f"Error loading configuration: {e}")
        return 1

    if args.validate:
        print("Configuration loaded successfully ✓")
        print(
            f"Sites: {len(c.supported_sites)}, Games: {len(c.supported_games)}, Databases: {len(c.supported_databases)}"
        )

    if args.show_sites or args.show_all:
        print("\n=== Configured Sites ===")
        for site_name in sorted(c.supported_sites.keys()):
            site = c.supported_sites[site_name]
            status = "✓ enabled" if site.enabled else "✗ disabled"
            print(f"  {site_name}: {status}")

    if args.show_games or args.show_all:
        print("\n=== Supported Games ===")
        for game_name in sorted(c.supported_games.keys()):
            print(f"  {game_name}")

    if args.show_databases or args.show_all:
        print("\n=== Database Configurations ===")
        for db_name in sorted(c.supported_databases.keys()):
            db = c.supported_databases[db_name]
            status = "✓ default" if db.db_selected else ""
            print(f"  {db_name}: {db.db_server} ({db.db_desc}) {status}")

    if args.interactive:
        print("Running original interactive test...")
        for _s in list(c.supported_sites.keys()):
            pass
        for _game in list(c.supported_games.keys()):
            pass
        for _db in list(c.supported_databases.keys()):
            pass
        for _w in list(c.aux_windows.keys()):
            pass
        for _w in list(c.layout_sets.keys()):
            pass
        for _w in list(c.stat_sets.keys()):
            pass
        for _w in list(c.hhcs.keys()):
            pass
        for _w in list(c.popup_windows.keys()):
            pass
        for _hud_param, _value in list(c.get_hud_ui_parameters().items()):
            pass
        for _s in list(c.supported_sites.keys()):
            pass
        print("Press ENTER to continue...")
        sys.stdin.readline()

    return 0


if __name__ == "__main__":
    sys.exit(main())
