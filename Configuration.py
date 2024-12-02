#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Configuration####
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

# TODO fix / rethink edit stats - it is broken badly just now

#    Standard Library modules
from __future__ import with_statement
from __future__ import print_function


# import L10n
# _ = L10n.get_translation()

import codecs
import os
import sys
import inspect
import shutil
import locale
import re
import xml.dom.minidom

# # import Charset
import platform
import traceback


if platform.system() == "Windows":
    # import winpaths
    # winpaths_appdata = winpaths.get_appdata()
    import os

    winpaths_appdata = os.getenv("APPDATA")
    # winpaths_appdata = os.getcwd()
    winpaths_appdata = winpaths_appdata.replace("\\", "/")
else:
    winpaths_appdata = False

from loggingFpdb import get_logger


# config version is used to flag a warning at runtime if the users config is
#  out of date.
# The CONFIG_VERSION should be incremented __ONLY__ if the add_missing_elements()
#  method cannot update existing standard configurations
CONFIG_VERSION = 83

#
# Setup constants
# code is centralised here to ensure uniform handling of path names
# especially important when user directory includes non-ascii chars
#
# INSTALL_METHOD ("source" or "exe")
# FPDB_ROOT_PATH (path to the root fpdb installation dir root (normally ...../fpdb)
# APPDATA_PATH (root path for appdata eg /~ or appdata)
# CONFIG_PATH (path to the directory holding logs, sqlite db's and config)
# GRAPHICS_PATH (path to graphics assets (normally .gfx)
# PYFPDB_PATH (path to py's)
# OS_FAMILY (OS Family for installed system (Linux, Mac, XP, Win7)
# POSIX (True=Linux or Mac platform, False=Windows platform)
# PYTHON_VERSION (n.n)

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
    FPDB_ROOT_PATH = os.path.dirname(sys.executable)

    FPDB_ROOT_PATH = FPDB_ROOT_PATH.replace("\\", "/")
# should be exe path to \fpdbroot\pyfpdb
elif INSTALL_METHOD == "app":
    FPDB_ROOT_PATH = os.path.dirname(sys.executable)
elif INSTALL_METHOD == "appimage":
    FPDB_ROOT_PATH = os.environ["APPDIR"]
elif sys.path[0] == "":  # we are probably running directly (>>>import Configuration)
    temp = os.getcwd()  # should be ./pyfpdb
    FPDB_ROOT_PATH = os.path.join(temp, os.pardir)  # go up one level (to fpdbroot)
else:  # all other cases
    # FPDB_ROOT_PATH = os.path.dirname(sys.path[0])  # should be source path to /fpdbroot
    FPDB_ROOT_PATH = os.getcwd()

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
    OS_FAMILY = False

# GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
# PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")

if OS_FAMILY in ["XP", "Win7"]:
    APPDATA_PATH = winpaths_appdata
    CONFIG_PATH = os.path.join(APPDATA_PATH, "fpdb")
    CONFIG_PATH = CONFIG_PATH.replace("\\", "/")
    FPDB_ROOT_PATH = os.path.dirname(sys.executable)
    FPDB_ROOT_PATH = FPDB_ROOT_PATH.replace("\\", "/")
    if INSTALL_METHOD == "source":
        script = os.path.realpath(__file__)
        script = script.replace("\\", "/")
        script = script.rsplit("/", 1)[0]
        GRAPHICS_PATH = script + "/gfx"
    else:
        GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
        GRAPHICS_PATH = GRAPHICS_PATH.replace("\\", "/")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")
    PYFPDB_PATH = PYFPDB_PATH.replace("\\", "/")
elif OS_FAMILY == "Mac":
    APPDATA_PATH = os.getenv("HOME")
    CONFIG_PATH = os.path.join(APPDATA_PATH, ".fpdb")
    GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH, "pyfpdb")
elif OS_FAMILY == "Linux":
    APPDATA_PATH = os.path.expanduser("~")
    CONFIG_PATH = os.path.join(APPDATA_PATH, ".fpdb")
    GRAPHICS_PATH = os.path.join(FPDB_ROOT_PATH, "gfx")
    PYFPDB_PATH = os.path.join(FPDB_ROOT_PATH)
else:
    APPDATA_PATH = False
    CONFIG_PATH = False

if os.name == "posix":
    POSIX = True
else:
    POSIX = False

PYTHON_VERSION = sys.version[:3]

# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("config")


def get_config(file_name, fallback=True):
    """Looks in cwd and in self.default_config_path for a config file.
    -- FIXME --
    This function has become difficult to understand, plus it no-longer
    just looks for a config file, it actually does file copying
    """

    # look for example file even if not used here, path is returned to caller
    config_found, example_copy = False, False
    config_path, example_path = None, None
    if sysPlatform == "Windows":
        # print('-> windows')
        if platform.release() != "XP":
            OS_FAMILY = "Win7"  # Vista and win7
        #    print('-> windows Win7')
    else:
        OS_FAMILY = "XP"
        # print('-> windows XP')
    if OS_FAMILY == "XP" or "Win7":
        #    print('-> windows XP or Win7')
        config_path = os.path.join(CONFIG_PATH, file_name)
        config_path = config_path.replace("\\", "/")
    else:
        config_path = os.path.join(CONFIG_PATH, file_name)
    if os.path.exists(config_path):  # there is a file in the cwd
        config_found = True
        fallback = False
    else:  # no file in the cwd, look where it should be in the first place
        config_path = os.path.join(CONFIG_PATH, file_name)
        config_path = config_path.replace("\\", "/")
        if os.path.exists(config_path):
            config_found = True
            fallback = False

    if POSIX:
        # If we're on linux, try to copy example from the place
        # debian package puts it; get_default_config_path() creates
        # the config directory for us so there's no need to check it
        # again
        example_path = "/usr/share/python-fpdb/" + file_name + ".example"
        if not os.path.exists(example_path):
            if os.path.exists(file_name + ".example"):
                example_path = file_name + ".example"
            else:
                example_path = os.path.join(PYFPDB_PATH, file_name + ".example")
        if not config_found and fallback:
            try:
                shutil.copyfile(example_path, config_path)
                example_copy = True
                msg = ("Config file has been created at %s.") % (config_path)
                log.info(f"Config posix not found: {msg}")
            except IOError:
                try:
                    example_path = file_name + ".example"
                    shutil.copyfile(example_path, config_path)
                    example_copy = True
                    msg = ("Config file has been created at %s.") % (config_path)
                    log.info(f"Config posix not found: {msg}")
                except IOError:
                    pass

    #    OK, fall back to the .example file, should be in the start dir

    elif os.path.exists(os.path.join(CONFIG_PATH, file_name + ".example").replace("\\", "/")):
        try:
            example_path = os.path.join(CONFIG_PATH, file_name + ".example").replace("\\", "/")
            if not config_found and fallback:
                shutil.copyfile(example_path, config_path)
                example_copy = True
                log.info(
                    f'No {file_name!r} found in "{FPDB_ROOT_PATH!r}" or "{CONFIG_PATH!r}". Config file has been created at {config_path!r}.'
                )

        except IOError:
            log.error(("Error copying .example config file, cannot fall back. Exiting."))
            sys.stderr.write(("Error copying .example config file, cannot fall back. Exiting.") + "\n")
            sys.stderr.write(str(sys.exc_info()))
            sys.exit()
    elif fallback:
        sys.stderr.write((("No %s found, cannot fall back. Exiting.") % file_name) + "\n")
        sys.exit()

    return (config_path, example_copy, example_path)


