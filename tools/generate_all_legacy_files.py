#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch generate all legacy test files (.hp, .hands, .gt) for regression testing.

This tool generates all three types of legacy test files in one command:
- .hp files (HandsPlayers statistics)
- .hands files (Hands table statistics)
- .gt files (GameType information)

The generated files are used by TestHandsPlayers_legacy.py for regression testing.

Usage:
    # Generate all types for a single hand
    uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars

    # Generate all types for directory
    uv run python tools/generate_all_legacy_files.py --directory regression-test-files/active-sites/pokerstars/ --site PokerStars

    # Generate only specific types
    uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars --types hp,hands

    # Auto-detect site from path
    uv run python tools/generate_all_legacy_files.py --directory regression-test-files/active-sites/pokerstars/ --auto-detect-site

    # Overwrite existing files
    uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars --force
"""

import argparse
import codecs
import pprint
import sys
from pathlib import Path
from typing import List, Set

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import Configuration
import Database
import Importer


# Site name mapping for auto-detection
SITE_MAPPING = {
    'pokerstars': 'PokerStars',
    'stars': 'PokerStars',
    'winamax': 'Winamax',
    '888poker': 'PacificPoker',
    'pacific': 'PacificPoker',
    'partypoker': 'PartyPoker',
    'party': 'PartyPoker',
    'ipoker': 'iPoker',
    'ipoker-network': 'iPoker',
    'ggpoker': 'GGPoker',
    'cake': 'Cake',
    'bovada': 'Bovada',
    'ignition': 'Bovada',
}


def detect_site_from_path(file_path: Path) -> str:
    """
    Auto-detect poker site from file path.

    Looks for site names in the directory structure:
    e.g., regression-test-files/active-sites/pokerstars/ -> PokerStars
    """
    path_lower = str(file_path).lower()

    for key, site in SITE_MAPPING.items():
        if key in path_lower:
            return site

    # Default fallback
    return None


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


def generate_hp_file(file_path: Path, site: str, importer, force: bool) -> bool:
    """Generate .hp file (HandsPlayers stats)."""
    hp_path = file_path.with_suffix(file_path.suffix + ".hp")

    if hp_path.exists() and not force:
        return None  # Skip

    try:
        importer.clearFileList()
        file_added = importer.addBulkImportImportFileOrDir(str(file_path), site=site)
        if not file_added:
            return False

        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()
        if errs > 0:
            return False

        hhc = importer.getCachedHHC()
        if not hhc:
            return False

        handlist = hhc.getProcessedHands() or []
        if not handlist:
            return False

        hand = handlist[0]
        hp_stats = hand.stats.getHandsPlayers()
        if not hp_stats:
            return False

        with codecs.open(hp_path, "w", "utf8") as f:
            pp = pprint.PrettyPrinter(indent=2, width=100, stream=f)
            pp.pprint(hp_stats)

        return True

    except Exception:
        return False


def generate_hands_file(file_path: Path, site: str, importer, force: bool) -> bool:
    """Generate .hands file (Hands table stats)."""
    hands_path = file_path.with_suffix(file_path.suffix + ".hands")

    if hands_path.exists() and not force:
        return None  # Skip

    try:
        importer.clearFileList()
        file_added = importer.addBulkImportImportFileOrDir(str(file_path), site=site)
        if not file_added:
            return False

        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()
        if errs > 0:
            return False

        hhc = importer.getCachedHHC()
        if not hhc:
            return False

        handlist = hhc.getProcessedHands() or []
        if not handlist:
            return False

        hand = handlist[0]
        hands_stats = hand.stats.getHands()
        if not hands_stats:
            return False

        with codecs.open(hands_path, "w", "utf8") as f:
            pp = pprint.PrettyPrinter(indent=4, width=100, stream=f)
            pp.pprint(hands_stats)

        return True

    except Exception:
        return False


def generate_gt_file(file_path: Path, site: str, importer, force: bool) -> bool:
    """Generate .gt file (GameType info)."""
    gt_path = file_path.with_suffix(file_path.suffix + ".gt")

    if gt_path.exists() and not force:
        return None  # Skip

    try:
        importer.clearFileList()
        file_added = importer.addBulkImportImportFileOrDir(str(file_path), site=site)
        if not file_added:
            return False

        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()
        if errs > 0:
            return False

        hhc = importer.getCachedHHC()
        if not hhc:
            return False

        handlist = hhc.getProcessedHands() or []
        if not handlist:
            return False

        hand = handlist[0]
        gt_tuple = hand.gametyperow
        if not gt_tuple:
            return False

        with codecs.open(gt_path, "w", "utf8") as f:
            pp = pprint.PrettyPrinter(indent=4, width=100, stream=f)
            pp.pprint(gt_tuple)

        return True

    except Exception:
        return False


def generate_all_for_file(
    file_path: Path,
    site: str,
    importer,
    types: Set[str],
    force: bool
) -> dict:
    """
    Generate all requested legacy files for a single hand history file.

    Returns:
        Dict with results: {'hp': True/False/None, 'hands': True/False/None, 'gt': True/False/None}
        True = success, False = error, None = skipped
    """
    results = {}

    if 'hp' in types:
        results['hp'] = generate_hp_file(file_path, site, importer, force)

    if 'hands' in types:
        results['hands'] = generate_hands_file(file_path, site, importer, force)

    if 'gt' in types:
        results['gt'] = generate_gt_file(file_path, site, importer, force)

    return results


def generate_all_for_directory(
    directory: Path,
    site: str,
    importer,
    types: Set[str],
    force: bool,
    auto_detect_site: bool
):
    """Generate all requested legacy files for all .txt files in directory."""
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

    print(f"\n🔍 Found {len(txt_files)} hand history files")
    print(f"📝 Generating types: {', '.join(sorted(types))}\n")

    # Track results
    success_counts = {t: 0 for t in types}
    skip_counts = {t: 0 for t in types}
    error_counts = {t: 0 for t in types}

    for i, txt_file in enumerate(txt_files, 1):
        rel_path = txt_file.relative_to(directory) if directory in txt_file.parents else txt_file.name

        # Auto-detect site if requested
        file_site = site
        if auto_detect_site:
            detected = detect_site_from_path(txt_file)
            if detected:
                file_site = detected

        print(f"[{i}/{len(txt_files)}] {rel_path} (site: {file_site})")

        results = generate_all_for_file(txt_file, file_site, importer, types, force)

        # Update counts
        for file_type, result in results.items():
            if result is True:
                success_counts[file_type] += 1
                print(f"  ✅ .{file_type}")
            elif result is None:
                skip_counts[file_type] += 1
                print(f"  ⏭️  .{file_type} (exists)")
            else:
                error_counts[file_type] += 1
                print(f"  ❌ .{file_type}")

        print()  # Blank line between files

    # Summary
    print("=" * 70)
    print("📊 SUMMARY BY FILE TYPE:")
    print("=" * 70)

    for file_type in sorted(types):
        total = len(txt_files)
        success = success_counts[file_type]
        skip = skip_counts[file_type]
        error = error_counts[file_type]

        print(f"\n.{file_type.upper()} FILES:")
        print(f"  ✅ Generated: {success:>4} / {total}")
        print(f"  ⏭️  Skipped:   {skip:>4} / {total}")
        print(f"  ❌ Errors:    {error:>4} / {total}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Batch generate all legacy test files (.hp, .hands, .gt)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all types for single file
  uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars

  # Generate all types for directory
  uv run python tools/generate_all_legacy_files.py --directory regression-test-files/active-sites/pokerstars/ --site PokerStars

  # Generate only .hp and .hands (skip .gt)
  uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars --types hp,hands

  # Auto-detect site from directory structure
  uv run python tools/generate_all_legacy_files.py --directory regression-test-files/active-sites/pokerstars/ --auto-detect-site

  # Overwrite existing files
  uv run python tools/generate_all_legacy_files.py hand.txt --site PokerStars --force

What are legacy files?
  .hp    - HandsPlayers statistics (per-player stats)
  .hands - Hands table statistics (per-hand aggregates)
  .gt    - GameType information (stakes, game type, structure)

All three are used by TestHandsPlayers_legacy.py for regression testing.
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
        help="Poker site name (e.g., PokerStars, Winamax, 888poker)"
    )

    parser.add_argument(
        "--auto-detect-site",
        action="store_true",
        help="Auto-detect poker site from directory path"
    )

    parser.add_argument(
        "-t", "--types",
        default="hp,hands,gt",
        help="Comma-separated list of file types to generate (default: hp,hands,gt)"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Overwrite existing files"
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

    if not args.site and not args.auto_detect_site:
        print("❌ Error: Must specify either --site or --auto-detect-site")
        return 1

    if args.file and not args.file.exists():
        print(f"❌ File not found: {args.file}")
        return 1

    if args.directory and not args.directory.exists():
        print(f"❌ Directory not found: {args.directory}")
        return 1

    # Parse types
    requested_types = set(t.strip().lower() for t in args.types.split(','))
    valid_types = {'hp', 'hands', 'gt'}
    invalid_types = requested_types - valid_types

    if invalid_types:
        print(f"❌ Invalid types: {', '.join(invalid_types)}")
        print(f"   Valid types: {', '.join(valid_types)}")
        return 1

    # Setup test environment
    print("⚙️  Setting up test environment...")
    try:
        importer, db, config = setup_test_environment()
        print("✅ Test environment ready\n")
    except Exception as e:
        print(f"❌ Failed to setup test environment: {e}")
        return 1

    # Generate files
    if args.file:
        # Single file mode
        site = args.site or detect_site_from_path(args.file)
        if not site:
            print("❌ Could not auto-detect site. Please specify --site")
            return 1

        print(f"📝 Generating {', '.join(sorted(requested_types))} for {args.file.name}")
        print(f"   Site: {site}\n")

        results = generate_all_for_file(args.file, site, importer, requested_types, args.force)

        # Show results
        all_success = True
        for file_type, result in results.items():
            if result is True:
                print(f"✅ Generated .{file_type}")
            elif result is None:
                print(f"⏭️  Skipped .{file_type} (already exists)")
            else:
                print(f"❌ Failed to generate .{file_type}")
                all_success = False

        return 0 if all_success else 1

    else:
        # Directory mode
        generate_all_for_directory(
            args.directory,
            args.site,
            importer,
            requested_types,
            args.force,
            args.auto_detect_site
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
