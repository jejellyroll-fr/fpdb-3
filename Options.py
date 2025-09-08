"""Options module for FPDB command line argument parsing.

Copyright 2008-2011 Ray E. Barker
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
In the "official" distribution you can find the license in agpl-3.0.txt.
"""

import sys
from optparse import OptionParser

from loggingFpdb import get_logger

log = get_logger("options")


def fpdb_options() -> tuple:
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
    parser.add_option(
        "-d",
        "--databaseName",
        dest="dbname",
        help=("Specifies a database name."),
    )
    # Option to specify configuration file path
    parser.add_option(
        "-c",
        "--configFile",
        dest="config",
        default=None,
        help=("Specifies the full path to a configuration file."),
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
        "-k",
        "--konverter",
        dest="hhc",
        default="PokerStarsToFpdb",
        help=("Module name for Hand History Converter"),
    )
    # Option to specify a site name
    parser.add_option(
        "-s",
        "--sitename",
        dest="sitename",
        default=None,
        help=("A sitename"),
    )
    # Option to set the logging level
    parser.add_option(
        "-l",
        "--logging",
        dest="log_level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "EMPTY"),
        help="Error logging level: (DEBUG, INFO, WARNING, ERROR, CRITICAL, EMPTY)",
        default="EMPTY",
    )
    # Option to print version information and exit
    parser.add_option(
        "-v",
        "--version",
        action="store_true",
        help=("Print version information and exit."),
    )
    # Option to force the initial run dialog
    parser.add_option(
        "-i",
        "--initialrun",
        action="store_true",
        dest="initialRun",
        help=("Force initial-run dialog"),
    )
    # Option to print useful usage lines
    parser.add_option(
        "-u",
        "--usage",
        action="store_true",
        dest="usage",
        default=False,
        help=("Print some useful one liners"),
    )
    # The following options are used for SplitHandHistory.py (not used anymore)
    # Option to specify input file
    parser.add_option(
        "-f",
        "--file",
        dest="filename",
        metavar="FILE",
        default=None,
        help=("Input file"),
    )
    # Option to specify input directory
    parser.add_option(
        "-D",
        "--directory",
        dest="directory",
        metavar="FILE",
        default=None,
        help=("Input directory"),
    )
    # Option to specify output path in quiet mode
    parser.add_option(
        "-o",
        "--outpath",
        dest="outpath",
        metavar="FILE",
        default=None,
        help=("Out path in quiet mode"),
    )
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
    parser.add_option(
        "--xloc",
        dest="xloc",
        default=None,
        type="int",
        help=("X location to open window"),
    )
    # Option to specify the Y location for opening the window
    parser.add_option(
        "--yloc",
        dest="yloc",
        default=None,
        type="int",
        help=("Y location to open window"),
    )
    # Option to auto-start the auto-import feature
    parser.add_option(
        "--autoimport",
        action="store_true",
        dest="autoimport",
        help=("Auto-start Auto-import"),
    )
    # Option to start minimized
    parser.add_option(
        "--minimized",
        action="store_true",
        dest="minimized",
        help=("Start Minimized"),
    )
    # Option to start hidden
    parser.add_option(
        "--hidden",
        action="store_true",
        dest="hidden",
        help=("Start Hidden"),
    )

    (options, argv) = parser.parse_args()
    return (options, argv)


