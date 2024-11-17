#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2008-2011 Ray E. Barker
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

# import L10n
##_ = L10n.get_translation()

import sys
from optparse import OptionParser


from loggingFpdb import get_logger

log = get_logger("parser")


def fpdb_options():
    """Process command line options for fpdb and HUD_main."""
    parser = OptionParser()  # Initialize option parser
    # Option for sending error messages to console instead of log file
    parser.add_option(
        "-x",
        "--errorsToConsole",
        action="store_true",
        help=("Send error messages to the console rather than the log file."),
    )
    # Option to specify database name
    parser.add_option("-d", "--databaseName", dest="dbname", help=("Specifies a database name."))
    # Option to specify configuration file path
    parser.add_option(
        "-c", "--configFile", dest="config", default=None, help=("Specifies the full path to a configuration file.")
    )
    # Option indicating program was restarted with a different path
    parser.add_option(
        "-r",
        "--rerunPython",
        action="store_true",
        help=("Indicates program was restarted with a different path (only allowed once)."),
    )
    # Option to specify hand history converter module name
    parser.add_option(
        "-k", "--konverter", dest="hhc", default="PokerStarsToFpdb", help=("Module name for Hand History Converter")
    )
    # Option to specify a site name
    parser.add_option("-s", "--sitename", dest="sitename", default=None, help=("A sitename"))
    # Option to set the logging level
    parser.add_option(
        "-l",
        "--logging",
        dest="log_level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "EMPTY"),
        help=("Error logging level:") + " (DEBUG, INFO, WARNING, ERROR, CRITICAL, EMPTY)",
        default="EMPTY",
    )
    # Option to print version information and exit
    parser.add_option("-v", "--version", action="store_true", help=("Print version information and exit."))
    # Option to force the initial run dialog
    parser.add_option("-i", "--initialrun", action="store_true", dest="initialRun", help=("Force initial-run dialog"))
    # Option to print useful usage lines
    parser.add_option(
        "-u", "--usage", action="store_true", dest="usage", default=False, help=("Print some useful one liners")
    )
    # The following options are used for SplitHandHistory.py (not used anymore)
    # Option to specify input file
    parser.add_option("-f", "--file", dest="filename", metavar="FILE", default=None, help=("Input file"))
    # Option to specify input directory
    parser.add_option("-D", "--directory", dest="directory", metavar="FILE", default=None, help=("Input directory"))
    # Option to specify output path in quiet mode
    parser.add_option("-o", "--outpath", dest="outpath", metavar="FILE", default=None, help=("Out path in quiet mode"))
    # Option for handling archive files from PokerStars or Full Tilt Poker
    parser.add_option(
        "-a",
        "--archive",
        action="store_true",
        dest="archive",
        default=False,
        help=("File to be split is a PokerStars or Full Tilt Poker archive file"),
    )
    # Developer option to print regression test data
    parser.add_option(
        "-t",
        "--testdata",
        action="store_true",
        dest="testData",
        default=False,
        help=("Developer option to print regression test data"),
    )
    # Option to specify the number of hands to be saved in each file
    parser.add_option(
        "-n",
        "--numhands",
        dest="hands",
        default="100",
        type="int",
        help=("How many hands do you want saved to each file. Default is 100"),
    )
    # Option to specify the X location for opening the window
    parser.add_option("--xloc", dest="xloc", default=None, type="int", help=("X location to open window"))
    # Option to specify the Y location for opening the window
    parser.add_option("--yloc", dest="yloc", default=None, type="int", help=("Y location to open window"))
    # Option to auto-start the auto-import feature
    parser.add_option("--autoimport", action="store_true", dest="autoimport", help=("Auto-start Auto-import"))
    # Option to start minimized
    parser.add_option("--minimized", action="store_true", dest="minimized", help=("Start Minimized"))
    # Option to start hidden
    parser.add_option("--hidden", action="store_true", dest="hidden", help=("Start Hidden"))

    (options, argv) = parser.parse_args()
    return (options, argv)


def site_alias(alias):
    """Function for converting various site aliases to the FPDB name"""
    tmp = alias  # Initialize with the original alias (not really up to date)
    aliases = {
        "Absolute": "Absolute",
        "AP": "Absolute",
        "Betfair": "Betfair",
        "BetOnline": "BetOnline",
        "Boss": "Boss",
        "Bovada": "Bovada",
        "Cake": "Cake",
        "Enet": "Enet",
        "Entraction": "Entraction",
        "Everest": "Everest",
        "Everleaf": "Everleaf",
        "FTP": "Full Tilt Poker",
        "Full Tilt Poker": "Full Tilt Poker",
        "iPoker": "iPoker",
        "Merge": "Merge",
        "Microgaming": "Microgaming",
        "OnGame": "OnGame",
        "PacificPoker": "PacificPoker",
        "Pacific": "PacificPoker",
        "Party": "PartyPoker",
        "PartyPoker": "PartyPoker",
        "Pkr": "Pkr",
        "PKR": "Pkr",
        "PokerStars": "PokerStars",
        "SealsWithClubs": "SealsWithClubs",
        "Stars": "PokerStars",
        "PT": "PokerTracker",
        "PokerTracker": "PokerTracker",
        "UltimateBet": "UltimateBet",
        "UB": "UltimateBet",
        "Winamax": "Winamax",
        "Win2day": "Boss",
    }

    try:
        tmp = aliases[alias]
    except KeyError as e:
        tmp = False
        log.error(f"Alias '{alias}' unknown")
        log.error(f"Exception: {e}")

    return tmp


if __name__ == "__main__":
    (options, argv) = fpdb_options()

    print("errorsToConsole =", options.errorsToConsole)
    print("database name   =", options.dbname)
    print("config file     =", options.config)

    print(("press enter to end"))
    sys.stdin.readline()
