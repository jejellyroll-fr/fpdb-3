
import os

from Hand import *
import Configuration

import Importer

import pprint
import pathlib
from Hand import *

import Configuration
import Database
import SQL
import ImporterLight
import Exceptions

config = Configuration.Config(file = "HUD_config.test.xml")
db = Database.Database(config)
sql = SQL.Sql(db_server = 'sqlite')

settings = {}
settings.update(config.get_db_parameters())
settings.update(config.get_import_parameters())
settings.update(config.get_default_paths())

pp = pprint.PrettyPrinter(indent=4)

path = pathlib.Path(Configuration.GRAPHICS_PATH)
transformed_path = path.parent
locale_path = pathlib.Path(transformed_path, "pyfpdb", "regression-test-files")
reg_path =  str(locale_path)


def get_path_files(path):
    """
    Get all path files in a dict()

    Args:
        path (str): The path to the directory

    Returns:
        dict: A dict of all path files
    """
    files = {}
    for file in os.listdir(path):
        full_path = os.path.join(path, file)
        if os.path.isfile(full_path):
            files[file] = full_path
    return files

def get_parent_of_last_subpath(last_subpath):
    """
    Get the parent of the last subpath in a path

    Args:
        last_subpath (str): The last subpath

    Returns:
        str: The parent path
    """
    parent_path = os.path.dirname(last_subpath)
    while last_subpath != os.path.basename(parent_path):
        last_subpath = os.path.basename(parent_path)
        parent_path = os.path.dirname(parent_path)
    return parent_path




def get_last_level_subpaths(path):
    """
    Lists all the last level subpaths of a directory and writes them to a dictionary.

    Args:
        path (str): The path to the directory.

    Returns:
        dict: A dictionary of all last level subpaths with their full paths as values.
    """
    subpaths = {}

    # Walk through the directory tree
    for dirpath, dirnames, filenames in os.walk(path):
        # For each directory, get its full path and the name of the last level subpath
        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            last_level_subpath = os.path.basename(full_path)
            path_trans = pathlib.Path(full_path)
            full_path_minus_one = path_trans.parent
            last_level_subpath_minus_one = os.path.basename(full_path_minus_one)
            full_path_minus_two = full_path_minus_one.parent
            last_level_subpath_minus_two = os.path.basename(full_path_minus_two)
            key = f"{last_level_subpath_minus_one}-{last_level_subpath_minus_two}-{last_level_subpath}"
            if key in list_sites and key not in subpaths:
                subpaths[key] = full_path


    return subpaths



def delete_keys(dict_, keys):
    """
    Delete keys in a dict

    Args:
        dict_ (dict): The dict to delete keys from
        keys (list): The list of keys to delete

    Returns:
        dict: The dict with the keys deleted
    """
    for key in keys:
        if key in dict_:
            del dict_[key]
    return dict_

def run_Import(filename, site):

        db.recreate_tables()
        importer = ImporterLight.Importer(False, settings, config)
        importer.setDropIndexes("don't drop")

        importer.setThreads(-1)
        importer.addBulkImportImportFileOrDir(str(filename), site= str(site))

        importer.setCallHud(False)
        stored, dups, partial, errs, ttime, *excess = importer.runImport()

        print(
            f"DEBUG: stored: {stored} dups: {dups} partial: {partial} errs: {errs} ttime: {ttime}"
        )
        importer.clearFileList()


