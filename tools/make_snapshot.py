#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility tool to generate snapshots from hand history files for pytest-syrupy.
Helps developers create baseline snapshots for new hand histories.

NOTE: v1.0 - Migration from legacy system, will need performance optimizations
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Add the project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import Configuration
import Database
import Importer
from serialize_hand_for_snapshot import serialize_hands_batch, verify_hand_invariants
import json
import glob
from pathlib import Path


def setup_test_environment():
    """Set up a test environment with clean database."""
    config = Configuration.Config(file="HUD_config.test.xml")
    db = Database.Database(config)

    settings = {}
    settings.update(config.get_db_parameters())
    settings.update(config.get_import_parameters())
    settings.update(config.get_default_paths())

    # Recreate tables for clean state
    db.recreate_tables()

    # Create importer
    importer = Importer.Importer(False, settings, config, None)
    importer.setDropIndexes("don't drop")
    importer.setThreads(-1)
    importer.setCallHud(False)
    importer.setFakeCacheHHC(True)

    return importer, db, config


def parse_hand_history(file_path: str, site_name: str, importer) -> List[Dict[str, Any]]:
    """Parse a hand history file and return serialized hands."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Hand history file not found: {file_path}")

    # Clear any previous files
    importer.clearFileList()

    # Import the file
    file_added = importer.addBulkImportImportFileOrDir(file_path, site=site_name)
    if not file_added:
        raise ValueError(f"Could not add file to importer: {file_path}")

    # Run import
    try:
        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()

        if errs > 0:
            print(f"Warning: {errs} parsing errors encountered")

    except Exception as e:
        raise RuntimeError(f"Import failed: {e}")

    # Get processed hands
    hhc = importer.getCachedHHC()
    if not hhc:
        raise RuntimeError("No HHC (Hand History Converter) available")

    handlist = hhc.getProcessedHands()
    if not handlist:
        raise RuntimeError("No hands were processed")

    print(f"Successfully processed {len(handlist)} hands from {file_path}")

    # Serialize hands
    serialized_hands = serialize_hands_batch(handlist)

    # Verify invariants
    total_violations = 0
    for i, hand_data in enumerate(serialized_hands):
        if 'error' not in hand_data:
            violations = verify_hand_invariants(hand_data)
            if violations:
                hand_id = hand_data.get('hand_text_id', f'hand_{i}')
                print(f"Warning: Invariant violations in hand {hand_id}:")
                for violation in violations:
                    print(f"  - {violation}")
                total_violations += len(violations)

    if total_violations > 0:
        print(f"Total invariant violations: {total_violations}")
    else:
        print("All hands pass invariant checks")

    return serialized_hands


def detect_site_name(file_path: str) -> str:
    """Try to detect the poker site from file path or content."""
    file_path_lower = file_path.lower()

    # Common site mappings based on file path
    site_mappings = {
        'stars': 'PokerStars',
        'pokerstars': 'PokerStars',
        'ftp': 'Full Tilt Poker',
        'fulltilt': 'Full Tilt Poker',
        'party': 'Party Poker',
        'partypoker': 'Party Poker',
        'winamax': 'Winamax',
        '888': '888poker',
        'merge': 'Merge',
        'bovada': 'Bovada',
        'betonline': 'BetOnline',
        'cake': 'Cake',
    }

    for keyword, site_name in site_mappings.items():
        if keyword in file_path_lower:
            return site_name

    # Try to detect from file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            first_lines = f.read(1000)  # Read first 1000 chars

        first_lines_lower = first_lines.lower()

        if 'pokerstars' in first_lines_lower:
            return 'PokerStars'
        elif 'full tilt' in first_lines_lower:
            return 'Full Tilt Poker'
        elif 'winamax' in first_lines_lower:
            return 'Winamax'
        elif 'partypoker' in first_lines_lower:
            return 'Party Poker'
        elif '888poker' in first_lines_lower:
            return '888poker'
        elif 'merge' in first_lines_lower:
            return 'Merge'
        elif 'bovada' in first_lines_lower:
            return 'Bovada'

    except Exception:
        pass

    # Default fallback
    print("Warning: Could not auto-detect site, defaulting to PokerStars")
    return 'PokerStars'


def compare_snapshots(before_path: str, after_path: str):
    """Compare two snapshot files and report differences."""
    try:
        with open(before_path, 'r', encoding='utf-8') as f:
            before_data = json.load(f)
        with open(after_path, 'r', encoding='utf-8') as f:
            after_data = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: Could not find snapshot file: {e}")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format: {e}")
        return 1

    # Compare snapshots
    before_snapshot = before_data.get('snapshot', [])
    after_snapshot = after_data.get('snapshot', [])

    print(f"Comparing snapshots:")
    print(f"  Before: {before_path} ({len(before_snapshot)} hands)")
    print(f"  After:  {after_path} ({len(after_snapshot)} hands)")
    print()

    if len(before_snapshot) != len(after_snapshot):
        print(f"Different number of hands: {len(before_snapshot)} vs {len(after_snapshot)}")
        return 1

    differences_found = False

    for i, (before_hand, after_hand) in enumerate(zip(before_snapshot, after_snapshot)):
        hand_id = before_hand.get('hand_text_id', f'hand_{i}')

        # Compare critical fields
        critical_fields = ['total_pot', 'rake', 'players']
        for field in critical_fields:
            if before_hand.get(field) != after_hand.get(field):
                differences_found = True
                print(f"Hand {hand_id}: {field} changed")
                print(f"   Before: {before_hand.get(field)}")
                print(f"   After:  {after_hand.get(field)}")
                print()

    if not differences_found:
        print("No differences found in critical fields")
        return 0
    else:
        print(f"Differences found - regression detected!")
        return 1


def filter_files_by_game_type(files: List[str], filter_game: str = None, filter_type: str = None) -> List[str]:
    """Filter files based on game type and format."""
    if not filter_game and not filter_type:
        return files

    filtered = []

    for file_path in files:
        path_lower = file_path.lower()

        # Filter by game type
        if filter_game:
            if filter_game == 'FLOP' and not any(game in path_lower for game in ['flop', 'holdem', 'omaha']):
                continue
            elif filter_game == 'STUD' and not any(game in path_lower for game in ['stud', 'razz']):
                continue
            elif filter_game == 'DRAW' and not any(game in path_lower for game in ['draw', 'badugi']):
                continue

        # Filter by type
        if filter_type:
            if filter_type == 'cash' and 'cash' not in path_lower:
                continue
            elif filter_type == 'tourney' and not any(t in path_lower for t in ['tourney', 'tournament']):
                continue
            elif filter_type == 'sng' and 'sng' not in path_lower:
                continue

        filtered.append(file_path)

    return filtered


def collect_files_from_directory(directory: str, filter_game: str = None, filter_type: str = None) -> List[str]:
    """Collect all hand history files from directory and subdirectories."""
    directory_path = Path(directory)

    if not directory_path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    # Common hand history file extensions
    patterns = ['*.txt', '*.log', '*.hh']

    all_files = []
    for pattern in patterns:
        all_files.extend(directory_path.rglob(pattern))

    # Convert to strings and filter
    file_paths = [str(f) for f in all_files]
    filtered_files = filter_files_by_game_type(file_paths, filter_game, filter_type)

    return sorted(filtered_files)


def save_snapshot_file(serialized_hands: List[Dict[str, Any]], output_path: str):
    """Save serialized hands to a snapshot-compatible format."""
    import json

    # Create syrupy-compatible snapshot data
    snapshot_data = {
        'serialized_snapshot_name': f"snapshot_{Path(output_path).stem}",
        'snapshot': serialized_hands
    }

    # Save as JSON for manual inspection
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot_data, f, indent=2, sort_keys=True)

    print(f"Snapshot data saved to: {output_path}")

    # Also save a human-readable summary
    summary_path = output_path.replace('.json', '_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"Snapshot Summary for {output_path}\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Total hands: {len(serialized_hands)}\n\n")

        for i, hand in enumerate(serialized_hands):
            if 'error' in hand:
                f.write(f"Hand {i+1}: ERROR - {hand['error']}\n")
            else:
                f.write(f"Hand {i+1}:\n")
                f.write(f"  Site: {hand.get('site', 'Unknown')}\n")
                f.write(f"  Hand ID: {hand.get('hand_text_id', 'Unknown')}\n")
                f.write(f"  Game: {hand.get('game_type', 'Unknown')}\n")
                f.write(f"  Stakes: {hand.get('stakes', 'Unknown')}\n")
                f.write(f"  Players: {len(hand.get('players', []))}\n")
                f.write(f"  Total Pot: ${hand.get('total_pot', 0):.2f}\n")
                f.write(f"  Rake: ${hand.get('rake', 0):.2f}\n")
                f.write("\n")

    print(f"Summary saved to: {summary_path}")


def main():
    """Main entry point for the make_snapshot tool."""
    parser = argparse.ArgumentParser(
        description="Generate snapshots from poker hand history files for pytest-syrupy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage - generate snapshot from a Stars hand history
  python tools/make_snapshot.py hands/pokerstars_session.txt

  # Specify site explicitly
  python tools/make_snapshot.py hands/mystery_site.txt --site "Winamax"

  # Custom output location
  python tools/make_snapshot.py hands/session.txt --output snapshots/my_test.json

  # Process multiple files
  python tools/make_snapshot.py hands/*.txt --output-dir snapshots/

Worros Workflow Examples:
  # Step 1.0: Process all Stars cash FLOP games (baseline)
  python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop --site PokerStars --regression-mode

  # Step 2.0: Process single file and generate snapshot for manual editing
  python tools/make_snapshot.py ~/Downloads/Anonymised.txt --site PokerStars --output Anon-better-name.json

  # Step 5.0: Compare before/after snapshots
  python tools/make_snapshot.py --compare before.json after.json

  # Step 6.0: Re-run regression test after code changes
  python tools/make_snapshot.py --directory regression-test-files/Stars/cash/Flop --site PokerStars --regression-mode

  # Step 7.0: Test all FLOP cash games across sites
  python tools/make_snapshot.py --directory regression-test-files --filter-game FLOP --type cash --regression-mode

Advanced Filtering:
  # Process only FLOP games (Hold'em/Omaha variants)
  python tools/make_snapshot.py --directory test-files/ --filter-game FLOP

  # Process only cash games
  python tools/make_snapshot.py --directory test-files/ --type cash

  # Process only tournament STUD games
  python tools/make_snapshot.py --directory test-files/ --filter-game STUD --type tourney

  # Verify hands only (no snapshot generation)
  python tools/make_snapshot.py hands/*.txt --verify-only
        """
    )

    parser.add_argument(
        'files',
        nargs='*',
        help='Hand history file(s) to process'
    )

    parser.add_argument(
        '--site', '-s',
        help='Poker site name (auto-detected if not specified)'
    )

    parser.add_argument(
        '--output', '-o',
        help='Output file path (default: input_filename.snapshot.json)'
    )

    parser.add_argument(
        '--output-dir', '-d',
        help='Output directory for multiple files'
    )

    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify hands, do not create snapshots'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )

    parser.add_argument(
        '--compare',
        nargs=2,
        metavar=('BEFORE', 'AFTER'),
        help='Compare two snapshot files and show differences'
    )

    parser.add_argument(
        '--directory',
        help='Process all files in directory (equivalent to Worros workflow step 1.0)'
    )

    parser.add_argument(
        '--filter-game',
        choices=['FLOP', 'STUD', 'DRAW'],
        help='Filter by game type (FLOP=Hold\'em/Omaha, STUD=Stud variants, DRAW=Draw variants)'
    )

    parser.add_argument(
        '--type',
        choices=['cash', 'tourney', 'sng'],
        help='Filter by game format'
    )

    parser.add_argument(
        '--regression-mode',
        action='store_true',
        help='Regression testing mode - process directory and compare against existing snapshots'
    )

    args = parser.parse_args()

    # Handle special modes first
    if args.compare:
        return compare_snapshots(args.compare[0], args.compare[1])

    # Validate arguments
    if args.directory and args.files:
        parser.error("Cannot specify both --directory and individual files")

    if not args.directory and not args.files and not args.compare:
        parser.error("Must specify either --directory or individual files (unless using --compare)")

    if len(args.files or []) > 1 and args.output:
        parser.error("Cannot specify --output with multiple input files. Use --output-dir instead.")

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    # Collect files to process
    if args.directory:
        try:
            files_to_process = collect_files_from_directory(
                args.directory,
                args.filter_game,
                args.type
            )
            if not files_to_process:
                print(f"No matching files found in directory: {args.directory}")
                return 1
            print(f"Found {len(files_to_process)} files to process")
        except Exception as e:
            print(f"Error collecting files from directory: {e}")
            return 1
    else:
        files_to_process = filter_files_by_game_type(args.files, args.filter_game, args.type)
        if not files_to_process:
            print("No files match the specified filters")
            return 1

    # Setup test environment
    print("Setting up test environment...")
    try:
        importer, db, config = setup_test_environment()
        print("Test environment ready ✓")
    except Exception as e:
        print(f"Error setting up test environment: {e}")
        return 1

    # Process each file
    total_processed = 0
    total_errors = 0

    for file_path in files_to_process:
        try:
            print(f"\nProcessing: {file_path}")

            # Detect or use specified site
            site_name = args.site or detect_site_name(file_path)
            print(f"Site: {site_name}")

            # Parse hands
            serialized_hands = parse_hand_history(file_path, site_name, importer)
            total_processed += len(serialized_hands)

            if not args.verify_only:
                # Determine output path
                if args.output:
                    output_path = args.output
                elif args.output_dir:
                    base_name = Path(file_path).stem
                    output_path = os.path.join(args.output_dir, f"{base_name}.snapshot.json")
                elif args.regression_mode:
                    # In regression mode, use temp files for comparison
                    output_path = f"{file_path}.temp.snapshot.json"
                else:
                    output_path = f"{file_path}.snapshot.json"

                # Save snapshot
                save_snapshot_file(serialized_hands, output_path)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            total_errors += 1
            if args.verbose:
                import traceback
                traceback.print_exc()

    # Handle regression mode
    if args.regression_mode and not args.verify_only:
        print(f"\n=== Regression Testing Mode ===")
        print("Checking for changes against existing snapshots...")

        regression_errors = 0
        for file_path in files_to_process:
            snapshot_path = f"{file_path}.snapshot.json"
            temp_snapshot_path = f"{file_path}.temp.snapshot.json"

            if os.path.exists(snapshot_path) and os.path.exists(temp_snapshot_path):
                result = compare_snapshots(snapshot_path, temp_snapshot_path)
                if result != 0:
                    regression_errors += 1
                    print(f"Regression detected in {file_path}")
                else:
                    print(f"No regression in {file_path}")
                    # Clean up temp file if no differences
                    os.remove(temp_snapshot_path)
            elif os.path.exists(temp_snapshot_path):
                print(f"  New baseline created for {file_path}")
                os.rename(temp_snapshot_path, snapshot_path)

        if regression_errors > 0:
            print(f"\n {regression_errors} files show regressions")
            return 1
        else:
            print(f"\n No regressions detected")

    # Summary
    print(f"\n=== Summary ===")
    print(f"Files processed: {len(files_to_process)}")
    print(f"Total hands: {total_processed}")
    print(f"Errors: {total_errors}")

    if total_errors == 0:
        print("All files processed successfully ✓")

        if not args.verify_only:
            print("\nNext steps:")
            if args.regression_mode:
                print("1. Review any regression differences above")
                print("2. Update code if regressions are bugs")
                print("3. Update snapshots if changes are intentional")
            else:
                print("1. Review the generated .json and _summary.txt files")
                print("2. Copy snapshot data into your test files")
                print("3. Run pytest tests to verify everything works")

        return 0
    else:
        print("Some files had errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
