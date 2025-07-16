#!/usr/bin/env python

import argparse
import datetime
import os
import sys
from time import time

import Configuration
import Database
from Importer import Importer, ImportProgressDialog

import logging
import warnings

def main():
    # Suppress FutureWarnings
    warnings.simplefilter(action='ignore', category=FutureWarning)
    # Silence logs below ERROR level
    logging.basicConfig(level=logging.ERROR)

    parser = argparse.ArgumentParser(description="Import hand history files into fpdb.")
    parser.add_argument('paths', metavar='PATH', type=str, nargs='+',
                        help='File or directory paths to import.')
    parser.add_argument('--site', type=str, default='auto',
                        help='Poker site name (e.g., PokerStars). Default: auto-detect.')
    parser.add_argument('--no-progress', action='store_true',
                        help='Disable progress reporting.')
    parser.add_argument('--config', type=str,
                        help='Path to fpdb.toml configuration file.')

    args = parser.parse_args()

    # Setup configuration
    config_file = None
    if args.config:
        if os.path.exists(args.config):
            config_file = args.config
        else:
            print(f"Config file not found: {args.config}", file=sys.stderr)
            # Decide if you want to exit or proceed with default config
            # sys.exit(1)

    config = Configuration.Config(file=config_file)

    # Setup database
    db = Database.Database(config)

    # Setup importer
    importer = Importer(caller=None, settings={}, config=config, sql=db.sql, parent=None)
    if args.no_progress:
        importer.parent = "CLI_NO_PROGRESS" # Special value to completely silence progress dialog

    # Add files/dirs to importer
    for path in args.paths:
        if not os.path.exists(path):
            print(f"Path not found: {path}", file=sys.stderr)
            continue
        print(f"Adding {path} to import list...")
        importer.addBulkImportImportFileOrDir(path, site=args.site)

    if not importer.filelist:
        print("No valid files found to import.")
        return

    print(f"Starting import of {len(importer.filelist)} files...")
    # Run the import
    (stored, dups, partial, skipped, errors, ttime) = importer.runImport()
    
    # Process tournament summaries for files marked as "both"
    print("Processing tournament summaries...")
    
    # Debug: check which files are marked as "both"
    both_files = [f for f, fpdbfile in importer.filelist.items() if fpdbfile.ftype == "both"]
    print(f"Files marked as 'both': {len(both_files)}")
    for f in both_files:
        print(f"  - {f}")
    
    importer.autoSummaryGrab(force=True)

    # Print summary report
    # Colors and icons for the report
    class Colors:
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        BLUE = '\033[94m'
        BOLD = '\033[1m'
        END = '\033[0m'

    ICONS = {
        "time": "⏱️",
        "files": "📁",
        "stored": "✔️",
        "duplicates": "⚠️",
        "partial": "↪️",
        "skipped": "⏭️",
        "errors": "❌"
    }

    print(f"\n{Colors.BOLD}--- Import Summary ---{Colors.END}")
    print(f"  {ICONS['time']} Total time: {Colors.BLUE}{ttime:.2f} seconds{Colors.END}")
    print(f"  {ICONS['files']} Files processed: {Colors.BLUE}{len(importer.filelist)}{Colors.END}")
    print(f"  {ICONS['stored']} Hands stored: {Colors.GREEN}{stored}{Colors.END}")
    print(f"  {ICONS['duplicates']} Duplicates: {Colors.YELLOW}{dups}{Colors.END}")
    print(f"  {ICONS['partial']} Partial (skipped): {Colors.YELLOW}{partial}{Colors.END}")
    print(f"  {ICONS['skipped']} Skipped (other): {Colors.YELLOW}{skipped}{Colors.END}")
    print(f"  {ICONS['errors']} Errors: {Colors.RED if errors > 0 else Colors.GREEN}{errors}{Colors.END}")
    print(f"{Colors.BOLD}----------------------{Colors.END}")

    if importer.import_issues:
        print(f"\n{Colors.BOLD}--- Import Issues ---{Colors.END}")
        for issue in importer.import_issues:
            if issue.startswith("[ERROR]"):
                print(f"  {Colors.RED}{issue}{Colors.END}")
            else:
                print(f"  {Colors.YELLOW}{issue}{Colors.END}")
        print(f"{Colors.BOLD}----------------------{Colors.END}")

    importer.cleanup()


if __name__ == "__main__":
    main()