#!/usr/bin/env python

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


import datetime
import os
import re
import shutil
import sys
from time import process_time, time

import zmq
from past.utils import old_div
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout

import Configuration
import Database
import IdentifySite
from Exceptions import FpdbHandDuplicate, FpdbHandPartial, FpdbParseError
from loggingFpdb import get_logger

# import L10n
# _ = L10n.get_translation()

#    Standard Library modules


#    fpdb/FreePokerTools modules


try:
    import xlrd
except ImportError:
    xlrd = None

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = get_logger("importer")


class ZMQSender:
    def __init__(self, port="5555") -> None:
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUSH)
        self.socket.bind(f"tcp://127.0.0.1:{port}")
        log.info(f"ZMQ sender initialized on port {port}")

    def send_hand_id(self, hand_id) -> None:
        try:
            self.socket.send_string(str(hand_id))
            log.debug(f"Sent hand ID {hand_id} via ZMQ")
        except zmq.ZMQError as e:
            log.exception(f"Failed to send hand ID {hand_id}: {e}")

    def close(self) -> None:
        self.socket.close()
        self.context.term()
        log.info("ZMQ sender closed")


class Importer:
    def __init__(self, caller, settings, config, sql=None, parent=None) -> None:
        """Constructor."""
        self.settings = settings
        self.caller = caller
        self.config = config
        self.sql = sql
        self.parent = parent

        self.import_issues = []
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
        for _i in range(self.settings["threads"]):
            self.writerdbs.append(Database.Database(self.config, sql=self.sql))

        # Modification : spécifier le port pour ZMQ
        self.zmq_sender = None
        process_time()  # init clock in windows

    # Set functions
    def setMode(self, value) -> None:
        self.mode = value

    def setCallHud(self, value) -> None:
        self.callHud = value

    def setCacheSessions(self, value) -> None:
        self.cacheSessions = value

    def setHandCount(self, value) -> None:
        self.settings["handCount"] = int(value)

    def setQuiet(self, value) -> None:
        self.settings["quiet"] = value

    def setHandsInDB(self, value) -> None:
        self.settings["handsInDB"] = value

    def setThreads(self, value) -> None:
        self.settings["threads"] = value
        if self.settings["threads"] > len(self.writerdbs):
            for _i in range(self.settings["threads"] - len(self.writerdbs)):
                self.writerdbs.append(Database.Database(self.config, sql=self.sql))

    def setDropIndexes(self, value) -> None:
        self.settings["dropIndexes"] = value

    def setDropHudCache(self, value) -> None:
        self.settings["dropHudCache"] = value

    def setStarsArchive(self, value) -> None:
        self.settings["starsArchive"] = value

    def setFTPArchive(self, value) -> None:
        self.settings["ftpArchive"] = value

    def setPrintTestData(self, value) -> None:
        self.settings["testData"] = value

    def setFakeCacheHHC(self, value) -> None:
        self.settings["cacheHHC"] = value

    def getCachedHHC(self):
        return self.handhistoryconverter

    #   def setWatchTime(self):
    #       self.updated = time()

    def clearFileList(self) -> None:
        self.updatedsize = {}
        self.updatetime = {}
        self.pos_in_file = {}
        self.filelist = {}

    def logImport(self, type, file, stored, dups, partial, skipped, errs, ttime, id) -> None:
        hands = stored + dups + partial + skipped + errs
        now = datetime.datetime.utcnow()
        ttime100 = ttime * 100
        self.database.updateFile(
            [
                type,
                now,
                now,
                hands,
                stored,
                dups,
                partial,
                skipped,
                errs,
                ttime100,
                True,
                id,
            ],
        )
        self.database.commit()

    def addFileToList(self, fpdbfile) -> None:
        """FPDBFile."""
        file = os.path.splitext(os.path.basename(fpdbfile.path))[0]
        try:  # TODO: this is a dirty hack. GBI needs it, GAI fails with it.
            file = str(file, "utf8", "replace")
        except TypeError:
            pass
        fpdbfile.fileId = self.database.get_id(file)
        if not fpdbfile.fileId:
            now = datetime.datetime.utcnow()
            fpdbfile.fileId = self.database.storeFile(
                [file, fpdbfile.site.name, now, now, 0, 0, 0, 0, 0, 0, 0, False],
            )
            self.database.commit()

    # Add an individual file to filelist
    def addImportFile(self, filename, site="auto") -> bool:
        # DEBUG->print("addimportfile: filename is a", filename.__class__, filename)
        # filename not guaranteed to be unicode
        if self.filelist.get(filename) is not None or not os.path.exists(filename):
            return False

        self.idsite.processFile(filename)
        if self.idsite.get_fobj(filename):
            fpdbfile = self.idsite.filelist[filename]
        else:
            log.warning(f"siteId Failed for: '{filename}'")
            return False

        self.addFileToList(fpdbfile)
        self.filelist[filename] = fpdbfile
        if site not in self.siteIds:
            # Get id from Sites table in DB
            result = self.database.get_site_id(fpdbfile.site.name)
            if len(result) == 1:
                self.siteIds[fpdbfile.site.name] = result[0][0]
            elif len(result) == 0:
                log.warning(f"Database ID for {fpdbfile.site.name} not found")
            else:
                log.warning(
                    f"More than 1 Database ID found for {fpdbfile.site.name}",
                )

        return True

    # Called from GuiBulkImport to add a file or directory. Bulk import never monitors
    def addBulkImportImportFileOrDir(self, inputPath, site="auto"):
        """Add a file or directory for bulk import."""
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
        return self.addImportFile(inputPath, site=site)

    # Add a directory of files to filelist
    # Only one import directory per site supported.
    # dirlist is a hash of lists:
    # dirlist{ 'PokerStars' => ["/path/to/import/", "filtername"] }
    def addImportDirectory(
        self, dir, monitor=False, site=("default", "hh"), filter="passthrough",
    ) -> None:
        # gets called by GuiAutoImport.
        # This should really be using os.walk
        # http://docs.python.org/library/os.html
        if os.path.isdir(dir):
            if monitor is True:
                self.monitor = True
                self.dirlist[site] = [dir, filter]

            # print "addImportDirectory: checking files in", dir
            for subdir in os.walk(dir):
                for file in subdir[2]:
                    filename = os.path.join(subdir[0], file)
                    # ignore symbolic links (Linux & Mac)
                    if os.path.islink(filename):
                        log.info(f"Ignoring symlink {filename}")
                        continue
                    if (
                        time() - os.stat(filename).st_mtime
                    ) <= 43200:  # look all files modded in the last 12 hours
                        # need long time because FTP in Win does not
                        # update the timestamp on the HH during session
                        self.addImportFile(filename, "auto")
        else:
            log.warning(
                f"Attempted to add non-directory '{dir!s}' as an import directory",
            )

    def runImport(self):
        """ "Run full import on self.filelist. This is called from GuiBulkImport.py."""
        # Initial setup
        start = datetime.datetime.now()
        starttime = time()
        log.info(
            f"Started at {start} -- {len(self.filelist)} files to import. indexes: {self.settings['dropIndexes']}",
        )
        if self.settings["dropIndexes"] == "auto":
            self.settings["dropIndexes"] = self.calculate_auto2(
                self.database, 12.0, 500.0,
            )
        if "dropHudCache" in self.settings and self.settings["dropHudCache"] == "auto":
            self.settings["dropHudCache"] = self.calculate_auto2(
                self.database, 25.0, 500.0,
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
        return (
            totstored,
            totdups,
            totpartial,
            totskipped,
            toterrors,
            endtime - starttime,
        )

    # end def runImport

    def runPostImport(self) -> None:
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
        moveimportedfiles = (
            False  # TODO need to wire this into GUI and make it prettier
        )
        movefailedfiles = False  # TODO and this too

        # prepare progress popup window
        ProgressDialog = ImportProgressDialog(len(self.filelist), self.parent)
        ProgressDialog.resize(500, 200)
        ProgressDialog.show()

        for f in self.filelist:
            filecount += 1
            ProgressDialog.progress_update(f, str(self.database.getHandCount()))

            try:
                (stored, duplicates, partial, skipped, errors, ttime, _) = (
                    self._import_despatch(self.filelist[f])
                )
                totstored += stored
                totdups += duplicates
                totpartial += partial
                totskipped += skipped
                toterrors += errors

                self.logImport(
                    "bulk",
                    f,
                    stored,
                    duplicates,
                    partial,
                    skipped,
                    errors,
                    ttime,
                    self.filelist[f].fileId,
                )
            except Exception as e:
                log.exception(f"A fatal error occurred while processing file: {f}. Error: {e}")
                toterrors += 1
                continue

            if moveimportedfiles or movefailedfiles:
                try:
                    if moveimportedfiles:
                        shutil.move(
                            f,
                            "c:\\fpdbimported\\%d-%s"
                            % (filecount, os.path.basename(f[3:])),
                        )
                except (shutil.Error, OSError) as e:
                    fileerrorcount += 1
                    log.exception(f"Error moving imported file {f}: {e}")
                    if movefailedfiles:
                        try:
                            shutil.move(
                                f,
                                "c:\\fpdbfailed\\%d-%s"
                                % (fileerrorcount, os.path.basename(f[3:])),
                            )
                        except (shutil.Error, OSError) as e:
                            log.exception(f"Error moving failed file {f}: {e}")

        ProgressDialog.accept()
        del ProgressDialog

        return totstored, totdups, totpartial, totskipped, toterrors

    # end def importFiles

    def _import_despatch(self, fpdbfile):
        stored, duplicates, partial, skipped, errors, ttime = 0, 0, 0, 0, 0, 0
        detected_sitename = None
        if fpdbfile.ftype in ("hh", "both"):
            (stored, duplicates, partial, skipped, errors, ttime, detected_sitename) = (
                self._import_hh_file(fpdbfile)
            )
        if fpdbfile.ftype == "summary":
            (stored, duplicates, partial, skipped, errors, ttime) = (
                self._import_summary_file(fpdbfile)
            )
        if fpdbfile.ftype == "both" and fpdbfile.path not in self.updatedsize:
            self._import_summary_file(fpdbfile)
        #    pass
        log.debug(f"_import_summary_file.ttime: {ttime:.3f} {fpdbfile.ftype}")

        return (stored, duplicates, partial, skipped, errors, ttime, detected_sitename)

    def calculate_auto2(self, db, scale, increment):
        """A second heuristic to determine a reasonable value of drop/don't drop
        This one adds up size of files to import to guess number of hands in them
        Example values of scale and increment params might be 10 and 500 meaning
        roughly: drop if importing more than 10% (100/scale) of hands in db or if
        less than 500 hands in db.
        """
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
                log.exception(f"Failed to retrieve hands count from database: {e}")
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
        if (
            self.settings["handsInDB"]
            < scale * (old_div(total_size, size_per_hand)) + increment
        ):
            ret = "drop"
        # print "auto2: handsindb =", self.settings['handsInDB'], "total_size =", total_size, "size_per_hand =", \
        #      size_per_hand, "inc =", increment, "return:", ret
        return ret

    # Run import on updated files, then store latest update time. Called from GuiAutoImport.py
    def runUpdated(self) -> None:
        """Check for new files in monitored directories."""
        for site, type in self.dirlist:
            self.addImportDirectory(
                self.dirlist[(site, type)][0],
                False,
                (site, type),
                self.dirlist[(site, type)][1],
            )

        for f in self.filelist:
            if os.path.exists(f):
                stat_info = os.stat(f)
                if (
                    f in self.updatedsize
                ):  # we should be able to assume that if we're in size, we're in time as well
                    if (
                        stat_info.st_size > self.updatedsize[f]
                        or stat_info.st_mtime > self.updatedtime[f]
                    ):
                        try:
                            if not os.path.isdir(f):
                                # Extract site name from the file object
                                site_name = self.filelist[f].site.name if self.filelist[f] and self.filelist[f].site else "Unknown"

                                # Extract hand number from filename (assuming it's in the filename)
                                import re
                                hand_match = re.search(r"(\d{6,})", os.path.basename(f))
                                hand_number = hand_match.group(1) if hand_match else "N/A"

                                log.debug(f"os.path.basename: {os.path.basename(f)}")
                                log.debug(f"self.caller: {self.caller}")
                                log.debug(os.path.basename(f))
                        except KeyError:
                            log.exception(f"File '{f}' seems to have disappeared")

                        (stored, duplicates, partial, skipped, errors, ttime, detected_sitename) = (
                            self._import_despatch(self.filelist[f])
                        )
                        self.logImport(
                            "auto",
                            f,
                            stored,
                            duplicates,
                            partial,
                            skipped,
                            errors,
                            ttime,
                            self.filelist[f].fileId,
                        )
                        self.database.commit()
                        try:
                            if not os.path.isdir(f):
                                # Use detected sitename if available, otherwise fall back to config sitename
                                site_name = detected_sitename or (self.filelist[f].site.name if self.filelist[f] and self.filelist[f].site else "Unknown")

                                # Extract hand number from filename
                                import re
                                hand_match = re.search(r"(\d{6,})", os.path.basename(f))
                                hand_number = hand_match.group(1) if hand_match else os.path.basename(f)[:20]

                                event_text = f"{site_name} - {hand_number}"

                                # Determine status
                                if errors > 0:
                                    status = "error"
                                    event_text += " KO"
                                elif stored > 0:
                                    status = "import"
                                    event_text += " OK"
                                elif duplicates > 0:
                                    status = "warning"
                                    event_text += " (duplicate)"
                                elif skipped > 0:
                                    status = "warning"
                                    event_text += " (skipped)"
                                else:
                                    status = "info"
                                    event_text += " (no changes)"

                                # Add details if there were any actions
                                if stored > 0 or duplicates > 0 or partial > 0 or skipped > 0 or errors > 0:
                                    details = []
                                    if stored > 0:
                                        details.append(f"{stored} stored")
                                    if duplicates > 0:
                                        details.append(f"{duplicates} duplicates")
                                    if partial > 0:
                                        details.append(f"{partial} partial")
                                    if skipped > 0:
                                        details.append(f"{skipped} skipped")
                                    if errors > 0:
                                        details.append(f"{errors} errors")
                                    event_text += f" ({', '.join(details)})"

                                self.caller.addText(f"\n{event_text}", status)

                                log.debug(f"self.caller2: {self.caller}")
                        except (
                            KeyError
                        ):  # TODO: Again, what error happens here? fix when we find out ..
                            log.exception(
                                f"KeyError encountered while processing file: {f}",
                            )
                        self.updatedsize[f] = stat_info.st_size
                        self.updatedtime[f] = time()
                elif os.path.isdir(f) or (time() - stat_info.st_mtime) < 60:
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
        This is now an internal function that should not be called directly.
        """
        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())
        detected_sitename = None  # Will store the sitename detected by the parser

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

            # Add parsing issues to the main importer's list
            for issue in hhc.parsing_issues:
                self.import_issues.append(f"In {fpdbfile.path}: {issue}")

            # Capture the detected sitename from the parser (for iPoker skin detection)
            detected_sitename = getattr(hhc, "sitename", None)

            self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()

            # Tally the results
            partial = hhc.numPartial
            skipped = hhc.numSkipped
            errors = hhc.numErrors
            stored = hhc.numHands
            stored -= errors
            stored -= partial
            stored -= skipped

            # Initialize variables that are used later in the function
            (phands, ahands, ihands, to_hud) = ([], [], [], [])

            if stored > 0:
                if self.caller:
                    self.progressNotify()
                handlist = hhc.getProcessedHands()
                self.database.resetBulkCache(True)
                self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()
                self.database.resetBulkCache()

                ####Lock Placeholder####
                for hand in handlist:
                    hand.prepInsert(self.database, printtest=self.settings["testData"])
                    ahands.append(hand)
                self.database.commit()
                ####Lock Placeholder####

                for hand in ahands:
                    hand.assembleHand()
                    log.debug(f"final import of hand: {hand}")
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
                        hand.insertHands(
                            self.database,
                            fpdbfile.fileId,
                            doinsert,
                            self.settings["testData"],
                        )
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
                    except FpdbHandPartial as e:
                        partial += 1
                        self.import_issues.append(f"[PARTIAL] In {fpdbfile.path}: Hand starting with '{hand.handText[:30]}...' - {e}")
                    except Exception as e:
                        errors += 1
                        self.import_issues.append(f"[ERROR] In {fpdbfile.path}: Hand starting with '{hand.handText[:30]}...' - {e}")
                        log.exception(
                            f"Importer._import_hh_file: '{fpdbfile.path}' Fatal error: '{e}'",
                        )
                        log.exception(f"'{hand.handText[0:200]}'")
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
                        self.database.bbulk = [
                            b for b in self.database.bbulk if hand.dbid_hands != b[0]
                        ]
                        hand.updateSessionsCache(self.database, None, doinsert)
                        hand.insertHands(
                            self.database,
                            fpdbfile.fileId,
                            doinsert,
                            self.settings["testData"],
                        )
                        hand.updateCardsCache(self.database, None, doinsert)
                        hand.updatePositionsCache(self.database, None, doinsert)
                        hand.updateHudCache(self.database, doinsert)
                        hand.handsplayers, hand.hero = hp, hero

                self.database.commit()
                ####Lock Placeholder####

                for i in range(len(ihands)):
                    doinsert = len(ihands) == i + 1
                    hand = ihands[i]
                    hand.insertHandsPlayers(
                        self.database, doinsert, self.settings["testData"],
                    )
                    hand.insertHandsActions(
                        self.database, doinsert, self.settings["testData"],
                    )
                    hand.insertHandsStove(self.database, doinsert)
                self.database.commit()

                # pipe the Hands.id out to the HUD
                if self.callHud:
                    if self.zmq_sender is None:
                        self.zmq_sender = ZMQSender()
                    for hid in to_hud:
                        try:
                            log.debug(f"Sending hand ID {hid} to HUD via socket")
                            self.zmq_sender.send_hand_id(hid)
                        except OSError as e:
                            log.exception(f"Failed to send hand ID to HUD via socket: {e}")

                # Cache HHC if enabled
                if self.settings.get("cacheHHC", False):
                    self.handhistoryconverter = hhc
        elif self.mode == "auto":
            return (0, 0, partial, skipped, errors, time() - ttime, detected_sitename)

        stored -= duplicates

        # Mark file for summary processing if it's a tournament with summary in file
        # Process even if stored=0 (duplicates) to ensure tournament summaries are processed
        # Use phands instead of ihands to include duplicates
        if len(phands) > 0:
            gametype = phands[0].gametype
            log.debug("Checking summary conditions:")
            log.debug(f"  len(phands): {len(phands)}")
            log.debug(f"  gametype: {gametype}")
            log.debug(f"  gametype['type']: {gametype.get('type', 'NOT_FOUND')}")
            log.debug(f"  summaryInFile: {getattr(hhc, 'summaryInFile', 'NOT_FOUND')}")
            log.debug(f"  hhc type: {type(hhc)}")
            log.debug(f"  hhc sitename: {getattr(hhc, 'sitename', 'NOT_FOUND')}")

            if gametype.get("type") == "tour" and getattr(hhc, "summaryInFile", False):
                fpdbfile.ftype = "both"
                log.info(f"✅ File {fpdbfile.path} marked as 'both' for summary processing")
            else:
                log.warning(f"❌ File {fpdbfile.path} NOT marked for summary processing")
                log.warning(f"   - type is '{gametype.get('type')}' (expected 'tour')")
                log.warning(f"   - summaryInFile is '{getattr(hhc, 'summaryInFile', False)}' (expected True)")
        else:
            log.warning("❌ No phands available for summary checking")

        ttime = time() - ttime
        return (stored, duplicates, partial, skipped, errors, ttime, detected_sitename)

    def autoSummaryGrab(self, force=False) -> None:
        log.debug(f"autoSummaryGrab called with force={force}")
        log.debug(f"Total files in filelist: {len(self.filelist)}")

        both_files_count = 0
        for f, fpdbfile in list(self.filelist.items()):
            log.debug(f"Processing file: {f}, ftype: {fpdbfile.ftype}")

            if fpdbfile.ftype == "both":
                both_files_count += 1
                stat_info = os.stat(f)
                file_age = time() - stat_info.st_mtime
                log.debug(f"File {f} marked as 'both', age: {file_age:.1f}s, force: {force}")

                if file_age > 300 or force:
                    log.debug(f"Processing summary for file: {f}")
                    self._import_summary_file(fpdbfile)
                    fpdbfile.ftype = "hh"
                    log.debug(f"Summary processing completed for: {f}")
                else:
                    log.debug(f"File {f} too recent (age: {file_age:.1f}s), skipping summary processing")

        log.debug(f"autoSummaryGrab completed. Files marked as 'both': {both_files_count}")

    def _import_summary_file(self, fpdbfile):
        log.debug(f"_import_summary_file called for: {fpdbfile.path}")
        log.debug(f"Site: {fpdbfile.site.name}, Summary module: {fpdbfile.site.summary}")

        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())

        try:
            mod = __import__(fpdbfile.site.summary)
            log.debug(f"Successfully imported module: {fpdbfile.site.summary}")
        except ImportError as e:
            log.error(f"Failed to import summary module {fpdbfile.site.summary}: {e}")
            return (0, 0, 0, 0, 1, time())

        obj = getattr(mod, fpdbfile.site.summary, None)
        log.debug(f"Summary class object: {obj}")

        if callable(obj):
            if self.caller:
                self.progressNotify()
            summaryTexts = self.readFile(obj, fpdbfile.path, fpdbfile.site.name)
            log.debug(f"readFile returned: {type(summaryTexts)}, length: {len(summaryTexts) if summaryTexts else 0}")

            if summaryTexts is None:
                log.warning(
                    f"Found: '{fpdbfile.path}' with 0 characters... skipping",
                )
                return (0, 0, 0, 0, 1, time())  # File had 0 characters

            log.debug(f"Processing {len(summaryTexts)} summary texts")
            ####Lock Placeholder####
            for j, summaryText in enumerate(summaryTexts, start=1):
                log.debug(f"Processing summary {j}/{len(summaryTexts)}, length: {len(summaryText)}")
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
                    self.import_issues.append(f"[PARTIAL] In {fpdbfile.path}: Summary starting with '{summaryText[:30]}...'")
                except FpdbParseError:
                    log.exception(f"Summary import parse error in file: {fpdbfile.path}")
                    errors += 1
                    self.import_issues.append(f"[ERROR] In {fpdbfile.path}: Summary starting with '{summaryText[:30]}...'")
                if j != 1:
                    log.info(
                        f"Finished importing {j}/{len(summaryTexts)} tournament summaries",
                    )
                stored = j
            ####Lock Placeholder####
        ttime = time() - ttime
        log.debug(
            f"Import summary completed: {stored} stored, {duplicates} duplicates, {partial} partial, {skipped} skipped, {errors} errors in {ttime:.3f} seconds",
        )
        return (stored - errors - partial, duplicates, partial, skipped, errors, ttime)

    def progressNotify(self) -> None:
        """A callback to the interface while events are pending."""
        QCoreApplication.processEvents()

    def readFile(self, obj, filename, site):
        if filename.endswith(".xls") or filename.endswith(".xlsx") and xlrd:
            obj.hhtype = "xls"
            tourNoField = "Tourney" if site == "PokerStars" else "tournament key"
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
            # The summary files tend to have a header
            # Remove the first entry if it has < 150 characters
            if len(summaryTexts) > 1 and len(summaryTexts[0]) <= 150:
                del summaryTexts[0]
                log.warning(
                    (
                        "TourneyImport: Removing text < 150 characters from start of file"
                    ),
                )

            # Sometimes the summary files also have a footer
            # Remove the last entry if it has < 100 characters
            if len(summaryTexts) > 1 and len(summaryTexts[-1]) <= 100:
                summaryTexts.pop()
                log.warning(
                    (
                        "TourneyImport: Removing text < 100 characters from end of file"
                    ),
                )
        return summaryTexts

    def cleanup(self):
        """Explicitly clean up resources to prevent database timeouts."""
        if hasattr(self, "database") and self.database is not None:
            try:
                self.database.cleanup_connections()
                log.debug("Importer database connections cleaned up.")
            except Exception as e:
                log.warning(f"Error during importer cleanup: {e}")

    def __del__(self) -> None:
        if hasattr(self, "zmq_sender") and self.zmq_sender is not None:
            self.zmq_sender.close()
        # Clean up database connections to prevent timeout issues
        if hasattr(self, "database") and self.database is not None:
            try:
                self.database.cleanup_connections()
            except:
                pass  # Ignore errors during cleanup


class ImportProgressDialog(QDialog):
    """Popup window to show progress.

    Init method sets up total number of expected iterations
    If no parent is passed to init, command line
    mode assumed, and does not create a progress bar
    """

    def __init__(self, total, parent) -> None:
        self.parent = parent
        self.fraction = 0
        self.total = total

        if self.parent is None or self.parent == "CLI_NO_PROGRESS":
            # Command line mode, no GUI
            return

        # GUI Mode
        QDialog.__init__(self, parent)
        self.setWindowTitle("Importing")
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

    def progress_update(self, filename, handcount) -> None:
        self.fraction += 1

        if self.parent is None:
            # Command line mode
            if self.total > 0:
                try:
                    progress = self.fraction / self.total
                    bar_length = 40
                    filled_len = int(round(bar_length * progress))
                    bar = "█" * filled_len + "─" * (bar_length - filled_len)
                    percentage = round(progress * 100, 1)
                    # Use sys.stdout.write for continuous line update
                    sys.stdout.write(f"\rProgress: |{bar}| {percentage}% Complete - {os.path.basename(filename)}")
                    sys.stdout.flush()
                except (ZeroDivisionError, ValueError):
                    pass # Avoid errors if total is 0 for some reason
            return
        if self.parent == "CLI_NO_PROGRESS":
            return # No output at all

        # GUI mode
        # update total if fraction exceeds expected total number of iterations
        if self.fraction > self.total:
            self.total = self.fraction
            self.pbar.setRange(0, self.total)

        self.pbar.setValue(self.fraction)

        self.handcount.setText(
            ("Database Statistics") + " - " + ("Number of Hands:") + " " + handcount,
        )

        now = datetime.datetime.now()
        now_formatted = now.strftime("%H:%M:%S")
        self.progresstext.setText(
            now_formatted + " - " + ("Importing") + " " + filename + "\n",
        )

    def accept(self):
        if self.parent is None:
            sys.stdout.write("\n") # Newline after progress bar finishes
            return
        if self.parent == "CLI_NO_PROGRESS":
            return
        super().accept()

    def resize(self, *args):
        if self.parent is None or self.parent == "CLI_NO_PROGRESS":
            return
        super().resize(*args)

    def show(self):
        if self.parent is None or self.parent == "CLI_NO_PROGRESS":
            return
        super().show()

