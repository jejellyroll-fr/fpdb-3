#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2008-2011 Steffen Schaumburg
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, version 3 of the License.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program. If not, see <http://www.gnu.org/licenses/>.
#In the "official" distribution you can find the license in agpl-3.0.txt.

# Modifications made by jejellyroll on 2020-2023:
# refactor code for python 3

#Import statements come next


# Standard library imports
from __future__ import print_function
import codecs
import logging
import os
import re
import sys
from optparse import OptionParser
from time import time

# fpdb/FreePokerTools modules
import Configuration
import Database

# Third-party imports
try:
    import xlrd
except Exception:
    xlrd = None


# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("parser")

# Regular expressions for hand history parsing
re_Divider, re_Head, re_XLS  = {}, {}, {}

# Divider regex for PokerStars hand histories
re_Divider['PokerStars'] = re.compile(r'^Hand #(\d+)\s*$', re.MULTILINE)

# Divider regex for Full Tilt hand histories
re_Divider['Fulltilt'] = re.compile(r'\*{20}\s#\s\d+\s\*{15,25}\s?', re.MULTILINE)

# Header regex for Full Tilt hand histories
re_Head['Fulltilt'] = re.compile(r'^((BEGIN)?\n)?FullTiltPoker.+\n\nSeat', re.MULTILINE)

# Regex for identifying XLS files in PokerStars and Full Tilt hand histories
re_XLS['PokerStars'] = re.compile(r'Tournaments\splayed\sby\s\'.+?\'')
re_XLS['Fulltilt'] = re.compile(r'Player\sTournament\sReport\sfor\s.+?\s\(.*\)')


class FPDBFile(object):
    """
    A class that represents a FPDB file.

    Attributes:
        path (str): The path of the file.
        ftype (str): The type of file. Can be 'hh', 'summary', 'both' or None.
        site (str): The name of the poker site. Can be None.
        kodec (str): The codec used to encode the file. Can be None.
        archive (bool): Whether the file is an archive or not.
        archiveHead (bool): Whether the file is an archive head or not.
        archiveDivider (bool): Whether the file is an archive divider or not.
        gametype (bool): Whether the file is a game type file or not.
        hero (str): The hero of the game. Can be '-' or None.

    Methods:
        __init__(self, path: str): Initializes a new instance of the FPDBFile class.

    """

    def __init__(self, path: str):
        """
        Initializes a new instance of the FPDBFile class.

        Parameters:
            path (str): The path of the file.
        """
        self.path = path
        self.ftype = None
        self.site = None
        self.kodec = None
        self.archive = False
        self.archiveHead = False
        self.archiveDivider = False
        self.gametype = False
        self.hero = '-'


