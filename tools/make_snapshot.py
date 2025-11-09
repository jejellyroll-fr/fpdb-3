#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility tool to generate snapshots from hand history files for pytest-syrupy.
Helps developers create baseline snapshots for new hand histories.

NOTE: v1.0 - Migration from legacy system, will need performance optimizations
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add the project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import Configuration
import Database
import Importer
from tools.serialize_hand_for_snapshot import (
    serialize_hands_batch,
    verify_hand_invariants,
    print_hand_to_stdout,
    save_raw_hand_objects,
    compare_raw_hand_objects,
    validate_snapshot_for_db,
)


def hand_label(hand_data: Dict[str, Any], default: str) -> str:
    """Human-readable identifier for a serialized hand."""
    details = hand_data.get("hand_details") or {}
    label = details.get("siteHandNo") or details.get("tableName")
    if label is None:
        return default
    return str(label)


def cents_to_dollars(value: Any) -> str:
    """Format integer cents as a dollar string."""
    if value is None:
        return "n/a"
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return str(value)
    return f"${cents / 100:.2f}"


def format_stakes(gametype: Dict[str, Any]) -> str:
    """Return a human-readable stakes string from gametype metadata."""
    if not gametype:
        return "n/a"
    sb = gametype.get("sb")
    bb = gametype.get("bb")
    if sb is None or bb is None:
        return "n/a"
    try:
        sb_value = float(sb)
        bb_value = float(bb)
        return f"${sb_value:.2f}/${bb_value:.2f}"
    except (TypeError, ValueError):
        return f"{sb}/{bb}"


def read_text_preview_with_fallback(file_path: str, chars: int = 1000) -> tuple[str, str]:
    """Read a small portion of a file with UTF-8 first, then fall back to CP1252."""
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return fh.read(chars), "utf-8"
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="cp1252") as fh:
                preview = fh.read(chars)
            print(f"Decoded {file_path} using cp1252 fallback")
            return preview, "cp1252"
        except UnicodeDecodeError:
            raise


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


def parse_hand_history(file_path: str, site_name: str, importer, args=None) -> tuple:
    """Parse a hand history file and return both raw hands and serialized data."""
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
        if stored == 0:
            print(f"No hand history converter available for {file_path} – writing empty snapshot")
            return [], []
        raise RuntimeError("No HHC (Hand History Converter) available")

    handlist = hhc.getProcessedHands() or []
    if not handlist:
        if stored == 0:
            print(f"No hands were processed for {file_path} – writing empty snapshot")
            return [], []
        raise RuntimeError("No hands were processed")

    print(f"Successfully processed {len(handlist)} hands from {file_path}")

    # Handle print-hand-stdout mode
    if args and args.print_hand_stdout:
        for hand in handlist:
            print_hand_to_stdout(hand)
        return handlist, []

    # Process hands according to format options
    serialized_hands = []
    if not args or not args.raw_hand_objects or args.both_formats:
        # Generate snapshot format
        serialized_hands = serialize_hands_batch(handlist)

        # Verify invariants for snapshot format
        total_violations = 0
        for i, hand_data in enumerate(serialized_hands):
            if "error" not in hand_data:
                hand_id = hand_label(hand_data, f"hand_{i}")

                invariant_violations = verify_hand_invariants(hand_data)
                if invariant_violations:
                    print(f"Warning: Invariant violations in hand {hand_id}:")
                    for violation in invariant_violations:
                        print(f"  - {violation}")
                    total_violations += len(invariant_violations)

                schema_violations = validate_snapshot_for_db(hand_data)
                if schema_violations:
                    print(f"Warning: Schema violations in hand {hand_id}:")
                    for violation in schema_violations:
                        print(f"  - {violation}")
                    total_violations += len(schema_violations)

        if total_violations > 0:
            print(f"Total invariant violations: {total_violations}")
        else:
            print("All hands pass invariant checks")

    return handlist, serialized_hands


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
        preview, _encoding = read_text_preview_with_fallback(file_path)
        first_lines_lower = preview.lower()

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

    except UnicodeDecodeError as exc:
        print(f"Unable to decode {file_path}: {exc}")

    # Default fallback
    print("Warning: Could not auto-detect site, defaulting to PokerStars")
    return 'PokerStars'


def _exclude_db_ids(data: Any, exclude_keys: set = None) -> Any:
    """Recursively remove database-generated IDs from data structures for comparison.

    Args:
        data: The data to filter (dict, list, or scalar)
        exclude_keys: Set of keys to exclude (defaults to database ID fields)

    Returns:
        Filtered copy of the data
    """
    if exclude_keys is None:
        # Database-generated fields that should not be compared
        exclude_keys = {'id', 'fileId', 'gametypeId', 'sessionId', 'gameId'}

    if isinstance(data, dict):
        return {
            key: _exclude_db_ids(value, exclude_keys)
            for key, value in data.items()
            if key not in exclude_keys
        }
    elif isinstance(data, list):
        return [_exclude_db_ids(item, exclude_keys) for item in data]
    else:
        return data


