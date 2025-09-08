# -*- coding: UTF-8 -*-
#    Copyright 2012, Chaz Littlejohn
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


class FPDBArchive:
    def __init__(self, hand) -> None:
        self.hid = hand.dbid_hands
        self.handText = hand.handText


class Archive:
    def __init__(self, config=None, path=None, ftype="hh") -> None:
        self.config = config
        self.archivePath = None
        if config:
            self.archivePath = config.imp.archivePath
        self.path = path
        self.ftype = ftype
        self.handList = {}
        self.sessionsArchive = {}
        self.startCardsArchive = {}
        self.positionsArchive = {}

    def quickImport(self, userid, filtertype, game, filter, settings, tz) -> None:
        pass

    """Sets up import in 'quick' mode to import the HandsPlayers, HandsActions, and HandsStove records"""

    def getSiteSplit(self) -> None:
        pass

    """Returns split string for each site so it can be added back into the handText when writing to archive"""

    def fileInfo(self, path, site, filter, filter_name, obj=None, summary=None) -> None:
        pass

    """Sets file site and header info if applicable"""

    def addHand(self, hand, write=False) -> None:
        pass

    """Creates a FPDBArchive object for the hand and adds it to the handList dictionary"""

    def createSession(self, sid) -> None:
        pass

    """Creates a session directory for a given sessionId"""

    def mergeFiles(self, path1, path2) -> None:
        pass

    """Merges two files together in cases where cash sessions need to be combined within a session"""

    def mergeSessions(self, oldsid, newsid) -> None:
        pass

    """Merges two session directories together"""

    def mergeSubSessions(self, type, sid, oldId, newId, hids) -> None:
        pass

    """Merges two cash session files together"""

    def addSessionHands(self, type, sid, id, hids) -> None:
        pass

    """Adds the handText records for a session to the sessionsArchive dictionary and sets the path"""

    def addStartCardsHands(self, category, type, startCards, wid, siteId, hids) -> None:
        pass

    """Adds the handText records for startCards to the startCardsArchive dictionary and sets the path"""

    def addPositionsHands(self, type, activeSeats, position, wid, siteId, hids) -> None:
        pass

    """Adds the handText records for Positions to the positionsArchive dictionary and sets the path"""

    def getFile(self, path) -> None:
        pass

    """Method for creating, appending and or unzipping a file"""

    def fileOrZip(self, path) -> None:
        pass

    """Checks to see if the file exists or if the zip file exists. Unzips if necessary"""

    def writeHands(self, doinsert) -> None:
        pass

    """Take the hands stored in the sessionsArchive, startCardsArchive, and positionsArchive dictionaries
       and write or append those hands to files organized in the archive directory"""

    def zipFile(self, path) -> None:
        pass

    """Zip a file for archiving"""

    def unzipFile(self, path) -> None:
        pass

    """Unzip a file for import"""

    def zipAll(self) -> None:
        pass

    """Recursively zip all the files in the archive directory"""

    def unzipAll(self) -> None:
        pass

    """Recursively unzip all the files in the archive directory"""