class Site(object):
    """
    A class that represents a poker site.

    Attributes:
        name (str): The name of the poker site.
        hhc_fname (str): The name of the HH converter file.
        filter_name (str): The name of the filter. Can be renamed to hhc_type.
        re_SplitHands (re.Pattern): The compiled regular expression pattern to split hands.
        codepage (str): The codepage used to encode the file.
        copyGameHeader (bool): Whether the game header should be copied or not.
        summaryInFile (bool): Whether the summary is included in the file or not.
        re_Identify (re.Pattern): The compiled regular expression pattern to identify the file.
        summary (str): The name of the summary file.
        re_SumIdentify (re.Pattern): The compiled regular expression pattern to identify the summary file.
        line_delimiter (str): The delimiter used in the file.
        line_addendum (str): The addendum used in the file.
        spaces (bool): Whether spaces are used in the file or not.

    Methods:
        __init__(self, name: str, hhc_fname: str, filter_name: str, summary: str, obj: Any): Initializes a new instance of the Site class.
        getDelimiter(self, filter_name: str) -> str: Returns the delimiter used in the file.
        getAddendum(self, filter_name: str) -> str: Returns the addendum used in the file.
        getHeroRegex(self, obj: Any, filter_name: str): Returns the regular expression pattern for the hero of the game.

    """

    def __init__(self, name, hhc_fname, filter_name, summary, obj):
        """
        Initializes a new instance of the Site class.

        Args:
            name (str): The name of the poker site.
            hhc_fname (str): The name of the HH converter file.
            filter_name (str): The name of the filter. Can be renamed to hhc_type.
            summary (str): The name of the summary file.
            obj (Any): An object containing various settings for the parser.
        """
        # Initialize class attributes
        self.name = name
        self.hhc_fname = hhc_fname
        self.filter_name = filter_name
        self.re_SplitHands = obj.re_SplitHands
        self.codepage = obj.codepage
        self.copyGameHeader = obj.copyGameHeader
        self.summaryInFile = obj.summaryInFile
        self.re_Identify = obj.re_Identify

        # If summary is provided, set self.summary attribute and get self.re_SumIdentify attribute
        if summary:
            self.summary = summary
            self.re_SumIdentify = getattr(__import__(summary), summary, None).re_Identify
        else:
            self.summary = None

        # Set line_delimiter, line_addendum, and spaces attributes using helper methods
        self.line_delimiter = self.getDelimiter(filter_name)
        self.line_addendum = self.getAddendum(filter_name)
        self.spaces = filter_name == 'Entraction'

        # Get hero regex using helper method
        self.getHeroRegex(obj, filter_name)

        
    def getDelimiter(self, filter_name):
        """
        Returns the line delimiter for a given filter name.
        If the filter name is not recognized, returns None.

        Args:
            filter_name (str): The name of the filter.

        Returns:
            str: The line delimiter for the filter name.
        """

        # Define a dictionary of filters
        filters = {
            'PokerStars': '\n\n',
            'Fulltilt': '\n\n\n',
            'PokerTracker': '\n\n\n',
            'Entraction': None  # default value
        }

        # Get the line delimiter for the filter name
        line_delimiter = filters.get(filter_name)

        # If the line delimiter is not found, try to match it with a regular expression
        if not line_delimiter:
            if self.re_SplitHands.match('\n\n'):
                line_delimiter = '\n\n'
            elif self.re_SplitHands.match('\n\n\n'):
                line_delimiter = '\n\n\n'

        return line_delimiter


    def getAddendum(self, filter_name):
        """
        Returns a line addendum based on the filter name

        Args:
            filter_name (str): The name of the filter

        Returns:
            str: The line addendum
        """
        line_addendum = ''
        if filter_name == 'OnGame':
            line_addendum = '*'  # Add a '*' to the end of the line
        elif filter_name == 'Merge':
            line_addendum = '<'  # Add a '<' to the end of the line
        elif filter_name == 'Entraction':
            line_addendum = '\n\n'  # Add two newlines to the end of the line

        return line_addendum

    
    def getHeroRegex(self, obj, filter_name):
        """Gets a regex pattern for hero cards based on a filter name.

        Args:
            obj: An object that contains a regex pattern for hero cards.
            filter_name: A string that specifies the filter to use to get the hero regex pattern.

        Returns:
            None

        """
        self.re_HeroCards = None
        # Check if the object has a regex pattern for hero cards
        if hasattr(obj, 're_HeroCards') and filter_name not in ('Bovada', 'Enet'):
            self.re_HeroCards = obj.re_HeroCards
        # If the filter name is 'PokerTracker', use the regex patterns for hero cards 1 and 2
        if filter_name == 'PokerTracker':
            self.re_HeroCards1 = obj.re_HeroCards1
            self.re_HeroCards2 = obj.re_HeroCards2


