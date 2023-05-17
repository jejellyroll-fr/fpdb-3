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

from __future__ import print_function
from __future__ import division




from past.utils import old_div
#import L10n
#_ = L10n.get_translation()

#    Standard Library modules

import os  # todo: remove this once import_dir is in fpdb_import
from time import time, sleep, process_time
import datetime
import queue
import shutil
import re

import logging, traceback

from PyQt5.QtWidgets import QProgressBar, QLabel, QDialog, QVBoxLayout
from PyQt5.QtCore import QCoreApplication

#    fpdb/FreePokerTools modules

import Database

import Configuration

import IdentifySite

from Exceptions import FpdbParseError, FpdbHandDuplicate, FpdbHandPartial

try:
    import xlrd
except:
    xlrd = None

if __name__ == "__main__":
    Configuration.set_logfile("fpdb-log.txt")
# logging has been set up in fpdb.py or HUD_main.py, use their settings:
log = logging.getLogger("importer")

import IdentifySite
import Database
import time

class Importer:
    """
    Class for importing data into a database.

    Attributes:
        caller: The caller object.
        settings: A dictionary of settings for the importer.
        config: The configuration object.
        sql: The SQL object for the database.
        parent: The parent object.

        idsite: An IdentifySite object.
        filelist: A dictionary of files to import.
        dirlist: A dictionary of directories to import.
        siteIds: A dictionary of site IDs.
        removeFromFileList: A dictionary of files to remove from the filelist.
        monitor: Whether or not to monitor the importing process.
        updatedsize: A dictionary of updated file sizes.
        updatedtime: A dictionary of updated file times.
        lines: A list of lines in a file.
        faobs: A file as one big string.
        mode: The mode for the importer.
        pos_in_file: A dictionary to remember how far the importer has read in each file.
        callHud: Whether or not to call FpdbHud.
        writeq: The write queue.
        database: The Database object for the database.
        writerdbs: A list of Database objects for writing to the database.
    """
    def __init__(self, caller, settings, config, sql=None, parent=None):
        """
        Constructor for the Importer class.

        Args:
            caller: The caller object.
            settings: A dictionary of settings for the importer.
            config: The configuration object.
            sql: The SQL object for the database.
            parent: The parent object.
        """
        self.settings = settings
        self.caller = caller
        self.config = config
        self.sql = sql
        self.parent = parent

        self.idsite = IdentifySite.IdentifySite(config)

        self.filelist = {}
        self.dirlist = {}
        self.siteIds = {}
        self.removeFromFileList = {}
        self.monitor = False
        self.updatedsize = {}
        self.updatedtime = {}
        self.lines = None
        self.faobs = None
        self.mode = None
        self.pos_in_file = {}
        self.callHud = self.config.get_import_parameters().get("callFpdbHud")

        # Set defaults
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
        self.writerdbs.extend(
            Database.Database(self.config, sql=self.sql)
            for _ in range(self.settings['threads'])
        )
        # Init clock in windows
        process_time()


    #Set functions
    def setMode(self, value):
        """
        Set the mode to the given value.

        Parameters:
        value (any): The value to set the mode to.
        """
        # Set the mode to the given value
        self.mode = value

        
    def setCallHud(self, value):
        """
        Sets the callHud attribute to the given value.

        Args:
            value: The value to set callHud to.
        """
        # Set the callHud attribute to the given value.
        self.callHud = value

        
    def setCacheSessions(self, value):
        """
        Setter method for the cacheSessions attribute.

        Args:
            value (bool): The value to set the cacheSessions attribute to.
        """
        # Set the cacheSessions attribute to the given value.
        self.cacheSessions = value

    def setHandCount(self, value):
        """
        Sets the hand count value in the settings dictionary.

        Args:
            value (int): The value to set for the hand count.
        """
        self.settings['handCount'] = int(value)


    def setQuiet(self, value):
        """
        Sets the 'quiet' setting to the given value.

        Args:
            value (bool): The value to set the 'quiet' setting to.

        Returns:
            None
        """
        # Update the 'quiet' setting with the given value
        self.settings['quiet'] = value


    def setHandsInDB(self, value):
        """
        Sets the value of the 'handsInDB' key in the settings dictionary to the specified value.

        Args:
            value: The value to set the 'handsInDB' key to.
        """
        self.settings['handsInDB'] = value


    def setThreads(self, value):
        """
        Sets the number of threads to use for writing to the database.

        Args:
            value (int): The number of threads to use.
        """
        # Update the settings dictionary with the new value.
        self.settings['threads'] = value

        # If the new number of threads is greater than the current number of writer databases,
        # create new writer databases as needed.
        if self.settings["threads"] > len(self.writerdbs):
            # Use a list comprehension to create new Database objects and append them to the writerdbs list.
            self.writerdbs.extend(
                [
                    Database.Database(self.config, sql=self.sql)
                    for _ in range(self.settings['threads'] - len(self.writerdbs))
                ]
            )

    def setDropIndexes(self, value):
        """
        Sets the value of 'dropIndexes' in the settings dictionary to the given value.

        Args:
            value (bool): The value to set for 'dropIndexes'.
        """
        self.settings['dropIndexes'] = value  # Set the value of 'dropIndexes'


    def setDropHudCache(self, value):
        """
        Sets the value of the 'dropHudCache' key in the settings dictionary to the given value.

        Args:
            value: The value to set the 'dropHudCache' key to.
        """
        # Update the 'dropHudCache' key in the settings dictionary
        self.settings['dropHudCache'] = value


    def setStarsArchive(self, value):
        """
        Sets the value of the 'starsArchive' key in the settings dictionary to the given value.

        Args:
            value: The value to set for the 'starsArchive' key.
        """
        self.settings['starsArchive'] = value


    def setFtpArchive(self, value):
        """
        Sets the value of ftpArchive in the settings dictionary to the given value.

        Args:
            value: The value to set ftpArchive to.
        """
        self.settings['ftpArchive'] = value


    def setPrintTestData(self, value):
        """
        Set the value of the 'testData' key in the settings dictionary to the provided value.

        Args:
            value (any): The value to set for the 'testData' key in the settings dictionary.
        """
        self.settings['testData'] = value


    def setFakeCacheHHC(self, value):
        """
        Set the value of the 'cacheHHC' key in the 'settings' dictionary to the given value.

        Args:
            value: The value to set the 'cacheHHC' key to.
        """
        # Set the value of the 'cacheHHC' key to the given value.
        self.settings['cacheHHC'] = value


    def getCachedHHC(self):
        """
        Returns the cached hand history converter object.
        """
        return self.handhistoryconverter


    def clearFileList(self):
        """
        Removes all entries from the file list and related data structures.
        """
        # Clear the dictionaries that store file size, modification time, and position in file list
        self.updatedsize = {}
        self.updatetime = {}
        self.pos_in_file = {}

        # Clear the file list itself
        self.filelist = {}

    def logImport(self, type, file, stored, dups, partial, skipped, errs, ttime, id):
        """
        Logs import information to the database.

        Args:
        - type (str): The type of import.
        - file (str): The file being imported.
        - stored (int): The number of stored entries.
        - dups (int): The number of duplicate entries.
        - partial (int): The number of partially imported entries.
        - skipped (int): The number of skipped entries.
        - errs (int): The number of entries with errors.
        - ttime (float): The total time taken for import in seconds.
        - id (int): The ID of the import.

        Returns:
        - None
        """
        # Calculate the total number of handled entries
        hands = stored + dups + partial + skipped + errs

        # Get the current UTC time
        now = datetime.datetime.now(datetime.timezone.utc)

        # Convert the total import time to hundredths of a second
        ttime100 = ttime * 100

        # Update the file in the database with the import information
        self.database.updateFile([type, now, now, hands, stored, dups, partial, skipped, errs, ttime100, True, id])

        # Commit the changes to the database
        self.database.commit()
    

    def addFileToList(self, fpdbfile):
        """
        Add file to list in database.

        Args:
            fpdbfile (FPDBFile): Object representing the file to add.

        Returns:
            None.
        """
        # Get the filename without the extension
        file = os.path.splitext(os.path.basename(fpdbfile.path))[0]

        # Convert filename to string if necessary
        if not isinstance(file, str):
            file = file.decode("utf-8", "replace")

        # Get the file ID from the database, or create a new one if it doesn't exist
        fpdbfile.fileId = self.database.get_id(file) or self.database.storeFile(
            [
                file,
                fpdbfile.site.name,
                datetime.datetime.now(datetime.timezone.utc),
                datetime.datetime.now(datetime.timezone.utc),
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                False,
            ]
        )
        self.database.commit()
            
    #Add an individual file to filelist
    def addImportFile(self, filename, site="auto"):
        """
        Add a file to the Importer's filelist.

        Args:
            filename (str): The name of the file to add.
            site (str, optional): The name of the site to associate the file with.

        Returns:
            bool: True if the file was added successfully, False otherwise.
        """
        # Check if the file already exists in the filelist or if it doesn't exist on disk
        if self.filelist.get(filename) != None or not os.path.exists(filename):
            return False

        # Process the file using the idsite
        self.idsite.processFile(filename)

        # Get the processed file from the idsite
        if self.idsite.get_fobj(filename):
            fpdbfile = self.idsite.filelist[filename]
        else:
            log.error(f"Importer.addImportFile: siteId Failed for: '{filename}'")
            return False

        # Add the file to the Importer's filelist
        self.addFileToList(fpdbfile)
        self.filelist[filename] = fpdbfile

        # If the site is not already in the siteIds dictionary, get its ID from the database
        if site not in self.siteIds:
            result = self.database.get_site_id(fpdbfile.site.name)
            if len(result) == 1:
                self.siteIds[fpdbfile.site.name] = result[0][0]
            elif len(result) == 0:
                log.error(f"Database ID for {fpdbfile.site.name} not found")
            else:
                log.error(f"More than 1 Database ID found for {fpdbfile.site.name}")

        return True
    # Called from GuiBulkImport to add a file or directory. Bulk import never monitors

    def addBulkImportImportFileOrDir(self, inputPath, site="auto"):
        """
        Add a file or directory for bulk import.

        Args:
            inputPath (str): Path to the file or directory to be imported.
            site (str, optional): Site to which the file should be imported. Defaults to "auto".

        Returns:
            bool: True if the file(s) were added successfully, False otherwise.
        """
        # For Windows platform, force os.walk variable to be unicode.
        # See fpdb-main post 9th July 2011.
        if not self.config.posix:
            inputPath = str(inputPath)

        if not os.path.isdir(inputPath):
            # Otherwise, add the single file.
            return self.addImportFile(inputPath, site=site)
        for subdir in os.walk(inputPath):
            for file in subdir[2]:
                self.addImportFile(os.path.join(subdir[0], file), site=site)
        return True


    #Add a directory of files to filelist
    #Only one import directory per site supported.
    #dirlist is a hash of lists:
    #dirlist{ 'PokerStars' => ["/path/to/import/", "filtername"] }

    def addImportDirectory(self, dir, monitor=False, site=("default","hh"), filter="passthrough"):
        """
        Adds a directory to the list of directories to search for files to import.

        Args:
            dir (str): The directory path to add.
            monitor (bool): Whether or not to monitor the directory for changes.
            site (tuple): A tuple containing the site name and hostname.
            filter (str): A filter to apply to the files in the directory.
        """
        # Check if the given path is a directory
        if os.path.isdir(dir):
            # If monitor is True, set self.monitor to True and add the directory and filter to the dirlist
            if monitor:
                self.monitor = True
                self.dirlist[site] = [dir] + [filter]

            # Loop through all subdirectories and files in the given directory
            for subdir in os.walk(dir):
                for file in subdir[2]:
                    filename = os.path.join(subdir[0], file)
                    # Check if the file was modified in the last 12 hours
                    if (time.time() - os.stat(filename).st_mtime) <= 43200:
                        # If so, add the file to the list of files to import
                        self.addImportFile(filename, "auto")
        else:
            # If the given path is not a directory, log a warning message
            log.warning(f"Attempted to add non-directory '{str(dir)}' as an import directory")
        


    def runImport(self):
        """Run full import on self.filelist. This is called from GuiBulkImport.py"""

        # Initial setup
        start = datetime.datetime.now()  # Get the current datetime
        starttime = time.time()  # Get the current time
        log.info(("Started at %s -- %d files to import. indexes: %s") % (start, len(self.filelist), self.settings['dropIndexes']))

        # Automatically drop indexes if set to 'auto'
        if self.settings['dropIndexes'] == 'auto':
            self.settings['dropIndexes'] = self.calculate_auto2(self.database, 12.0, 500.0)

        # Automatically drop HUD cache if set to 'auto'
        if 'dropHudCache' in self.settings and self.settings['dropHudCache'] == 'auto':
            self.settings['dropHudCache'] = self.calculate_auto2(self.database, 25.0, 500.0)    # returns "drop"/"don't drop"

        # Import files and get the number of stored, duplicate, partial, skipped, and error files
        (totstored, totdups, totpartial, totskipped, toterrors) = self.importFiles(None)

        # Tidying up after import
        self.runPostImport()  # Run post-import tasks
        self.database.analyzeDB()  # Analyze the database for optimization
        endtime = time.time()  # Get the current time
        return (totstored, totdups, totpartial, totskipped, toterrors, endtime-starttime)  # Return results

    # end def runImport
    
    def runPostImport(self):
        """
        Perform post-import cleanup operations on the database.
        """
        # Clean up tourney types
        self.database.cleanUpTourneyTypes()

        # Clean up weeks and months
        self.database.cleanUpWeeksMonths()

        # Reset the clean flag
        self.database.resetClean()


    def importFiles(self, q):
        """
        Read filenames in self.filelist and pass to despatcher.
        :param q: queue
        :return: tuple of integers (totstored, totdups, totpartial, totskipped, toterrors)
        """

        totstored = 0  # count of hands stored in the database
        totdups = 0  # count of hands that are duplicates
        totpartial = 0  # count of hands that are partially imported
        totskipped = 0  # count of hands that are skipped
        toterrors = 0  # count of hands that cause errors
        tottime = 0  # total time spent importing hands
        filecount = 0  # count of files processed
        fileerrorcount = 0  # count of files that caused errors
        moveimportedfiles = False  # TODO need to wire this into GUI and make it prettier
        movefailedfiles = False  # TODO and this too

        # prepare progress popup window
        ProgressDialog = ImportProgressDialog(len(self.filelist), self.parent)
        ProgressDialog.resize(500, 200)
        ProgressDialog.show()

        for f in self.filelist:
            filecount = filecount + 1
            ProgressDialog.progress_update(f, str(self.database.getHandCount()))

            (stored, duplicates, partial, skipped, errors, ttime) = self._import_despatch(self.filelist[f])
            totstored += stored
            totdups += duplicates
            totpartial += partial
            totskipped += skipped
            toterrors += errors

            if moveimportedfiles and movefailedfiles:
                try:
                    if moveimportedfiles:
                        shutil.move(f, "c:\\fpdbimported\\%d-%s" % (filecount, os.path.basename(f[3:])))
                except:
                    fileerrorcount = fileerrorcount + 1
                    if movefailedfiles:
                        shutil.move(f, "c:\\fpdbfailed\\%d-%s" % (fileerrorcount, os.path.basename(f[3:])))

            self.logImport('bulk', f, stored, duplicates, partial, skipped, errors, ttime, self.filelist[f].fileId)

        ProgressDialog.accept()
        del ProgressDialog

        return (totstored, totdups, totpartial, totskipped, toterrors)

    # end def importFiles

    def _import_despatch(self, fpdbfile):
        """Imports data from a file into the database.

        Args:
            fpdbfile (File): The file to import.

        Returns:
            Tuple: A tuple containing the number of stored records, number of duplicates,
            number of partially imported records, number of skipped records, number of errors,
            and the total time it took to import the file.
        """
        stored, duplicates, partial, skipped, errors, ttime = 0,0,0,0,0,0

        if fpdbfile.ftype in ("hh", "both"):
            # Import data from hh file
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_hh_file(fpdbfile)

        if fpdbfile.ftype == "summary":
            # Import data from summary file
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_summary_file(fpdbfile)

        if fpdbfile.ftype == "both" and fpdbfile.path not in self.updatedsize:
            # If file type is both and file path has not been updated, import data from summary file
            self._import_summary_file(fpdbfile)

        # Print time it took to import the file
        print("DEBUG: _import_summary_file.ttime: %.3f %s" % (ttime, fpdbfile.ftype))

        # Return tuple of import results
        return (stored, duplicates, partial, skipped, errors, ttime)



    def calculate_auto2(self, db, scale, increment):
        """A second heuristic to determine a reasonable value of drop/don't drop
        This one adds up size of files to import to guess number of hands in them
        Example values of scale and increment params might be 10 and 500 meaning
        roughly: drop if importing more than 10% (100/scale) of hands in db or if
        less than 500 hands in db

        Args:
            db: Database object
            scale: Integer representing the scale parameter
            increment: Integer representing the increment parameter

        Returns:
            String representing whether to drop or not drop indexes
        """

        size_per_hand = 1300.0  # wag based on a PS 6-up FLHE file. Actual value not hugely important
                                # as values of scale and increment compensate for it anyway.
                                # decimal used to force float arithmetic

        # get number of hands in db
        if 'handsInDB' not in self.settings:
            try:
                tmpcursor = db.get_cursor()
                tmpcursor.execute("Select count(1) from Hands;")
                self.settings['handsInDB'] = tmpcursor.fetchone()[0]
            except:
                pass # if this fails we're probably doomed anyway

        # add up size of import files
        total_size = 0.0
        for file in self.filelist:
            if os.path.exists(file):
                stat_info = os.stat(file)
                total_size += stat_info.st_size

        # if hands_in_db is zero or very low, we want to drop indexes, otherwise compare
        # import size with db size somehow:
        ret = "don't drop"
        if self.settings['handsInDB'] < scale * (old_div(total_size,size_per_hand)) + increment:
            ret = "drop"
        #print "auto2: handsindb =", self.settings['handsInDB'], "total_size =", total_size, "size_per_hand =", \
        #      size_per_hand, "inc =", increment, "return:", ret
        return ret


    #Run import on updated files, then store latest update time. Called from GuiAutoImport.py
    def runUpdated(self):
        """
        Check for new files in monitored directories, update the size and time of files, and import them if they have changed.
        """
        # Check for new directories to monitor
        self._check_new_directories()

        # Check for updated files in monitored directories
        self._check_updated_files()

        # Remove files that have been marked for deletion
        self._remove_marked_files()

        # Rollback any changes and run post-import actions
        self._rollback_and_run_post_import()


    def _check_new_directories(self):
        """
        Check for new directories and add them to the import list.

        This function loops through the `dirlist` attribute, which is a list of tuples containing site and type
        information. For each tuple, it calls the `addImportDirectory` method of the current object instance to add
        the directory to the import list.

        Returns:
            None
        """
        for (site, type) in self.dirlist:
            self.addImportDirectory(
                self.dirlist[(site, type)][0], 
                False, 
                (site, type), 
                self.dirlist[(site, type)][1]
            )


    def _check_updated_files(self):
        """Check if any files in the filelist have been updated."""
        for f in self.filelist:
            if os.path.exists(f):
                stat_info = os.stat(f)
                if f in self.updatedsize:
                    self._import_file_if_updated(f, stat_info)
                else:
                    self._add_file_to_updated_list(f, stat_info)
            else:
                self.removeFromFileList[f] = True

    def _import_file_if_updated(self, f, stat_info):
        """
        Import a file only if it has been updated since it was last imported.

        Args:
            f (str): The filename of the file to import.
            stat_info (os.stat_result): The result of calling os.stat on the file.

        Returns:
            None
        """
        # Check if the file has been updated since it was last imported
        if stat_info.st_size > self.updatedsize[f] or stat_info.st_mtime > self.updatedtime[f]:
            try:
                self._print_updated_file_name(f)
            except KeyError:
                log.error("File '%s' seems to have disappeared" % f)

            # Import the file
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_despatch(self.filelist[f])
            self.logImport('auto', f, stored, duplicates, partial, skipped, errors, ttime, self.filelist[f].fileId)
            self.database.commit()

            # Print the import results
            try:
                self._print_import_results(stored, duplicates, partial, skipped, errors, ttime,f)
            except KeyError:
                pass

            # Update the size and time of the last import
            self.updatedsize[f] = stat_info.st_size
            self.updatedtime[f] = time.time()


    def _print_updated_file_name(self, f):
        """
        Given a file path, prints the base name of the file.

        Args:
            f (str): The path to the file.
        """
        if not os.path.isdir(f):
            # Print the base name of the file on a new line
            self.caller.addText("\n"+os.path.basename(f))
            print("os.path.basename",os.path.basename(f) )
            print("self.caller:", self.caller)
            # Print the base name of the file on the same line as previous output
            print(os.path.basename(f))

    def _print_import_results(self, stored, duplicates, partial, skipped, errors, ttime, f):
        """
        Prints import results.

        Args:
        stored (int): Number of imports stored.
        duplicates (int): Number of duplicate imports.
        partial (int): Number of partially imported modules.
        skipped (int): Number of skipped imports.
        errors (int): Number of import errors.
        ttime (float): Time taken to import.
        f (str): File path.
        """
        # Check if file path is valid
        if not os.path.isdir(f):
            # Print import results
            self.caller.addText(" %d stored, %d duplicates, %d partial, %d skipped, %d errors (time = %f)" % (stored, duplicates, partial, skipped, errors, ttime))
            print("self.caller2:",self.caller)

    def _add_file_to_updated_list(self, f, stat_info):
        """
        Adds a file to the updated list with its size and time if it was modified more than 60 seconds ago.
        If the file is a directory or was modified less than 60 seconds ago, it is not added to the list.

        Args:
            f (str): The file to add to the updated list.
            stat_info (os.stat_result): The stat information of the file.

        Returns:
            None
        """
        if os.path.isdir(f) or (time.time() - stat_info.st_mtime) < 60:
            # If the file is a directory or was modified less than 60 seconds ago, do not add to the updated list
            self.updatedsize[f] = 0
            self.updatedtime[f] = 0
        else:
            # Add the file to the updated list with its size and time
            self.updatedsize[f] = stat_info.st_size
            self.updatedtime[f] = time.time()


    #END Run import on updated files, then store latest update time. Called from GuiAutoImport.py (cut in little functions)

    def _remove_marked_files(self):
        """
        Removes files from `self.filelist` that have been marked for removal in `self.removeFromFileList`.

        :return: None
        """
        for file in self.removeFromFileList:
            # Check if the file is in the list of files to be removed
            if file in self.filelist:
                # Delete the file from the list
                del self.filelist[file]
        # Clear the list of files to be removed
        self.removeFromFileList = {}


    def _rollback_and_run_post_import(self):
        """
        Rollback the database transaction and run the post-import function.

        This function first rolls back any changes made to the database during the current
        transaction, then runs the `runPostImport` function to perform any necessary
        post-import tasks.

        """
        # Roll back any changes made during the current transaction
        self.database.rollback()

        # Run the post-import function
        self.runPostImport()

    def _import_hh_file(self, fpdbfile):
        """Function for actual import of a hh file
            This is now an internal function that should not be called directly."""

        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time.time())

        # Load filter, process file, pass returned filename to import_fpdb_file
        log.info(("Converting %s") % fpdbfile.path)
            
        filter_name = fpdbfile.site.filter_name
        mod = __import__(fpdbfile.site.hhc_fname)
        obj = getattr(mod, filter_name, None)
        if callable(obj):
            
            if fpdbfile.path in self.pos_in_file:  idx = self.pos_in_file[fpdbfile.path]
            else: self.pos_in_file[fpdbfile.path], idx = 0, 0
                
            hhc = obj( self.config, in_path = fpdbfile.path, index = idx, autostart=False
                      ,starsArchive = fpdbfile.archive
                      ,ftpArchive   = fpdbfile.archive
                      ,sitename     = fpdbfile.site.name)
            hhc.setAutoPop(self.mode=='auto')
            hhc.start()
            
            self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()
            #Tally the results
            partial  = getattr(hhc, 'numPartial')
            skipped  = getattr(hhc, 'numSkipped')
            errors   = getattr(hhc, 'numErrors')
            stored   = getattr(hhc, 'numHands')
            stored -= errors
            stored -= partial
            stored -= skipped
            
            if stored > 0:
                if self.caller: self.progressNotify()
                handlist = hhc.getProcessedHands()
                self.database.resetBulkCache(True)
                self.pos_in_file[fpdbfile.path] = hhc.getLastCharacterRead()
                (phands, ahands, ihands, to_hud) = ([], [], [], [])
                self.database.resetBulkCache()
                
                ####Lock Placeholder####
                for hand in handlist:
                    hand.prepInsert(self.database, printtest = self.settings['testData'])
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
                    doinsert = len(phands)==i+1
                    hand = phands[i]
                    try:
                        id = hand.getHandId(self.database, id)
                        hand.updateSessionsCache(self.database, None, doinsert)
                        hand.insertHands(self.database, fpdbfile.fileId, doinsert, self.settings['testData'])
                        hand.updateCardsCache(self.database, None, doinsert)
                        hand.updatePositionsCache(self.database, None, doinsert) 
                        hand.updateHudCache(self.database, doinsert)
                        hand.updateTourneyResults(self.database)
                        ihands.append(hand)
                        to_hud.append(hand.dbid_hands)
                    except FpdbHandDuplicate:
                        duplicates += 1
                        if (doinsert and ihands): backtrack = True
                    except:
                        error_trace = ''
                        formatted_lines = traceback.format_exc().splitlines()
                        for line in formatted_lines:
                            error_trace += line
                        tmp = hand.handText[0:200]
                        log.error(("Importer._import_hh_file: '%r' Fatal error: '%r'") % (fpdbfile.path, error_trace))
                        log.error(("'%r'") % tmp)
                        if (doinsert and ihands): backtrack = True
                    if backtrack: #If last hand in the file is a duplicate this will backtrack and insert the new hand records
                        hand = ihands[-1]
                        hp, hero = hand.handsplayers, hand.hero
                        hand.hero, self.database.hbulk, hand.handsplayers  = 0, self.database.hbulk[:-1], [] #making sure we don't insert data from this hand
                        self.database.bbulk = [b for b in self.database.bbulk if hand.dbid_hands != b[0]]
                        hand.updateSessionsCache(self.database, None, doinsert)
                        hand.insertHands(self.database, fpdbfile.fileId, doinsert, self.settings['testData'])
                        hand.updateCardsCache(self.database, None, doinsert)
                        hand.updatePositionsCache(self.database, None, doinsert)
                        hand.updateHudCache(self.database, doinsert)
                        hand.handsplayers, hand.hero = hp, hero
                #log.debug("DEBUG: hand.updateSessionsCache: %s" % (t5tot))
                #log.debug("DEBUG: hand.insertHands: %s" % (t6tot))
                #log.debug("DEBUG: hand.updateHudCache: %s" % (t7tot))
                self.database.commit()
                ####Lock Placeholder####
                
                for i in range(len(ihands)):
                    doinsert = len(ihands)==i+1
                    hand = ihands[i]
                    hand.insertHandsPlayers(self.database, doinsert, self.settings['testData'])
                    hand.insertHandsActions(self.database, doinsert, self.settings['testData'])
                    hand.insertHandsStove(self.database, doinsert)
                self.database.commit()

                #pipe the Hands.id out to the HUD
                if self.callHud:
                    print('self.callHud',self.callHud)
                    print('self.caller',self.caller)
                    for hid in list(to_hud):
                        try:
                            print('os.linesep',os.linesep)
                            print(type(to_hud))
                            print('hid',hid)
                            print('self.caller.pipe_to_hud',self.caller.pipe_to_hud)
                            print('self.caller.pipe_to_hud.stdin.write',self.caller.pipe_to_hud.stdin.write)
                            print(("fpdb_import: sending hand to hud"), hid, "pipe =", self.caller.pipe_to_hud)
                            self.caller.pipe_to_hud.stdin.write("%s" % (hid) + os.linesep)
                        except IOError as e:
                            log.error(("Failed to send hand to HUD: %s") % e)
                # Really ugly hack to allow testing Hands within the HHC from someone
                # with only an Importer objec
                if self.settings['cacheHHC']:
                    self.handhistoryconverter = hhc
        elif (self.mode=='auto'):
            return (0, 0, partial, skipped, errors, time.time() - ttime)
        
        stored -= duplicates
        
        if stored>0 and ihands[0].gametype['type']=='tour':
            if hhc.summaryInFile:
                fpdbfile.ftype = "both"

        ttime = time.time() - ttime
        return (stored, duplicates, partial, skipped, errors, ttime)
    
    def autoSummaryGrab(self, force = False):
        for f, fpdbfile in list(self.filelist.items()):
            stat_info = os.stat(f)
            if ((time.time() - stat_info.st_mtime)> 300 or force) and fpdbfile.ftype == "both":
                self._import_summary_file(fpdbfile)
                fpdbfile.ftype = "hh"

    def _import_summary_file(self, fpdbfile):
        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time.time())
        mod = __import__(fpdbfile.site.summary)
        obj = getattr(mod, fpdbfile.site.summary, None)
        if callable(obj):
            if self.caller: self.progressNotify()
            summaryTexts = self.readFile(obj, fpdbfile.path, fpdbfile.site.name)
            if summaryTexts is None:
                log.error("Found: '%s' with 0 characters... skipping" % fpbdfile.path)
                return (0, 0, 0, 0, 1, time.time()) # File had 0 characters
            ####Lock Placeholder####
            for j, summaryText in enumerate(summaryTexts, start=1):
                doinsert = len(summaryTexts)==j
                try:
                    conv = obj(db=self.database, config=self.config, siteName=fpdbfile.site.name, summaryText=summaryText, in_path = fpdbfile.path, header=summaryTexts[0])
                    self.database.resetBulkCache(False)
                    conv.insertOrUpdate(printtest = self.settings['testData'])
                except FpdbHandPartial as e:
                    partial += 1
                except FpdbParseError as e:
                    log.error(("Summary import parse error in file: %s") % fpdbfile.path)
                    errors += 1
                if j != 1:
                    print(("Finished importing %s/%s tournament summaries") %(j, len(summaryTexts)))
                stored = j
            ####Lock Placeholder####
        ttime = time.time() - ttime
        return (stored - errors - partial, duplicates, partial, skipped, errors, ttime)

    def progressNotify(self):
        "A callback to the interface while events are pending"
        QCoreApplication.processEvents()
            
    def readFile(self, obj, filename, site):
        if filename.endswith('.xls') or filename.endswith('.xlsx') and xlrd:
            obj.hhtype = "xls"
            if site=='PokerStars':
                tourNoField = 'Tourney'
            else:
                tourNoField = 'tournament key'
            summaryTexts = obj.summaries_from_excel(filename, tourNoField)
        else:
            foabs = obj.readFile(obj, filename)
            if foabs is None:
                return None
            re_Split = obj.getSplitRe(obj,foabs)
            summaryTexts = re.split(re_Split, foabs)
            # Summary identified but not split
            if len(summaryTexts)==1:
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
        
class ImportProgressDialog(QDialog):

    """
    Popup window to show progress
    
    Init method sets up total number of expected iterations
    If no parent is passed to init, command line
    mode assumed, and does not create a progress bar
    """
    
    def __del__(self):
        
        if self.parent:
            self.progress.destroy()


    def progress_update(self, filename, handcount):
            
        self.fraction += 1
        #update total if fraction exceeds expected total number of iterations
        if self.fraction > self.total:
            self.total = self.fraction
            self.pbar.setRange(0,self.total)
        
        self.pbar.setValue(self.fraction)
        
        self.handcount.setText(("Database Statistics") + " - " + ("Number of Hands:") + " " + handcount)
        
        now = datetime.datetime.now()
        now_formatted = now.strftime("%H:%M:%S")
        self.progresstext.setText(now_formatted + " - " + ("Importing") + " " +filename+"\n")


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