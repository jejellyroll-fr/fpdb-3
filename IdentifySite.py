#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

from __future__ import print_function


# import L10n
# _ = L10n.get_translation()

import re
import sys
import os
from time import time
import codecs


import Configuration
from loggingFpdb import get_logger

try:
    import xlrd
except ImportError:
    xlrd = None
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("parser")

re_Divider, re_Head, re_XLS = {}, {}, {}
re_Divider["PokerStars"] = re.compile(r"^Hand #(\d+)\s*$", re.MULTILINE)
re_Divider["Fulltilt"] = re.compile(r"\*{20}\s#\s\d+\s\*{15,25}\s?", re.MULTILINE)
re_Head["Fulltilt"] = re.compile(r"^((BEGIN)?\n)?FullTiltPoker.+\n\nSeat", re.MULTILINE)
re_XLS["PokerStars"] = re.compile(r"Tournaments\splayed\sby\s\'.+?\'")
re_XLS["Fulltilt"] = re.compile(r"Player\sTournament\sReport\sfor\s.+?\s\(.*\)")


class FPDBFile(object):
    path = ""
    ftype = None  # Valid: hh, summary, both
    site = None
    kodec = None
    archive = False
    archiveHead = False
    archiveDivider = False
    gametype = False
    hero = "-"

    def __init__(self, path):
        self.path = path


class Site(object):
    def __init__(self, name, hhc_fname, filter_name, summary, obj):
        self.name = name
        # FIXME: rename filter to hhc_fname
        self.hhc_fname = hhc_fname
        # FIXME: rename filter_name to hhc_type
        self.filter_name = filter_name
        self.re_SplitHands = obj.re_SplitHands
        self.codepage = obj.codepage
        self.copyGameHeader = obj.copyGameHeader
        self.summaryInFile = obj.summaryInFile
        self.re_Identify = obj.re_Identify
        # self.obj            = obj
        if summary:
            self.summary = summary
            self.re_SumIdentify = getattr(__import__(summary), summary, None).re_Identify
        else:
            self.summary = None
        self.line_delimiter = self.getDelimiter(filter_name)
        self.line_addendum = self.getAddendum(filter_name)
        self.spaces = filter_name == "Entraction"
        self.getHeroRegex(obj, filter_name)

    def getDelimiter(self, filter_name):
        line_delimiter = None
        if filter_name == "PokerStars":
            line_delimiter = "\n\n"
        elif filter_name == "Fulltilt" or filter_name == "PokerTracker":
            line_delimiter = "\n\n\n"
        elif self.re_SplitHands.match("\n\n") and filter_name != "Entraction":
            line_delimiter = "\n\n"
        elif self.re_SplitHands.match("\n\n\n"):
            line_delimiter = "\n\n\n"

        return line_delimiter

    def getAddendum(self, filter_name):
        line_addendum = ""
        if filter_name == "OnGame":
            line_addendum = "*"
        elif filter_name == "Merge":
            line_addendum = "<"
        elif filter_name == "Entraction":
            line_addendum = "\n\n"

        return line_addendum

    def getHeroRegex(self, obj, filter_name):
        self.re_HeroCards = None
        if hasattr(obj, "re_HeroCards"):
            if filter_name not in ("Bovada", "Enet"):
                self.re_HeroCards = obj.re_HeroCards
        if filter_name == "PokerTracker":
            self.re_HeroCards1 = obj.re_HeroCards1
            self.re_HeroCards2 = obj.re_HeroCards2


