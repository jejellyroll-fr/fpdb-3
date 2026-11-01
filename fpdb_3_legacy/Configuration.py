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
import inspect
import json
import locale
import os
import platform
import re
import shutil
import sys
import traceback
import uuid
import xml.parsers.expat
from pathlib import Path
from stat import S_IMODE
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
from fpdb_3_legacy.config_common import LAYOUT_REFERENCE_TOLERANCE as LAYOUT_REFERENCE_TOLERANCE
from fpdb_3_legacy.config_common import LAYOUT_REFERENCE_UNDERHANG as LAYOUT_REFERENCE_UNDERHANG
from fpdb_3_legacy.config_common import layout_reference_fits as layout_reference_fits
from fpdb_3_legacy.config_common import normalizePath as normalizePath
from fpdb_3_legacy.config_common import string_to_bool as string_to_bool
from fpdb_3_legacy.config_databases import ConfigDatabasesMixin
from fpdb_3_legacy.config_databases import Database as Database
from fpdb_3_legacy.config_gui import ConfigGuiMixin
from fpdb_3_legacy.config_gui import General as General
from fpdb_3_legacy.config_gui import GUICashStats as GUICashStats
from fpdb_3_legacy.config_gui import GUITourStats as GUITourStats
from fpdb_3_legacy.config_hud_layouts import Aux_window as Aux_window
from fpdb_3_legacy.config_hud_layouts import ConfigHudLayoutsMixin
from fpdb_3_legacy.config_hud_layouts import Layout as Layout
from fpdb_3_legacy.config_hud_layouts import Layout_set as Layout_set
from fpdb_3_legacy.config_hud_layouts import Popup as Popup
from fpdb_3_legacy.config_hud_layouts import Stat as Stat
from fpdb_3_legacy.config_hud_layouts import Stat_sets as Stat_sets
from fpdb_3_legacy.config_hud_layouts import StatBlock as StatBlock
from fpdb_3_legacy.config_hud_layouts import parse_hud_panel_rules as parse_hud_panel_rules
from fpdb_3_legacy.config_hud_layouts import parse_hud_profile_rules as parse_hud_profile_rules
from fpdb_3_legacy.config_hud_ui import ConfigHudUiMixin
from fpdb_3_legacy.config_hud_ui import HudUI as HudUI
from fpdb_3_legacy.config_import import HHC as HHC
from fpdb_3_legacy.config_import import ConfigImportMixin
from fpdb_3_legacy.config_import import Import as Import
from fpdb_3_legacy.config_import import RawHands as RawHands
from fpdb_3_legacy.config_import import RawTourneys as RawTourneys
from fpdb_3_legacy.config_sites import DATA_SOURCES as DATA_SOURCES
from fpdb_3_legacy.config_sites import DataSource as DataSource
from fpdb_3_legacy.config_sites import Email as Email
from fpdb_3_legacy.config_sites import Game_stat_set as Game_stat_set
from fpdb_3_legacy.config_sites import HeroProfile as HeroProfile
from fpdb_3_legacy.config_sites import Site as Site
from fpdb_3_legacy.config_sites import Supported_games as Supported_games
from fpdb_3_legacy.disabled_sites import is_site_disabled
from fpdb_3_legacy.hud_profiles import HudProfileRule
from fpdb_3_legacy.loggingFpdb import get_logger

# config version is used to flag a warning at runtime if the users config is
#  out of date.
# Increment with shipped template changes; add an explicit migration when needed.
CONFIG_VERSION = 86
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
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if os.path.basename(exe_dir) == "MacOS":
        resources_dir = os.path.join(os.path.dirname(exe_dir), "Resources")
        if os.path.isdir(resources_dir):
            return resources_dir
    return exe_dir


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
        os.path.join(os.path.dirname(FPDB_ROOT_PATH), example_name),
        os.path.join(PYFPDB_PATH, example_name),
        os.path.join(os.path.dirname(PYFPDB_PATH), example_name),
    ]
    for candidate in candidates:
        normalized = candidate.replace("\\", "/")
        if os.path.exists(normalized):
            return normalized
    return os.path.join(CONFIG_PATH, example_name).replace("\\", "/")


# Parsed example configs, keyed by path -> ((mtime, size), document).
_EXAMPLE_DOC_CACHE: dict[str, tuple[tuple[float, int], Any]] = {}


