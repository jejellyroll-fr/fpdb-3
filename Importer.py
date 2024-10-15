#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2008-2011 Steffen Schaumburg
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
from __future__ import division


from past.utils import old_div
# import L10n
# _ = L10n.get_translation()

#    Standard Library modules

import os  # todo: remove this once import_dir is in fpdb_import
from time import time, process_time
import datetime
import shutil
import re
import zmq

import logging


from PyQt5.QtWidgets import QProgressBar, QLabel, QDialog, QVBoxLayout
from PyQt5.QtCore import QCoreApplication

#    fpdb/FreePokerTools modules

import Database

import Configuration

import IdentifySite

from Exceptions import FpdbParseError, FpdbHandDuplicate, FpdbHandPartial

try:
    import xlrd
except ImportError:
    xlrd = None

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("importer")


class ZMQSender:
    def __init__(self, port="5555"):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUSH)
        self.socket.bind(f"tcp://127.0.0.1:{port}")
        log.info(f"ZMQ sender initialized on port {port}")

    def send_hand_id(self, hand_id):
        try:
            self.socket.send_string(str(hand_id))
            log.debug(f"Sent hand ID {hand_id} via ZMQ")
        except zmq.ZMQError as e:
            log.error(f"Failed to send hand ID {hand_id}: {e}")

    def close(self):
        self.socket.close()
        self.context.term()
        log.info("ZMQ sender closed")