class IdentifySite(object):
    def __init__(self, config, hhcs=None):
        self.config = config
        self.codepage = ("utf8", "cp1252", "ISO-8859-1")
        self.sitelist = {}
        self.filelist = {}
        self.generateSiteList(hhcs)

    def scan(self, path):
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

    def clear_filelist(self):
        self.filelist = {}

    def generateSiteList(self, hhcs):
        """Generates a ordered dictionary of site, filter and filter name for each site in hhcs"""
        if not hhcs:
            hhcs = self.config.hhcs
        for site, hhc in list(hhcs.items()):
            filter = hhc.converter
            filter_name = filter.replace("ToFpdb", "")
            summary = hhc.summaryImporter
            mod = __import__(filter)
            obj = getattr(mod, filter_name, None)
            try:
                self.sitelist[obj.siteId] = Site(site, filter, filter_name, summary, obj)
            except Exception as e:
                log.error(f"Failed to load HH importer: {filter_name}. {e}")
        self.re_Identify_PT = getattr(__import__("PokerTrackerToFpdb"), "PokerTracker", None).re_Identify
        self.re_SumIdentify_PT = getattr(__import__("PokerTrackerSummary"), "PokerTrackerSummary", None).re_Identify

    def walkDirectory(self, dir, sitelist):
        """Walks a directory, and executes a callback on each file"""
        dir = os.path.abspath(dir)
        for file in [file for file in os.listdir(dir) if not file in [".", ".."]]:
            nfile = os.path.join(dir, file)
            if os.path.isdir(nfile):
                self.walkDirectory(nfile, sitelist)
            else:
                self.processFile(nfile)

    def __listof(self, x):
        if isinstance(x, list) or isinstance(x, tuple):
            return x
        else:
            return [x]

    def processFile(self, path):
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
        if (in_path.endswith(".xls") or in_path.endswith(".xlsx")) and xlrd:
            try:
                wb = xlrd.open_workbook(in_path)
                sh = wb.sheet_by_index(0)
                header = str(sh.cell(0, 0).value)
                return header, "utf-8"
            except (xlrd.XLRDError, IOError) as e:
                log.error(f"Error reading Excel file {in_path}: {e}")
                return None, None

        # Check for the presence of a BOM for UTF-16
        try:
            with open(in_path, "rb") as infile:
                raw_data = infile.read()

            # If the file begins with a UTF-16 BOM (little endian or big endian)
            if raw_data.startswith(b"\xff\xfe") or raw_data.startswith(b"\xfe\xff"):
                try:
                    whole_file = raw_data.decode("utf-16")
                    return whole_file, "utf-16"
                except UnicodeDecodeError as e:
                    log.error(f"Error decoding UTF-16 file {in_path}: {e}")
                    return None, None
        except IOError as e:
            log.error(f"Error reading file {in_path}: {e}")
            return None, None

        # Try different encodings in the `self.codepage` list
        for kodec in self.codepage:
            try:
                with codecs.open(in_path, "r", kodec) as infile:
                    whole_file = infile.read()
                    return whole_file, kodec
            except (IOError, UnicodeDecodeError) as e:
                log.warning(f"Failed to read file {in_path} with codec {kodec}: {e}")
                continue

        log.error(f"Unable to read file {in_path} with any known codecs.")
        return None, None

    def idSite(self, path, whole_file, kodec):
        """Identifies the site the hh file originated from"""
        f = FPDBFile(path)
        f.kodec = kodec
        # DEBUG:print('idsite path',path )
        # DEBUG:print('idsite f',f,f.ftype,f.site,f.gametype )

        # DEBUG:print('idsite self.sitelist.items',self.sitelist.items())
        for id, site in list(self.sitelist.items()):
            filter_name = site.filter_name
            m = site.re_Identify.search(whole_file[:5000])
            if m and filter_name in ("Fulltilt", "PokerStars"):
                m1 = re_Divider[filter_name].search(whole_file.replace("\r\n", "\n"))
                if m1:
                    f.archive = True
                    f.archiveDivider = True
                elif re_Head.get(filter_name) and re_Head[filter_name].match(whole_file[:5000].replace("\r\n", "\n")):
                    f.archive = True
                    f.archiveHead = True
            if m:
                f.site = site
                f.ftype = "hh"
                if f.site.re_HeroCards:
                    h = f.site.re_HeroCards.search(whole_file[:5000])
                    if h and "PNAME" in h.groupdict():
                        f.hero = h.group("PNAME")
                else:
                    f.hero = "Hero"
                return f

        for id, site in list(self.sitelist.items()):
            if site.summary:
                if path.endswith(".xls") or path.endswith(".xlsx"):
                    filter_name = site.filter_name
                    if filter_name in ("Fulltilt", "PokerStars"):
                        m2 = re_XLS[filter_name].search(whole_file[:5000])
                        if m2:
                            f.site = site
                            f.ftype = "summary"
                            return f
                else:
                    m3 = site.re_SumIdentify.search(whole_file[:10000])
                    if m3:
                        f.site = site
                        f.ftype = "summary"
                        return f

        m1 = self.re_Identify_PT.search(whole_file[:5000])
        m2 = self.re_SumIdentify_PT.search(whole_file[:100])
        if m1 or m2:
            filter = "PokerTrackerToFpdb"
            filter_name = "PokerTracker"
            mod = __import__(filter)
            obj = getattr(mod, filter_name, None)
            summary = "PokerTrackerSummary"
            f.site = Site("PokerTracker", filter, filter_name, summary, obj)
            if m1:
                f.ftype = "hh"
                if re.search("\*{2}\sGame\sID\s", m1.group()):
                    f.site.line_delimiter = None
                    f.site.re_SplitHands = re.compile("End\sof\sgame\s\d+")
                elif re.search("\*{2}\sHand\s\#\s", m1.group()):
                    f.site.line_delimiter = None
                    f.site.re_SplitHands = re.compile("Rake:\s[^\s]+")
                elif re.search("Server\spoker\d+\.ipoker\.com", whole_file[:250]):
                    f.site.line_delimiter = None
                    f.site.spaces = True
                    f.site.re_SplitHands = re.compile("GAME\s\#")
                m3 = f.site.re_HeroCards1.search(whole_file[:5000])
                if m3:
                    f.hero = m3.group("PNAME")
                else:
                    m4 = f.site.re_HeroCards2.search(whole_file[:5000])
                    if m4:
                        f.hero = m4.group("PNAME")
            else:
                f.ftype = "summary"
            return f

        return False

    def getFilesForSite(self, sitename, ftype):
        files_for_site = []
        for name, f in list(self.filelist.items()):
            if f.ftype is not None and f.site.name == sitename and f.ftype == "hh":
                files_for_site.append(f)
        return files_for_site

    def fetchGameTypes(self):
        for name, f in list(self.filelist.items()):
            if f.ftype is not None and f.ftype == "hh":
                try:  # TODO: this is a dirty hack. Borrowed from fpdb_import
                    name = str(name, "utf8", "replace")
                except TypeError:
                    log.error(TypeError)
                mod = __import__(f.site.hhc_fname)
                obj = getattr(mod, f.site.filter_name, None)
                hhc = obj(self.config, in_path=name, sitename=f.site.hhc_fname, autostart=False)
                if hhc.readFile():
                    f.gametype = hhc.determineGameType(hhc.whole_file)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    Configuration.set_logfile("fpdb-log.txt")
    config = Configuration.Config(file="HUD_config.xml")
    in_path = os.path.abspath("regression-test-files")
    IdSite = IdentifySite(config)
    start = time()
    IdSite.scan(in_path)
    print("duration", time() - start)

    print("\n----------- SITE LIST -----------")
    for sid, site in list(IdSite.sitelist.items()):
        print("%2d: Name: %s HHC: %s Summary: %s" % (sid, site.name, site.filter_name, site.summary))
    print("----------- END SITE LIST -----------")

    print("\n----------- ID REGRESSION FILES -----------")
    count = 0
    for f, ffile in list(IdSite.filelist.items()):
        tmp = ""
        tmp += ": Type: %s " % ffile.ftype
        count += 1
        if ffile.ftype == "hh":
            tmp += "Conv: %s" % ffile.site.hhc_fname
        elif ffile.ftype == "summary":
            tmp += "Conv: %s" % ffile.site.summary
        print(f, tmp)
    print(count, "files identified")
    print("----------- END ID REGRESSION FILES -----------")

    print("----------- RETRIEVE FOR SINGLE SITE -----------")
    IdSite.getFilesForSite("PokerStars", "hh")
    print("----------- END RETRIEVE FOR SINGLE SITE -----------")


if __name__ == "__main__":
    sys.exit(main())
