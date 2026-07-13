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
from time import time
from typing import Any

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
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


class Site:
    def __init__(
        self,
        name: str,
        hhc_fname: str,
        filter_name: str,
        summary: str | None,
        obj: type[HandHistoryConverter],
    ) -> None:
        self.name = name
        # FIXME: rename filter to hhc_fname
        self.hhc_fname = hhc_fname
        # FIXME: rename filter_name to hhc_type
        self.filter_name = filter_name
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
        self.line_delimiter = self.getDelimiter(filter_name)
        self.line_addendum = self.getAddendum(filter_name)
        self.spaces = filter_name == "Entraction"
        self.getHeroRegex(obj, filter_name)

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
    def __init__(self, config: Any, hhcs: Any = None) -> None:
        self.config = config
        self.codepage = ("utf8", "cp1252", "ISO-8859-1")
        self.sitelist: dict[int | None, Site] = {}
        self.filelist: dict[str | bytes, FPDBFile] = {}
        self.re_Identify_PT: re.Pattern[str] | None = None
        self.re_SumIdentify_PT: re.Pattern[str] | None = None
        self.generateSiteList(hhcs)

    def detectiPokerSkin(self, handText):
        """Detect specific iPoker skin from hand text content."""
        # Extract table name from hand text
        table_pattern = r"Table\s+(.+?),"
        table_match = re.search(table_pattern, handText)
        table_name = table_match.group(1) if table_match else ""

        log.debug(f"Detected table name: {table_name}")

        # Map of indicators to skin names (must match Sites table)
        skin_mapping = {
            "redbet": "Redbet Poker",
            "pmu": "PMU Poker",
            "fdj": "FDJ Poker",
            "betclic": "Betclic Poker",
            "netbet": "NetBet Poker",
            "poker770": "Poker770",
            "barriere": "Barrière Poker",
            "titan": "Titan Poker",
            "bet365": "Bet365 Poker",
            "william hill": "William Hill Poker",
            "williamhill": "William Hill Poker",
            "paddy power": "Paddy Power Poker",
            "paddypower": "Paddy Power Poker",
            "betfair": "Betfair Poker",
            "coral": "Coral Poker",
            "genting": "Genting Poker",
            "mansion": "Mansion Poker",
            "winner": "Winner Poker",
            "ladbrokes": "Ladbrokes Poker",
            "sky": "Sky Poker",
            "sisal": "Sisal Poker",
            "lottomatica": "Lottomatica Poker",
            "eurobet": "Eurobet Poker",
            "snai": "Snai Poker",
            "goldbet": "Goldbet Poker",
            "casino barcelona": "Casino Barcelona Poker",
            "sportium": "Sportium Poker",
            "marca": "Marca Apuestas Poker",
            "everest": "Everest Poker",
            "bet-at-home": "Bet-at-home Poker",
            "mybet": "Mybet Poker",
            "betsson": "Betsson Poker",
            "betsafe": "Betsafe Poker",
            "nordicbet": "NordicBet Poker",
            "unibet": "Unibet Poker",
            "maria": "Maria Casino Poker",
            "leovegas": "LeoVegas Poker",
            "mr green": "Mr Green Poker",
            "expekt": "Expekt Poker",
            "coolbet": "Coolbet Poker",
            "chilipoker": "Chilipoker",
            "dafa": "Dafa Poker",
            "dafabet": "Dafabet Poker",
            "fun88": "Fun88 Poker",
            "betfred": "Betfred Poker",
            "guts": "Guts Poker",
            "sportingbet": "Sportingbet Poker",
            "multipoker": "MultiPoker",
            "red star": "Red Star Poker",
            "redstar": "Red Star Poker",
        }

        # Check table name and hand text for skin indicators
        search_text = (table_name + " " + handText).lower()

        # Specific patterns for French sites
        if any(indicator in search_text for indicator in ["saratov", "scone", "moscow"]):
            # These table name patterns are typical of FDJ Poker
            log.debug("Detected FDJ Poker based on table name pattern")
            return "FDJ Poker"

        # Check each mapping
        for indicator, skin_name in skin_mapping.items():
            if indicator in search_text:
                log.debug(f"Detected iPoker skin: {skin_name} from indicator: {indicator}")
                return skin_name

        # Default to generic iPoker if no specific skin detected
        log.debug("No specific iPoker skin detected, using default 'iPoker'")
        return "iPoker"

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

    def scan(self, path) -> None:
        if os.path.isdir(path):
            self.walkDirectory(path, self.sitelist)
        else:
            self.processFile(path)

    def get_fobj(self, file):
        try:
            fobj = self.filelist[file]
        except KeyError:
            return False
        return fobj

    def get_filelist(self):
        return self.filelist

    def clear_filelist(self) -> None:
        self.filelist = {}

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
        if path not in self.filelist:
            log.debug(f"filelist {self.filelist}")
            whole_file, kodec = self.read_file(path)
            # log.debug('whole_file',whole_file)
            log.debug(f"kodec {kodec}")
            if whole_file:
                fobj = self.idSite(path, whole_file, kodec)
                log.debug(f"siteid obj {fobj}")
                # print(fobj.path)
                if fobj is False:  # Site id failed
                    log.debug(f"siteId Failed for: {path}")
                else:
                    self.filelist[path] = fobj

    def read_file(self, in_path):
        # Ignore macOS-specific hidden files such as .DS_Store
        if in_path.endswith(".DS_Store"):
            log.warning(f"Skipping system file {in_path}")
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

            # If the file begins with a UTF-16 BOM (little endian or big endian)
            if raw_data.startswith((b"\xff\xfe", b"\xfe\xff")):
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
                # For PokerStars, we need to determine the specific skin
                if filter_name == "PokerStars":
                    selected_site = self._select_pokerstars_skin_site(path, whole_file, site)
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

            # Detect specific iPoker skin for PokerTracker format
            detected_site_name = "PokerTracker"  # default
            if m1 and "GAME #" in m1.group():
                # This is an iPoker hand, detect the specific skin
                detected_site_name = self.detectiPokerSkin(whole_file)
                log.debug(f"Detected iPoker skin from PokerTracker format: {detected_site_name}")

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
                    m4 = (
                        pt_site.re_HeroCards2.search(whole_file[:5000])
                        if pt_site.re_HeroCards2 is not None
                        else None
                    )
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
        for name, f in list(self.filelist.items()):
            if f.ftype is not None and f.ftype == "hh":
                # Filenames are str on Python 3; decode only if a bytes path slips in.
                if isinstance(name, bytes):
                    name = name.decode("utf8", "replace")
                if f.site is None:
                    continue
                obj = get_parser_class(f.site.filter_name)
                hhc = obj(
                    self.config,
                    in_path=name,
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