def set_logfile(file_name):
    (conf_file, copied, example_file) = get_config("logging.conf", fallback=False)

    log_dir = os.path.join(CONFIG_PATH, "log").replace("\\", "/")
    check_dir(log_dir)
    log_file = os.path.join(log_dir, file_name).replace("\\", "/")

    if conf_file and os.path.isfile(conf_file):
        log.info("logging.conf file already exists")
    else:
        log.warning(f"No logging configuration file found at {conf_file}. Using basic configuration.")

    try:
        log.basicConfig(
            filename=log_file,
            filemode="a",
            level=log.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        log.info(f"Logging initialized to file: {log_file}")
    except Exception as e:
        # Ensure sys.stderr is functional
        if not sys.stderr:
            sys.stderr = open(os.devnull, "w")
        sys.stderr.write(f"Could not setup log file {file_name}: {e}\n")


def check_dir(path, create=True):
    """Check if a dir exists, optionally creates if not."""
    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        else:
            return False
    if create:
        path = path.replace("\\", "/")
        msg = ("Creating directory: '%s'") % (path)

        log.info(f"Directory: {msg}")
        os.makedirs(path)  # , "utf-8"))
    else:
        return False


def normalizePath(path):
    "Normalized existing pathes"
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
            (("Default encoding set to US-ASCII, defaulting to CP1252 instead."), ("Please report this problem."))
        )

# needs LOCALE_ENCODING (above), imported for sqlite setup in Config class below


########################################################################
def string_to_bool(string, default=True):
    """converts a string representation of a boolean value to boolean True or False
    @param string: (str) the string to convert
    @param default: value to return if the string can not be converted to a boolean value
    """
    string = string.lower()
    if string in ("1", "true", "t"):
        return True
    elif string in ("0", "false", "f"):
        return False
    return default


class Layout(object):
    def __init__(self, node):
        self.max = int(node.getAttribute("max"))
        self.width = int(node.getAttribute("width"))
        self.height = int(node.getAttribute("height"))

        self.location = []
        self.hh_seats = []
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
                self.common = (int(location_node.getAttribute("x")), int(location_node.getAttribute("y")))

    def __str__(self):
        if hasattr(self, "name"):
            name = str(self.name)
            log.info(f"attribut {name} exists")
        temp = "    Layout = %d max, width= %d, height = %d" % (self.max, self.width, self.height)
        if hasattr(self, "fav_seat"):
            temp = temp + ", fav_seat = %d\n" % self.fav_seat
        else:
            temp = temp + "\n"
        if hasattr(self, "common"):
            temp = temp + "        Common = (%d, %d)\n" % (self.common[0], self.common[1])
        temp = temp + "        Locations = "
        for i in range(1, len(self.location)):
            temp = temp + "%s:(%d,%d) " % (self.hh_seats[i], self.location[i][0], self.location[i][1])
        return temp + "\n"


class Email(object):
    def __init__(self, node):
        self.node = node
        self.host = node.getAttribute("host")
        self.username = node.getAttribute("username")
        self.password = node.getAttribute("password")
        self.useSsl = node.getAttribute("useSsl")
        self.folder = node.getAttribute("folder")
        self.fetchType = node.getAttribute("fetchType")

    def __str__(self):
        return (
            "    email\n        fetchType = %s  host = %s\n        username = %s password = %s\n        useSsl = %s folder = %s"
            % (self.fetchType, self.host, self.username, self.password, self.useSsl, self.folder)
        )


class Site(object):
    def __init__(self, node):
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

    def __str__(self):
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
            temp = temp + "    game_type = %s, layout_set = %s\n" % (game_type, self.layout_set[game_type])

        for max in self.fav_seat:
            temp = temp + "    max = %s, fav_seat = %s\n" % (max, self.fav_seat[max])

        return temp


class Stat(object):
    def __init__(self, node):
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
        self.stat_loth = node.getAttribute("stat_loth")
        self.stat_hith = node.getAttribute("stat_hith")
        self.stat_locolor = node.getAttribute("stat_locolor")
        self.stat_hicolor = node.getAttribute("stat_hicolor")
        self.stat_midcolor = node.getAttribute("stat_midcolor")

    def __str__(self):
        temp = "        _rowcol = %s, _stat_name = %s, \n" % (self.rowcol, self.stat_name)
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


class Stat_sets(object):
    """Representation of a HUD display configuration
    - stats: Dict of Tuples (position in HUD) -> Configuration.Stat
             Exemple: {
                (0,0): Stat(stat_name = 'vpip', stat_hicolor ='#F44336', ...),
                (0,1): Stat(stat_name = 'pfr', stat_hicolor ='#F44336', ...),
                ...
             }
    - rows, cols: siez of the HUD
    """

    def __init__(self, node):
        self.name = node.getAttribute("name")
        self.rows = int(node.getAttribute("rows"))
        self.cols = int(node.getAttribute("cols"))
        self.xpad = node.getAttribute("xpad")
        self.xpad = 0 if self.xpad == "" else int(self.xpad)
        self.ypad = node.getAttribute("ypad")
        self.ypad = 0 if self.ypad == "" else int(self.ypad)
        self.stats = None  #

        self.stats = {}
        for stat_node in node.getElementsByTagName("stat"):
            stat = Stat(stat_node)
            self.stats[stat.rowcol] = stat  # this is the key!

    def __str__(self):
        temp = "Name = " + self.name + "\n"
        temp = temp + "    rows = %d" % self.rows
        temp = temp + " cols = %d" % self.cols
        temp = temp + "    xpad = %d" % self.xpad
        temp = temp + " ypad = %d\n" % self.ypad

        for stat in list(self.stats.keys()):
            temp = temp + "%s" % self.stats[stat]

        return temp


