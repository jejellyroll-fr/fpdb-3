#!/usr/bin/env python
from __future__ import annotations

# Copyright 2010-2011 Chaz Littlejohn
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# In the "official" distribution you can find the license in agpl-3.0.txt.
import codecs
import copy
import os
import re
import sys
from collections.abc import Mapping
from time import time
from types import MappingProxyType
from typing import Any

from fpdb_3_legacy import Configuration, ipoker_rooms
from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter, unpack_sqlite_hand_history
from fpdb_3_legacy.import_failure_cache import FailureCache, is_sidecar_file
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.parser_registry import (
    LEGACY_MODULE_REGISTRY as LEGACY_MODULE_REGISTRY,
)
from fpdb_3_legacy.parser_registry import (
    get_parser_class,
    get_summary_class,
)
from fpdb_3_legacy.parser_registry import (
    import_fpdb_module as import_fpdb_module,
)

# import L10n
# _ = L10n.get_translation()


try:
    import xlrd
except ImportError:
    xlrd = None
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("identify_site")

IDENTIFY_SITE_IMPORT_ERRORS = (AttributeError, ImportError, TypeError, ValueError)
IDENTIFY_SITE_DECODE_ERRORS = (UnicodeDecodeError,)

re_Divider, re_Head, re_XLS = {}, {}, {}
re_Divider["PokerStars"] = re.compile(r"^Hand #(\d+)\s*$", re.MULTILINE)
re_Divider["Fulltilt"] = re.compile(r"\*{20}\s#\s\d+\s\*{15,25}\s?", re.MULTILINE)
re_Head["Fulltilt"] = re.compile(r"^((BEGIN)?\n)?FullTiltPoker.+\n\nSeat", re.MULTILINE)
re_XLS["PokerStars"] = re.compile(r"Tournaments\splayed\sby\s\'.+?\'")
re_XLS["Fulltilt"] = re.compile(r"Player\sTournament\sReport\sfor\s.+?\s\(.*\)")
re_iPokerNickname = re.compile(r"<nickname>([^<]+)</nickname>")


class FPDBFile:
    def __init__(self, path: str) -> None:
        self.path = path
        self.ftype: str | None = None  # Valid: hh, summary, both
        self.site: Site | None = None
        self.kodec: str | None = None
        self.archive = False
        self.archiveHead = False
        self.archiveDivider = False
        self.gametype: object = False
        self.hero = "-"
        self.fileId: int | None = None
        self.undecided_hero: str | None = None  # an iPoker hero whose room only the user can tell (#702)