class Importer(object):
    def __init__(self, caller, settings, config, sql=None, parent=None):
        """Constructor"""
        self.settings = settings
        self.caller = caller
        self.config = config
        self.sql = sql
        self.parent = parent

        self.idsite = IdentifySite.IdentifySite(config)

        self.filelist = {}
        self.dirlist = {}
        self.siteIds = {}
        self.removeFromFileList = {}  # to remove deleted files
        self.monitor = False
        self.updatedsize = {}
        self.updatedtime = {}
        self.lines = None
        self.faobs = None  # File as one big string
        self.mode = None
        self.pos_in_file = {}  # dict to remember how far we have read in the file

        # Configuration des paramètres par défaut
        self.callHud = self.config.get_import_parameters().get("callFpdbHud")
        self.settings.setdefault("handCount", 0)
        self.settings.setdefault("writeQSize", 1000)
        self.settings.setdefault("writeQMaxWait", 10)
        self.settings.setdefault("dropIndexes", "don't drop")
        self.settings.setdefault("dropHudCache", "don't drop")
        self.settings.setdefault("starsArchive", False)
        self.settings.setdefault("ftpArchive", False)
        self.settings.setdefault("testData", False)
        self.settings.setdefault("cacheHHC", False)

        self.writeq = None
        self.database = Database.Database(self.config, sql=self.sql)
        self.writerdbs = []
        self.settings.setdefault("threads", 1)
        for i in range(self.settings["threads"]):
            self.writerdbs.append(Database.Database(self.config, sql=self.sql))

        # Modification : spécifier le port pour ZMQ
        self.zmq_sender = None
        process_time()  # init clock in windows

    # Set functions
    def setMode(self, value):
        self.mode = value

    def setCallHud(self, value):
        self.callHud = value

    def setCacheSessions(self, value):
        self.cacheSessions = value

    def setHandCount(self, value):
        self.settings["handCount"] = int(value)

    def setQuiet(self, value):
        self.settings["quiet"] = value

    def setHandsInDB(self, value):
        self.settings["handsInDB"] = value

    def setThreads(self, value):
        self.settings["threads"] = value
        if self.settings["threads"] > len(self.writerdbs):
            for i in range(self.settings["threads"] - len(self.writerdbs)):
                self.writerdbs.append(Database.Database(self.config, sql=self.sql))

    def setDropIndexes(self, value):
        self.settings["dropIndexes"] = value

    def setDropHudCache(self, value):
        self.settings["dropHudCache"] = value

    def setStarsArchive(self, value):
        self.settings["starsArchive"] = value

    def setFTPArchive(self, value):
        self.settings["ftpArchive"] = value

    def setPrintTestData(self, value):
        self.settings["testData"] = value

    def setFakeCacheHHC(self, value):
        self.settings["cacheHHC"] = value

    def getCachedHHC(self):
        return self.handhistoryconverter

    #   def setWatchTime(self):
    #       self.updated = time()

    def clearFileList(self):
        self.updatedsize = {}
        self.updatetime = {}
        self.pos_in_file = {}
        self.filelist = {}

    def logImport(self, type, file, stored, dups, partial, skipped, errs, ttime, id):
        hands = stored + dups + partial + skipped + errs
        now = datetime.datetime.utcnow()
        ttime100 = ttime * 100
        self.database.updateFile([type, now, now, hands, stored, dups, partial, skipped, errs, ttime100, True, id])
        self.database.commit()

    def addFileToList(self, fpdbfile):
        """FPDBFile"""
        file = os.path.splitext(os.path.basename(fpdbfile.path))[0]
        try:  # TODO: this is a dirty hack. GBI needs it, GAI fails with it.
            file = str(file, "utf8", "replace")
        except TypeError:
            pass
        fpdbfile.fileId = self.database.get_id(file)
        if not fpdbfile.fileId:
            now = datetime.datetime.utcnow()
            fpdbfile.fileId = self.database.storeFile([file, fpdbfile.site.name, now, now, 0, 0, 0, 0, 0, 0, 0, False])
            self.database.commit()

    # Add an individual file to filelist
    def addImportFile(self, filename, site="auto"):
        # DEBUG->print("addimportfile: filename is a", filename.__class__, filename)
        # filename not guaranteed to be unicode
        if self.filelist.get(filename) is not None or not os.path.exists(filename):
            return False

        self.idsite.processFile(filename)
        if self.idsite.get_fobj(filename):
            fpdbfile = self.idsite.filelist[filename]
        else:
            log.error("Importer.addImportFile: siteId Failed for: '%s'" % filename)
            return False

        self.addFileToList(fpdbfile)
        self.filelist[filename] = fpdbfile
        if site not in self.siteIds:
            # Get id from Sites table in DB
            result = self.database.get_site_id(fpdbfile.site.name)
            if len(result) == 1:
                self.siteIds[fpdbfile.site.name] = result[0][0]
            else:
                if len(result) == 0:
                    log.error(("Database ID for %s not found") % fpdbfile.site.name)
                else:
                    log.error(("More than 1 Database ID found for %s") % fpdbfile.site.name)

        return True

    # Called from GuiBulkImport to add a file or directory. Bulk import never monitors
    def addBulkImportImportFileOrDir(self, inputPath, site="auto"):
        """Add a file or directory for bulk import"""
        # for windows platform, force os.walk variable to be unicode
        # see fpdb-main post 9th July 2011
        if self.config.posix:
            pass
        else:
            inputPath = str(inputPath)

        # TODO: only add sane files?
        if os.path.isdir(inputPath):
            for subdir in os.walk(inputPath):
                for file in subdir[2]:
                    self.addImportFile(os.path.join(subdir[0], file), site=site)
            return True
        else:
            return self.addImportFile(inputPath, site=site)

    # Add a directory of files to filelist
    # Only one import directory per site supported.
    # dirlist is a hash of lists:
    # dirlist{ 'PokerStars' => ["/path/to/import/", "filtername"] }
    def addImportDirectory(self, dir, monitor=False, site=("default", "hh"), filter="passthrough"):
        # gets called by GuiAutoImport.
        # This should really be using os.walk
        # http://docs.python.org/library/os.html
        if os.path.isdir(dir):
            if monitor is True:
                self.monitor = True
                self.dirlist[site] = [dir] + [filter]

            # print "addImportDirectory: checking files in", dir
            for subdir in os.walk(dir):
                for file in subdir[2]:
                    filename = os.path.join(subdir[0], file)
                    # ignore symbolic links (Linux & Mac)
                    if os.path.islink(filename):
                        log.info(f"Ignoring symlink {filename}")
                        continue
                    if (time() - os.stat(filename).st_mtime) <= 43200:  # look all files modded in the last 12 hours
                        # need long time because FTP in Win does not
                        # update the timestamp on the HH during session
                        self.addImportFile(filename, "auto")
        else:
            log.warning(("Attempted to add non-directory '%s' as an import directory") % str(dir))

    def runImport(self):
        """ "Run full import on self.filelist. This is called from GuiBulkImport.py"""

        # Initial setup
        start = datetime.datetime.now()
        starttime = time()
        log.info(
            ("Started at %s -- %d files to import. indexes: %s")
            % (start, len(self.filelist), self.settings["dropIndexes"])
        )
        if self.settings["dropIndexes"] == "auto":
            self.settings["dropIndexes"] = self.calculate_auto2(self.database, 12.0, 500.0)
        if "dropHudCache" in self.settings and self.settings["dropHudCache"] == "auto":
            self.settings["dropHudCache"] = self.calculate_auto2(
                self.database, 25.0, 500.0
            )  # returns "drop"/"don't drop"

        (totstored, totdups, totpartial, totskipped, toterrors) = self.importFiles(None)

        # Tidying up after import
        # if 'dropHudCache' in self.settings and self.settings['dropHudCache'] == 'drop':
        #    log.info(("rebuild_caches"))
        #    self.database.rebuild_caches()
        # else:
        #    log.info(("runPostImport"))
        self.runPostImport()
        self.database.analyzeDB()
        endtime = time()
        return (totstored, totdups, totpartial, totskipped, toterrors, endtime - starttime)

    # end def runImport

    def runPostImport(self):
        self.database.cleanUpTourneyTypes()
        self.database.cleanUpWeeksMonths()
        self.database.resetClean()

    def importFiles(self, q):
        """Read filenames in self.filelist and pass to despatcher."""

        totstored = 0
        totdups = 0
        totpartial = 0
        totskipped = 0
        toterrors = 0
        filecount = 0
        fileerrorcount = 0
        moveimportedfiles = False  # TODO need to wire this into GUI and make it prettier
        movefailedfiles = False  # TODO and this too

        # prepare progress popup window
        ProgressDialog = ImportProgressDialog(len(self.filelist), self.parent)
        ProgressDialog.resize(500, 200)
        ProgressDialog.show()

        for f in self.filelist:
            filecount += 1
            ProgressDialog.progress_update(f, str(self.database.getHandCount()))

            (stored, duplicates, partial, skipped, errors, ttime) = self._import_despatch(self.filelist[f])
            totstored += stored
            totdups += duplicates
            totpartial += partial
            totskipped += skipped
            toterrors += errors

            if moveimportedfiles or movefailedfiles:
                try:
                    if moveimportedfiles:
                        shutil.move(f, "c:\\fpdbimported\\%d-%s" % (filecount, os.path.basename(f[3:])))
                except (shutil.Error, OSError) as e:
                    fileerrorcount += 1
                    log.error(f"Error moving imported file {f}: {e}")
                    if movefailedfiles:
                        try:
                            shutil.move(f, "c:\\fpdbfailed\\%d-%s" % (fileerrorcount, os.path.basename(f[3:])))
                        except (shutil.Error, OSError) as e:
                            log.error(f"Error moving failed file {f}: {e}")

            self.logImport("bulk", f, stored, duplicates, partial, skipped, errors, ttime, self.filelist[f].fileId)

        ProgressDialog.accept()
        del ProgressDialog

        return totstored, totdups, totpartial, totskipped, toterrors

    # end def importFiles

    def _import_despatch(self, fpdbfile):
        stored, duplicates, partial, skipped, errors, ttime = 0, 0, 0, 0, 0, 0
        if fpdbfile.ftype in ("hh", "both"):
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_hh_file(fpdbfile)
        if fpdbfile.ftype == "summary":
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_summary_file(fpdbfile)
        if fpdbfile.ftype == "both" and fpdbfile.path not in self.updatedsize:
            self._import_summary_file(fpdbfile)
        #    pass
        print("DEBUG: _import_summary_file.ttime: %.3f %s" % (ttime, fpdbfile.ftype))
        return (stored, duplicates, partial, skipped, errors, ttime)

    def calculate_auto2(self, db, scale, increment):
        """A second heuristic to determine a reasonable value of drop/don't drop
        This one adds up size of files to import to guess number of hands in them
        Example values of scale and increment params might be 10 and 500 meaning
        roughly: drop if importing more than 10% (100/scale) of hands in db or if
        less than 500 hands in db"""
        size_per_hand = 1300.0  # wag based on a PS 6-up FLHE file. Actual value not hugely important
        # as values of scale and increment compensate for it anyway.
        # decimal used to force float arithmetic

        # get number of hands in db
        if "handsInDB" not in self.settings:
            try:
                tmpcursor = db.get_cursor()
                tmpcursor.execute("SELECT COUNT(1) FROM Hands;")
                self.settings["handsInDB"] = tmpcursor.fetchone()[0]
            except Exception as e:
                log.error(f"Failed to retrieve hands count from database: {e}")
                return "don't drop"

        # add up size of import files
        total_size = 0.0
        for file in self.filelist:
            if os.path.exists(file):
                stat_info = os.stat(file)
                total_size += stat_info.st_size

        # if hands_in_db is zero or very low, we want to drop indexes, otherwise compare
        # import size with db size somehow:
        ret = "don't drop"
        if self.settings["handsInDB"] < scale * (old_div(total_size, size_per_hand)) + increment:
            ret = "drop"
        # print "auto2: handsindb =", self.settings['handsInDB'], "total_size =", total_size, "size_per_hand =", \
        #      size_per_hand, "inc =", increment, "return:", ret
        return ret

    # Run import on updated files, then store latest update time. Called from GuiAutoImport.py
    def runUpdated(self):
        """Check for new files in monitored directories"""
        for site, type in self.dirlist:
            self.addImportDirectory(self.dirlist[(site, type)][0], False, (site, type), self.dirlist[(site, type)][1])

        for f in self.filelist:
            if os.path.exists(f):
                stat_info = os.stat(f)
                if f in self.updatedsize:  # we should be able to assume that if we're in size, we're in time as well
                    if stat_info.st_size > self.updatedsize[f] or stat_info.st_mtime > self.updatedtime[f]:
                        try:
                            if not os.path.isdir(f):
                                self.caller.addText("\n" + os.path.basename(f))
                                print("os.path.basename", os.path.basename(f))
                                print("self.caller:", self.caller)
                                print(os.path.basename(f))
                        except KeyError:
                            log.error("File '%s' seems to have disappeared" % f)
                        (stored, duplicates, partial, skipped, errors, ttime) = self._import_despatch(self.filelist[f])
                        self.logImport(
                            "auto", f, stored, duplicates, partial, skipped, errors, ttime, self.filelist[f].fileId
                        )
                        self.database.commit()
                        try:
                            if not os.path.isdir(f):  # Note: This assumes that whatever calls us has an "addText" func
                                self.caller.addText(
                                    " %d stored, %d duplicates, %d partial, %d skipped, %d errors (time = %f)"
                                    % (stored, duplicates, partial, skipped, errors, ttime)
                                )
                                print("self.caller2:", self.caller)
                        except KeyError:  # TODO: Again, what error happens here? fix when we find out ..
                            pass
                        self.updatedsize[f] = stat_info.st_size
                        self.updatedtime[f] = time()
                else:
                    if os.path.isdir(f) or (time() - stat_info.st_mtime) < 60:
                        self.updatedsize[f] = 0
                        self.updatedtime[f] = 0
                    else:
                        self.updatedsize[f] = stat_info.st_size
                        self.updatedtime[f] = time()
            else:
                self.removeFromFileList[f] = True

        for file in self.removeFromFileList:
            if file in self.filelist:
                del self.filelist[file]

        self.removeFromFileList = {}
        self.database.rollback()
        self.runPostImport()

    def _import_hh_file(self, fpdbfile):
        """Function for actual import of a hh file
        This is now an internal function that should not be called directly."""

        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())

        # Load filter, process file, pass returned filename to import_fpdb_file
        log.info(f"Converting {fpdbfile.path}")

        filter_name = fpdbfile.site.filter_name
        mod = __import__(fpdbfile.site.hhc_fname)
        obj = getattr(mod, filter_name, None)
        if callable(obj):
            if fpdbfile.path in self.pos_in_file:
                idx = self.pos_in_file[fpdbfile.path]
            else:
                self.pos_in_file[fpdbfile.path], idx = 0, 0

            hhc = obj(
                self.config,
                in_path=fpdbfile.path,
                index=idx,
                autostart=False,
                starsArchive=fpdbfile.archive,
                ftpArchive=fpdbfile.archive,
                sitename=fpdbfile.site.name,
            )
            hhc.setAutoPop(self.mode == "auto")
            hhc.start()

            self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()

            # Tally the results
            partial = getattr(hhc, "numPartial")
            skipped = getattr(hhc, "numSkipped")
            errors = getattr(hhc, "numErrors")
            stored = getattr(hhc, "numHands")
            stored -= errors
            stored -= partial
            stored -= skipped

            if stored > 0:
                if self.caller:
                    self.progressNotify()
                handlist = hhc.getProcessedHands()
                self.database.resetBulkCache(True)
                self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()
                (phands, ahands, ihands, to_hud) = ([], [], [], [])
                self.database.resetBulkCache()

                ####Lock Placeholder####
                for hand in handlist:
                    hand.prepInsert(self.database, printtest=self.settings["testData"])
                    ahands.append(hand)
                self.database.commit()
                ####Lock Placeholder####

                for hand in ahands:
                    hand.assembleHand()
                    phands.append(hand)

                ####Lock Placeholder####
                backtrack = False
                id = self.database.nextHandId()
                for i in range(len(phands)):
                    doinsert = len(phands) == i + 1
                    hand = phands[i]
                    try:
                        id = hand.getHandId(self.database, id)
                        hand.updateSessionsCache(self.database, None, doinsert)
                        hand.insertHands(self.database, fpdbfile.fileId, doinsert, self.settings["testData"])
                        hand.updateCardsCache(self.database, None, doinsert)
                        hand.updatePositionsCache(self.database, None, doinsert)
                        hand.updateHudCache(self.database, doinsert)
                        hand.updateTourneyResults(self.database)
                        ihands.append(hand)
                        to_hud.append(hand.dbid_hands)
                    except FpdbHandDuplicate:
                        duplicates += 1
                        if doinsert and ihands:
                            backtrack = True
                    except Exception as e:
                        log.error(f"Importer._import_hh_file: '{fpdbfile.path}' Fatal error: '{e}'")
                        log.error(f"'{hand.handText[0:200]}'")
                        if doinsert and ihands:
                            backtrack = True

                    if backtrack:
                        hand = ihands[-1]
                        hp, hero = hand.handsplayers, hand.hero
                        hand.hero, self.database.hbulk, hand.handsplayers = (
                            0,
                            self.database.hbulk[:-1],
                            [],
                        )  # making sure we don't insert data from this hand
                        self.database.bbulk = [b for b in self.database.bbulk if hand.dbid_hands != b[0]]
                        hand.updateSessionsCache(self.database, None, doinsert)
                        hand.insertHands(self.database, fpdbfile.fileId, doinsert, self.settings["testData"])
                        hand.updateCardsCache(self.database, None, doinsert)
                        hand.updatePositionsCache(self.database, None, doinsert)
                        hand.updateHudCache(self.database, doinsert)
                        hand.handsplayers, hand.hero = hp, hero

                self.database.commit()
                ####Lock Placeholder####

                for i in range(len(ihands)):
                    doinsert = len(ihands) == i + 1
                    hand = ihands[i]
                    hand.insertHandsPlayers(self.database, doinsert, self.settings["testData"])
                    hand.insertHandsActions(self.database, doinsert, self.settings["testData"])
                    hand.insertHandsStove(self.database, doinsert)
                self.database.commit()

                # pipe the Hands.id out to the HUD
                if self.callHud:
                    if self.zmq_sender is None:
                        self.zmq_sender = ZMQSender()
                    for hid in list(to_hud):
                        try:
                            log.debug(f"Sending hand ID {hid} to HUD via socket")
                            self.zmq_sender.send_hand_id(hid)
                        except IOError as e:
                            log.error(f"Failed to send hand ID to HUD via socket: {e}")

                # Cache HHC if enabled
                if self.settings.get("cacheHHC", False):
                    self.handhistoryconverter = hhc
        elif self.mode == "auto":
            return (0, 0, partial, skipped, errors, time() - ttime)

        stored -= duplicates

        if stored > 0 and ihands[0].gametype["type"] == "tour":
            if hhc.summaryInFile:
                fpdbfile.ftype = "both"

        ttime = time() - ttime
        return (stored, duplicates, partial, skipped, errors, ttime)

    def autoSummaryGrab(self, force=False):
        for f, fpdbfile in list(self.filelist.items()):
            stat_info = os.stat(f)
            if ((time() - stat_info.st_mtime) > 300 or force) and fpdbfile.ftype == "both":
                self._import_summary_file(fpdbfile)
                fpdbfile.ftype = "hh"

    def _import_summary_file(self, fpdbfile):
        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())
        mod = __import__(fpdbfile.site.summary)
        obj = getattr(mod, fpdbfile.site.summary, None)
        if callable(obj):
            if self.caller:
                self.progressNotify()
            summaryTexts = self.readFile(obj, fpdbfile.path, fpdbfile.site.name)
            if summaryTexts is None:
                log.error(
                    "Found: '%s' with 0 characters... skipping" % fpdbfile.path
                )  # Fixed the typo (fpbdfile -> fpdbfile)
                return (0, 0, 0, 0, 1, time())  # File had 0 characters
            ####Lock Placeholder####
            for j, summaryText in enumerate(summaryTexts, start=1):
                try:
                    conv = obj(
                        db=self.database,
                        config=self.config,
                        siteName=fpdbfile.site.name,
                        summaryText=summaryText,
                        in_path=fpdbfile.path,
                        header=summaryTexts[0],
                    )
                    self.database.resetBulkCache(False)
                    conv.insertOrUpdate(printtest=self.settings["testData"])
                except FpdbHandPartial:
                    partial += 1
                except FpdbParseError:
                    log.error(f"Summary import parse error in file: {fpdbfile.path}")
                    errors += 1
                if j != 1:
                    print(f"Finished importing {j}/{len(summaryTexts)} tournament summaries")
                stored = j
            ####Lock Placeholder####
        ttime = time() - ttime
        return (stored - errors - partial, duplicates, partial, skipped, errors, ttime)

    def progressNotify(self):
        "A callback to the interface while events are pending"
        QCoreApplication.processEvents()

    def readFile(self, obj, filename, site):
        if filename.endswith(".xls") or filename.endswith(".xlsx") and xlrd:
            obj.hhtype = "xls"
            if site == "PokerStars":
                tourNoField = "Tourney"
            else:
                tourNoField = "tournament key"
            summaryTexts = obj.summaries_from_excel(filename, tourNoField)
        else:
            foabs = obj.readFile(obj, filename)
            if foabs is None:
                return None
            re_Split = obj.getSplitRe(obj, foabs)
            summaryTexts = re.split(re_Split, foabs)
            # Summary identified but not split
            if len(summaryTexts) == 1:
                return summaryTexts
            else:
                # The summary files tend to have a header
                # Remove the first entry if it has < 150 characters
                if len(summaryTexts) > 1 and len(summaryTexts[0]) <= 150:
                    del summaryTexts[0]
                    log.warn(("TourneyImport: Removing text < 150 characters from start of file"))

                # Sometimes the summary files also have a footer
                # Remove the last entry if it has < 100 characters
                if len(summaryTexts) > 1 and len(summaryTexts[-1]) <= 100:
                    summaryTexts.pop()
                    log.warn(("TourneyImport: Removing text < 100 characters from end of file"))
        return summaryTexts

    def __del__(self):
        if hasattr(self, "zmq_sender"):
            self.zmq_sender.close()