class Database(object):
    def __init__(self, node):
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
            f"Database db_name:'{self.db_name}'  db_server:'{self.db_server}'  db_ip:'{self.db_ip}'  db_port:'{self.db_port}' db_user:'{self.db_user}'  db_pass (not logged)  selected:'{self.db_selected}'"
        )

    def __str__(self):
        temp = "Database = " + self.db_name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + repr(value) + "\n"
        return temp


class Aux_window(object):
    def __init__(self, node):
        for name, value in list(node.attributes.items()):
            setattr(self, name, value)

    def __str__(self):
        temp = "Aux = " + self.name + "\n"
        for key in dir(self):
            if key.startswith("__"):
                continue
            value = getattr(self, key)
            if callable(value):
                continue
            temp = temp + "    " + key + " = " + value + "\n"

        return temp


class Supported_games(object):
    def __init__(self, node):
        for name, value in list(node.attributes.items()):
            setattr(self, name, value)

        self.game_stat_set = {}
        for game_stat_set_node in node.getElementsByTagName("game_stat_set"):
            gss = Game_stat_set(game_stat_set_node)
            self.game_stat_set[gss.game_type] = gss

    def __str__(self):
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
            temp = temp + "%s" % str(self.game_stat_set[gs])
        return temp


class Layout_set(object):
    def __init__(self, node):
        for name, value in list(node.attributes.items()):
            setattr(self, name, value)

        self.layout = {}
        for layout_node in node.getElementsByTagName("layout"):
            lo = Layout(layout_node)
            self.layout[lo.max] = lo

    def __str__(self):
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
            temp = temp + "%s" % self.layout[layout]
        return temp


class Game_stat_set(object):
    def __init__(self, node):
        self.game_type = node.getAttribute("game_type")
        self.stat_set = node.getAttribute("stat_set")

    def __str__(self):
        return "      Game Type: '%s' Stat Set: '%s'\n" % (self.game_type, self.stat_set)


class HHC(object):
    def __init__(self, node):
        self.site = node.getAttribute("site")
        self.converter = node.getAttribute("converter")
        self.summaryImporter = node.getAttribute("summaryImporter")

    def __str__(self):
        return "%s:\tconverter: '%s' summaryImporter: '%s'" % (self.site, self.converter, self.summaryImporter)


class Popup(object):
    def __init__(self, node):
        self.name = node.getAttribute("pu_name")
        self.pu_class = node.getAttribute("pu_class")
        self.pu_stats = []
        self.pu_stats_submenu = []

        for stat_node in node.getElementsByTagName("pu_stat"):
            self.pu_stats.append(stat_node.getAttribute("pu_stat_name"))
            # if stat_node.getAttribute("pu_stat_submenu"):
            self.pu_stats_submenu.append(
                tuple((stat_node.getAttribute("pu_stat_name"), stat_node.getAttribute("pu_stat_submenu")))
            )

    def __str__(self):
        temp = "Popup = " + self.name + "  Class = " + self.pu_class + "\n"
        for stat in self.pu_stats:
            temp = temp + " " + stat
        return temp + "\n"


class Import(object):
    def __init__(self, node):
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

    def __str__(self):
        return (
            "    interval = %s\n    callFpdbHud = %s\n    saveActions = %s\n   cacheSessions = %s\n    publicDB = %s\n    sessionTimeout = %s\n    fastStoreHudCache = %s\n    ResultsDirectory = %s"
            % (
                self.interval,
                self.callFpdbHud,
                self.saveActions,
                self.cacheSessions,
                self.publicDB,
                self.sessionTimeout,
                self.fastStoreHudCache,
                self.ResultsDirectory,
            )
        )


class HudUI(object):
    def __init__(self, node):
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
        #
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
        #
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

    def __str__(self):
        return "    label = %s\n" % self.label


class General(dict):
    def __init__(self):
        super(General, self).__init__()

    def add_elements(self, node):
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

    def get_defaults(self):
        self["version"] = 0
        self["ui_language"] = "system"
        self["config_difficulty"] = "expert"
        self["config_wrap_len"] = "-1"
        self["day_start"] = "5"

    def __str__(self):
        s = ""
        for k in self:
            s = s + "    %s = %s\n" % (k, self[k])
        return s