def compare_snapshots(before_path: str, after_path: str):
    """Compare two snapshot files and report differences, excluding database IDs."""
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
        hand_id = hand_label(before_hand, f"hand_{i}")

        # Filter out database IDs before comparison
        before_filtered = _exclude_db_ids(before_hand)
        after_filtered = _exclude_db_ids(after_hand)

        sections = [
            ("hand_details", before_filtered.get("hand_details", {}), after_filtered.get("hand_details", {})),
            ("players", before_filtered.get("players", []), after_filtered.get("players", [])),
            ("actions", before_filtered.get("actions", []), after_filtered.get("actions", [])),
        ]

        for section_name, before_section, after_section in sections:
            if before_section != after_section:
                differences_found = True
                print(f"Hand {hand_id}: {section_name} changed")

    if not differences_found:
        print("No differences found in canonical snapshot sections (database IDs excluded)")
        return 0

    print("Differences found - regression detected!")
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

Legacy/Raw Hand Object Examples:
  # Generate raw Hand objects for Worros legacy workflow
  python tools/make_snapshot.py hand.txt --raw-hand-objects --output hand.raw.json
  
  # Print Hand objects to stdout for piping
  python tools/make_snapshot.py hand.txt --print-hand-stdout | grep "Hero"
  
  # Generate PokerStars format for web posting
  python tools/make_snapshot.py hand.txt --stars-format --output hand.stars.txt
  
  # Save as pickle for complete object preservation
  python tools/make_snapshot.py hand.txt --raw-hand-objects --raw-format pickle
  
  # Both snapshot and raw formats (hybrid workflow)
  python tools/make_snapshot.py hand.txt --both-formats
  
  # Compare raw Hand object files
  python tools/make_snapshot.py --compare-raw before.raw.json after.raw.json
  
  # Regression testing with raw objects
  python tools/make_snapshot.py --directory test-files/ --raw-hand-objects --regression-mode
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
    
    # Legacy/Raw Hand object options
    parser.add_argument(
        '--raw-hand-objects',
        action='store_true',
        help='Save raw Hand objects for legacy Worros workflow (JSON format)'
    )
    
    parser.add_argument(
        '--raw-format',
        choices=['json', 'pickle', 'stars'],
        default='json',
        help='Format for raw hand objects: json (default), pickle, or stars'
    )
    
    parser.add_argument(
        '--print-hand-stdout',
        action='store_true',
        help='Print Hand objects to stdout for piping/debugging'
    )
    
    parser.add_argument(
        '--stars-format',
        action='store_true',  
        help='Generate PokerStars-format hand history for web posting'
    )
    
    parser.add_argument(
        '--both-formats',
        action='store_true',
        help='Generate both snapshot JSON and raw Hand objects'
    )
    
    parser.add_argument(
        '--compare-raw',
        nargs=2,
        metavar=('BEFORE', 'AFTER'),
        help='Compare two raw Hand object files'
    )

    args = parser.parse_args()

    # Handle special modes first
    if args.compare:
        return compare_snapshots(args.compare[0], args.compare[1])
    
    if args.compare_raw:
        return compare_raw_hand_objects(args.compare_raw[0], args.compare_raw[1])

    # Validate arguments
    if args.directory and args.files:
        parser.error("Cannot specify both --directory and individual files")

    if not args.directory and not args.files and not args.compare and not args.compare_raw:
        parser.error("Must specify either --directory or individual files (unless using --compare or --compare-raw)")

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
            handlist, serialized_hands = parse_hand_history(file_path, site_name, importer, args)
            total_processed += len(handlist)
            
            # Handle raw hand object modes
            if args.print_hand_stdout:
                # Already handled in parse_hand_history
                continue

            if not args.verify_only:
                # Handle different output modes
                if args.raw_hand_objects or args.both_formats:
                    # Save raw Hand objects
                    if args.output:
                        raw_output_path = args.output.replace('.json', f'.raw.{args.raw_format}')
                    elif args.output_dir:
                        base_name = Path(file_path).stem
                        raw_output_path = os.path.join(args.output_dir, f"{base_name}.raw.{args.raw_format}")
                    elif args.regression_mode:
                        raw_output_path = f"{file_path}.temp.raw.{args.raw_format}"
                    else:
                        raw_output_path = f"{file_path}.raw.{args.raw_format}"
                    
                    save_raw_hand_objects(handlist, raw_output_path, args.raw_format)
                
                if args.stars_format or (args.raw_format == 'stars'):
                    # Save in Stars format
                    if args.output:
                        stars_output_path = args.output.replace('.json', '.stars.txt')
                    elif args.output_dir:
                        base_name = Path(file_path).stem
                        stars_output_path = os.path.join(args.output_dir, f"{base_name}.stars.txt")
                    else:
                        stars_output_path = f"{file_path}.stars.txt"
                    
                    save_raw_hand_objects(handlist, stars_output_path, 'stars')
                
                # Save standard snapshot format (unless raw-only mode)
                if not args.raw_hand_objects or args.both_formats:
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
