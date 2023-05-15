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
import contextlib
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
        """
        Generate a list of sites based on the supplied HHCS dictionary.

        If no dictionary is supplied, uses the dictionary found in the config.

        Args:
            hhcs (dict): A dictionary of HHCS codes and their corresponding sites.

        Returns:
            None
        """
        if not hhcs:
            # If no HHCS dictionary is supplied, use the one from the config.
            hhcs = self.config.hhcs

        # Add each site to the site list.
        for site, hhc in list(hhcs.items()):
            self.addSite(site, hhc)

        # Set the regex patterns used for parsing.
        self.setRegexPatterns()


    def addSite(self, site, hhc):
        """
        Add a site to the site list.

        Args:
            site (str): The name of the site.
            hhc (Hhc): The Hhc object for the site.
        """
        # Get the converter filter and name
        filter = hhc.converter
        filter_name = filter.replace("ToFpdb", "")

        # Get the summary importer and import the filter module
        summary = hhc.summaryImporter
        mod = __import__(filter)

        # Get the filter object
        obj = getattr(mod, filter_name, None)

        try:
            # Add the site to the site list
            self.sitelist[obj.siteId] = Site(site, filter, filter_name, summary, obj)
        except Exception as e:
            # Log an error if the site couldn't be added
            log.error(f"Failed to load HH importer: {filter_name}.  {e}")


    def setRegexPatterns(self):
        """
        Sets the regular expression patterns for identifying PokerTracker hands.
        """
        # Import the necessary modules.
        pt_module = __import__("PokerTrackerToFpdb")
        summary_module = __import__("PokerTrackerSummary")

        # Get the regular expression patterns from the imported modules.
        self.re_Identify_PT = getattr(pt_module, "PokerTracker", None).re_Identify
        self.re_SumIdentify_PT = getattr(summary_module, "PokerTrackerSummary", None).re_Identify



    def walkDirectory(self, directory, sitelist):
        """Walks a directory and executes a callback on each file

        Args:
            directory (str): The directory to walk
            sitelist (list): A list of file extensions to process
        """
        # Walk the directory tree
        for root, directories, files in os.walk(directory):
            for file in files:
                # Skip the current and parent directory links
                if file not in [".", ".."]:
                    # Get the full path to the file
                    file_path = os.path.join(root, file)
                    # Process the file
                    self.processFile(file_path)

    def __listof(self, x):
        """
        Convert a non-list/tuple object to a list.

        Args:
            x: The object to be converted.

        Returns:
            A list containing the object if it is not a list or tuple, or the
            original list or tuple.
        """
        return x if isinstance(x, (list, tuple)) else [x]


    def processFile(self, path):
        """
        Process the file given by `path`.

        Args:
            path (str): The path of the file to process.

        Returns:
            None
        """
        # Check if the file has already been processed, if so, return
        if path in self.filelist:
            return

        # Read the file content and detect the encoding
        whole_file, kodec = self.read_file(path)

        # If the file content exists, create a site id object and add it to the file list
        if whole_file:
            if fobj := self.idSite(path, whole_file, kodec):
                # Add the site id object to the file list
                self.filelist[path] = fobj
            else:
                log.debug("siteId Failed for: %s", path)





    def read_file(self, in_path):
        """
        Reads a file and returns its contents and encoding type

        Args:
            in_path (str): The path to the file to be read

        Returns:
            tuple: A tuple containing the contents of the file and its encoding type
        """

        # If the file is an Excel file, use xlrd to read it
        if in_path.endswith('.xls') or in_path.endswith('.xlsx') and xlrd:
            try:
                wb = xlrd.open_workbook(in_path)
                sh = wb.sheet_by_index(0)
                header = str(sh.cell(0,0).value)
                return header, 'utf-8'
            except Exception:
                return None, None

        # Try to read the file with its default encoding
        with contextlib.suppress(Exception):
            with open(in_path, 'r') as infile:
                whole_file = infile.read()
            return whole_file, 'default'
        # If the default encoding fails, try different codecs
        for kodec in self.codepage:
            try:
                infile = codecs.open(in_path, 'r', kodec)
                whole_file = infile.read()
                infile.close()
                return whole_file, kodec
            except Exception:
                continue

        # If the file cannot be read with any codec, return None
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
        """
        Returns a list of files that belong to the given site and have the given file type.

        Args:
            sitename (str): The name of the site to search for files.
            ftype (str): The file type to search for.

        Returns:
            list: A list of File objects that belong to the given site and have the given file type.
        """
        return [
            f
            for f in self.filelist.values()
            if f.ftype is not None and f.site.name == sitename and f.ftype == "hh"
        ]



    def fetchGameTypes(self):
        """
        Fetches the game types from the file list.

        Returns:
            None.
        """
        for name, f in self.filelist.items():
            # Only process files with type "hh"
            if f.ftype and f.ftype == "hh":
                try:
                    # Convert name to string, replacing any unrecognized characters with "?"
                    name = str(name, "utf8", "replace")
                except TypeError as e:
                    log.error(e)
                # Import the module that contains the filter class specified in f.site.filter_name
                mod = __import__(f.site.hhc_fname)
                # Get the filter class from the module
                obj = getattr(mod, f.site.filter_name, None)
                # Create an instance of the filter class
                hhc = obj(self.config, in_path=name, sitename=f.site.hhc_fname, autostart=False)
                # Read the file contents
                if hhc.readFile():
                    # Determine the game type from the file contents
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