class GUICashStats(list):
    """<gui_cash_stats>
        <col col_name="game" col_title="Game" disp_all="True" disp_posn="True" field_format="%s" field_type="str" xalignment="0.0" />
        ...
    </gui_cash_stats>
    """

    def __init__(self):
        super(GUICashStats, self).__init__()

    def add_elements(self, node):
        # is this needed?
        for child in node.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment = (
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
                    log.error(("bad number in xalignment was ignored"))

                self.append([col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment])

    def get_defaults(self):
        """A list of defaults to be called, should there be no entry in config"""
        # SQL column name, display title, display all, display positional, format, type, alignment
        defaults = [
            ["game", "Game", True, True, "%s", "str", 0.0],
            ["hand", "Hand", False, False, "%s", "str", 0.0],
            ["plposition", "Posn", False, False, "%s", "str", 1.0],
            ["pname", "Name", False, False, "%s", "str", 0.0],
            ["n", "Hds", True, True, "%1.0f", "str", 1.0],
            ["avgseats", "Seats", False, False, "%3.1f", "str", 1.0],
            ["vpip", "VPIP", True, True, "%3.1f", "str", 1.0],
            ["pfr", "PFR", True, True, "%3.1f", "str", 1.0],
            ["pf3", "PF3", True, True, "%3.1f", "str", 1.0],
            ["aggfac", "AggFac", True, True, "%2.2f", "str", 1.0],
            ["aggfrq", "AggFreq", True, True, "%3.1f", "str", 1.0],
            ["conbet", "ContBet", True, True, "%3.1f", "str", 1.0],
            ["rfi", "RFI", True, True, "%3.1f", "str", 1.0],
            ["steals", "Steals", True, True, "%3.1f", "str", 1.0],
            ["saw_f", "Saw_F", True, True, "%3.1f", "str", 1.0],
            ["sawsd", "SawSD", True, True, "%3.1f", "str", 1.0],
            ["wtsdwsf", "WtSDwsF", True, True, "%3.1f", "str", 1.0],
            ["wmsd", "W$SD", True, True, "%3.1f", "str", 1.0],
            ["flafq", "FlAFq", True, True, "%3.1f", "str", 1.0],
            ["tuafq", "TuAFq", True, True, "%3.1f", "str", 1.0],
            ["rvafq", "RvAFq", True, True, "%3.1f", "str", 1.0],
            ["pofafq", "PoFAFq", False, False, "%3.1f", "str", 1.0],
            ["net", "Net($)", True, True, "%6.2f", "cash", 1.0],
            ["bbper100", "bb/100", True, True, "%4.2f", "str", 1.0],
            ["rake", "Rake($)", True, True, "%6.2f", "cash", 1.0],
            ["bb100xr", "bbxr/100", True, True, "%4.2f", "str", 1.0],
            ["stddev", "Standard Deviation", True, True, "%5.2f", "str", 1.0],
        ]
        for col in defaults:
            self.append(col)


#    def __str__(self):
#        s = ""
#        for l in self:
#            s = s + "    %s = %s\n" % (k, self[k])
#        return(s)
class GUITourStats(list):
    """<gui_tour_stats>
        <col col_name="game" col_title="Game" disp_all="True" disp_posn="True" field_format="%s" field_type="str" xalignment="0.0" />
        ...
    </gui_tour_stats>
    """

    def __init__(self):
        super(GUITourStats, self).__init__()

    def add_elements(self, node):
        # is this needed?
        for child in node.childNodes:
            if child.nodeType == child.ELEMENT_NODE:
                col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment = (
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
                    log.error(("bad number in xalignment was ignored"))

                self.append([col_name, col_title, disp_all, disp_posn, field_format, field_type, xalignment])

    def get_defaults(self):
        """A list of defaults to be called, should there be no entry in config"""
        # SQL column name, display title, display all, display positional, format, type, alignment
        defaults = [
            ["game", "Game", True, True, "%s", "str", 0.0],
            ["hand", "Hand", False, False, "%s", "str", 0.0],
        ]
        for col in defaults:
            self.append(col)


class RawHands(object):
    def __init__(self, node=None):
        if node is None:
            self.save = "error"
            self.compression = "none"
            # print ("missing config section raw_hands")
        else:
            save = node.getAttribute("save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                log.warning(f"Invalid config value for {self.raw_hands.save}, defaulting to error")
                self.save = "error"

            compression = node.getAttribute("compression")
            if save in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                log.warning(f"Invalid config value for {self.raw_hands.compression}, defaulting to none")
                self.compression = "none"

    # end def __init__

    def __str__(self):
        return "        save= %s, compression= %s\n" % (self.save, self.compression)


# end class RawHands


class RawTourneys(object):
    def __init__(self, node=None):
        if node is None:
            self.save = "error"
            self.compression = "none"
            # print ("missing config section raw_tourneys")
        else:
            save = node.getAttribute("save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                log.warning(f"Invalid config value for {self.raw_tourneys.save}, defaulting to error")
                self.save = "error"

            compression = node.getAttribute("compression")
            if save in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                log.warning(f"Invalid config value for {self.raw_tourneys.compression}, defaulting to none")
                self.compression = "none"

    # end def __init__

    def __str__(self):
        return "        save= %s, compression= %s\n" % (self.save, self.compression)


# end class RawTourneys


class Config(object):
    def __init__(self, file=None, dbname="", custom_log_dir="", lvl="INFO"):
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
            self.dir_log = str(custom_log_dir, "utf8")
        else:
            if OS_FAMILY == "XP" or "Win7":
                self.dir_log = os.path.join(CONFIG_PATH, "log")
                self.dir_log = self.dir_log.replace("\\", "/")
            else:
                self.dir_log = os.path.join(CONFIG_PATH, "log")
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
                sys.stderr.write(("Configuration file %s not found. Using defaults.") % (file))
                file = None

        self.example_copy, example_file = True, None
        if file is None:
            (file, self.example_copy, example_file) = get_config("HUD_config.xml", True)

        self.file = file

        self.supported_sites = {}
        self.supported_games = {}
        self.supported_databases = {}  # databaseName --> Database instance
        self.aux_windows = {}
        self.layout_sets = {}
        self.stat_sets = {}
        self.hhcs = {}
        self.popup_windows = {}
        self.db_selected = None  # database the user would like to use
        self.general = General()
        self.emails = {}
        self.gui_cash_stats = GUICashStats()
        self.gui_tour_stats = GUITourStats()
        self.site_ids = {}  # site ID list from the database
        self.doc = None  # Root of XML tree

        added, n = 1, 0  # use n to prevent infinite loop if add_missing_elements() fails somehow
        while added > 0 and n < 2:
            n = n + 1
            log.info(f"Reading configuration file {file}")
            try:
                doc = xml.dom.minidom.parse(file)
                self.doc = doc  # Root of XML tree
                self.file_error = None

            except (OSError, IOError, xml.parsers.expat.ExpatError) as e:
                log.error(f"Error while processing XML: {traceback.format_exc()} Exception: {e}")

            if (not self.example_copy) and (example_file is not None):
                # reads example file and adds missing elements into current config
                added = self.add_missing_elements(doc, example_file)

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

        if doc.getElementsByTagName("gui_tour_stats") == []:
            self.gui_tour_stats.get_defaults()
        for gcs_node in doc.getElementsByTagName("gui_tour_stats"):
            self.gui_tour_stats.add_elements(node=gcs_node)  # add/overwrite elements in self.gui_cash_stats

        #        s_sites = doc.getElementsByTagName("supported_sites")
        for site_node in doc.getElementsByTagName("site"):
            site = Site(node=site_node)
            self.supported_sites[site.site_name] = site

        #        s_games = doc.getElementsByTagName("supported_games")
        for supported_game_node in doc.getElementsByTagName("game"):
            supported_game = Supported_games(supported_game_node)
            self.supported_games[supported_game.game_name] = supported_game

        # parse databases defined by user in the <supported_databases> section
        # the user may select the actual database to use via commandline or by setting the selected="bool"
        # attribute of the tag. if no database is explicitely selected, we use the first one we come across
        #        s_dbs = doc.getElementsByTagName("supported_databases")
        # TODO: do we want to take all <database> tags or all <database> tags contained in <supported_databases>
        #         ..this may break stuff for some users. so leave it unchanged for now untill there is a decission
        for db_node in doc.getElementsByTagName("database"):
            db = Database(node=db_node)
            if db.db_name in self.supported_databases:
                raise ValueError("Database names must be unique")
            if self.db_selected is None or db.db_selected:
                self.db_selected = db.db_name
                db_node.setAttribute("default", "True")
            self.supported_databases[db.db_name] = db
        # TODO: if the user may passes '' (empty string) as database name via command line, his choice is ignored
        #           ..when we parse the xml we allow for ''. there has to be a decission if to allow '' or not
        if dbname and dbname in self.supported_databases:
            self.db_selected = dbname
        # NOTE: fpdb can not handle the case when no database is defined in xml, so we throw an exception for now
        if self.db_selected is None:
            raise ValueError("There must be at least one database defined")

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

    def add_missing_elements(self, doc, example_file):
        """Look through example config file and add any elements that are not in the config
        May need to add some 'enabled' attributes to turn things off - can't just delete a
        config section now because this will add it back in"""

        nodes_added = 0

        try:
            example_doc = xml.dom.minidom.parse(example_file)
        except (OSError, IOError, xml.parsers.expat.ExpatError) as e:
            log.error(f"Error parsing example configuration file {example_file}. See error log file. Exception: {e}")
            return nodes_added

        for cnode in doc.getElementsByTagName("FreePokerToolsConfig"):
            for example_cnode in example_doc.childNodes:
                if example_cnode.localName == "FreePokerToolsConfig":
                    for e in example_cnode.childNodes:
                        # print "nodetype", e.nodeType, "name", e.localName, "found", len(doc.getElementsByTagName(e.localName))
                        if e.nodeType == e.ELEMENT_NODE and doc.getElementsByTagName(e.localName) == []:
                            new = doc.importNode(e, True)  # True means do deep copy
                            t_node = self.doc.createTextNode("    ")
                            cnode.appendChild(t_node)
                            cnode.appendChild(new)
                            t_node = self.doc.createTextNode("\r\n\r\n")
                            cnode.appendChild(t_node)
                            log.debug(f"... adding missing config section: {e.localName}")
                            nodes_added = nodes_added + 1

        if nodes_added > 0:
            log.debug(f"Added {nodes_added} missing config sections")
            self.save()

        return nodes_added

    def find_default_conf(self):
        if CONFIG_PATH:
            config_file = os.path.join(CONFIG_PATH, "default.conf")
        else:
            config_file = False

        if config_file and os.path.exists(config_file):
            file = config_file
        else:
            file = None
        return file

    def get_doc(self):
        return self.doc

    def get_site_node(self, site):
        for site_node in self.doc.getElementsByTagName("site"):
            if site_node.getAttribute("site_name") == site:
                return site_node

    def getEmailNode(self, siteName, fetchType):
        siteNode = self.get_site_node(siteName)
        for emailNode in siteNode.getElementsByTagName("email"):
            if emailNode.getAttribute("fetchType") == fetchType:
                return emailNode
                break

    # end def getEmailNode

    def getStatSetNode(self, statsetName):
        """returns DOM game node for a given game"""
        for statsetNode in self.doc.getElementsByTagName("ss"):
            # print "getStatSetNode statsetNode:",statsetNode
            if statsetNode.getAttribute("name") == statsetName:
                return statsetNode

    def getGameNode(self, gameName):
        """returns DOM game node for a given game"""
        for gameNode in self.doc.getElementsByTagName("game"):
            # print "getGameNode gameNode:",gameNode
            if gameNode.getAttribute("game_name") == gameName:
                return gameNode

    # end def getGameNode

    def get_aux_node(self, aux):
        for aux_node in self.doc.getElementsByTagName("aw"):
            if aux_node.getAttribute("name") == aux:
                return aux_node

    def get_layout_set_node(self, ls):
        for layout_set_node in self.doc.getElementsByTagName("ls"):
            if layout_set_node.getAttribute("name") == ls:
                return layout_set_node

    def get_layout_node(self, ls, max):
        for layout_node in ls.getElementsByTagName("layout"):
            if layout_node.getAttribute("max") == str(max):
                return layout_node

    def get_stat_set_node(self, ss):
        for stat_set_node in self.doc.getElementsByTagName("ss"):
            if os.ST_NODEV.getAttribute("name") == ss:
                return stat_set_node

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
        else:
            for location_node in layout_node.getElementsByTagName("location"):
                if int(location_node.getAttribute("seat")) == int(seat):
                    return location_node

    def save(self, file=None):
        if file is None:
            file = self.file
            try:
                shutil.move(file, f"{file}.backup")
            except OSError as e:
                log.error(f"Failed to move file {file} to backup. Exception: {e}")

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
            m = re.compile("\s+\S+\s+")
            mo = m.match(line)
            if mo:
                indent_len = mo.end()
                # print "indent = %s (%s)" % (indent_len, l[0:indent_len])
                indent = "\n" + " " * indent_len
                m = re.compile('(\S+="[^"]+"\s+)')
                parts = [x for x in m.split(line[indent_len:]) if x]
                if len(parts) > 1:
                    # print "parts =", parts
                    line = line[0:indent_len] + indent.join(parts)
            return line
        else:
            return line

    def editEmail(self, siteName, fetchType, newEmail):
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
    ):
        site_node = self.get_site_node(site_name)
        site_node.setAttribute("enabled", enabled)

        for fav_seat in site_node.getElementsByTagName("fav"):
            if fav_seat.getAttribute("max") == "2":
                fav_seat.setAttribute("fav_seat", seat2_dict)
            elif fav_seat.getAttribute("max") == "3":
                fav_seat.setAttribute("fav_seat", seat3_dict)
            elif fav_seat.getAttribute("max") == "4":
                fav_seat.setAttribute("fav_seat", seat4_dict)
            elif fav_seat.getAttribute("max") == "5":
                fav_seat.setAttribute("fav_seat", seat5_dict)
            elif fav_seat.getAttribute("max") == "6":
                fav_seat.setAttribute("fav_seat", seat6_dict)
            elif fav_seat.getAttribute("max") == "7":
                fav_seat.setAttribute("fav_seat", seat7_dict)
            elif fav_seat.getAttribute("max") == "8":
                fav_seat.setAttribute("fav_seat", seat8_dict)
            elif fav_seat.getAttribute("max") == "9":
                fav_seat.setAttribute("fav_seat", seat9_dict)
            elif fav_seat.getAttribute("max") == "10":
                fav_seat.setAttribute("fav_seat", seat10_dict)

    # end def

    def increment_position(self, position: str) -> str:
        # Adapt defined logic for hus stats form config file
        # TODO: Probably adapt hud logic instead
        """
        >>> self.increment_position('(0,0)')
        "(1,1)"
        >>> self.increment_position('(0, 0)')
        "(1,1)"
        >>> self.increment_position('(2,3)')
        "(3,4)"
        """
        assert position.startswith("(") and position.endswith(")"), position.__repr__()
        # Remove parentheses and split by comma
        row, col = map(int, position[1:-1].split(","))
        # Check that row and collar are not negative
        assert row >= 0 and col >= 0, f"Negative values detected: row={row}, col={col}"
        # Increment both row and column by 1
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
    ):
        """Replace given values onto self.doc (XML root node)"""
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

    def edit_site(self, site_name, enabled, screen_name, history_path, summary_path):
        site_node = self.get_site_node(site_name)
        site_node.setAttribute("enabled", enabled)
        site_node.setAttribute("screen_name", screen_name)
        site_node.setAttribute("HH_path", history_path)
        if summary_path:
            site_node.setAttribute("TS_path", summary_path)

    def editStats(self, statsetName, statArray):
        """replaces stat selection for the given gameName with the given statArray"""
        statsetNode = self.getStatSetNode(statsetName)
        statNodes = statsetNode.getElementsByTagName("stat")

        for node in statNodes:
            statsetNode.removeChild(node)

        statsetNode.setAttribute("rows", str(len(statArray)))
        statsetNode.setAttribute("cols", str(len(statArray[0])))

        for rowNumber in range(len(statArray)):
            for columnNumber in range(len(statArray[rowNumber])):
                newStat = self.doc.createElement("stat")

                attributes = {
                    "_stat_name": statArray[rowNumber][columnNumber],
                    "_rowcol": f"({rowNumber+1},{columnNumber+1})",
                    "click": "",
                    "popup": "default",
                    "tip": "",
                    "stat_locolor": "",
                    "stat_loth": "",
                    "stat_midcolor": "",  # Add stat_midcolor
                    "stat_hicolor": "",
                    "stat_hith": "",
                }

                for attr_name, attr_value in attributes.items():
                    newAttr = self.doc.createAttribute(attr_name)
                    newStat.setAttributeNode(newAttr)
                    newStat.setAttribute(attr_name, attr_value)

                statsetNode.appendChild(newStat)

        statNodes = statsetNode.getElementsByTagName("stat")  # TODO remove this line?

    # end def editStats
    def editImportFilters(self, games):
        self.imp.importFilters = games
        imp_node = self.doc.getElementsByTagName("import")[-1]
        imp_node.setAttribute("importFilters", games)

    def save_layout_set(self, ls, max, locations, width=None, height=None):
        # wid/height normally not specified when saving common from the mucked display

        log.debug(f"saving layout = {ls.name} {max}Max {locations} size: {width}x{height}")
        ls_node = self.get_layout_set_node(ls.name)
        layout_node = self.get_layout_node(ls_node, max)
        if width:
            layout_node.setAttribute("width", str(width))
        if height:
            layout_node.setAttribute("height", str(height))

        for i, pos in list(locations.items()):
            location_node = self.get_location_node(layout_node, i)
            location_node.setAttribute("x", str(locations[i][0]))
            location_node.setAttribute("y", str(locations[i][1]))
            # now refresh the live instance of the layout set with the new locations
            # this is needed because any future windows created after a save layout
            # MUST pickup the new layout
            # fixme - this is horrid
            if i == "common":
                self.layout_sets[ls.name].layout[max].common = (locations[i][0], locations[i][1])
            else:
                self.layout_sets[ls.name].layout[max].location[i] = (locations[i][0], locations[i][1])
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
        db = {}
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
            log.error(f"Error retrieving backend for {name}: {str(e)}")
            db["db-backend"] = None

        return db

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
    ):
        db_node = self.get_db_node(db_name)
        default = default.lower()
        defaultb = string_to_bool(default, False)
        if db_node is not None:
            if db_desc is not None:
                db_node.setAttribute("db_desc", db_desc)
            if db_ip is not None:
                db_node.setAttribute("db_ip", db_ip)
            if db_port is not None:
                db_node.setAttribute("db_port", db_port)
            if db_user is not None:
                db_node.setAttribute("db_user", db_user)
            if db_pass is not None:
                db_node.setAttribute("db_pass", db_pass)
            if db_server is not None:
                db_node.setAttribute("db_server", db_server)
            if defaultb or self.db_selected == db_name:
                db_node.setAttribute("default", "True")
                for dbn in self.doc.getElementsByTagName("database"):
                    if dbn.getAttribute("db_name") != db_name and dbn.hasAttribute("default"):
                        dbn.removeAttribute("default")
            elif db_node.hasAttribute("default"):
                db_node.removeAttribute("default")
        if db_name in self.supported_databases:
            if db_desc is not None:
                self.supported_databases[db_name].dp_desc = db_desc
            if db_ip is not None:
                self.supported_databases[db_name].dp_ip = db_ip
            if db_port is not None:
                self.supported_databases[db_name].dp_port = db_port
            if db_user is not None:
                self.supported_databases[db_name].dp_user = db_user
            if db_pass is not None:
                self.supported_databases[db_name].dp_pass = db_pass
            if db_server is not None:
                self.supported_databases[db_name].dp_server = db_server
            self.supported_databases[db_name].db_selected = defaultb
        if defaultb:
            self.db_selected = db_name
        return

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
    ):
        default = default.lower()
        defaultb = string_to_bool(default, False)
        if db_name in self.supported_databases:
            raise ValueError("Database names must be unique")

        db_node = self.get_db_node(db_name)
        if db_node is None:
            for db_node in self.doc.getElementsByTagName("supported_databases"):
                # should only be one supported_databases element, use last one if there are several
                suppdb_node = db_node
            t_node = self.doc.createTextNode("    ")
            suppdb_node.appendChild(t_node)
            db_node = self.doc.createElement("database")
            suppdb_node.appendChild(db_node)
            t_node = self.doc.createTextNode("\r\n    ")
            suppdb_node.appendChild(t_node)
            db_node.setAttribute("db_name", db_name)
            if db_desc is not None:
                db_node.setAttribute("db_desc", db_desc)
            if db_ip is not None:
                db_node.setAttribute("db_ip", db_ip)
            if db_port is not None:
                db_node.setAttribute("db_port", db_port)
            if db_user is not None:
                db_node.setAttribute("db_user", db_user)
            if db_pass is not None:
                db_node.setAttribute("db_pass", db_pass)
            if db_server is not None:
                db_node.setAttribute("db_server", db_server)
            if defaultb:
                db_node.setAttribute("default", "True")
                for dbn in self.doc.getElementsByTagName("database"):
                    if dbn.getAttribute("db_name") != db_name and dbn.hasAttribute("default"):
                        dbn.removeAttribute("default")
            elif db_node.hasAttribute("default"):
                db_node.removeAttribute("default")
        else:
            if db_desc is not None:
                db_node.setAttribute("db_desc", db_desc)
            if db_ip is not None:
                db_node.setAttribute("db_ip", db_ip)
            if db_port is not None:
                db_node.setAttribute("db_port", db_port)
            if db_user is not None:
                db_node.setAttribute("db_user", db_user)
            if db_pass is not None:
                db_node.setAttribute("db_pass", db_pass)
            if db_server is not None:
                db_node.setAttribute("db_server", db_server)
            if defaultb or self.db_selected == db_name:
                db_node.setAttribute("default", "True")
            elif db_node.hasAttribute("default"):
                db_node.removeAttribute("default")

        if db_name in self.supported_databases:
            if db_desc is not None:
                self.supported_databases[db_name].dp_desc = db_desc
            if db_ip is not None:
                self.supported_databases[db_name].dp_ip = db_ip
            if db_port is not None:
                self.supported_databases[db_name].dp_port = db_port
            if db_user is not None:
                self.supported_databases[db_name].dp_user = db_user
            if db_pass is not None:
                self.supported_databases[db_name].dp_pass = db_pass
            if db_server is not None:
                self.supported_databases[db_name].dp_server = db_server
            self.supported_databases[db_name].db_selected = defaultb
        else:
            db = Database(node=db_node)
            self.supported_databases[db.db_name] = db

        if defaultb:
            self.db_selected = db_name
        return

    def get_backend(self, name):
        """Returns the number of the currently used backend"""

        # Mapper les chaînes de caractères reçues aux constantes attendues
        name_mapping = {
            "sqlite": "DATABASE_TYPE_SQLITE",
            "mysql": "DATABASE_TYPE_MYSQL",
            "postgresql": "DATABASE_TYPE_POSTGRESQL",
        }

        # Convertir le nom en majuscules en utilisant le mapping
        if name in name_mapping:
            name = name_mapping[name]
        else:
            raise ValueError(f"Unsupported database backend: {name}")

        # Utilisation des constantes attendues
        backends = {"DATABASE_TYPE_MYSQL": 2, "DATABASE_TYPE_POSTGRESQL": 3, "DATABASE_TYPE_SQLITE": 4}

        return backends[name]

    def getDefaultSite(self):
        "Returns first enabled site or None"
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
            log.error(f"Error getting label: {e}")
            hui["label"] = default_text

        try:
            hui["card_ht"] = int(self.ui.card_ht)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting card height: {e}")
            hui["card_ht"] = 42

        try:
            hui["card_wd"] = int(self.ui.card_wd)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting card width: {e}")
            hui["card_wd"] = 30

        try:
            hui["deck_type"] = str(self.ui.deck_type)
        except AttributeError as e:
            log.error(f"Error getting deck type: {e}")
            hui["deck_type"] = "colour"

        try:
            hui["card_back"] = str(self.ui.card_back)
        except AttributeError as e:
            log.error(f"Error getting card back: {e}")
            hui["card_back"] = "back04"

        try:
            hui["stat_range"] = self.ui.stat_range
        except AttributeError as e:
            log.error(f"Error getting stat range: {e}")
            hui["stat_range"] = "A"  # default is show stats for All-time, also S(session) and T(ime)

        try:
            hui["hud_days"] = int(self.ui.hud_days)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting HUD days: {e}")
            hui["hud_days"] = 90

        try:
            hui["agg_bb_mult"] = int(self.ui.agg_bb_mult)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting aggregate BB multiplier: {e}")
            hui["agg_bb_mult"] = 1

        try:
            hui["seats_style"] = self.ui.seats_style
        except AttributeError as e:
            log.error(f"Error getting seats style: {e}")
            hui["seats_style"] = "A"  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:
            hui["seats_cust_nums_low"] = int(self.ui.seats_cust_nums_low)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting custom seat numbers low: {e}")
            hui["seats_cust_nums_low"] = 1

        try:
            hui["seats_cust_nums_high"] = int(self.ui.seats_cust_nums_high)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting custom seat numbers high: {e}")
            hui["seats_cust_nums_high"] = 10

        # Hero specific
        try:
            hui["h_stat_range"] = self.ui.h_stat_range
        except AttributeError as e:
            log.error(f"Error getting hero stat range: {e}")
            hui["h_stat_range"] = "S"

        try:
            hui["h_hud_days"] = int(self.ui.h_hud_days)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting hero HUD days: {e}")
            hui["h_hud_days"] = 30

        try:
            hui["h_agg_bb_mult"] = int(self.ui.h_agg_bb_mult)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting hero aggregate BB multiplier: {e}")
            hui["h_agg_bb_mult"] = 1

        try:
            hui["h_seats_style"] = self.ui.h_seats_style
        except AttributeError as e:
            log.error(f"Error getting hero seats style: {e}")
            hui["h_seats_style"] = "A"  # A / C / E, use A(ll) / C(ustom) / E(xact) seat numbers

        try:
            hui["h_seats_cust_nums_low"] = int(self.ui.h_seats_cust_nums_low)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting hero custom seat numbers low: {e}")
            hui["h_seats_cust_nums_low"] = 1

        try:
            hui["h_seats_cust_nums_high"] = int(self.ui.h_seats_cust_nums_high)
        except (AttributeError, ValueError) as e:
            log.error(f"Error getting hero custom seat numbers high: {e}")
            hui["h_seats_cust_nums_high"] = 10

        return hui

    def get_import_parameters(self):
        imp = {}

        try:
            imp["callFpdbHud"] = self.imp.callFpdbHud
        except AttributeError as e:
            log.error(f"Error getting 'callFpdbHud': {e}")
            imp["callFpdbHud"] = True

        try:
            imp["interval"] = self.imp.interval
        except AttributeError as e:
            log.error(f"Error getting 'interval': {e}")
            imp["interval"] = 10

        # Use if instead of try/except for ResultsDirectory
        if self.imp.ResultsDirectory != "":
            imp["ResultsDirectory"] = self.imp.ResultsDirectory
        else:
            imp["ResultsDirectory"] = "~/.fpdb/Results/"

        try:
            imp["hhBulkPath"] = self.imp.hhBulkPath
        except AttributeError as e:
            log.error(f"Error getting 'hhBulkPath': {e}")
            imp["hhBulkPath"] = ""

        try:
            imp["saveActions"] = self.imp.saveActions
        except AttributeError as e:
            log.error(f"Error getting 'saveActions': {e}")
            imp["saveActions"] = False

        try:
            imp["cacheSessions"] = self.imp.cacheSessions
        except AttributeError as e:
            log.error(f"Error getting 'cacheSessions': {e}")
            imp["cacheSessions"] = False

        try:
            imp["publicDB"] = self.imp.publicDB
        except AttributeError as e:
            log.error(f"Error getting 'publicDB': {e}")
            imp["publicDB"] = False

        try:
            imp["sessionTimeout"] = self.imp.sessionTimeout
        except AttributeError as e:
            log.error(f"Error getting 'sessionTimeout': {e}")
            imp["sessionTimeout"] = 30

        try:
            imp["saveStarsHH"] = self.imp.saveStarsHH
        except AttributeError as e:
            log.error(f"Error getting 'saveStarsHH': {e}")
            imp["saveStarsHH"] = False

        try:
            imp["fastStoreHudCache"] = self.imp.fastStoreHudCache
        except AttributeError as e:
            log.error(f"Error getting 'fastStoreHudCache': {e}")
            imp["fastStoreHudCache"] = False

        try:
            imp["importFilters"] = self.imp.importFilters
        except AttributeError as e:
            log.error(f"Error getting 'importFilters': {e}")
            imp["importFilters"] = []

        try:
            imp["timezone"] = self.imp.timezone
        except AttributeError as e:
            log.error(f"Error getting 'timezone': {e}")
            imp["timezone"] = "America/New_York"

        return imp

    def set_timezone(self, timezone):
        self.imp.timezone = timezone

    def get_default_paths(self, site=None):
        if site is None:
            site = self.getDefaultSite()
        paths = {}
        try:
            path = os.path.expanduser(self.supported_sites[site].HH_path)
            assert os.path.isdir(path) or os.path.isfile(path)  # maybe it should try another site?
            paths["hud-defaultPath"] = paths["bulkImport-defaultPath"] = path
            if self.imp.hhBulkPath:
                paths["bulkImport-defaultPath"] = self.imp.hhBulkPath
            if self.supported_sites[site].TS_path != "":
                tspath = os.path.expanduser(self.supported_sites[site].TS_path)
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
            log.error(f"Error retrieving layout set locations for set='{set}', max='{max}': {e}")
            locations = (
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
            )
        return locations

    def get_supported_sites(self, all=False):
        """Returns the list of supported sites."""
        if all:
            return list(self.supported_sites.keys())
        else:
            return [site_name for (site_name, site) in list(self.supported_sites.items()) if site.enabled]

    def get_site_parameters(self, site):
        """Returns a dict of the site parameters for the specified site"""
        parms = {}
        parms["converter"] = self.hhcs[site].converter
        parms["summaryImporter"] = self.hhcs[site].summaryImporter
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
        elif "all" in site_layouts:
            return self.layout_sets[site_layouts["all"]]
        else:
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

    def set_general(self, lang=None):
        for general_node in self.doc.getElementsByTagName("general"):
            if lang:
                general_node.setAttribute("ui_language", lang)

    def set_site_ids(self, sites):
        self.site_ids = dict(sites)

    def get_site_id(self, site):
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

    def get_supported_games_parameters(self, name, game_type):
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

            game_stat_set = getattr(self.supported_games[name], "game_stat_set")

            if game_type in game_stat_set:
                param["game_stat_set"] = self.stat_sets[game_stat_set[game_type].stat_set]
            elif "all" in game_stat_set:
                param["game_stat_set"] = self.stat_sets[game_stat_set["all"].stat_set]
            else:
                return None

            return param

        return None

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