def _parse_example_config(path: str) -> Any | None:
    """Return the parsed example config at ``path``, reusing an earlier parse.

    Every ``Config()`` used to parse the ~120 KB example twice -- once for
    ``add_missing_elements()`` and once for the AoF Omaha migration -- and a
    single popup that rebuilds several ``Config`` objects paid for it each
    time. The example ships with the application and only ever gets read
    (migrations import copies of its nodes into the user document), so one
    parse can serve every caller. The cache is keyed on the file's mtime and
    size so a replaced example -- an upgrade dropping a new file in place -- is
    picked up rather than served stale.

    Returns None when the file is missing or unparsable; callers treat that as
    "no example available" exactly as they did before.
    """
    if not path or not os.path.exists(path):
        return None

    try:
        stat = os.stat(path)
        stamp = (stat.st_mtime, stat.st_size)
    except OSError:
        return None

    cached = _EXAMPLE_DOC_CACHE.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    try:
        doc = defusedxml.minidom.parse(path)
    except XML_PARSE_ERRORS as e:
        log.exception(f"Error parsing example configuration file {path}. Exception: {e}")
        return None

    _EXAMPLE_DOC_CACHE[path] = (stamp, doc)
    return doc


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


########################################################################
# application wide consts

APPLICATION_NAME_SHORT = "fpdb"

#: What get_default_paths() returns when the default site's hand-history path
#: exists nowhere. It is a message, not a folder: never import from it (#662).
MISSING_DEFAULT_PATH = "** ERROR DEFAULT PATH IN CONFIG DOES NOT EXIST **"

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


# Entain France skins that left the PartyPoker network for iPoker in 2026.
# Old user configs still declare them with network="PartyPoker" and the
# PartyPoker converter; Config.__init__ migrates such entries in place.
ENTAIN_FR_IPOKER_SITES = ("Bwin.fr Poker", "PartyPoker.fr")

# Windows data directories of the new Entain France iPoker clients, used to
# repoint HH_path/TS_path during the migration (client/data/<account>/History).
ENTAIN_FR_WINDOWS_DATA_DIRS: dict[str, tuple[str, ...]] = {
    "Bwin.fr Poker": ("bwin Poker France",),
}


