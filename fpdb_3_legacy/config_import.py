"""Hand-history import settings and the raw hand / tourney storage policies."""

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

from fpdb_3_legacy import config_xml as cx
from fpdb_3_legacy.config_common import (
    ConfigBase,
    string_to_bool,
)
from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("configuration")


class HHC:
    def __init__(self, node) -> None:
        # pylint: disable=invalid-name  # the attribute names are the HUD_config.xml ones, read by name elsewhere
        self.site = cx.attr(node, "site")
        self.converter = cx.attr(node, "converter")
        self.summaryImporter = cx.attr(node, "summaryImporter")

    def __str__(self) -> str:
        return f"{self.site}:\tconverter: '{self.converter}' summaryImporter: '{self.summaryImporter}'"


class Import:
    def __init__(self, node) -> None:
        # pylint: disable=invalid-name  # the attribute names are the HUD_config.xml ones, read by name elsewhere
        self.node = node
        self.interval = cx.attr(node, "interval")
        self.sessionTimeout = string_to_bool(cx.attr(node, "sessionTimeout"), default=30)
        self.ResultsDirectory = cx.attr(node, "ResultsDirectory")
        self.hhBulkPath = cx.attr(node, "hhBulkPath")
        self.saveActions = string_to_bool(cx.attr(node, "saveActions"), default=False)
        self.cacheSessions = string_to_bool(cx.attr(node, "cacheSessions"), default=False)
        self.publicDB = string_to_bool(cx.attr(node, "publicDB"), default=False)
        self.callFpdbHud = string_to_bool(cx.attr(node, "callFpdbHud"), default=False)
        self.fastStoreHudCache = string_to_bool(cx.attr(node, "fastStoreHudCache"), default=False)
        self.saveStarsHH = string_to_bool(cx.attr(node, "saveStarsHH"), default=False)
        if cx.attr(node, "importFilters"):
            self.importFilters = cx.attr(node, "importFilters").split(",")
        else:
            self.importFilters = []
        if cx.attr(node, "timezone"):
            self.timezone = cx.attr(node, "timezone")
        else:
            self.timezone = "America/New_York"

    def __str__(self) -> str:
        return f"    interval = {self.interval}\n    callFpdbHud = {self.callFpdbHud}\n    saveActions = {self.saveActions}\n   cacheSessions = {self.cacheSessions}\n    publicDB = {self.publicDB}\n    sessionTimeout = {self.sessionTimeout}\n    fastStoreHudCache = {self.fastStoreHudCache}\n    ResultsDirectory = {self.ResultsDirectory}"


class RawHands:
    def __init__(self, node=None) -> None:
        if node is None:
            self.save = "error"
            self.compression = "none"
            # print ("missing config section raw_hands")
        else:
            save = cx.attr(node, "save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                log.warning(f"Invalid raw_hands save value {save!r}, defaulting to error")
                self.save = "error"

            compression = cx.attr(node, "compression")
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
            save = cx.attr(node, "save")
            if save in ("none", "error", "all"):
                self.save = save
            else:
                log.warning(f"Invalid raw_tourneys save value {save!r}, defaulting to error")
                self.save = "error"

            compression = cx.attr(node, "compression")
            if compression in ("none", "gzip", "bzip2"):
                self.compression = compression
            else:
                log.warning(f"Invalid raw_tourneys compression value {compression!r}, defaulting to none")
                self.compression = "none"

    # end def __init__

    def __str__(self) -> str:
        return f"        save= {self.save}, compression= {self.compression}\n"


# end class RawTourneys


class ConfigImportMixin(ConfigBase):
    """Read and edit the import settings."""

    # end def editStats
    def editImportFilters(self, games) -> None:
        self.imp.importFilters = games
        imp_node = cx.find_all(self.doc, "import")[-1]
        cx.set_attr(imp_node, "importFilters", games)

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
