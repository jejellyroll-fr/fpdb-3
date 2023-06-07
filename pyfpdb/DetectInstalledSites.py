#!/usr/bin/env python
# -*- coding: utf-8 -*-

#Copyright 2011 Gimick bbtgaf@googlemail.com
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

"""
Attempt to detect which poker sites are installed by the user, their
 heroname and the path to the HH files.

This is intended for new fpdb users to get them up and running quickly.

We assume that the majority of these users will install the poker client
into default locations so we will only check those places.

We just look for a hero HH folder, and don't really care if the
  application is installed

Situations not handled are:
    Multiple screennames using the computer
    TODO Unexpected dirs in HH dir (e.g. "archive" may become a heroname!)
    Non-standard installation locations
    TODO Mac installations

Typical Usage:
    See TestDetectInstalledSites.py

Todo:
    replace hardcoded site list with something more subtle

"""


import contextlib
import platform
import os
import sys

import Configuration

if platform.system() == 'Windows':
    #import winpaths
    #PROGRAM_FILES = winpaths.get_program_files()
    #LOCAL_APPDATA = winpaths.get_local_appdata()
    import os
    PROGRAM_FILES = os.getenv('ProgramW6432')
    ROAMING_APPDATA = os.getenv('APPDATA')
    LOCAL_APPDATA = os.getenv('LOCALAPPDATA')