def _replace_with(path: str, data: bytes, *, permissions_of: str | None = None) -> None:
    """Make ``path`` hold ``data``, or leave it exactly as it was if anything fails.

    The file gets the permissions of ``permissions_of`` (``path`` itself when
    None) if that file exists, and the umask's otherwise. They are set before a
    byte is written: a configuration holds database passwords, and a 0600 one
    must not pass through a readable copy -- its backup included.
    """
    # A configuration linked from elsewhere is written where the link points,
    # so the link itself survives.
    target = Path(os.path.realpath(path))
    model = Path(os.path.realpath(permissions_of)) if permissions_of else target
    mode = S_IMODE(model.stat().st_mode) if model.exists() else None
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex[:12]}.tmp")
    # Without a model, created as open() would create it (the umask decides),
    # not owner-only as mkstemp would: a file saved under a new name keeps the
    # usual permissions.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(temporary, flags, 0o600 if mode is not None else 0o666)
    try:
        if mode is not None and hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None and not hasattr(os, "fchmod"):
            os.chmod(temporary, mode)  # Windows: only the read-only flag
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Config(
    ConfigHudLayoutsMixin,
    ConfigDatabasesMixin,
    ConfigHudUiMixin,
    ConfigImportMixin,
    ConfigGuiMixin,
):
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
        self.data_sources: dict[str, DataSource] = {}
        self.supported_games: dict[str, Supported_games] = {}
        self.supported_databases: dict[str, Database] = {}
        self.aux_windows: dict[str, Aux_window] = {}
        self.layout_sets: dict[str, Layout_set] = {}
        self.stat_sets: dict[str, Any] = {}
        self.hhcs: dict[str, Any] = {}
        self.popup_windows: dict[str, Any] = {}
        self.hud_profile_rules: list[HudProfileRule] = []
        # Context-aware dynamic HUD panels (#298). Empty and disabled by
        # default: the static grid is what a configuration without a
        # <hud_panel_rules> section gets, and that is the shipped default.
        self.hud_panel_rules: list[Any] = []
        self.hud_panel_fallback: str = ""
        self.hud_panel_rules_enabled: bool = False
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

        from fpdb_3_legacy.config_migrations import reference_errors

        self.config_reference_errors = reference_errors(doc)
        for error in self.config_reference_errors:
            log.warning("Configuration %s: %s", self.file, error)

        #        s_sites = doc.getElementsByTagName("supported_sites")
        for site_node in doc.getElementsByTagName("site"):
            site = Site(node=site_node)
            self.supported_sites[site.site_name] = site

        # Multiroom hero profiles (optional <hero_profiles> section).
        for hp_node in doc.getElementsByTagName("hero_profile"):
            hp = HeroProfile(node=hp_node)
            if hp.name:
                self.hero_profiles[hp.name] = hp

        # Data source hero identities (optional <data_sources> section, #423).
        for ds_node in doc.getElementsByTagName("data_source"):
            source = DataSource(node=ds_node)
            if source.name:
                self.data_sources[source.name] = source

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
        self.hud_panel_rules, self.hud_panel_fallback, self.hud_panel_rules_enabled = parse_hud_panel_rules(doc)

        #     s_dbs = doc.getElementsByTagName("mucked_windows")
        for hhc_node in doc.getElementsByTagName("hhc"):
            hhc = HHC(node=hhc_node)
            # Without a converter binding, IdentifySite never builds a parser
            # for the room, so bulk/auto import stops recognising its files.
            if is_site_disabled(hhc.site):
                continue
            self.hhcs[hhc.site] = hhc

        #        s_dbs = doc.getElementsByTagName("popup_windows")
        for pu_node in doc.getElementsByTagName("pu"):
            pu = Popup(node=pu_node)
            self.popup_windows[pu.name] = pu

        # The shipped popup packs (#299) are additive: they never replace a
        # popup this file defines, so a broken pack library cannot leave the
        # user without a popup.
        self.install_popup_packs()

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

    def upgrade_config(self) -> str:
        """Upgrade against the bundled template, preserving personal settings."""
        from fpdb_3_legacy.config_migrations import upgrade_document, write_upgrade

        source = _find_example_config("HUD_config.xml")
        template = _parse_example_config(source)
        if template is None:
            raise ValueError(f"Cannot read configuration template {source}")
        candidate = upgrade_document(self.doc, template, CONFIG_VERSION)
        backup = write_upgrade(self.file, candidate)
        log.warning("Configuration upgraded to %s; backup: %s", CONFIG_VERSION, backup)
        return backup

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
            if not os.path.exists(source_path):
                log.info("Example config file %s not found, skipping AoF Omaha HUD migration", source_path)
                return False
            source_doc = _parse_example_config(source_path)
            if source_doc is None:
                log.warning("Could not read the shipped AoF Omaha HUD profile from %s", source_path)
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

        if not example_file or not os.path.exists(example_file):
            log.info(f"Example configuration file {example_file} not found. Skipping missing elements addition.")
            return nodes_added

        example_doc = _parse_example_config(example_file)
        if example_doc is None:
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
                            if example_node.localName == "general":
                                # Adding defaults is not a schema migration.
                                new.setAttribute("version", "0")
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

            # Hero identities: multiroom profiles and data sources (#423). Read here
            # too, or a reload kept the identities the file no longer holds.
            hero_profiles = {}
            for hp_node in doc.getElementsByTagName("hero_profile"):
                hp = HeroProfile(node=hp_node)
                if hp.name:
                    hero_profiles[hp.name] = hp
            data_sources = {}
            for ds_node in doc.getElementsByTagName("data_source"):
                source = DataSource(node=ds_node)
                if source.name:
                    data_sources[source.name] = source

            # Profile selection rules
            hud_profile_rules = parse_hud_profile_rules(doc)

            # Context-aware dynamic panel rules (#298)
            hud_panel_rules, hud_panel_fallback, hud_panel_rules_enabled = parse_hud_panel_rules(doc)

            # HHCs (disabled rooms keep no converter binding -- see the
            # matching skip in the initial load)
            for hhc_node in doc.getElementsByTagName("hhc"):
                hhc = HHC(node=hhc_node)
                if is_site_disabled(hhc.site):
                    continue
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
        self.hero_profiles = hero_profiles
        self.data_sources = data_sources
        self.supported_games = supported_games
        self.supported_databases = supported_databases
        self.db_selected = db_selected
        self.aux_windows = aux_windows
        self.layout_sets = layout_sets
        self.stat_sets = stat_sets
        self.hud_profile_rules = hud_profile_rules
        self.hud_panel_rules = hud_panel_rules
        self.hud_panel_fallback = hud_panel_fallback
        self.hud_panel_rules_enabled = hud_panel_rules_enabled
        self.hhcs = hhcs
        self.popup_windows = popup_windows
        # The packs are re-installed onto the freshly parsed registry, so a
        # reload is not a way to lose them.
        self.pack_popups: dict[str, str] = {}
        self.install_popup_packs()
        if imp is not None:
            self.imp = imp
        if ui is not None:
            self.ui = ui

        log.info("Configuration reloaded successfully")
        return True

    def save(self, file=None) -> None:
        """Write the configuration so that a failed save leaves the previous file whole (#642).

        The new content goes to a temporary file beside the target, reaches the
        disk, and only then replaces the target in one step. Saving fpdb's own
        file first copies it to ``.backup``; the file itself is never moved away.
        """
        if file is None:
            file = self.file
            try:
                _replace_with(f"{file}.backup", Path(file).read_bytes(), permissions_of=file)
            except OSError as e:
                log.exception(f"Failed to copy file {file} to backup. Exception: {e}")

        _replace_with(file, self.wrap_long_lines(self.doc.toxml()).encode("utf-8"))

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
            paths["hud-defaultPath"] = paths["bulkImport-defaultPath"] = MISSING_DEFAULT_PATH
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


    def execution_path(self, filename):
        """Join the fpdb path to filename."""
        return os.path.join(os.path.dirname(inspect.getfile(sys._getframe(0))), filename)


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