class Site:
    def __init__(
        self,
        name: str,
        hhc_fname: str,
        hhc_type: str,
        summary: str | None,
        obj: type[HandHistoryConverter],
    ) -> None:
        self.name = name
        self.hhc_fname = hhc_fname
        self.hhc_type = hhc_type
        self.re_SplitHands = getattr(obj, "re_split_hands", getattr(obj, "re_SplitHands", None))
        self.codepage = obj.codepage
        self.copyGameHeader = obj.copyGameHeader
        self.summaryInFile = obj.summaryInFile
        self.re_Identify = getattr(obj, "re_identify", getattr(obj, "re_Identify", None))
        self.re_SumIdentify: re.Pattern[str] | None = None
        self.re_HeroCards: re.Pattern[str] | None = None
        self.re_HeroCards1: re.Pattern[str] | None = None
        self.re_HeroCards2: re.Pattern[str] | None = None
        self.summary: str | None = summary
        # self.obj            = obj
        if summary:
            sum_class = get_summary_class(summary)
            self.re_SumIdentify = (
                getattr(sum_class, "re_identify", getattr(sum_class, "re_Identify", None)) if sum_class else None
            )
        self.line_delimiter = self.getDelimiter(hhc_type)
        self.line_addendum = self.getAddendum(hhc_type)
        self.spaces = hhc_type == "Entraction"
        self.getHeroRegex(obj, hhc_type)

    @property
    def filter_name(self) -> str:
        """Return the legacy parser-type attribute used by older callers."""
        return self.hhc_type

    @filter_name.setter
    def filter_name(self, value: str) -> None:
        """Keep legacy assignments synchronized with the canonical field."""
        self.hhc_type = value

    def getDelimiter(self, filter_name: str) -> str | None:
        line_delimiter = None
        if filter_name == "PokerStars":
            line_delimiter = "\n\n"
        elif filter_name in ("Fulltilt", "PokerTracker"):
            line_delimiter = "\n\n\n"
        elif self.re_SplitHands is not None and self.re_SplitHands.match("\n\n") and filter_name != "Entraction":
            line_delimiter = "\n\n"
        elif self.re_SplitHands is not None and self.re_SplitHands.match("\n\n\n"):
            line_delimiter = "\n\n\n"

        return line_delimiter

    def getAddendum(self, filter_name: str) -> str:
        line_addendum = ""
        if filter_name == "OnGame":
            line_addendum = "*"
        elif filter_name == "Merge":
            line_addendum = "<"
        elif filter_name == "Entraction":
            line_addendum = "\n\n"

        return line_addendum

    def getHeroRegex(self, obj: type[HandHistoryConverter], filter_name: str) -> None:
        if hasattr(obj, "re_hero_cards") and filter_name not in ("Bovada", "Enet"):
            self.re_HeroCards = obj.re_hero_cards
        elif hasattr(obj, "re_HeroCards") and filter_name not in ("Bovada", "Enet"):
            self.re_HeroCards = obj.re_HeroCards
        if filter_name == "PokerTracker":
            self.re_HeroCards1 = getattr(obj, "re_HeroCards1", None)
            self.re_HeroCards2 = getattr(obj, "re_HeroCards2", None)