list_sites = {
    'Betfair-cash-Flop': True,
    'Betfair-cash-Draw': True,
    'Betfair-cash-Stud': True,
    'Betfair-tour-Flop': True,
    'Betfair-tour-Draw': True,
    'Betfair-tour-Stud': True,
    'Betfair-summaries-Flop': True,
    'Betfair-summaries-Draw': True,
    'Betfair-summaries-Stud': True,
    'BetOnline-cash-Flop': False,
    'BetOnline-cash-Draw': False,
    'BetOnline-cash-Stud': False,
    'BetOnline-tour-Flop': False,
    'BetOnline-tour-Draw': False,
    'BetOnline-tour-Stud': False,
    'BetOnline-summaries-Flop': False,
    'BetOnline-summaries-Draw': False,
    'BetOnline-summaries-Stud': False,
    'Bovada-cash-Flop': False,
    'Bovada-cash-Draw': False,
    'Bovada-cash-Stud': False,
    'Bovada-tour-Flop': False,
    'Bovada-tour-Draw': False,
    'Bovada-tour-Stud': False,
    'Bovada-summaries-Flop': False,
    'Bovada-summaries-Draw': False,
    'Bovada-summaries-Stud': False,
    'Cake-cash-Flop': False,
    'Cake-cash-Draw': False,
    'Cake-cash-Stud': False,
    'Cake-tour-Flop': False,
    'Cake-tour-Draw': False,
    'Cake-tour-Stud': False,
    'Cake-summaries-Flop': False,
    'Cake-summaries-Draw': False,
    'Cake-summaries-Stud': False,
    'Enet-cash-Flop': False,
    'Enet-cash-Draw': False,
    'Enet-cash-Stud': False,
    'Enet-tour-Flop': False,
    'Enet-tour-Draw': False,
    'Enet-tour-Stud': False,
    'Enet-summaries-Flop': False,
    'Enet-summaries-Draw': False,
    'Enet-summaries-Stud': False,
    'Entraction-cash-Flop': False,
    'Entraction-cash-Draw': False,
    'Entraction-cash-Stud': False,
    'Entraction-tour-Flop': False,
    'Entraction-tour-Draw': False,
    'Entraction-tour-Stud': False,
    'Entraction-summaries-Flop': False,
    'Entraction-summaries-Draw': False,
    'Entraction-summaries-Stud': False,
    'PokerStars-cash-Stud': False,
    'PokerStars-tour-Flop': False,
    'PokerStars-tour-Draw': False,
    'PokerStars-tour-Stud': False,
    'PokerStars-summaries-Flop': False,
    'PokerStars-summaries-Draw': False,
    'PokerStars-summaries-Stud': False,
    'SealsWithClubs-cash-Flop': False,
    'SealsWithClubs-cash-Draw': False,
    'SealsWithClubs-cash-Stud': False,
    'SealsWithClubs-tour-Flop': False,
    'SealsWithClubs-tour-Draw': False,
    'SealsWithClubs-tour-Stud': False,
    'SealsWithClubs-summaries-Flop': False,
    'SealsWithClubs-summaries-Draw': False,
    'SealsWithClubs-summaries-Stud': False,
    'Stars-cash-Flop': False,
    'Stars-cash-Draw': False,
    'Stars-cash-Stud': False,
    'Stars-tour-Flop': False,
    'Stars-tour-Draw': False,
    'Stars-tour-Stud': False,
    'Stars-summaries-Flop': False,
    'Stars-summaries-Draw': False,
    'Stars-summaries-Stud': False,
    'PT-cash-Flop': False,
    'PT-cash-Draw': False,
    'PT-cash-Stud': False,
    'PT-tour-Flop': False,
    'PT-tour-Draw': False,
    'PT-tour-Stud': False,
    'PT-summaries-Flop': False,
    'PT-summaries-Draw': False,
    'PT-summaries-Stud': False,
    'PokerTracker-cash-Flop': False,
    'PokerTracker-cash-Draw': False,
    'PokerTracker-cash-Stud': False,
    'PokerTracker-tour-Flop': False,
    'PokerTracker-tour-Draw': False,
    'PokerTracker-tour-Stud': False,
    'PokerTracker-summaries-Flop': False,
    'PokerTracker-summaries-Draw': False,
    'PokerTracker-summaries-Stud': False,
    'Winamax-cash-Flop': True,
    'Winamax-cash-Draw': False,
    'Winamax-cash-Stud': False,
    'Winamax-tour-Flop': False,
    'Winamax-tour-Draw': False,
    'Winamax-tour-Stud': False,
    'Winamax-summaries-Flop': False,
    'Winamax-summaries-Draw': False,
    'Winamax-summaries-Stud': False,
    'GGPoker-cash-Flop': False,
    'GGPoker-cash-Draw': False,
    'GGPoker-cash-Stud': False,
    'GGPoker-tour-Flop': False,
    'GGPoker-tour-Draw': False,
    'GGPoker-tour-Stud': False,
    'GGPoker-summaries-Flop': False,
    'GGPoker-summaries-Draw': False,
    'GGPoker-summaries-Stud': False,
    'iPoker-cash-Flop': False,
    'iPoker-cash-Draw': False,
    'iPoker-cash-Stud': False,
    'iPoker-tour-Flop': False,
    'iPoker-tour-Draw': False,
    'iPoker-tour-Stud': False,
    'iPoker-summaries-Flop': False,
    'iPoker-summaries-Draw': False,
    'iPoker-summaries-Stud': False,
    'Merge-cash-Flop': False,
    'Merge-cash-Draw': False,
    'Merge-cash-Stud': False,
    'Merge-tour-Flop': False,
    'Merge-tour-Draw': False,
    'Merge-tour-Stud': False,
    'Merge-summaries-Flop': False,
    'Merge-summaries-Draw': False,
    'Merge-summaries-Stud': False,
    'Microgaming-cash-Flop': False,
    'Microgaming-cash-Draw': False,
    'Microgaming-cash-Stud': False,
    'Microgaming-tour-Flop': False,
    'Microgaming-tour-Draw': False,
    'Microgaming-tour-Stud': False,
    'Microgaming-summaries-Flop': False,
    'Microgaming-summaries-Draw': False,
    'Microgaming-summaries-Stud': False,
    'PacificPoker-cash-Flop': False,
    'PacificPoker-cash-Draw': False,
    'PacificPoker-cash-Stud': False,
    'PacificPoker-tour-Flop': False,
    'PacificPoker-tour-Draw': False,
    'PacificPoker-tour-Stud': False,
    'PacificPoker-summaries-Flop': False,
    'PacificPoker-summaries-Draw': False,
    'PacificPoker-summaries-Stud': False,
    'PartyPoker-cash-Flop': False,
    'PartyPoker-cash-Draw': False,
    'PartyPoker-cash-Stud': False,
    'PartyPoker-tour-Flop': False,
    'PartyPoker-tour-Draw': False,
    'PartyPoker-tour-Stud': False,
    'PartyPoker-summaries-Flop': False,
    'PartyPoker-summaries-Draw': False,
    'PartyPoker-summaries-Stud': False,
    'PokerStars-cash-Flop': False,
    'PokerStars-cash-Draw': False,
}

delete_path = {   
            'cash',
            'tour', 
            'summaries',
            'Flop',
            'Draw',
            'test',
            'Stud',
            'Mixed',


        }



subpath = get_last_level_subpaths(reg_path)

for key, value in subpath.items():
    print(f"Key: {key}, Value: {value}")  

clean_subpath = delete_keys(subpath, delete_path)

for key, value in clean_subpath.items():
   print(f"Key: {key}, Value: {value}")  

for key, value in clean_subpath.items():
    if list_sites[key] == True:
        print(f"Key: {key}, Value: {value}")
        new_dict = get_path_files(value)


for key, value in new_dict.items():
    print(f"Key: {key}, Value: {value}")
    print(type(value))
    #test_Import(value, "auto")
