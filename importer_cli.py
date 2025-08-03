#!/usr/bin/env python

import argparse
import logging
import os
import sys
import warnings

import Configuration
import Database
from HandDataReporter import HandDataReporter
from Importer import Importer


def main() -> None:
    # Suppress FutureWarnings
    warnings.simplefilter(action="ignore", category=FutureWarning)

    parser = argparse.ArgumentParser(description="Import hand history files into fpdb.")
    parser.add_argument("paths", metavar="PATH", type=str, nargs="+",
                        help="File or directory paths to import.")
    parser.add_argument("--site", type=str, default="auto",
                        help="Poker site name (e.g., PokerStars). Default: auto-detect.")
    parser.add_argument("--no-progress", action="store_true",
                        help="Disable progress reporting.")
    parser.add_argument("--config", type=str,
                        help="Path to fpdb.toml configuration file.")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging to see detailed import information.")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose logging (INFO level).")

    # Hand data reporting options
    parser.add_argument("--report-level", choices=["summary", "detailed", "full", "hierarchy"], default="summary",
                        help="Level of hand data reporting detail. Default: summary")
    parser.add_argument("--report-file", type=str,
                        help="Generate detailed report for specific file path")
    parser.add_argument("--export-json", type=str,
                        help="Export detailed hand data to JSON file")
    parser.add_argument("--enable-hand-reporting", action="store_true",
                        help="Enable detailed hand data reporting and analysis")

    args = parser.parse_args()

    # Setup logging based on debug/verbose flags
    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s:%(funcName)s] [%(levelname)s] %(message)s")
    elif args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s:%(funcName)s] [%(levelname)s] %(message)s")
    else:
        # Silence all logs except CRITICAL (quiet mode for normal usage)
        # Capture and disable all logging immediately
        logging.getLogger().disabled = True

        # Redirect stderr to suppress system messages
        original_stderr = sys.stderr
        devnull = open(os.devnull, "w")
        sys.stderr = devnull

        # Store originals for restoration when needed
        globals()["original_stderr"] = original_stderr
        globals()["devnull"] = devnull

    # Setup configuration
    config_file = None
    if args.config:
        if os.path.exists(args.config):
            config_file = args.config
        else:
            pass
            # Decide if you want to exit or proceed with default config
            # sys.exit(1)

    config = Configuration.Config(file=config_file)

    # Setup database
    db = Database.Database(config)

    # Setup hand data reporter if requested
    hand_reporter = None
    if args.enable_hand_reporting:
        hand_reporter = HandDataReporter(report_level=args.report_level)
        # Pass debug mode information to reporter
        if args.debug:
            hand_reporter._debug_mode = True

    # Setup importer
    importer = Importer(caller=None, settings={}, config=config, sql=db.sql, parent=None)
    if args.no_progress:
        importer.parent = "CLI_NO_PROGRESS" # Special value to completely silence progress dialog

    # Pass reporter to importer if enabled
    if hand_reporter:
        importer.setHandDataReporter(hand_reporter)

    # Add files/dirs to importer
    for path in args.paths:
        if not os.path.exists(path):
            continue
        importer.addBulkImportImportFileOrDir(path, site=args.site)

    if not importer.filelist:
        return

    # Run the import
    (stored, dups, partial, skipped, errors, ttime) = importer.runImport()

    # Process tournament summaries for files marked as "both"

    # Debug: check which files are marked as "both"
    both_files = [f for f, fpdbfile in importer.filelist.items() if fpdbfile.ftype == "both"]
    for _f in both_files:
        pass

    importer.autoSummaryGrab(force=True)

    # Print summary report
    # Colors and icons for the report
    class Colors:
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        BLUE = "\033[94m"
        BOLD = "\033[1m"
        END = "\033[0m"



    if importer.import_issues:
        for issue in importer.import_issues:
            if issue.startswith("[ERROR]"):
                pass
            else:
                pass

    # Generate hand data report if enabled
    if hand_reporter:
        hand_reporter.generate_report()

        if args.export_json:
            hand_reporter.export_json(args.export_json)

    importer.cleanup()


if __name__ == "__main__":
    main()