def site_alias(alias: str) -> str | bool:
    """Function for converting various site aliases to the FPDB name."""
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
    except KeyError:
        tmp = False
        log.exception("Alias '%s' unknown", alias)

    return tmp


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    import argparse

    parser = argparse.ArgumentParser(description="FPDB Options utility and command line parser")

    # Add all the standard FPDB options that are in fpdb_options()
    parser.add_argument(
        "-x",
        "--errorsToConsole",
        action="store_true",
        help="Send error messages to the console rather than the log file",
    )
    parser.add_argument("-d", "--databaseName", dest="dbname", help="Specifies a database name")
    parser.add_argument("-c", "--configFile", dest="config", help="Specifies the full path to a configuration file")
    parser.add_argument(
        "-r",
        "--rerunPython",
        action="store_true",
        help="Indicates program was restarted with a different path (only allowed once)",
    )
    parser.add_argument(
        "-k", "--konverter", dest="hhc", default="PokerStarsToFpdb", help="Module name for Hand History Converter"
    )
    parser.add_argument("-s", "--sitename", dest="sitename", help="A sitename")
    parser.add_argument(
        "-l",
        "--logging",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "EMPTY"],
        default="EMPTY",
        help="Error logging level: (DEBUG, INFO, WARNING, ERROR, CRITICAL, EMPTY)",
    )
    parser.add_argument("-v", "--version", action="store_true", help="Print version information and exit")
    parser.add_argument("-i", "--initialrun", action="store_true", dest="initialRun", help="Force initial-run dialog")
    parser.add_argument("-u", "--usage", action="store_true", help="Print some useful one liners")
    parser.add_argument("-f", "--file", dest="filename", metavar="FILE", help="Input file")
    parser.add_argument("-D", "--directory", dest="directory", metavar="DIR", help="Input directory")
    parser.add_argument("-o", "--outpath", dest="outpath", metavar="PATH", help="Out path in quiet mode")
    parser.add_argument(
        "-a", "--archive", action="store_true", help="File to be split is a PokerStars or Full Tilt Poker archive file"
    )
    parser.add_argument(
        "-t", "--testdata", action="store_true", dest="testData", help="Developer option to print regression test data"
    )

    # Add testing/utility options
    parser.add_argument("--test-parsing", action="store_true", help="Test FPDB option parsing with legacy OptionParser")
    parser.add_argument("--test-aliases", action="store_true", help="Show poker site aliases")
    parser.add_argument("--interactive", action="store_true", help="Run original interactive test")

    args = parser.parse_args(argv)

    # Handle version flag
    if args.version:
        print("FPDB Options Parser - Part of Free Poker DataBase")
        print("Version information would go here")
        return 0

    # Handle usage flag
    if args.usage:
        print("\n=== Useful FPDB Command Line Examples ===")
        print("fpdb.py -c /path/to/config.xml")
        print("fpdb.py -d mydatabase -l DEBUG")
        print("HUD_main.py -x -c /path/to/config.xml")
        return 0

    # If no specific action requested, show help
    if not any(
        [
            args.test_parsing,
            args.test_aliases,
            args.interactive,
            args.errorsToConsole,
            args.dbname,
            args.config,
            args.rerunPython,
            args.hhc != "PokerStarsToFpdb",
            args.sitename,
            args.log_level != "EMPTY",
            args.initialRun,
            args.filename,
            args.directory,
            args.outpath,
            args.archive,
            args.testData,
        ]
    ):
        parser.print_help()
        return 0

    if args.test_parsing:
        print("Testing FPDB option parsing...")
        try:
            # Test with empty args to avoid conflicts
            original_argv = sys.argv[:]
            sys.argv = ["Options.py"]  # Reset sys.argv temporarily
            (options, remaining_argv) = fpdb_options()
            sys.argv = original_argv  # Restore original argv
            print("✓ Option parsing successful")
            print(f"Parsed options: {options}")
            print(f"Remaining args: {remaining_argv}")
        except Exception as e:
            sys.argv = original_argv if "original_argv" in locals() else sys.argv
            print(f"✗ Option parsing failed: {e}")
            return 1

    if args.test_aliases:
        print("\n=== Poker Site Aliases ===")
        test_aliases = ["Stars", "Party", "FTP", "Bovada", "PKR", "UB", "Cake", "PT"]
        for alias in test_aliases:
            try:
                site = site_alias(alias)
                if site:
                    print(f"  {alias} → {site}")
                else:
                    print(f"  {alias} → (unknown)")
            except Exception as e:
                print(f"  {alias} → Error: {e}")

    if args.interactive:
        print("Running original interactive test...")
        (options, argv_parsed) = fpdb_options()
        print("Press ENTER to continue...")
        sys.stdin.readline()

    return 0


if __name__ == "__main__":
    sys.exit(main())
