#!/usr/bin/env python
from __future__ import annotations

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
import builtins
import contextlib
import datetime
import os
import re
import shutil
import sys
from collections.abc import Callable
from time import process_time, time
from typing import Any

import zmq as _zmq
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout

from fpdb_3_legacy import Configuration, Database, IdentifySite, db_profile
from fpdb_3_legacy.Exceptions import (
    FpdbHandDuplicate,
    FpdbHandPartial,
    FpdbParseError,
    FpdbSummaryNotFound,
)
from fpdb_3_legacy.import_failure_cache import SIDECAR_EXTENSIONS, FailureCache
from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path as get_ipoker_parser_class_for_path
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.parser_registry import get_parser_class, get_summary_class

zmq: Any = _zmq

# Event-driven imports (optional, for new architecture)
try:
    from fpdb.domain.events.domain_events import BatchImportCompletedEvent, HandImportedEvent
except ImportError:
    BatchImportCompletedEvent = None
    HandImportedEvent = None

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

IMPORTER_FILE_READ_ERRORS = (OSError, UnicodeDecodeError)
ZMQ_CLOSE_ERRORS = (RuntimeError, zmq.ZMQError)

# Round-trip profiling (off unless FPDB_DB_PROFILE=1). Module-level rather than
# per-Importer: the profile it reports is process-wide anyway, and a profiling
# hook must not be something the import path can trip over.
_profile_reporter = db_profile.DeltaReporter("Auto-import round-trip profile:")


class ZMQSender:
    """ZMQ sender for sending hand IDs to the HUD."""

    def __init__(self, port="5555") -> None:
        """Initialize the ZMQSender and connect to the specified port.

        Args:
            port (str, optional): The port to connect to on localhost. Defaults to "5555".
        """
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUSH)
        # Set high water mark to prevent memory issues
        self.socket.setsockopt(zmq.SNDHWM, 1000)
        # Set send timeout to prevent blocking forever
        self.socket.setsockopt(zmq.SNDTIMEO, 100)  # 100ms timeout
        self.socket.connect(f"tcp://127.0.0.1:{port}")
        log.info(f"ZMQ sender connected to port {port}")

    def send_hand_id(self, hand_id) -> None:
        """Send a hand ID to the connected ZMQ server.

        Args:
            hand_id: The hand ID to send.
        """
        try:
            self.socket.send_string(str(hand_id), zmq.NOBLOCK)
            log.debug(f"Sent hand ID {hand_id} via ZMQ")
        except zmq.Again:
            log.warning(f"ZMQ queue full, dropping hand ID {hand_id}")
        except zmq.ZMQError as e:
            log.exception(f"Failed to send hand ID {hand_id}: {e}")

    def close(self) -> None:
        """Close the ZMQ socket and terminate the context.

        This method releases all ZMQ resources and logs the closure of the sender.
        """
        try:
            # Set linger to 0 to close immediately without waiting for pending messages
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.close()
            # Terminate context with a timeout to prevent hanging
            self.context.term()
            log.info("ZMQ sender closed")
        except ZMQ_CLOSE_ERRORS as e:
            log.warning(f"Error during ZMQ sender close: {e}")
            # Force termination if there's an error
            with contextlib.suppress(builtins.BaseException):
                self.context.term()