class ImportProgressDialog(QDialog):
    """
    Popup window to show progress

    Init method sets up total number of expected iterations
    If no parent is passed to init, command line
    mode assumed, and does not create a progress bar
    """

    def progress_update(self, filename, handcount):
        self.fraction += 1
        # update total if fraction exceeds expected total number of iterations
        if self.fraction > self.total:
            self.total = self.fraction
            self.pbar.setRange(0, self.total)

        self.pbar.setValue(self.fraction)

        self.handcount.setText(("Database Statistics") + " - " + ("Number of Hands:") + " " + handcount)

        now = datetime.datetime.now()
        now_formatted = now.strftime("%H:%M:%S")
        self.progresstext.setText(now_formatted + " - " + ("Importing") + " " + filename + "\n")

    def __init__(self, total, parent):
        if parent is None:
            return
        QDialog.__init__(self, parent)

        self.fraction = 0
        self.total = total
        self.setWindowTitle(("Importing"))

        self.setLayout(QVBoxLayout())

        self.pbar = QProgressBar()
        self.pbar.setRange(0, total)
        self.layout().addWidget(self.pbar)

        self.handcount = QLabel()
        self.handcount.setWordWrap(True)
        self.layout().addWidget(self.handcount)

        self.progresstext = QLabel()
        self.progresstext.setWordWrap(True)
        self.layout().addWidget(self.progresstext)