if __name__ == "__main__":
    set_logfile("fpdb-log.txt")
    c = Config()

    print("\n----------- GENERAL -----------")
    print(c.general)

    print("\n----------- SUPPORTED SITES -----------")
    for s in list(c.supported_sites.keys()):
        print(c.supported_sites[s])

    print("\n----------- SUPPORTED GAMES -----------")
    for game in list(c.supported_games.keys()):
        print(c.supported_games[game])

    print("\n----------- SUPPORTED DATABASES -----------")
    for db in list(c.supported_databases.keys()):
        print(c.supported_databases[db])

    print("\n----------- AUX WINDOW FORMATS -----------")
    for w in list(c.aux_windows.keys()):
        print(c.aux_windows[w])

    print("\n----------- LAYOUT SETS FORMATS -----------")
    for w in list(c.layout_sets.keys()):
        print(c.layout_sets[w])

    print("\n----------- STAT SETS FORMATS -----------")
    for w in list(c.stat_sets.keys()):
        print(c.stat_sets[w])

    print("\n----------- HAND HISTORY CONVERTERS -----------")
    for w in list(c.hhcs.keys()):
        print(c.hhcs[w])

    print("\n----------- POPUP WINDOW FORMATS -----------")
    for w in list(c.popup_windows.keys()):
        print(c.popup_windows[w])

    print("\n-----------  DATABASE PARAMS -----------")
    print("db    = ", c.get_db_parameters())

    print("\n-----------  HUD PARAMS -----------")
    print("hud params =")
    for hud_param, value in list(c.get_hud_ui_parameters().items()):
        print(" %s = %s" % (hud_param, value))

    print("\n-----------  STARTUP PATH -----------")
    print("start up path = ", c.execution_path(""))

    print("\n-----------  GUI CASH STATS -----------")
    print("gui_cash_stats =", c.gui_cash_stats)

    print("\n----------- Heroes -----------")
    for s in list(c.supported_sites.keys()):
        print(c.supported_sites[s].screen_name)

    print("\n----------- ENVIRONMENT CONSTANTS -----------")
    print("Configuration.install_method {source,exe,app} =", INSTALL_METHOD)
    print("Configuration.fpdb_root_path =", FPDB_ROOT_PATH, type(FPDB_ROOT_PATH))
    print("Configuration.graphics_path =", GRAPHICS_PATH, type(GRAPHICS_PATH))
    print("Configuration.appdata_path =", APPDATA_PATH, type(APPDATA_PATH))
    print("Configuration.config_path =", CONFIG_PATH, type(CONFIG_PATH))
    print("Configuration.pyfpdb_path =", PYFPDB_PATH, type(PYFPDB_PATH))
    print("Configuration.os_family {Linux,Mac,XP,Win7} =", OS_FAMILY)
    print("Configuration.posix {True/False} =", POSIX)
    print("Configuration.python_version =", PYTHON_VERSION)
    print("\n\n----------- END OF CONFIG REPORT -----------")

    print("press enter to end")
    sys.stdin.readline()