class Importer:
    """Importer class for handling file imports and processing."""

    def __init__(self, caller, settings, config, sql=None, parent=None, event_bus=None) -> None:
        """Initialize the Importer for handling file imports and processing.

        Sets up configuration, database connections, and prepares internal state for importing files.

        Args:
            caller: The object that initiated the import process.
            settings: A dictionary of import settings.
            config: The configuration object.
            sql: Optional SQL connection or cursor.
            parent: Optional parent object, typically for GUI integration.
            event_bus: Optional EventBus for publishing domain events.
        """
        self.settings = settings
        self.caller = caller
        self.config = config
        self.sql = sql
        self.parent = parent
        self.event_bus = event_bus

        self.import_issues: list[Any] = []
        self.idsite = IdentifySite.IdentifySite(config)

        self.filelist: dict[str, IdentifySite.FPDBFile] = {}
        self.failed_files = FailureCache()
        self.dirlist: dict[Any, list[Any]] = {}
        self.siteIds: dict[str, int] = {}
        self.removeFromFileList: dict[str, bool] = {}  # to remove deleted files
        self.monitor = False
        self.updatedsize: dict[str, int] = {}
        self.updatedtime: dict[str, float] = {}
        self.lines = None
        self.faobs = None  # File as one big string
        self.mode = None
        self.pos_in_file: dict[str, int] = {}  # dict to remember how far we have read in the file

        # Configuration of default parameters
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
        # Populated only when cacheHHC is on (see runImport).
        self.handhistoryconverter: Any = None
        self.cached_hhcs: dict[str, Any] = {}

        self.writeq = None
        self.database = Database.Database(self.config, sql=self.sql)
        # Explicit ids copied into PostgreSQL do not advance BIGSERIAL. Repair
        # every owned id sequence before auto/bulk import starts inserting rows.
        with self.database.transaction():
            self.database.repair_sequences()
        self.writerdbs = []
        self.settings.setdefault("threads", 1)
        for _i in range(self.settings["threads"]):
            self.writerdbs.append(Database.Database(self.config, sql=self.sql))

        # Modification: specify port for ZMQ
        self.zmq_sender: ZMQSender | None = None

        # HandDataReporter for quality analysis
        self.hand_data_reporter = None

        process_time()  # init clock in windows
        self.progress_start_cb: Callable[[int], None] | None = None
        self.progress_update_cb: Callable[[str, str], None] | None = None
        self.progress_end_cb: Callable[[], None] | None = None

    def set_progress_callbacks(
        self,
        start_cb: Callable[[int], None],
        update_cb: Callable[[str, str], None],
        end_cb: Callable[[], None],
    ) -> None:
        """Configure progress callbacks for thread-safe UI updates."""
        self.progress_start_cb = start_cb
        self.progress_update_cb = update_cb
        self.progress_end_cb = end_cb

    # Set functions
    def setMode(self, value) -> None:
        """Set the import mode for the Importer.

        Updates the mode attribute to control how files are processed during import.

        Args:
            value: The mode to set for the importer.
        """
        self.mode = value

    def setCallHud(self, value) -> None:
        """Enable or disable HUD calls during import.

        Sets the callHud attribute to control whether the HUD is notified during file imports.

        Args:
            value: Boolean or value indicating whether to call the HUD.
        """
        self.callHud = value

    def setCacheSessions(self, value) -> None:
        """Enable or disable session caching during import.

        Sets the cacheSessions attribute to control whether session data is cached.

        Args:
            value: Boolean or value indicating whether to cache sessions.
        """
        self.cacheSessions = value

    def setHandCount(self, value) -> None:
        """Set the hand count value in the import settings.

        Updates the 'handCount' setting to the specified integer value.

        Args:
            value: The new hand count to set.
        """
        self.settings["handCount"] = int(value)

    def setQuiet(self, value) -> None:
        """Set the quiet mode for the importer.

        Updates the 'quiet' setting to control the verbosity of the import process.

        Args:
            value: Boolean or value indicating whether to enable quiet mode.
        """
        self.settings["quiet"] = value

    def setHandsInDB(self, value) -> None:
        """Set the number of hands in the database.

        Updates the 'handsInDB' setting to the specified value.

        Args:
            value: The new number of hands to set in the database.
        """
        self.settings["handsInDB"] = value

    def setThreads(self, value) -> None:
        """Set the number of threads used for importing.

        Updates the 'threads' setting and ensures the writer database list matches the thread count.

        Args:
            value: The number of threads to use for importing.
        """
        self.settings["threads"] = value
        if self.settings["threads"] > len(self.writerdbs):
            for _i in range(self.settings["threads"] - len(self.writerdbs)):
                self.writerdbs.append(Database.Database(self.config, sql=self.sql))

    def setDropIndexes(self, value) -> None:
        """Set the dropIndexes setting for the importer.

        Updates the 'dropIndexes' setting to control index dropping behavior during import.

        Args:
            value: The value to set for the dropIndexes setting.
        """
        self.settings["dropIndexes"] = value

    def setHandDataReporter(self, reporter) -> None:
        """Enable HandDataReporter for detailed import analysis.

        Args:
            reporter: HandDataReporter instance
        """
        self.hand_data_reporter = reporter
        log.info(f"HandDataReporter enabled with level: {reporter.report_level}")

    def setDropHudCache(self, value) -> None:
        """Set the dropHudCache setting for the importer.

        Updates the 'dropHudCache' setting to control HUD cache dropping behavior during import.

        Args:
            value: The value to set for the dropHudCache setting.
        """
        self.settings["dropHudCache"] = value

    def setStarsArchive(self, value) -> None:
        """Set the starsArchive setting for the importer.

        Updates the 'starsArchive' setting to control PokerStars hand history archiving.

        Args:
            value: The value to set for the starsArchive setting.
        """
        self.settings["starsArchive"] = value

    def setFTPArchive(self, value) -> None:
        """Set the ftpArchive setting for the importer.

        Updates the 'ftpArchive' setting to control FTP hand history archiving.

        Args:
            value: The value to set for the ftpArchive setting.
        """
        self.settings["ftpArchive"] = value

    def setPrintTestData(self, value) -> None:
        """Set the testData setting for the importer.

        Updates the 'testData' setting to control whether test data is printed during import.

        Args:
            value: The value to set for the testData setting.
        """
        self.settings["testData"] = value

    def setFakeCacheHHC(self, value) -> None:
        """Set the cacheHHC setting for the importer.

        Updates the 'cacheHHC' setting to control fake hand history converter caching.

        Args:
            value: The value to set for the cacheHHC setting.
        """
        self.settings["cacheHHC"] = value

    def getCachedHHC(self, path: str | None = None):
        """Retrieve a cached hand history converter (``None`` when there is none).

        Args:
            path: return the converter for that file; defaults to the last one
                imported. Caching only happens when ``cacheHHC`` is enabled, so
                this used to raise AttributeError instead of answering "nothing
                cached".

        Returns:
            The cached hand history converter instance, or None.
        """
        if path is not None:
            return self.cached_hhcs.get(path, None)
        return self.handhistoryconverter

    #   def setWatchTime(self):
    #       self.updated = time()

    def clearFileList(self) -> None:
        """Clear all tracked file lists and related state.

        Resets the updated size, update time, file position, and file list dictionaries to empty.
        """
        self.updatedsize = {}
        self.updatedtime = {}
        self.pos_in_file = {}
        self.filelist = {}
        # Reassigned rather than cleared in place: callers that build an
        # Importer without running __init__ rely on this creating the cache.
        self.failed_files = FailureCache()

    def logImport(self, type, file, stored, dups, partial, skipped, errs, ttime, id) -> None:
        """Log the results of an import operation to the database.

        Records import statistics such as the number of hands processed, duplicates, partials, skipped, errors, and timing information.

        Args:
            type: The type of import operation.
            file: The file being imported.
            stored: Number of hands successfully stored.
            dups: Number of duplicate hands found.
            partial: Number of partially imported hands.
            skipped: Number of skipped hands.
            errs: Number of errors encountered.
            ttime: Time taken for the import operation.
            id: The database ID associated with the file.
        """
        hands = stored + dups + partial + skipped + errs
        now = datetime.datetime.utcnow()
        ttime100 = ttime * 100
        with self.database.transaction():
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

    def addFileToList(self, fpdbfile) -> None:
        """Add a file to the database and assign a file ID.

        Extracts the file name, retrieves or stores its ID in the database, and updates the file object.

        Args:
            fpdbfile: The file object to add and update with a file ID.
        """
        if fpdbfile.site is None:
            msg = f"Cannot register unidentified file: {fpdbfile.path}"
            raise ValueError(msg)
        file = os.path.splitext(os.path.basename(fpdbfile.path))[0]
        # Filenames are str on Python 3; decode only if a bytes path slips in.
        if isinstance(file, bytes):
            file = file.decode("utf8", "replace")
        fpdbfile.fileId = self.database.get_id(file)
        if not fpdbfile.fileId:
            now = datetime.datetime.utcnow()
            with self.database.transaction():
                fpdbfile.fileId = self.database.storeFile(
                    [file, fpdbfile.site.name, now, now, 0, 0, 0, 0, 0, 0, 0, False],
                )

    # Add an individual file to filelist
    def addImportFile(self, filename, site="auto") -> bool:
        """Add a single file to the import list and associate it with a site.

        Processes the file, determines its site, adds it to the file list, and updates site IDs as needed.

        Args:
            filename: The path to the file to import.
            site: The site identifier or "auto" to detect automatically.

        Returns:
            bool: True if the file was successfully added, False otherwise.
        """
        # DEBUG->print("addimportfile: filename is a", filename.__class__, filename)
        # filename not guaranteed to be unicode
        if (
            self.filelist.get(filename) is not None
            or self.failed_files.failed(filename)
            or not os.path.exists(filename)
        ):
            return False

        if not self._is_valid_import_file(filename):
            self.failed_files.remember(filename)
            return False

        self.idsite.processFile(filename)
        if self.idsite.get_fobj(filename):
            fpdbfile = self.idsite.filelist[filename]
        else:
            log.warning(f"siteId Failed for: '{filename}'")
            self.failed_files.remember(filename)
            return False

        self.addFileToList(fpdbfile)
        self.filelist[filename] = fpdbfile
        fpdb_site = fpdbfile.site
        if fpdb_site is None:
            return False
        if site not in self.siteIds:
            # Get id from Sites table in DB
            result = self.database.get_site_id(fpdb_site.name)
            if len(result) == 1:
                self.siteIds[fpdb_site.name] = result[0][0]
            elif len(result) == 0:
                log.warning(f"Database ID for {fpdb_site.name} not found")
            else:
                log.warning(
                    f"More than 1 Database ID found for {fpdb_site.name}",
                )

        return True

    def _is_valid_import_file(self, filepath: str) -> bool:
        """Check if a file is a valid candidate for import.

        Checks for:
        1. Hidden files (starting with .)
        2. Common system files
        3. Known binary/ignored extensions

        Args:
            filepath: The full path to the file.

        Returns:
            bool: True if the file seems valid, False otherwise.
        """
        filename = os.path.basename(filepath)

        # 1. Skip hidden files and common system files
        if filename.startswith("."):
            return False

        if filename.lower() in ("desktop.ini", "thumbs.db"):
            return False

        # 2. Check extension blacklist
        ext = os.path.splitext(filename)[1].lower()

        # List of extensions to explicitly ignore
        ignored_extensions = {
            # Images
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".ico",
            ".tiff",
            ".webp",
            ".svg",
            ".psd",
            # Archives
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
            ".iso",
            # Executables and Libraries
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".bin",
            ".msi",
            ".app",
            ".bat",
            ".sh",
            ".cmd",
            # Media
            ".mp3",
            ".wav",
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".flv",
            ".wmv",
            # Documents/Office (excluding xls/xlsx which are supported)
            ".pdf",
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
            ".odt",
            ".rtf",
            # Database
            ".db",
            ".db-wal",
            ".db-shm",
            ".sqlite",
            ".sqlite-wal",
            ".sqlite-shm",
            ".sqlite3",
            ".sqlite3-wal",
            ".sqlite3-shm",
            ".mdb",
            # Code/Compiled
            ".pyc",
            ".class",
            ".o",
            ".obj",
            ".py",
            # Test & sidecar reference data (shared with IdentifySite)
            *SIDECAR_EXTENSIONS,
        }

        if ext in ignored_extensions:
            return False

        return True

    # Called from GuiBulkImport to add a file or directory. Bulk import never monitors
    def addBulkImportImportFileOrDir(self, inputPath, site="auto"):
        """Add a file or all files in a directory to the bulk import list.

        Handles both individual files and directories, recursively adding all files in a directory to the import list.

        Args:
            inputPath: The path to a file or directory to import.
            site: The site identifier or "auto" to detect automatically.

        Returns:
            bool: True if files were successfully added, False otherwise.
        """
        # for windows platform, force os.walk variable to be unicode
        # see fpdb-main post 9th July 2011
        if self.config.posix:
            pass
        else:
            inputPath = str(inputPath)

        if os.path.isdir(inputPath):
            for subdir in os.walk(inputPath):
                for file in subdir[2]:
                    filepath = os.path.join(subdir[0], file)
                    if self._is_valid_import_file(filepath):
                        self.addImportFile(filepath, site=site)
            return True
        else:
            if self._is_valid_import_file(inputPath):
                return self.addImportFile(inputPath, site=site)
            else:
                log.warning(f"Skipping invalid file: {inputPath}")
                return False

    # Add a directory of files to filelist. Each (site, content type) key owns
    # one path, so all enabled sites and both hand-history/tournament-summary
    # directories can be monitored concurrently.
    def addImportDirectory(
        self,
        dir,
        monitor=False,
        site=("default", "hh"),
        filter="passthrough",
    ) -> None:
        """Add all files from a directory to the import list, optionally enabling monitoring.

        Recursively scans the specified directory, adding files modified in the last 12 hours to the import list. Optionally enables monitoring for the directory.

        Args:
            dir: The directory path to import files from.
            monitor: Whether to enable monitoring for new files in the directory.
            site: The site identifier tuple.
            filter: The filter name to use for imported files.
        """
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
                    if not self._is_valid_import_file(filename) or self.failed_files.failed(filename):
                        continue
                    if (time() - os.stat(filename).st_mtime) <= 43200:  # look all files modded in the last 12 hours
                        # need long time because FTP in Win does not
                        # update the timestamp on the HH during session
                        self.addImportFile(filename, "auto")
        else:
            log.warning(
                f"Attempted to add non-directory '{dir!s}' as an import directory",
            )

    def removeImportDirectory(self, dir=None, site=None) -> None:
        """Remove monitored import directories and stale files below them.

        ``GuiAutoImport`` can reload paths while running.  The importer keeps a
        persistent ``dirlist`` and ``filelist`` for incremental polling, so
        deleting only the config entry is not enough: files from removed
        directories would continue to be checked/imported.
        """
        removed_dirs = []
        for key, value in list(self.dirlist.items()):
            watched_dir = value[0]
            if (site is not None and key == site) or (dir is not None and watched_dir == dir):
                removed_dirs.append(watched_dir)
                del self.dirlist[key]

        if dir is not None and not removed_dirs:
            removed_dirs.append(dir)

        for watched_dir in removed_dirs:
            watched_prefix = os.path.abspath(watched_dir)
            for filename in list(self.filelist.keys()):
                try:
                    file_path = os.path.abspath(filename)
                    common = os.path.commonpath([watched_prefix, file_path])
                except ValueError:
                    continue
                if common == watched_prefix:
                    self.filelist.pop(filename, None)
                    self.updatedsize.pop(filename, None)
                    self.updatedtime.pop(filename, None)
                    self.pos_in_file.pop(filename, None)
            for failed_path in list(self.failed_files):
                try:
                    # The cache accepts bytes paths, which commonpath cannot mix
                    # with the str prefix, so normalise before comparing.
                    file_path = os.path.abspath(os.fsdecode(failed_path))
                    common = os.path.commonpath([watched_prefix, file_path])
                except ValueError:
                    continue
                if common == watched_prefix:
                    self.failed_files.discard(failed_path)

    def runImport(self):
        """Run the import process for all files in the file list.

        Initializes import settings, processes all files, performs post-import cleanup, and returns import statistics and duration.

        Returns:
            tuple: A tuple containing the number of stored, duplicate, partial, skipped, and error hands, and the total import duration in seconds.
        """
        # Initial setup
        start = datetime.datetime.now()
        starttime = time()
        log.info(
            f"Started at {start} -- {len(self.filelist)} files to import. indexes: {self.settings['dropIndexes']}",
        )
        if self.settings["dropIndexes"] == "auto":
            self.settings["dropIndexes"] = self.calculate_auto2(
                self.database,
                12.0,
                500.0,
            )
        if "dropHudCache" in self.settings and self.settings["dropHudCache"] == "auto":
            self.settings["dropHudCache"] = self.calculate_auto2(
                self.database,
                25.0,
                500.0,
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

        # Publish BatchImportCompleted event (new architecture)
        if self.event_bus and BatchImportCompletedEvent:
            try:
                batch_id = f"batch_{start.strftime('%Y%m%d_%H%M%S')}"
                total_hands = totstored + totdups + totpartial + toterrors
                event = BatchImportCompletedEvent(
                    batch_id=batch_id,
                    total_hands=total_hands,
                    successful_hands=totstored,
                    failed_hands=toterrors,
                    duration_seconds=endtime - starttime,
                )
                self.event_bus.publish(event.event_type, event.to_dict())
                log.debug(f"Published BatchImportCompletedEvent: {batch_id}, {total_hands} hands")
            except Exception as e:  # intentional broad catch: event bus subscribers are optional runtime hooks.
                log.warning(f"Failed to publish BatchImportCompletedEvent: {e}")

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
        """Perform post-import cleanup operations on the database.

        Cleans up tournament types, weeks, and months, and resets the database clean state after import.
        """
        self.database.cleanUpTourneyTypes()
        self.database.cleanUpWeeksMonths()
        self.database.resetClean()

    def importFiles(self, q):
        """Import all files in the file list and aggregate import statistics.

        Processes each file in the file list, updates progress, logs results, and handles file movement on success or failure.

        Args:
            q: Unused parameter, reserved for future use.

        Returns:
            tuple: A tuple containing the total number of stored, duplicate, partial, skipped, and error hands.
        """
        totstored = 0
        totdups = 0
        totpartial = 0
        totskipped = 0
        toterrors = 0

        # prepare progress popup window
        has_callbacks = all(
            callback is not None
            for callback in (self.progress_start_cb, self.progress_update_cb, self.progress_end_cb)
        )

        if not has_callbacks:
            ProgressDialog = ImportProgressDialog(len(self.filelist), self.parent)
            ProgressDialog.resize(500, 200)
            ProgressDialog.show()
        else:
            assert self.progress_start_cb is not None
            self.progress_start_cb(len(self.filelist))

        for f in self.filelist:
            if not has_callbacks:
                ProgressDialog.progress_update(f, str(self.database.getHandCount()))
            else:
                assert self.progress_update_cb is not None
                self.progress_update_cb(f, str(self.database.getHandCount()))

            try:
                (stored, duplicates, partial, skipped, errors, ttime, _) = self._import_despatch(self.filelist[f])
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
            except Exception as e:  # intentional broad catch: file import must isolate per-file failures.
                self.database.rollback()
                log.exception(f"A fatal error occurred while processing file: {f}. Error: {e}")
                toterrors += 1
                self._relocate_processed_file(f, failed=True)
                continue

            # Optionally archive the file once processed: successful imports go to
            # the "imported" directory, files that produced errors to the "failed" one.
            self._relocate_processed_file(f, failed=errors > 0)

        if not has_callbacks:
            ProgressDialog.accept()
            del ProgressDialog
        else:
            assert self.progress_end_cb is not None
            self.progress_end_cb()

        return totstored, totdups, totpartial, totskipped, toterrors

    # end def importFiles

    def _relocate_processed_file(self, filepath: str, *, failed: bool) -> None:
        """Move a just-processed file to the configured imported/failed directory.

        Controlled by the importer settings:
          - ``moveimportedfiles`` / ``moveImportedFilesDir`` for successful imports,
          - ``movefailedfiles`` / ``moveFailedFilesDir`` for files with errors.
        No-op if the relevant flag is disabled or no target directory is set, so
        the default behaviour is to leave files in place.

        Args:
            filepath: Path of the file that was just processed.
            failed: True if the file failed to import (errors or exception).
        """
        if failed:
            enabled = self.settings.get("movefailedfiles")
            target_dir = self.settings.get("moveFailedFilesDir")
        else:
            enabled = self.settings.get("moveimportedfiles")
            target_dir = self.settings.get("moveImportedFilesDir")

        if not enabled or not target_dir:
            return

        kind = "failed" if failed else "imported"
        try:
            os.makedirs(target_dir, exist_ok=True)
            dest = os.path.join(target_dir, os.path.basename(filepath))
            shutil.move(filepath, dest)
            log.info(f"Moved {kind} file {filepath!r} to {dest!r}")
        except (shutil.Error, OSError) as e:
            log.exception(f"Error moving {kind} file {filepath!r} to {target_dir!r}: {e}")

    def setMoveImportedFiles(self, enabled, target_dir=None) -> None:
        """Enable/disable moving successfully imported files, with an optional target dir."""
        self.settings["moveimportedfiles"] = bool(enabled)
        if target_dir is not None:
            self.settings["moveImportedFilesDir"] = target_dir

    def setMoveFailedFiles(self, enabled, target_dir=None) -> None:
        """Enable/disable moving files that failed to import, with an optional target dir."""
        self.settings["movefailedfiles"] = bool(enabled)
        if target_dir is not None:
            self.settings["moveFailedFilesDir"] = target_dir

    def _import_despatch(self, fpdbfile):
        """Dispatch the import process for a given file based on its type.

        Determines the file type and calls the appropriate import method, returning import statistics and detected site name.

        Args:
            fpdbfile: The file object to import.

        Returns:
            tuple: A tuple containing the number of stored, duplicate, partial, skipped, and error hands, the import time, and the detected site name.
        """
        stored, duplicates, partial, skipped, errors, ttime = 0, 0, 0, 0, 0, 0
        detected_sitename = None
        if fpdbfile.ftype in ("hh", "both"):
            (stored, duplicates, partial, skipped, errors, ttime, detected_sitename) = self._import_hh_file(fpdbfile)
        if fpdbfile.ftype == "summary":
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_summary_file(fpdbfile)
        if fpdbfile.ftype == "both" and fpdbfile.path not in self.updatedsize:
            self._import_summary_file(fpdbfile)
        #    pass
        log.debug(f"_import_summary_file.ttime: {ttime:.3f} {fpdbfile.ftype}")

        return (stored, duplicates, partial, skipped, errors, ttime, detected_sitename)

    def calculate_auto2(self, db, scale, increment):
        """Determine whether to drop indexes based on database and import file sizes.

        Calculates if indexes should be dropped by comparing the number of hands in the database and the total size of import files, using provided scale and increment values.

        Args:
            db: The database connection or object.
            scale: The scaling factor for the calculation.
            increment: The increment value for the calculation.

        Returns:
            str: "drop" if indexes should be dropped, otherwise "don't drop".
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
            except Exception as e:  # intentional broad catch: DB cursor errors vary by configured backend.
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
        if self.settings["handsInDB"] < scale * ((total_size) // (size_per_hand)) + increment:
            ret = "drop"
        # print "auto2: handsindb =", self.settings['handsInDB'], "total_size =", total_size, "size_per_hand =", \
        #      size_per_hand, "inc =", increment, "return:", ret
        return ret

    # Run import on updated files, then store latest update time. Called from GuiAutoImport.py
    def runUpdated(self) -> None:
        """Import updated files and refresh their tracked state.

        Scans the tracked directories and files, imports any files that have changed, updates their state, and performs post-import cleanup.
        """
        # Importing a file is a multi-statement transaction, so there is no safe
        # way to replay it after the connection dies half way through -- the
        # connection is checked here instead, between cycles. Skipping the cycle
        # (rather than raising) leaves the files untracked and un-timestamped,
        # so they are picked up by the next cycle once the database is back.
        if not self.database.ensure_connection():
            log.warning("Auto-import cycle skipped: database unreachable.")
            return

        with db_profile.scope("import_cycle"):
            self._run_updated_cycle()
        _profile_reporter.maybe_log()

    def _run_updated_cycle(self) -> None:
        """One pass over the tracked directories and files."""
        for site, type in self.dirlist:
            self.addImportDirectory(
                self.dirlist[(site, type)][0],
                False,
                (site, type),
                self.dirlist[(site, type)][1],
            )

        for f in list(self.filelist):
            tracked_file = self.filelist.get(f)
            if tracked_file is None:
                continue
            if os.path.exists(f):
                stat_info = os.stat(f)
                if f in self.updatedsize:  # we should be able to assume that if we're in size, we're in time as well
                    if stat_info.st_size > self.updatedsize[f] or stat_info.st_mtime > self.updatedtime[f]:
                        if not os.path.isdir(f):
                            log.debug(f"os.path.basename: {os.path.basename(f)}")
                            log.debug(f"self.caller: {self.caller}")

                        (stored, duplicates, partial, skipped, errors, ttime, detected_sitename) = (
                            self._import_despatch(tracked_file)
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
                            tracked_file.fileId,
                        )
                        if not os.path.isdir(f):
                            # Use detected sitename if available, otherwise fall back to config sitename
                            tracked_site = tracked_file.site
                            site_name = detected_sitename or (
                                tracked_site.name if tracked_site is not None else "Unknown"
                            )

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

    def _import_hh_file(self, fpdbfile):  # noqa: C901, PLR0912, PLR0915
        """Import a hand history file and process its contents.

        Loads the appropriate hand history converter, processes the file, updates the database, and handles HUD and summary processing as needed.

        Pipeline call order is asserted by
        ``tests/integration/test_importer_call_order.py``. Re-ordering the
        ``prepInsert -> assembleHand -> getHandId -> updateSessionsCache ->
        insertHands -> updateCardsCache -> updatePositionsCache ->
        updateHudCache -> updateTourneyResults`` sequence will fail that
        test; update its EXPECTED_ORDER if the change is intentional.

        Args:
            fpdbfile: The file object representing the hand history file to import.

        Returns:
            tuple: A tuple containing the number of stored, duplicate, partial, skipped, and error hands, the import time, and the detected site name.
        """
        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())
        detected_sitename = None  # Will store the sitename detected by the parser

        # Load filter, process file, pass returned filename to import_fpdb_file
        log.info(f"Converting {fpdbfile.path}")

        # Start HandDataReporter file tracking if enabled
        if self.hand_data_reporter:
            self.hand_data_reporter.start_file(fpdbfile.path)

        fpdb_site = fpdbfile.site
        if fpdb_site is None:
            msg = f"Cannot import unidentified file: {fpdbfile.path}"
            raise ValueError(msg)
        filter_name = fpdb_site.filter_name
        obj = get_parser_class(filter_name)
        if filter_name == "iPoker":
            obj = get_ipoker_parser_class_for_path(fpdbfile.path)
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
                sitename=fpdb_site.name,
            )
            if filter_name == "PartyPoker":
                # Party tournament results are embedded in hand histories.
                # Reuse the Importer's connection without making standalone
                # hand parsing open a database by itself.
                setattr(hhc, "db", self.database)
            hhc.setAutoPop(self.mode == "auto")
            hhc.start()

            # Add parsing issues to the main importer's list
            for issue in hhc.parsing_issues:
                self.import_issues.append(f"In {fpdbfile.path}: {issue}")

                # Report parsing issues if HandDataReporter is enabled
                if self.hand_data_reporter:
                    # Extract the actual hand content from the error message
                    hand_context = ""
                    if "Hand starting with" in str(issue):
                        # Try to extract the hand snippet from the error message
                        import re

                        match = re.search(r"Hand starting with '([^']+)'", str(issue))
                        if match:
                            hand_snippet = match.group(1)
                            # Read directly a portion of the file for more context
                            try:
                                with open(fpdbfile.path, encoding="utf-8") as f:
                                    file_content = f.read()
                                    # Search for the snippet in the file to get more context
                                    if hand_snippet.replace("...", "") in file_content:
                                        start_pos = file_content.find(hand_snippet.replace("...", ""))
                                        if start_pos != -1:
                                            hand_context = file_content[
                                                start_pos : start_pos + 1000
                                            ]  # 1000 characters of context
                            except IMPORTER_FILE_READ_ERRORS:
                                hand_context = hand_snippet
                        else:
                            hand_context = str(issue)[:500]
                    else:
                        hand_context = str(issue)[:500]

                    # Create an enriched error for parsing issues
                    parsing_error = Exception(str(issue))
                    parsing_error.full_traceback = f"Parsing issue in {fpdbfile.path}: {issue}"
                    self.hand_data_reporter.report_hand_failure(fpdbfile.path, parsing_error, hand_context)

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
                with self.database.transaction():
                    if self.caller:
                        self.progressNotify()
                    handlist = hhc.getProcessedHands()
                    self.database.resetBulkCache(True)
                    self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()
                    self.database.resetBulkCache()

                    for hand in handlist:
                        hand.prepInsert(self.database, printtest=self.settings["testData"])
                        ahands.append(hand)

                    for hand in ahands:
                        hand.assembleHand()
                        log.debug(f"final import of hand: {hand}")
                        phands.append(hand)

                    # Everything below runs inside the surrounding
                    # database.transaction() context manager above.
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
                            log.info(f"Hand {hand.dbid_hands} added to HUD queue")

                            # Report successful hand processing
                            if self.hand_data_reporter:
                                try:
                                    log.debug(f"DEBUG: Calling report_hand_success for hand {hand.handid}")
                                    self.hand_data_reporter.report_hand_success(fpdbfile.path, hand)
                                    log.debug(f"DEBUG: report_hand_success completed for hand {hand.handid}")
                                except Exception as e:  # intentional broad catch: reporter callback must not abort import.
                                    log.exception(f"DEBUG: Exception in report_hand_success: {e}")

                        except FpdbHandDuplicate as e:
                            duplicates += 1
                            log.info("Duplicate hand detected - not sending to HUD")
                            if doinsert and ihands:
                                backtrack = True

                            # Report duplicate hand
                            if self.hand_data_reporter:
                                self.hand_data_reporter.report_hand_failure(
                                    fpdbfile.path, e, hand.handText[:200] if hasattr(hand, "handText") else ""
                                )

                        except FpdbHandPartial as e:
                            import traceback

                            partial += 1
                            self.import_issues.append(
                                f"[PARTIAL] In {fpdbfile.path}: Hand starting with '{hand.handText[:30]}...' - {e}"
                            )

                            # Report partial hand with traceback
                            if self.hand_data_reporter:
                                # Capture the stack trace for partial hands as well
                                full_traceback = traceback.format_exc()
                                enriched_error = Exception(
                                    f"[PARTIAL] Hand starting with '{hand.handText[:30] if hasattr(hand, 'handText') else 'Unknown'}...': '{e}'"
                                )
                                enriched_error.full_traceback = full_traceback
                                self.hand_data_reporter.report_hand_failure(
                                    fpdbfile.path,
                                    enriched_error,
                                    hand.handText[:500] if hasattr(hand, "handText") else "",
                                    hand,
                                )

                        except Exception as e:  # intentional broad catch: per-hand import errors are counted and skipped.
                            import traceback

                            errors += 1
                            self.import_issues.append(
                                f"[ERROR] In {fpdbfile.path}: Hand starting with '{hand.handText[:30]}...' - {e}"
                            )
                            log.exception(
                                f"Importer._import_hh_file: '{fpdbfile.path}' Fatal error: '{e}'",
                            )

                            # Report error hand with full traceback
                            if self.hand_data_reporter:
                                # Capture the stack trace here, where it is available
                                full_traceback = traceback.format_exc()
                                # Create an error object enriched with the stack trace
                                enriched_error = Exception(str(e))
                                enriched_error.full_traceback = full_traceback
                                self.hand_data_reporter.report_hand_failure(
                                    fpdbfile.path, enriched_error, hand.handText[:500] if hasattr(hand, "handText") else ""
                                )
                            else:
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
                            self.database.bbulk = [b for b in self.database.bbulk if hand.dbid_hands != b[0]]
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

                    for i in range(len(ihands)):
                        doinsert = len(ihands) == i + 1
                        hand = ihands[i]
                        hand.insertHandsPlayers(
                            self.database,
                            doinsert,
                            self.settings["testData"],
                        )
                        hand.insertPlayerAutoNotes(self.database, doinsert)
                        hand.insertHandsActions(
                            self.database,
                            doinsert,
                            self.settings["testData"],
                        )
                        hand.insertHandsStove(self.database, doinsert)
                        hand.insertHandsShowdown(self.database, doinsert)
                        hand.insertHandsCashout(self.database, doinsert)

                    # Cache HHC if enabled
                    if self.settings.get("cacheHHC", False):
                        self.handhistoryconverter = hhc
                        # Keyed too, so a caller comparing a whole directory gets
                        # each file's own converter instead of the last one.
                        self.cached_hhcs[fpdbfile.path] = hhc

                # Notify the HUD only after the transaction above has committed.
                # The HUD reads each hand on its own DB connection; sending while
                # the write is still open lets that SELECT miss the uncommitted
                # row, so the hand is dropped ("table info not found in DB"). The
                # send is a non-blocking ZMQ push, so moving it out of the
                # transaction only shortens the write lock -- it costs nothing.
                if self.callHud:
                    log.info(f"ZMQ DEBUG - to_hud contains {len(to_hud)} hands: {to_hud}")
                    if self.zmq_sender is None:
                        self.zmq_sender = ZMQSender()
                    zmq_sender = self.zmq_sender
                    for hid in to_hud:
                        try:
                            log.info(f"Sending hand ID {hid} to HUD via ZMQ socket")
                            zmq_sender.send_hand_id(hid)
                        except OSError as e:
                            log.exception(f"Failed to send hand ID to HUD via socket: {e}")
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
                log.info(f"File {fpdbfile.path} marked as 'both' for summary processing")
            else:
                # Not an anomaly: a cash file has no tournament summary to grab, and
                # plenty of tournament histories are stored without one. This used to
                # log three WARNING lines per imported file - including the nonsense
                # "type is 'tour' (expected 'tour')" whenever only the summary was
                # missing - which buried the warnings that do matter.
                reasons = []
                if gametype.get("type") != "tour":
                    reasons.append(f"type is {gametype.get('type')!r}, not 'tour'")
                if not getattr(hhc, "summaryInFile", False):
                    reasons.append("the file holds no tournament summary")
                log.debug(
                    "File %s not marked for summary processing: %s",
                    fpdbfile.path,
                    "; ".join(reasons),
                )
        else:
            log.debug("No hands parsed from %s, nothing to check for a summary", fpdbfile.path)

        ttime = time() - ttime

        # Finalize HandDataReporter file tracking if enabled
        if self.hand_data_reporter:
            self.hand_data_reporter.finish_file(fpdbfile.path)

        return (stored, duplicates, partial, skipped, errors, ttime, detected_sitename)

    def autoSummaryGrab(self, force=False) -> None:
        """Automatically process summary files marked as 'both' if they are old enough or if forced.

        Iterates through the file list, processing tournament summary files that are ready, and updates their type after processing.

        Args:
            force: If True, process all 'both' files regardless of age.
        """
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
        """Import and process a tournament summary file.

        Loads the appropriate summary converter, processes the file, updates the database, and handles errors and partial imports.

        Args:
            fpdbfile: The file object representing the summary file to import.

        Returns:
            tuple: A tuple containing the number of stored, duplicate, partial, skipped, and error summaries, and the import time.
        """
        log.debug(f"_import_summary_file called for: {fpdbfile.path}")
        log.debug(f"Site: {fpdbfile.site.name}, Summary module: {fpdbfile.site.summary}")

        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())
        not_a_summary = 0  # chunks of the file that hold no tournament at all

        try:
            obj = get_summary_class(fpdbfile.site.summary)
            log.debug(f"Successfully resolved summary importer: {fpdbfile.site.summary}")
        except ImportError as e:
            log.exception(f"Failed to import summary module {fpdbfile.site.summary}: {e}")
            return (0, 0, 0, 0, 1, time())

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
            # Wrap the summary insertion loop in a single transaction so a
            # crash mid-file rolls back the whole batch instead of leaving
            # half-imported summaries committed (mirrors the hand-history
            # path in _import_hh_file above).
            with self.database.transaction():
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
                    except FpdbSummaryNotFound as exc:
                        # Page furniture, not a half-imported tournament: an
                        # archive page splits into its head, its column headers
                        # and its totals row as well as its summaries. Counting
                        # those as partial told the user 15 summaries had failed
                        # in a file holding 5 tournaments, all of them imported.
                        not_a_summary += 1
                        log.debug("Not a tournament summary in %s: %s", fpdbfile.path, exc)
                    except FpdbHandPartial:
                        partial += 1
                        self.import_issues.append(
                            f"[PARTIAL] In {fpdbfile.path}: Summary starting with '{summaryText[:30]}...'"
                        )
                    except FpdbParseError:
                        log.exception(f"Summary import parse error in file: {fpdbfile.path}")
                        errors += 1
                        self.import_issues.append(
                            f"[ERROR] In {fpdbfile.path}: Summary starting with '{summaryText[:30]}...'"
                        )
                    if j != 1:
                        log.info(
                            f"Finished importing {j}/{len(summaryTexts)} tournament summaries",
                        )
                    stored = j
        stored -= errors + partial + not_a_summary
        ttime = time() - ttime
        log.debug(
            f"Import summary completed: {stored} stored, {duplicates} duplicates, {partial} partial, "
            f"{skipped} skipped, {errors} errors, {not_a_summary} non-summary chunks in {ttime:.3f} seconds",
        )
        return (stored, duplicates, partial, skipped, errors, ttime)

    def progressNotify(self) -> None:
        """Notify the application to process pending GUI events.

        Ensures the GUI remains responsive during long-running import operations.
        """
        QCoreApplication.processEvents()

    def readFile(self, obj, filename, site):
        """Read and split a tournament summary file into individual summaries.

        Handles both Excel and text summary files, splitting them into separate summaries and removing short headers or footers as needed.

        Args:
            obj: The summary converter object.
            filename: The path to the summary file.
            site: The site name associated with the summary file.

        Returns:
            list: A list of summary texts extracted from the file, or None if the file could not be read.
        """
        if filename.endswith(".xls") or (filename.endswith(".xlsx") and xlrd):
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
            # Dropping the header/footer is the normal path for a summary file, not
            # a problem worth a warning on every import.
            if len(summaryTexts) > 1 and len(summaryTexts[0]) <= 150:
                del summaryTexts[0]
                log.debug("TourneyImport: removed header (< 150 characters) from start of %s", filename)

            # Sometimes the summary files also have a footer
            # Remove the last entry if it has < 100 characters
            if len(summaryTexts) > 1 and len(summaryTexts[-1]) <= 100:
                summaryTexts.pop()
                log.debug("TourneyImport: removed footer (< 100 characters) from end of %s", filename)
        return summaryTexts

    def get_hand_data_report(self, file_path: str | None = None) -> str:
        """Get a formatted report from HandDataReporter.

        Args:
            file_path: Path to specific file to report on. If None, returns session summary.

        Returns:
            Formatted report string
        """
        if not self.hand_data_reporter:
            return "HandDataReporter not enabled. Use setHandDataReporter() to enable detailed reporting."

        if file_path:
            return self.hand_data_reporter.generate_file_report(file_path)
        return self.hand_data_reporter.generate_session_summary()

    def export_hand_data_json(self, output_path: str) -> None:
        """Export HandDataReporter data to JSON file.

        Args:
            output_path: Path where to save the JSON report
        """
        if not self.hand_data_reporter:
            log.warning("HandDataReporter not enabled. Cannot export JSON report.")
            return

        self.hand_data_reporter.export_json(output_path)

    def cleanup(self) -> None:
        """Clean up database connections and ZMQ resources used by the importer.

        Closes any open database connections and ZMQ sender, logging the cleanup process or any errors encountered.
        """
        # Close ZMQ sender first
        if hasattr(self, "zmq_sender") and self.zmq_sender is not None:
            try:
                self.zmq_sender.close()
                self.zmq_sender = None
                log.debug("ZMQ sender closed during cleanup.")
            except Exception as e:  # intentional broad catch: cleanup should never mask caller outcome.
                log.warning(f"Error closing ZMQ sender during cleanup: {e}")

        # Close database connections
        if hasattr(self, "database") and self.database is not None:
            try:
                self.database.cleanup_connections()
                log.debug("Importer database connections cleaned up.")
            except Exception as e:  # intentional broad catch: DB cleanup spans driver/runtime backends.
                log.warning(f"Error during importer cleanup: {e}")

    def __del__(self) -> None:
        """Destructor to clean up resources used by the importer.

        Closes the ZMQ sender and database connections to prevent resource leaks and timeout issues.
        """
        if hasattr(self, "zmq_sender") and self.zmq_sender is not None:
            self.zmq_sender.close()
        # Clean up database connections to prevent timeout issues
        if hasattr(self, "database") and self.database is not None:
            try:
                self.database.cleanup_connections()
            except Exception as e:  # intentional broad catch: destructor cleanup must not raise.
                log.debug(f"Database connection cleanup failed in Importer.__del__: {e}")


class ImportProgressDialog(QDialog):
    """Popup window to show progress.

    Init method sets up total number of expected iterations
    If no parent is passed to init, command line
    mode assumed, and does not create a progress bar
    """

    def __init__(self, total, parent) -> None:
        """Initialize the ImportProgressDialog to display import progress.

        Sets up the progress bar and labels for both GUI and command line modes, tracking the total number of import iterations.

        Args:
            total: The total number of expected iterations (files to import).
            parent: The parent widget or indicator for command line mode.
        """
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
        """Update the progress display for the import process.

        Increments the progress bar or command line indicator, updates the hand count, and displays the current file being imported.

        Args:
            filename: The name of the file currently being imported.
            handcount: The current number of hands in the database.
        """
        self.fraction += 1

        if self.parent is None:
            # Command line mode
            if self.total > 0:
                try:
                    progress = self.fraction / self.total
                    bar_length = 40
                    filled_len = round(bar_length * progress)
                    bar = "█" * filled_len + "─" * (bar_length - filled_len)
                    percentage = round(progress * 100, 1)
                    # Use sys.stdout.write for continuous line update
                    sys.stdout.write(f"\rProgress: |{bar}| {percentage}% Complete - {os.path.basename(filename)}")
                    sys.stdout.flush()
                except (ZeroDivisionError, ValueError):
                    pass  # Avoid errors if total is 0 for some reason
            return
        if self.parent == "CLI_NO_PROGRESS":
            return  # No output at all

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

    def accept(self) -> None:
        """Finalize and close the progress dialog.

        Handles both command line and GUI modes, ensuring proper cleanup and display behavior.
        """
        if self.parent is None:
            sys.stdout.write("\n")  # Newline after progress bar finishes
            return
        if self.parent == "CLI_NO_PROGRESS":
            return
        super().accept()

    def resize(self, *args) -> None:
        """Resize the progress dialog window.

        Adjusts the dialog size in GUI mode; does nothing in command line mode.
        """
        if self.parent is None or self.parent == "CLI_NO_PROGRESS":
            return
        super().resize(*args)

    def show(self) -> None:
        """Display the progress dialog window.

        Shows the dialog in GUI mode; does nothing in command line mode.
        """
        if self.parent is None or self.parent == "CLI_NO_PROGRESS":
            return
        super().show()
