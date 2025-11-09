#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate legacy .hands (Hands table) test files for regression testing.

This tool imports a hand history file, extracts the Hands table statistics,
and saves them in the legacy .hands format (Python dictionary serialized as text).

The .hands files are used by TestHandsPlayers_legacy.py for regression testing.

Usage:
    # Generate .hands file for a single hand
    uv run python tools/generate_hands_file.py hand.txt --site PokerStars

    # Generate .hands files for all hands in directory
    uv run python tools/generate_hands_file.py --directory regression-test-files/active-sites/pokerstars/ --site PokerStars

    # Overwrite existing .hands files
    uv run python tools/generate_hands_file.py hand.txt --site PokerStars --force
"""

import argparse
import codecs
import pprint
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import Configuration
import Database
import Importer


def setup_test_environment():
    """Set up test environment with clean database."""
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    db.recreate_tables()

    importer = Importer.Importer(False, settings, config, None)
    importer.setDropIndexes("don't drop")
    importer.setThreads(-1)
    importer.setCallHud(False)
    importer.setFakeCacheHHC(True)

    return importer, db, config


def generate_hands_for_file(file_path: Path, site: str, importer, force: bool = False) -> bool:
    """
    Generate .hands file for a single hand history file.

    Args:
        file_path: Path to hand history .txt file
        site: Poker site name (e.g., "PokerStars", "Winamax")
        importer: Importer instance
        force: Overwrite existing .hands file

    Returns:
        True if successful, False otherwise
    """
    hands_path = file_path.with_suffix(file_path.suffix + ".hands")

    # Check if .hands already exists
    if hands_path.exists() and not force:
        print(f"⚠️  {hands_path.name} already exists (use --force to overwrite)")
        return False

    try:
        # Clear previous imports
        importer.clearFileList()

        # Import the file
        file_added = importer.addBulkImportImportFileOrDir(str(file_path), site=site)
        if not file_added:
            print(f"❌ Could not add {file_path.name} to importer")
            return False

        # Run import
        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()

        if errs > 0:
            print(f"❌ {errs} parsing errors in {file_path.name}")
            return False

        # Get processed hands
        hhc = importer.getCachedHHC()
        if not hhc:
            print(f"❌ No HHC available for {file_path.name}")
            return False

        handlist = hhc.getProcessedHands() or []
        if not handlist:
            print(f"⚠️  No hands processed in {file_path.name}")
            return False

        if len(handlist) > 1:
            print(f"⚠️  Multiple hands found ({len(handlist)}) - only first will be used")

        # Extract Hands stats from first hand
        hand = handlist[0]
        hands_stats = hand.stats.getHands()

        if not hands_stats:
            print(f"❌ No Hands stats for {file_path.name}")
            return False

        # Serialize to .hands file (pretty-printed Python dictionary)
        with codecs.open(hands_path, "w", "utf8") as f:
            # Use pprint for readable output
            pp = pprint.PrettyPrinter(indent=4, width=100, stream=f)
            pp.pprint(hands_stats)

        print(f"✅ Generated {hands_path.name}")

        # Show summary of key fields
        print(f"   Hand ID: {hands_stats.get('siteHandNo', 'N/A')}")
        print(f"   Seats: {hands_stats.get('seats', 'N/A')}")
        print(f"   Players at showdown: {hands_stats.get('playersAtShowdown', 0)}")
        print(f"   Total fields: {len(hands_stats)}")

        return True

    except Exception as e:
        print(f"❌ Error processing {file_path.name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def generate_hands_for_directory(directory: Path, site: str, importer, force: bool = False):
    """Generate .hands files for all .txt files in directory."""
    txt_files = sorted(directory.rglob("*.txt"))

    # Filter out files that already have special extensions
    txt_files = [
        f for f in txt_files
        if not f.name.endswith(".snapshot.json")
        and not f.name.endswith(".hp")
        and not f.name.endswith(".hands")
        and not f.name.endswith(".gt")
    ]

    if not txt_files:
        print(f"⚠️  No .txt files found in {directory}")
        return

    print(f"\n🔍 Found {len(txt_files)} hand history files\n")

    success_count = 0
    skip_count = 0
    error_count = 0

    for i, txt_file in enumerate(txt_files, 1):
        rel_path = txt_file.relative_to(directory) if directory in txt_file.parents else txt_file.name
        print(f"[{i}/{len(txt_files)}] {rel_path}")

        result = generate_hands_for_file(txt_file, site, importer, force)

        if result:
            success_count += 1
        elif txt_file.with_suffix(txt_file.suffix + ".hands").exists():
            skip_count += 1
        else:
            error_count += 1

        print()  # Blank line between files

    # Summary
    print("=" * 60)
    print(f"✅ Generated: {success_count}")
    print(f"⏭️  Skipped:   {skip_count}")
    print(f"❌ Errors:    {error_count}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate legacy .hands files for regression testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate .hands for single file
  uv run python tools/generate_hands_file.py hand.txt --site PokerStars

  # Generate for all files in directory
  uv run python tools/generate_hands_file.py --directory regression-test-files/active-sites/pokerstars/ --site PokerStars

  # Overwrite existing .hands files
  uv run python tools/generate_hands_file.py hand.txt --site PokerStars --force

What is a .hands file?
  Legacy .hands files contain Hands table statistics (Python dictionary)
  used by TestHandsPlayers_legacy.py for regression testing.

  Format: {'siteHandNo': '123456', 'seats': 9, 'playersAtShowdown': 2, ...}

  The file is a serialized Python dictionary that can be eval()'d.
  It contains statistics about the hand itself (not individual players).
        """
    )

    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="Hand history .txt file to process"
    )

    parser.add_argument(
        "-d", "--directory",
        type=Path,
        help="Directory containing hand history files"
    )

    parser.add_argument(
        "-s", "--site",
        required=True,
        help="Poker site name (e.g., PokerStars, Winamax, 888poker)"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing .hands files"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.file and not args.directory:
        parser.print_help()
        print("\n❌ Error: Must specify either file or --directory")
        return 1

    if args.file and args.directory:
        print("❌ Error: Cannot specify both file and --directory")
        return 1

    if args.file and not args.file.exists():
        print(f"❌ File not found: {args.file}")
        return 1

    if args.directory and not args.directory.exists():
        print(f"❌ Directory not found: {args.directory}")
        return 1

    # Setup test environment
    print("⚙️  Setting up test environment...")
    try:
        importer, db, config = setup_test_environment()
        print("✅ Test environment ready\n")
    except Exception as e:
        print(f"❌ Failed to setup test environment: {e}")
        return 1

    # Generate .hands file(s)
    if args.file:
        success = generate_hands_for_file(args.file, args.site, importer, args.force)
        return 0 if success else 1
    else:
        generate_hands_for_directory(args.directory, args.site, importer, args.force)
        return 0


if __name__ == "__main__":
    sys.exit(main())