class DetectInstalledSites(object):
    """
    DetectInstalledSites is a class that detects the installed sites on a system.

    Args:
        sitename (str): The name of the site to detect. If "All", detects all supported sites.
    """

    def __init__(self, sitename="All"):

        self.Config = Configuration.Config()  # Initializing the Config object

        # Initializing the objects returned
        self.sitestatusdict = {}
        self.sitename = sitename
        self.heroname = ""
        self.hhpath = ""
        self.tspath = ""
        self.detected = ""

        # Since each site has to be hand-coded in this module, there is little advantage in querying the sites table at the moment.
        # Plus we can run from the command line as no dependencies.
        # Initializing the supported sites and platforms
        self.supportedSites = ["PartyPoker",
                               "Merge",
                               "PokerStars",
                               "Winamax"]

        self.supportedPlatforms = ["Linux", "XP", "Win7"]

        if sitename == "All":   # Detecting all supported sites
            for siteiter in self.supportedSites:
                self.sitestatusdict[siteiter] = self.detect(siteiter)
        else:   # Detecting the specified site
            self.sitestatusdict[sitename] = self.detect(sitename)
            self.heroname = self.sitestatusdict[sitename]['heroname']
            self.hhpath = self.sitestatusdict[sitename]['hhpath']
            self.tspath = self.sitestatusdict[sitename]['tspath']
            self.detected = self.sitestatusdict[sitename]['detected']

        return

    def detect(self, siteToDetect):
        """
        Detects the presence of a poker site and returns relevant information.

        Args:
            siteToDetect (str): The name of the poker site to detect.

        Returns:
            dict: A dictionary containing the detection status and relevant information.

        """
        # Initialize variables
        self.hhpathfound = ""
        self.tspathfound = ""
        self.herofound = ""

        # Detect the site
        if siteToDetect == "Winamax":
            self.detectWinamax()
        elif siteToDetect == "PartyPoker":
            self.detectPartyPoker()
        elif siteToDetect == "PokerStars":
            self.detectPokerStars()
        elif siteToDetect == "Merge":
            self.detectMergeNetwork()

        # Check if all necessary information is found
        if (self.hhpathfound and self.herofound):
            encoding = sys.getfilesystemencoding()
            if type(self.hhpathfound) is not str:
                self.hhpathfound = str(self.hhpathfound, encoding)
            if type(self.tspathfound) is not str:
                self.tspathfound = str(self.tspathfound, encoding)
            if type(self.herofound) is not str:
                self.herofound = str(self.herofound, encoding)
            return {"detected":True, "hhpath":self.hhpathfound, "heroname":self.herofound, "tspath":self.tspathfound}
        else:
            return {"detected":False, "hhpath":u"", "heroname":u"", "tspath":u""}
    

        
    def detectPokerStars(self):
        """
        Detects the location of the PokerStars hand history files and tournament summary files based on the operating system.

        Returns:
            None
        """
        # Set the paths of the hand history files and tournament summary files based on the operating system
        if self.Config.os_family == "Linux":
            hhp = os.path.expanduser("~/.wine/drive_c/Program Files/PokerStars/HandHistory/") 
            hhpFR = os.path.expanduser("~/.wine/drive_c/Program Files/PokerStars.FR/HandHistory/")
            tsp = os.path.expanduser("~/.wine/drive_c/Program Files/PokerStars/TournSummary/")
            tspFR = os.path.expanduser("~/.wine/drive_c/Program Files/PokerStars.FR/TournSummary/")
        elif self.Config.os_family == "Win7":
            hhp = os.path.expanduser(LOCAL_APPDATA+"\\PokerStars\\HandHistory\\") 
            hhpFR = os.path.expanduser(LOCAL_APPDATA+"\\PokerStars.FR\\HandHistory\\")
            tsp = os.path.expanduser(LOCAL_APPDATA+"\\PokerStars\\TournSummary\\")
            tspFR = os.path.expanduser(LOCAL_APPDATA+"\\PokerStars.FR\\TournSummary\\")
        elif self.Config.os_family == "Mac":
            hhp = os.path.expanduser("~/Library/Application Support/PokerStars/HandHistory/")
            hhpFR = os.path.expanduser("~/Library/Application Support/PokerStarsFR/HandHistory/")
            tsp = os.path.expanduser("~/Library/Application Support/PokerStars/TournSummary/")
            tspFR = os.path.expanduser("~/Library/Application Support/PokerStars/TournSummary/")
        else:
            return

        # Check if the hand history files path exists
        if os.path.exists(hhp):
            # Set the hand history files path and check if the tournament summary files path exists
            self.hhpathfound = hhp
            if os.path.exists(tsp):
                self.tspathfound = tsp
        elif os.path.exists(hhpFR):
            self.hhpathfound = hhpFR
            if os.path.exists(tspFR):
                self.tspathfound = tspFR
        else:
            return

        # Try to get the name of the first hero found in the hand history files and update the paths accordingly
        with contextlib.suppress(Exception):
            if self.Config.os_family == "Mac":
                self.herofound = os.listdir(self.hhpathfound)[1]
            else:
                self.herofound = os.listdir(self.hhpathfound)[0]
            self.hhpathfound = self.hhpathfound + self.herofound
            if self.tspathfound:
                self.tspathfound = self.tspathfound + self.herofound

        return

    def detectPartyPoker(self):
        """Detect the PartyPoker installation directory."""

        # Set the HandHistory path depending on the operating system
        if self.Config.os_family == "Linux":
            hhp = os.path.expanduser("~/.wine/drive_c/Program Files/PartyGaming/PartyPoker/HandHistory/")
        elif self.Config.os_family == "XP":
            hhp = os.path.expanduser(PROGRAM_FILES + "\\PartyGaming\\PartyPoker\\HandHistory\\")
        elif self.Config.os_family == "Win7":
            hhp = os.path.expanduser("c:\\Programs\\PartyGaming\\PartyPoker\\HandHistory\\")
        else:
            return

        # Check if HandHistory path exists
        if os.path.exists(hhp):
            self.hhpathfound = hhp
        else:
            return

        # Get the list of subdirectories in the HandHistory path
        dirs = os.listdir(self.hhpathfound)

        # Remove XMLHandHistory directory from the list if present
        if "XMLHandHistory" in dirs:
            dirs.remove("XMLHandHistory")

        # Try to find the first non-empty directory and set it as hero folder
        with contextlib.suppress(Exception):
            self.herofound = dirs[0]
            self.hhpathfound = self.hhpathfound + self.herofound

        return


    def detectMergeNetwork(self):
        """
        Detects the Merge network and sets the path to the Carbon poker room.

        Carbon is the principal room on the Merge network but there are many other skins.
        Normally, we understand that a player can only be valid at one room on the Merge network so we will exit once successful.
        Many thanks to Ilithios for the PlayersOnly information.
        """

        merge_skin_names = [
            "CarbonPoker",
            "PlayersOnly",
            "BlackChipPoker",
            "RPMPoker",
            "HeroPoker",
            "PDCPoker",
        ]

        for skin in merge_skin_names:
            # Set the path to the history folder for the given skin
            if self.Config.os_family == "Linux":
                hhp = os.path.expanduser(f"~/.wine/drive_c/Program Files/{skin}/history/")
            elif self.Config.os_family in ["XP", "Win7"]:
                hhp=os.path.expanduser(PROGRAM_FILES+"\\"+skin+"\\history\\")
            else:
                return

            # If the history folder exists, set the path to it and try to find the hero file
            if os.path.exists(hhp):
                self.hhpathfound = hhp
                try:
                    self.herofound = os.listdir(self.hhpathfound)[0]
                    self.hhpathfound = self.hhpathfound + self.herofound
                    break
                except Exception:
                    continue

        # Return the function once it has successfully found the Merge network
        return

    def detectWinamax(self):
        """
        Detects the location of the Winamax hand history files based on the operating system.

        Returns:
            None
        """
        # Set the path of the hand history files based on the operating system
        if self.Config.os_family == "Linux":
            hhp = os.path.expanduser("~/.wine/drive_c/Program Files/Winamax/hand-history/")
            tsp = os.path.expanduser("~/.wine/drive_c/Program Files/Winamax/hand-history/")
        elif self.Config.os_family == "Mac":
            hhp = os.path.expanduser("~/Library/Application Support/Winamax/documents/accounts/")
            tsp = os.path.expanduser("~/Library/Application Support/Winamax/documents/accounts/")
        elif self.Config.os_family == "Win7":
            hhp = os.path.expanduser(ROAMING_APPDATA+"\\Winamax\\documents\\accounts\\")
            tsp = os.path.expanduser(ROAMING_APPDATA+"\\Winamax\\documents\\accounts\\")
        else:
            return None

        # Check if the hand history files path exists
        if not os.path.exists(hhp):
            return None

        # Set the hand history files path and check if the tournament summary files path exists
        self.hhpathfound = hhp
        if os.path.exists(tsp):
            self.tspathfound = tsp

        # Try to get the name of the first hero found in the hand history files and update the paths accordingly
        with contextlib.suppress(Exception):
            self.herofound = os.listdir(self.hhpathfound)[0]
            if self.Config.os_family == "Mac":
                self.hhpathfound = self.hhpathfound + self.herofound + "/history/"
                if self.tspathfound:
                    self.tspathfound = self.tspathfound + self.herofound + "/history"
            else:
                self.hhpathfound = self.hhpathfound + self.herofound + "\\history\\"
                if self.tspathfound:
                    self.tspathfound = self.tspathfound + self.herofound + "\\history\\"

        return