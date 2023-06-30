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



from concurrent.futures import ThreadPoolExecutor
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
import glob
import logging, traceback


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

class Importer(object):
    def __init__(self, caller, settings, config, sql=None, parent=None):
        """
        Constructor for the class.

        Parameters:
        caller (str): The name of the caller.
        settings (dict): A dictionary containing settings for the object.
        config (Config): The configuration object.
        sql (Optional[SQL]): An SQL object to use for database operations.
        parent (Optional[object]): The parent object.

        Returns:
        None
        """
        # Assign variables
        self.settings = settings
        self.caller = caller
        self.config = config
        self.sql = sql
        self.parent = parent

        # Initialize variables
        self.idsite = IdentifySite.IdentifySite(config)
        self.filelist = {}
        self.dirlist = {}
        self.siteIds = {}
        self.removeFromFileList = {} # to remove deleted files
        self.monitor = False
        self.updatedsize = {}
        self.updatedtime = {}
        self.lines = None
        self.faobs = None # File as one big string
        self.mode = None
        self.pos_in_file = {} # dict to remember how far we have read in the file

        # Set defaults
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

        # Initialize writeq
        self.writeq = None
        self.database = Database.Database(self.config, sql=self.sql)
        self.writerdbs = []
        self.settings.setdefault("threads", 1) # value set by GuiBulkImport
        for i in range(self.settings['threads']):
            self.writerdbs.append(Database.Database(self.config, sql=self.sql))

        process_time() # init clock in windows


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
            self.writerdbs.extend([Database.Database(self.config, sql=self.sql) for i in range(self.settings['threads'] - len(self.writerdbs))])


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
        now = datetime.datetime.utcnow()

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
            [file, fpdbfile.site.name, datetime.datetime.utcnow(), datetime.datetime.utcnow(),
            0, 0, 0, 0, 0, 0, 0, False])
        self.database.commit()

            
    #Add an individual file to filelist
    def addImportFile(self, filename, site="auto"):
        """
        Add an import file to the list of files to be processed.

        Args:
            filename (str): The name of the file to be imported.
            site (str): The name of the site to which the file belongs. Defaults to "auto".

        Returns:
            bool: True if the file was successfully added, False otherwise.
        """
        #DEBUG->print("addimportfile: filename is a", filename.__class__, filename)

        # Check if file already exists in the list or if it does not exist in the file system
        if self.filelist.get(filename) != None or not os.path.exists(filename):
            return False

        # Process the file using the IDSite object
        self.idsite.processFile(filename)

        # If the file object is found in the IDSite object, add it to the list of files
        if self.idsite.get_fobj(filename):
            fpdbfile = self.idsite.filelist[filename]
        else:
            log.error("Importer.addImportFile: siteId Failed for: '%s'" % filename)
            return False

        self.addFileToList(fpdbfile)
        self.filelist[filename] = fpdbfile

        # If site is not in the list of siteIds, get the site ID from the database
        if site not in self.siteIds:
            result = self.database.get_site_id(fpdbfile.site.name)

            # If only one site ID is found, add it to the siteIds dictionary
            if len(result) == 1:
                self.siteIds[fpdbfile.site.name] = result[0][0]
            else:
                # If site ID is not found or multiple site IDs are found, log an error
                if len(result) == 0:
                    log.error(("Database ID for %s not found") % fpdbfile.site.name)
                else:
                    log.error(("More than 1 Database ID found for %s") % fpdbfile.site.name)

        return True

    # Called from GuiBulkImport to add a file or directory. Bulk import never monitors


    def addBulkImportImportFileOrDir(self, inputPath, site="auto"):
        """Add a file or directory for bulk import.

        Args:
            inputPath (str): The path of the file or directory to add for bulk import.
            site (str, optional): The site to import to. Defaults to "auto".

        Returns:
            bool: True if the file or directory was added for bulk import successfully, False otherwise.
        """
        # For Windows platform, force os.walk variable to be unicode.
        # See fpdb-main post 9th July 2011.
        if self.config.posix:
            pass
        else:
            inputPath = str(inputPath)

        # TODO: Only add sane files?
        if os.path.isdir(inputPath):
            # If inputPath is a directory, add all files inside it for bulk import.
            for file in glob.iglob(os.path.join(inputPath, '**', '*'), recursive=True):
                if os.path.isfile(file):
                    self.addImportFile(file, site=site)
            return True
        else:
            # If inputPath is a file, add it for bulk import.
            return self.addImportFile(inputPath, site=site)


    #Add a directory of files to filelist
    #Only one import directory per site supported.
    #dirlist is a hash of lists:
    #dirlist{ 'PokerStars' => ["/path/to/import/", "filtername"] }





    def addImportDirectory(self, dir, monitor=False, site=("default", "hh"), filter="passthrough"):
        """
        Adds a directory to the list of directories to be monitored for auto-imports.

        Args:
            dir (str): The directory to be added.
            monitor (bool, optional): To monitor the directory or not. Defaults to False.
            site (tuple, optional): Site name and hostname. Defaults to ("default", "hh").
            filter (str, optional): Filter to be applied. Defaults to "passthrough".
        """
        if os.path.isdir(dir):
            if monitor:
                self.monitor = True
                self.dirlist[site] = [dir] + [filter]

            # Define a function to handle each file
            def handle_file(filename):
                # Check if the file was modified in the last 12 hours
                if (time() - os.stat(filename).st_mtime) <= 43200:
                    # Add the file to the list of files to be auto-imported
                    self.addImportFile(filename, "auto")

            # Create a thread pool with 8 workers
            with ThreadPoolExecutor(max_workers=8) as executor:
                # Recursively iterate through all sub-directories and files in the given directory
                for subdir, _, files in os.walk(dir):
                    # Submit a task for each file to be handled asynchronously
                    for file in files:
                        # Generate the absolute path of the file
                        filename = os.path.join(subdir, file)
                        executor.submit(handle_file, filename)
        else:
            # Log a warning if the given path is not a directory
            logging.warning(f"Attempted to add non-directory '{dir}' as an import directory")

    def runImport(self):
        """Run full import on self.filelist. This is called from GuiBulkImport.py"""

        # Initial setup
        start = datetime.datetime.now()
        starttime = time()
        log.info(("Started at %s -- %d files to import. indexes: %s") % (start, len(self.filelist), self.settings['dropIndexes']))

        # If dropIndexes is set to 'auto', calculate the value using calculate_auto2
        if self.settings['dropIndexes'] == 'auto':
            self.settings['dropIndexes'] = self.calculate_auto2(self.database, 12.0, 500.0)

        # If dropHudCache is set to 'auto', calculate the value using calculate_auto2
        if 'dropHudCache' in self.settings and self.settings['dropHudCache'] == 'auto':
            self.settings['dropHudCache'] = self.calculate_auto2(self.database, 25.0, 500.0)    # returns "drop"/"don't drop"

        # Import files
        (totstored, totdups, totpartial, totskipped, toterrors) = self.importFiles(None)

        # Tidying up after import
        #if 'dropHudCache' in self.settings and self.settings['dropHudCache'] == 'drop':
        #    log.info(("rebuild_caches"))
        #    self.database.rebuild_caches()
        #else:
        #    log.info(("runPostImport"))
        self.runPostImport()
        self.database.analyzeDB()
        endtime = time()

        # Return results of import
        return (totstored, totdups, totpartial, totskipped, toterrors, endtime-starttime)

    
    def runPostImport(self):
        """
        Clean up the database after importing data.
        """
        # Clean up tourney types
        self.database.cleanUpTourneyTypes()

        # Clean up weeks and months
        self.database.cleanUpWeeksMonths()

        # Reset clean
        self.database.resetClean()


    def importFiles(self, q):
        """Read filenames in self.filelist and pass to despatcher.

        Args:
            q: Queue object to enable communication with the GUI.

        Returns:
            A tuple containing the number of files stored, duplicates, partial, skipped and errors.
        """

        # Initialize counters
        totstored = 0
        totdups = 0
        totpartial = 0
        totskipped = 0
        toterrors = 0
        tottime = 0
        filecount = 0
        fileerrorcount = 0

        # Initialize flags for moving files
        moveimportedfiles = True
        movefailedfiles = True



        # Check if directories exist, create them if they don't
        imported_path = os.path.join(os.getcwd(), "fpdbimported")
        if not os.path.exists(imported_path):
            os.makedirs(imported_path)
        failed_path = os.path.join(os.getcwd(), "fpdbfailed")
        if not os.path.exists(failed_path):
            os.makedirs(failed_path)

        for f in self.filelist:
            filecount += 1


            # Import the current file and update the counters
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_despatch(self.filelist[f])
            totstored += stored
            totdups += duplicates
            totpartial += partial
            totskipped += skipped
            toterrors += errors

            # Move the imported and failed files, if applicable
            # TODO: sub directory named by site name and home directory
            if moveimportedfiles and movefailedfiles:
                try:
                    if moveimportedfiles:
                        imported_path = os.path.join(os.getcwd(), "fpdbimported", f"{filecount}-{os.path.basename(f)[3:]}")
                        shutil.move(f, imported_path)
                    if movefailedfiles:
                        failed_path = os.path.join(os.getcwd(), "fpdbfailed", f"{fileerrorcount}-{os.path.basename(f)[3:]}")
                        shutil.move(f, failed_path)
                except:
                    fileerrorcount += 1

            # Log the import
            self.logImport('bulk', f, stored, duplicates, partial, skipped, errors, ttime, self.filelist[f].fileId)



        # Return tuple containing counters
        return (totstored, totdups, totpartial, totskipped, toterrors)


    # end def importFiles

    def _import_despatch(self, fpdbfile):
        """
        Import data from a file and update the database.

        Parameters:
            fpdbfile (FPDBFile): The file object to import.

        Returns:
            Tuple: A tuple containing the number of records stored, the number of duplicates found, the number of partially imported records, the number of records skipped, the number of errors encountered, and the time taken for the import.
        """
        # Initialize the counters and timer.
        stored, duplicates, partial, skipped, errors, ttime = 0, 0, 0, 0, 0, 0

        # If the file type is "hh" or "both", import the household file and update the counters and timer.
        if fpdbfile.ftype in ("hh", "both"):
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_hh_file(fpdbfile)

        # If the file type is "summary", import the summary file and update the counters and timer.
        if fpdbfile.ftype == "summary":
            (stored, duplicates, partial, skipped, errors, ttime) = self._import_summary_file(fpdbfile)

        # If the file type is "both" and the file path has not been updated, import the summary file and update the counters and timer.
        if fpdbfile.ftype == "both" and fpdbfile.path not in self.updatedsize:
            self._import_summary_file(fpdbfile)

        # Print a debug message with the time taken for the import and the file type.
        #print("DEBUG: _import_summary_file.ttime: %.3f %s" % (ttime, fpdbfile.ftype))

        # Return the counters and timer.
        return (stored, duplicates, partial, skipped, errors, ttime)


    def calculate_auto2(self, db, scale, increment):
        """
        A second heuristic to determine a reasonable value of drop/don't drop
        This one adds up size of files to import to guess number of hands in them
        Example values of scale and increment params might be 10 and 500 meaning
        roughly: drop if importing more than 10% (100/scale) of hands in db or if
        less than 500 hands in db

        Args:
        - self: the instance of the class
        - db: the database to connect to
        - scale: an integer to determine when to drop indexes
        - increment: an integer to determine when to drop indexes

        Returns:
        A string "drop" or "don't drop"
        """
        # Size per hand estimated based on a PS 6-up FLHE file. Actual value not hugely important
        # as values of scale and increment compensate for it anyway. Decimal used to force float arithmetic
        size_per_hand = 1300.0  

        # Get number of hands in the database
        if 'handsInDB' not in self.settings:
            try:
                tmpcursor = db.get_cursor()
                tmpcursor.execute("Select count(1) from Hands;")
                self.settings['handsInDB'] = tmpcursor.fetchone()[0]
            except:
                # If this fails we're probably doomed anyway
                pass 

        # Add up size of import files
        total_size = 0.0
        for file in self.filelist:
            if os.path.exists(file):
                stat_info = os.stat(file)
                total_size += stat_info.st_size

        # If hands_in_db is zero or very low, we want to drop indexes, otherwise compare
        # import size with db size somehow:
        ret = "don't drop"
        if self.settings['handsInDB'] < scale * (old_div(total_size,size_per_hand)) + increment:
            ret = "drop"

        # Debugging line for printing the values of different variables
        # print "auto2: handsindb =", self.settings['handsInDB'], "total_size =", total_size, "size_per_hand =", \
        #       size_per_hand, "inc =", increment, "return:", ret

        return ret


    #Run import on updated files, then store latest update time. Called from GuiAutoImport.py
    def runUpdated(self):
        """Check for new files in monitored directories"""
        for (site,type) in self.dirlist:
            self.addImportDirectory(self.dirlist[(site,type)][0], False, (site,type), self.dirlist[(site,type)][1])

        for f in self.filelist:
            if os.path.exists(f):
                stat_info = os.stat(f)
                if f in self.updatedsize: # we should be able to assume that if we're in size, we're in time as well
                    if stat_info.st_size > self.updatedsize[f] or stat_info.st_mtime > self.updatedtime[f]:
                        try:
                            if not os.path.isdir(f):
                                self.caller.addText("\n"+os.path.basename(f))
                                #("os.path.basename",os.path.basename(f) )
                                #print("self.caller:", self.caller)
                                #print(os.path.basename(f))
                        except KeyError:
                            log.error("File '%s' seems to have disappeared" % f)
                        (stored, duplicates, partial, skipped, errors, ttime) = self._import_despatch(self.filelist[f])
                        self.logImport('auto', f, stored, duplicates, partial, skipped, errors, ttime, self.filelist[f].fileId)
                        self.database.commit()
                        try:
                            if not os.path.isdir(f): # Note: This assumes that whatever calls us has an "addText" func
                                self.caller.addText(" %d stored, %d duplicates, %d partial, %d skipped, %d errors (time = %f)" % (stored, duplicates, partial, skipped, errors, ttime))
                                #print("self.caller2:",self.caller)
                        except KeyError: # TODO: Again, what error happens here? fix when we find out ..
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
            return (0, 0, partial, skipped, errors, time() - ttime)
        
        stored -= duplicates
        
        if stored>0 and ihands[0].gametype['type']=='tour':
            if hhc.summaryInFile:
                fpdbfile.ftype = "both"

        ttime = time() - ttime
        return (stored, duplicates, partial, skipped, errors, ttime)
    
    def autoSummaryGrab(self, force = False):
        for f, fpdbfile in list(self.filelist.items()):
            stat_info = os.stat(f)
            if ((time() - stat_info.st_mtime)> 300 or force) and fpdbfile.ftype == "both":
                self._import_summary_file(fpdbfile)
                fpdbfile.ftype = "hh"

    def _import_summary_file(self, fpdbfile):
        (stored, duplicates, partial, skipped, errors, ttime) = (0, 0, 0, 0, 0, time())
        mod = __import__(fpdbfile.site.summary)
        obj = getattr(mod, fpdbfile.site.summary, None)
        if callable(obj):
            if self.caller: self.progressNotify()
            summaryTexts = self.readFile(obj, fpdbfile.path, fpdbfile.site.name)
            if summaryTexts is None:
                log.error("Found: '%s' with 0 characters... skipping" % fpbdfile.path)
                return (0, 0, 0, 0, 1, time()) # File had 0 characters
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
        ttime = time() - ttime
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
        