class IdentifySite(object):
    def __init__(self, config, hhcs=None):
        """
        Initializes a new instance of the IdentifySite class.

        Args:
        config (dict): A dictionary containing configuration settings.
        hhcs (list): A list of HHC files to process.
        """
        self.config = config
        self.codepage = ("utf8", "utf-16", "cp1252", "ISO-8859-1")
        self.sitelist = {}
        self.filelist = {}
        self.generateSiteList(hhcs)

    def scan(self, path):
        """Scans a file or directory.

        Args:
            path (str): The path to the file or directory.
        """
        if os.path.isdir(path):
            self.walkDirectory(path, self.sitelist)
        else:
            self.processFile(path)
            
    def get_fobj(self, file):
        """
        Retrieves the file object for the given file from the file list.

        Args:
            file (str): The name of the file to retrieve the object for.

        Returns:
            The file object if found, otherwise False.
        """
        try:
            fobj = self.filelist[file]  # Attempt to retrieve the file object from the file list.
        except KeyError:
            return False  # Return False if the file object is not found in the file list.
        return fobj  # Return the file object if found.


    def get_filelist(self):
        """
        Returns the filelist attribute of the MyClass instance.
        """
        return self.filelist
    
    def clear_filelist(self):
        """Clears the file list dictionary."""
        self.filelist = {}  # reset the file list to an empty dictionary

    # WIP # WIP
    def generateSiteList(self, hhcs):
        if not hhcs:
            hhcs = self.config.hhcs

        for site, hhc in list(hhcs.items()):
            self.addSite(site, hhc)

        self.setRegexPatterns()

    def addSite(self, site, hhc):
        filter = hhc.converter
        filter_name = filter.replace("ToFpdb", "")
        summary = hhc.summaryImporter
        mod = __import__(filter)
        obj = getattr(mod, filter_name, None)
        try:
            self.sitelist[obj.siteId] = Site(site, filter, filter_name, summary, obj)
        except Exception as e:
            log.error(f"Failed to load HH importer: {filter_name}.  {e}")

    def setRegexPatterns(self):
        pt_module = __import__("PokerTrackerToFpdb")
        summary_module = __import__("PokerTrackerSummary")
        self.re_Identify_PT = getattr(pt_module, "PokerTracker", None).re_Identify
        self.re_SumIdentify_PT = getattr(summary_module, "PokerTrackerSummary", None).re_Identify
 # WIP # WIP


    def walkDirectory(self, dir, sitelist):
        """Walks a directory, and executes a callback on each file"""
        dir = os.path.abspath(dir)
        for file in [file for file in os.listdir(dir) if not file in [".",".."]]:
            nfile = os.path.join(dir,file)
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
        print('process fill identify',path)
        if path not in self.filelist:
            print('filelist', self.filelist)
            whole_file, kodec = self.read_file(path)
            print('whole_file',whole_file)
            print('kodec',kodec )
            if whole_file:
                fobj = self.idSite(path, whole_file, kodec)
                print('siteid obj')
                #print(fobj.path)
                if fobj == False: # Site id failed
                    log.debug(("DEBUG:") + " " + ("siteId Failed for: %s") % path)
                else:
                    self.filelist[path] = fobj

    def read_file(self, in_path):
        if in_path.endswith('.xls') or in_path.endswith('.xlsx') and xlrd:
            try:
                wb = xlrd.open_workbook(in_path)
                sh = wb.sheet_by_index(0)
                header = str(sh.cell(0,0).value)
                return header, 'utf-8'
            except:
                return None, None
        for kodec in self.codepage:
            try:
                infile = codecs.open(in_path, 'r', kodec)
                whole_file = infile.read()
                infile.close()
                return whole_file, kodec
            except:
                continue
        return None, None
    
    def idSite(self, path, whole_file, kodec):
        """Identifies the site the hh file originated from"""
        f = FPDBFile(path)
        f.kodec = kodec
        #DEBUG:print('idsite path',path )
        #DEBUG:print('idsite f',f,f.ftype,f.site,f.gametype )
        
        #DEBUG:print('idsite self.sitelist.items',self.sitelist.items())
        for id, site in list(self.sitelist.items()):
            filter_name = site.filter_name
            m = site.re_Identify.search(whole_file[:5000])
            if m and filter_name in ('Fulltilt', 'PokerStars'):
                m1 = re_Divider[filter_name].search(whole_file.replace('\r\n', '\n'))
                if m1:
                    f.archive = True
                    f.archiveDivider = True
                elif re_Head.get(filter_name) and re_Head[filter_name].match(whole_file[:5000].replace('\r\n', '\n')):
                    f.archive = True
                    f.archiveHead = True
            if m:
                f.site = site
                f.ftype = "hh"
                if f.site.re_HeroCards:
                    h = f.site.re_HeroCards.search(whole_file[:5000])
                    if h and 'PNAME' in h.groupdict():
                        f.hero = h.group('PNAME')
                else:
                    f.hero = 'Hero'
                return f

        for id, site in list(self.sitelist.items()):
            if site.summary:
                if path.endswith('.xls') or path.endswith('.xlsx'):
                    filter_name = site.filter_name
                    if filter_name in ('Fulltilt', 'PokerStars'):
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
            filter = 'PokerTrackerToFpdb'
            filter_name = 'PokerTracker'
            mod = __import__(filter)
            obj = getattr(mod, filter_name, None)
            summary = 'PokerTrackerSummary'
            f.site = Site('PokerTracker', filter, filter_name, summary, obj)
            if m1:
                f.ftype = "hh"
                if re.search(u'\*{2}\sGame\sID\s', m1.group()):
                    f.site.line_delimiter = None
                    f.site.re_SplitHands = re.compile(u'End\sof\sgame\s\d+')
                elif re.search(u'\*{2}\sHand\s\#\s', m1.group()):
                    f.site.line_delimiter = None
                    f.site.re_SplitHands = re.compile(u'Rake:\s[^\s]+')
                elif re.search(u'Server\spoker\d+\.ipoker\.com', whole_file[:250]):
                    f.site.line_delimiter = None
                    f.site.spaces = True
                    f.site.re_SplitHands = re.compile(u'GAME\s\#')
                m3 = f.site.re_HeroCards1.search(whole_file[:5000])
                if m3:
                    f.hero = m3.group('PNAME')
                else:
                     m4 = f.site.re_HeroCards2.search(whole_file[:5000])
                     if m4:
                         f.hero = m4.group('PNAME')
            else:
                f.ftype = "summary"
            return f
        
        return False

    def getFilesForSite(self, sitename, ftype):
        l = []
        for name, f in list(self.filelist.items()):
            if f.ftype != None and f.site.name == sitename and f.ftype == "hh":
                l.append(f)
        return l

    def fetchGameTypes(self):
        for name, f in list(self.filelist.items()):
            if f.ftype != None and f.ftype == "hh":
                try: #TODO: this is a dirty hack. Borrowed from fpdb_import
                    name = str(name, "utf8", "replace")
                except TypeError:
                    log.error(TypeError)
                mod = __import__(f.site.hhc_fname)
                obj = getattr(mod, f.site.filter_name, None)
                hhc = obj(self.config, in_path = name, sitename = f.site.hhc_fname, autostart = False)
                if hhc.readFile():
                    f.gametype = hhc.determineGameType(hhc.whole_file)

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    Configuration.set_logfile("fpdb-log.txt")
    config = Configuration.Config(file = "HUD_config.test.xml")
    in_path = os.path.abspath('regression-test-files')
    IdSite = IdentifySite(config)
    start = time()
    IdSite.scan(in_path)
    print('duration', time() - start)

    print("\n----------- SITE LIST -----------")
    for sid, site in list(IdSite.sitelist.items()):
        print("%2d: Name: %s HHC: %s Summary: %s" %(sid, site.name, site.filter_name, site.summary))
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
    print(count, 'files identified')
    print("----------- END ID REGRESSION FILES -----------")

    print("----------- RETRIEVE FOR SINGLE SITE -----------")
    IdSite.getFilesForSite("PokerStars", "hh")
    print("----------- END RETRIEVE FOR SINGLE SITE -----------")

if __name__ == '__main__':
    sys.exit(main())