class IdentifySite:
    # The room the user chose for each iPoker hero nothing else could place (#702).
    chosen_ipoker_rooms: Mapping[str, str] = MappingProxyType({})

    def __init__(self, config: Any, hhcs: Any = None) -> None:
        self.config = config
        self.codepage = ("utf8", "cp1252", "ISO-8859-1")
        self.sitelist: dict[int | None, Site] = {}
        self.filelist: dict[str | bytes, FPDBFile] = {}
        self.failed_files = FailureCache()
        self.re_Identify_PT: re.Pattern[str] | None = None
        self.re_SumIdentify_PT: re.Pattern[str] | None = None
        self.generateSiteList(hhcs)

    def identification_failed(self, path) -> bool:
        """True if `path` already failed and has not been written to since."""
        return self.failed_files.failed(path)

    def remember_failure(self, path) -> None:
        """Record that `path` failed as it currently stands."""
        self.failed_files.remember(path)

    def _select_pokerstars_skin_site(self, path, whole_file, fallback_site):
        """Return the configured PokerStars skin site for this file."""
        from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

        ps = PokerStars(self.config, in_path=path, autostart=False)
        skin_name, _skin_id = ps.detectPokerStarsSkin(whole_file, path)

        for _sid, site in list(self.sitelist.items()):
            if site.name == skin_name:
                return site
        if skin_name != fallback_site.name:
            skin_site = copy.copy(fallback_site)
            skin_site.name = skin_name
            return skin_site
        return fallback_site

    def _select_winning_skin_site(self, path, fallback_site):
        """Return the configured WinningPoker (WPN) skin site for this file.

        All WPN skins (Americas Cardroom, ACR Poker, WinningPoker,
        BlackChipPoker, TruePoker, Ya Poker) share the same parser class and
        ``siteId = 24``, so only one survives keyed by ``site_id`` in
        ``self.sitelist``. The hand-history content carries no skin marker, so
        the skin is resolved from the configured HH/TS paths, falling back to
        whichever single WPN skin the user has enabled.
        """
        return self._select_network_skin_site(path, fallback_site, "WinningPoker")

    def choose_ipoker_rooms(self, rooms: Mapping[str, str]) -> None:
        """File each of these iPoker heroes under the room the user chose for them.

        Files already identified were placed without these answers, so they are forgotten.
        """
        self.chosen_ipoker_rooms = dict(rooms)
        self.clear_filelist()

    def _select_ipoker_skin_site(self, path, fallback_site, whole_file=""):
        """Return the configured iPoker skin site for this file.

        All iPoker skins share the iPoker parser class, so only one survives
        keyed by ``site_id`` in ``self.sitelist`` and the surviving name is
        arbitrary (whichever <hhc> came last in the config). The XML content
        carries no skin marker either, so resolve the skin from the
        configured HH/TS paths (PMU Poker, Bwin.fr Poker, ... each watch
        their own client directory), then from the hero the file names: an
        archive such as PokerTracker's sits outside every configured path.
        A file nothing places stays on the network rather than in a room picked
        for being first.
        """
        room = ipoker_rooms.room_for(self.config, self._ipoker_xml_hero(whole_file), self.chosen_ipoker_rooms)
        return self._select_network_skin_site(
            path,
            fallback_site,
            "iPoker",
            preferred=room or ipoker_rooms.GENERIC_ROOM,
        )

    @staticmethod
    def _ipoker_xml_hero(whole_file: str) -> list[str]:
        match = re_iPokerNickname.search(whole_file)
        return [match.group(1)] if match else []

    def _undecided_ipoker_hero(self, path: str, whole_file: str) -> str | None:
        """The hero of an iPoker XML file whose room only the user can tell, if it is one."""
        heroes = self._ipoker_xml_hero(whole_file)
        if not heroes or ipoker_rooms.room_for(self.config, heroes, self.chosen_ipoker_rooms):
            return None
        norm_path = os.path.normcase(os.path.abspath(path))
        supported = getattr(self.config, "supported_sites", None) or {}
        for site in supported.values():
            if getattr(site, "network", "") == "iPoker" and self._configured_path_length(site, norm_path) >= 0:
                return None
        return heroes[0]

    def _name_ipoker_export(self, f: FPDBFile, whole_file: str, hero_regex: Any) -> str:
        """Name the room of a PokerTracker ``GAME #`` file, noting a hero only the user can place."""
        match = hero_regex.search(whole_file) if hero_regex is not None else None
        hero = match.group("PNAME") if match else None
        room = ipoker_rooms.room_for(self.config, [hero] if hero else [], self.chosen_ipoker_rooms)
        if room is None:
            f.undecided_hero = hero
            return ipoker_rooms.GENERIC_ROOM
        return room

    def _select_partypoker_skin_site(self, path, fallback_site):
        """Return the configured PartyPoker skin site for this file.

        Every Party skin (PartyPoker, the .fr/.it/.es/.de/.eu locales, Bwin,
        Borgata, WPT, PMU Poker (PartyPoker), ...) shares the PartyPoker parser
        class and its ``siteId = 9``, so only one survives keyed by ``site_id``
        in ``self.sitelist``: whichever ``<hhc>`` came last in the config, which
        has nothing to do with the room the file came from. The hand history
        carries no skin marker either -- its ``(SITE)`` header group names the
        network, not the skin -- so resolve the skin from the configured HH/TS
        paths like the other multi-skin networks do.
        """
        return self._select_network_skin_site(path, fallback_site, "PartyPoker")

    @staticmethod
    def _configured_path_length(site: Any, norm_path: str) -> int:
        """How long the configured HH/TS path holding this file is, or -1 if none holds it."""
        path_len = -1
        for cfg_path in (site.HH_path, site.TS_path):
            if not cfg_path:
                continue
            cfg_abs = os.path.normcase(os.path.abspath(os.path.expanduser(cfg_path)))
            if norm_path.startswith(cfg_abs):
                path_len = max(path_len, len(cfg_abs))
        return path_len

    def _best_network_skin(self, path, network):
        """The skin of a network best fitting this file, with whether a configured path holds it and it is enabled."""
        supported = getattr(self.config, "supported_sites", None) or {}
        norm_path = os.path.normcase(os.path.abspath(path))
        best_site, best_score = None, None
        for site in supported.values():
            if getattr(site, "network", "") != network:
                continue
            path_len = self._configured_path_length(site, norm_path)
            # Rank candidates: a file under a configured path beats non-matches,
            # an enabled skin beats a disabled one, and a longer (more specific)
            # configured path breaks remaining ties.
            score = (path_len >= 0, bool(site.enabled), path_len)
            if best_score is None or score > best_score:
                best_site, best_score = site, score
        if best_site is None or best_score is None:
            return None
        return best_site, best_score[0], best_score[1]

    @staticmethod
    def _site_named(fallback_site, name):
        if name == fallback_site.name:
            return fallback_site
        skin_site = copy.copy(fallback_site)
        skin_site.name = name
        return skin_site

    def _select_network_skin_site(self, path, fallback_site, network, preferred=None):
        """Resolve the skin site of a multi-skin network from the file path.

        ``preferred`` names the skin to use when no configured path holds the file.
        """
        best = self._best_network_skin(path, network)
        if best is None:
            return fallback_site
        site, matched_by_path, is_enabled = best
        if preferred and not matched_by_path:
            return self._site_named(fallback_site, preferred)
        # Nothing matched by path and nothing is enabled: keep the fallback
        # rather than silently renaming to an arbitrary skin.
        if not matched_by_path and not is_enabled:
            return fallback_site
        return self._site_named(fallback_site, site.site_name)

    def scan(self, path) -> None:
        if os.path.isdir(path):
            self.walkDirectory(path, self.sitelist)
        else:
            self.processFile(path)

    def get_fobj(self, file):
        if self.identification_failed(file):
            return False
        try:
            fobj = self.filelist[file]
        except KeyError:
            return False
        return fobj

    def get_filelist(self):
        return self.filelist

    def clear_filelist(self) -> None:
        self.filelist = {}
        self.failed_files = FailureCache()

    def generateSiteList(self, hhcs) -> None:
        """Generates a ordered dictionary of site, filter and filter name for each site in hhcs."""
        if not hhcs:
            hhcs = self.config.hhcs
        for site, hhc in list(hhcs.items()):
            filter = hhc.converter
            filter_name = filter.replace("ToFpdb", "")
            summary = hhc.summaryImporter
            try:
                obj = get_parser_class(filter_name)
                site_id = getattr(obj, "site_id", getattr(obj, "siteId", None))
                self.sitelist[site_id] = Site(
                    site,
                    filter,
                    filter_name,
                    summary,
                    obj,
                )
            except ModuleNotFoundError:
                log.warning(f"Could not find module {filter}, skipping.")
            except IDENTIFY_SITE_IMPORT_ERRORS as e:
                log.exception(f"Failed to load HH importer: {filter_name}. {e}")
        pt_class = get_parser_class("PokerTracker")
        self.re_Identify_PT = (
            getattr(pt_class, "re_identify", getattr(pt_class, "re_Identify", None)) if pt_class else None
        )
        pt_sum_class = get_summary_class("PokerTrackerSummary")
        self.re_SumIdentify_PT = (
            getattr(pt_sum_class, "re_identify", getattr(pt_sum_class, "re_Identify", None)) if pt_sum_class else None
        )

    def walkDirectory(self, dir, sitelist) -> None:
        """Walks a directory, and executes a callback on each file."""
        dir = os.path.abspath(dir)
        for file in [file for file in os.listdir(dir) if not file in [".", ".."]]:
            nfile = os.path.join(dir, file)
            if os.path.isdir(nfile):
                self.walkDirectory(nfile, sitelist)
            else:
                self.processFile(nfile)

    def __listof(self, x):
        if isinstance(x, (list, tuple)):
            return x
        return [x]

    def processFile(self, path) -> None:
        log.debug(f"process fill identify {path}")
        if path in self.filelist or self.identification_failed(path):
            return

        log.debug(f"filelist {self.filelist}")
        whole_file, kodec = self.read_file(path)
        # log.debug('whole_file',whole_file)
        log.debug(f"kodec {kodec}")
        if not whole_file:
            # Empty or unreadable: the poker client creates the history file when
            # a table opens and only writes the first hand later, so this is a
            # file that has not been written yet, not one that never will be.
            # Recording the signature means the next poll re-reads it as soon as
            # anything lands in it, without re-reading an unchanged one.
            self.remember_failure(path)
            return

        fobj = self.idSite(path, whole_file, kodec)
        log.debug(f"siteid obj {fobj}")
        # print(fobj.path)
        if fobj is False:  # Site id failed
            log.debug(f"siteId Failed for: {path}")
            self.remember_failure(path)
        else:
            self.filelist[path] = fobj

    def read_file(self, in_path):
        # System leftovers and the regression corpus' reference data are not
        # hand histories. Logged at debug: they are expected in a watched
        # directory, and shouting about them is the noise this set out to fix.
        if is_sidecar_file(in_path):
            log.debug(f"Skipping system or sidecar file {in_path}")
            return None, None

        # Excel file management if xlrd is available
        if (in_path.endswith((".xls", ".xlsx"))) and xlrd:
            try:
                wb = xlrd.open_workbook(in_path)
                sh = wb.sheet_by_index(0)
                header = str(sh.cell(0, 0).value)
                return header, "utf-8"
            except (OSError, xlrd.XLRDError) as e:
                log.exception(f"Error reading Excel file {in_path}: {e}")
                return None, None

        # Check for the presence of a BOM for UTF-16
        try:
            with open(in_path, "rb") as infile:
                raw_data = infile.read()

            unpacked = unpack_sqlite_hand_history(in_path, raw_data)
            if unpacked is not None:
                return unpacked, "utf-8"

            # If the file begins with a UTF-16 BOM (little endian or big endian)
            if raw_data.startswith((b"\xff\xfe", b"\xfe\xff")):
                if len(raw_data) % 2:
                    # A UTF-16 code unit is two bytes, so an odd length means a
                    # stray byte was appended (typically a lone "\n" added by a
                    # tool that treated the file as 8-bit). Dropping it is
                    # lossless and avoids a scary decode warning on files that
                    # are otherwise perfectly readable.
                    log.debug("Dropping stray trailing byte of UTF-16 file %s", in_path)
                    raw_data = raw_data[:-1]
                try:
                    whole_file = raw_data.decode("utf-16")
                    return whole_file, "utf-16"
                except UnicodeDecodeError as e:
                    log.warning(f"Strict UTF-16 decoding failed for {in_path} (trying with errors='replace'): {e}")
                    try:
                        whole_file = raw_data.decode("utf-16", errors="replace")
                        return whole_file, "utf-16"
                    except IDENTIFY_SITE_DECODE_ERRORS as e2:
                        log.warning(f"Fallback UTF-16 decoding failed for {in_path}: {e2}")
        except OSError as e:
            log.exception(f"Error reading file {in_path}: {e}")
            return None, None

        # Try different encodings in the `self.codepage` list
        for kodec in self.codepage:
            try:
                with codecs.open(in_path, "r", kodec) as infile:
                    whole_file = infile.read()
                    return whole_file, kodec
            except (OSError, UnicodeDecodeError) as e:
                log.warning(f"Failed to read file {in_path} with codec {kodec}: {e}")
                continue

        log.error(f"Unable to read file {in_path} with any known codecs.")
        return None, None

    def idSite(self, path, whole_file, kodec):
        """Identifies the site the hh file originated from."""
        f = FPDBFile(path)
        f.kodec = kodec
        # DEBUG:print('idsite path',path )
        # DEBUG:print('idsite f',f,f.ftype,f.site,f.gametype )

        # SwC hands look like "SwCPoker Hand #..." and are currently mis-identified as GGPoker
        first_chunk = whole_file[:5000]
        if "SwCPoker Hand #" in first_chunk or "SwCPoker Hand" in first_chunk:
            for _sid, site in list(self.sitelist.items()):
                if site.name == "SealsWithClubs":
                    f.site = site
                    f.ftype = "hh"
                    if site.re_HeroCards:
                        h = site.re_HeroCards.search(first_chunk)
                        if h and "PNAME" in h.groupdict():
                            f.hero = h.group("PNAME")
                    else:
                        f.hero = "Hero"
                    return f

        # DEBUG:print('idsite self.sitelist.items',self.sitelist.items())
        for _id, site in list(self.sitelist.items()):
            filter_name = site.filter_name
            m = site.re_Identify.search(first_chunk) if site.re_Identify is not None else None
            if m and filter_name in ("Fulltilt", "PokerStars"):
                m1 = re_Divider[filter_name].search(whole_file.replace("\r\n", "\n"))
                if m1:
                    f.archive = True
                    f.archiveDivider = True
            elif re_Head.get(filter_name) and re_Head[filter_name].match(
                whole_file[:5000].replace("\r\n", "\n"),
            ):
                f.archive = True
                f.archiveHead = True
            if m:
                # For PokerStars, WPN, iPoker and Party, we need to determine the specific skin
                if filter_name == "PokerStars":
                    selected_site = self._select_pokerstars_skin_site(path, whole_file, site)
                elif filter_name == "Winning":
                    selected_site = self._select_winning_skin_site(path, site)
                elif filter_name == "iPoker":
                    selected_site = self._select_ipoker_skin_site(path, site, whole_file)
                    f.undecided_hero = self._undecided_ipoker_hero(path, whole_file)
                elif filter_name == "PartyPoker":
                    selected_site = self._select_partypoker_skin_site(path, site)
                else:
                    selected_site = site
                f.site = selected_site

                f.ftype = "hh"
                if selected_site.re_HeroCards:
                    h = selected_site.re_HeroCards.search(whole_file[:5000])
                    if h and "PNAME" in h.groupdict():
                        f.hero = h.group("PNAME")
                else:
                    f.hero = "Hero"
                return f

        for _id, site in list(self.sitelist.items()):
            if site.summary:
                if path.endswith((".xls", ".xlsx")):
                    filter_name = site.filter_name
                    if filter_name in ("Fulltilt", "PokerStars"):
                        m2 = re_XLS[filter_name].search(whole_file[:5000])
                        if m2:
                            f.site = site
                            f.ftype = "summary"
                            return f
                else:
                    m3 = site.re_SumIdentify.search(whole_file[:10000]) if site.re_SumIdentify is not None else None
                    if m3:
                        if site.filter_name == "PokerStars":
                            f.site = self._select_pokerstars_skin_site(path, whole_file, site)
                        elif site.filter_name == "Winning":
                            f.site = self._select_winning_skin_site(path, site)
                        elif site.filter_name == "iPoker":
                            f.site = self._select_ipoker_skin_site(path, site, whole_file)
                            f.undecided_hero = self._undecided_ipoker_hero(path, whole_file)
                        elif site.filter_name == "PartyPoker":
                            f.site = self._select_partypoker_skin_site(path, site)
                        else:
                            f.site = site
                        f.ftype = "summary"
                        return f

        m1 = self.re_Identify_PT.search(whole_file[:5000]) if self.re_Identify_PT is not None else None
        m2 = self.re_SumIdentify_PT.search(whole_file[:100]) if self.re_SumIdentify_PT is not None else None
        if m1 or m2:
            filter = "PokerTrackerToFpdb"
            filter_name = "PokerTracker"
            obj = get_parser_class(filter_name)
            summary = "PokerTrackerSummary"

            detected_site_name = "PokerTracker"  # default
            if m1 and m1.group().startswith("GAME #"):
                detected_site_name = self._name_ipoker_export(f, whole_file, getattr(obj, "re_HeroCards1", None))
                log.debug(f"Room of a PokerTracker iPoker file: {detected_site_name}")
            elif m1 and "GAME #" in m1.group():
                # Merge's "MERGE_GAME #": the parser reads the room from the hand header.
                detected_site_name = ipoker_rooms.GENERIC_ROOM
            elif not m1:
                # PokerTracker is the format: the summary itself names its room,
                # down to the network for iPoker, whose players tell the skin.
                from fpdb_3_legacy.PokerTrackerSummary import PokerTrackerSummary

                detected_site_name = PokerTrackerSummary.room_named_in(whole_file[:200]) or detected_site_name
                if detected_site_name == ipoker_rooms.GENERIC_ROOM:
                    detected_site_name = (
                        ipoker_rooms.room_for(
                            self.config,
                            PokerTrackerSummary.players_named_in(whole_file),
                            self.chosen_ipoker_rooms,
                        )
                        or detected_site_name
                    )

            pt_site = Site(detected_site_name, filter, filter_name, summary, obj)
            f.site = pt_site
            if m1:
                f.ftype = "hh"
                if re.search(r"\*{2}\sGame\sID\s", m1.group()):
                    pt_site.line_delimiter = None
                    pt_site.re_SplitHands = re.compile(r"End\sof\sgame\s\d+")
                elif re.search(r"\*{2}\sHand\s\#\s", m1.group()):
                    pt_site.line_delimiter = None
                    pt_site.re_SplitHands = re.compile(r"Rake:\s[^\s]+")
                elif re.search(r"Server\spoker\d+\.ipoker\.com", whole_file[:250]):
                    pt_site.line_delimiter = None
                    pt_site.spaces = True
                    pt_site.re_SplitHands = re.compile(r"GAME\s\#")
                m3 = pt_site.re_HeroCards1.search(whole_file[:5000]) if pt_site.re_HeroCards1 is not None else None
                if m3:
                    f.hero = m3.group("PNAME")
                else:
                    m4 = pt_site.re_HeroCards2.search(whole_file[:5000]) if pt_site.re_HeroCards2 is not None else None
                    if m4:
                        f.hero = m4.group("PNAME")
            else:
                f.ftype = "summary"
            return f

        return False

    def getFilesForSite(self, sitename, ftype):
        files_for_site = []
        for _name, f in list(self.filelist.items()):
            if f.ftype is not None and f.site is not None and f.site.name == sitename and f.ftype == "hh":
                files_for_site.append(f)
        return files_for_site

    def fetchGameTypes(self) -> None:
        for raw_file_name, f in list(self.filelist.items()):
            if f.ftype is not None and f.ftype == "hh":
                # Filenames are str on Python 3; decode only if a bytes path slips in.
                file_name = (
                    raw_file_name.decode("utf8", "replace") if isinstance(raw_file_name, bytes) else raw_file_name
                )
                if f.site is None:
                    continue
                obj = get_parser_class(f.site.filter_name)
                hhc = obj(
                    self.config,
                    in_path=file_name,
                    sitename=f.site.hhc_fname,
                    autostart=False,
                )
                if hhc.readFile():
                    f.gametype = hhc.determineGameType(hhc.whole_file)


def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    Configuration.set_logfile("fpdb-log.txt")
    config = Configuration.Config(file="HUD_config.xml")
    in_path = os.path.abspath("regression-test-files")
    IdSite = IdentifySite(config)
    time()
    IdSite.scan(in_path)

    for _sid, _site in list(IdSite.sitelist.items()):
        pass

    count = 0
    for _f, ffile in list(IdSite.filelist.items()):
        tmp = ""
        tmp += f": Type: {ffile.ftype} "
        count += 1
        if ffile.ftype == "hh" and ffile.site is not None:
            tmp += f"Conv: {ffile.site.hhc_fname}"
        elif ffile.ftype == "summary" and ffile.site is not None:
            tmp += f"Conv: {ffile.site.summary}"

    IdSite.getFilesForSite("PokerStars", "hh")


if __name__ == "__main__":
    main()
