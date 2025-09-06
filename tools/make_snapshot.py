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
  # Generate snapshot from a Stars hand history
  python tools/make_snapshot.py hands/pokerstars_session.txt
  
  # Specify site explicitly  
  python tools/make_snapshot.py hands/mystery_site.txt --site "Winamax"
  
  # Custom output location
  python tools/make_snapshot.py hands/session.txt --output snapshots/my_test.json
  
  # Process multiple files
  python tools/make_snapshot.py hands/*.txt --output-dir snapshots/
        """
    )
    
    parser.add_argument(
        'files',
        nargs='+',
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
    
    args = parser.parse_args()
    
    # Validate arguments
    if len(args.files) > 1 and args.output:
        parser.error("Cannot specify --output with multiple input files. Use --output-dir instead.")
    
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
    
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
    
    for file_path in args.files:
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
    
    # Summary
    print(f"\n=== Summary ===")
    print(f"Files processed: {len(args.files)}")
    print(f"Total hands: {total_processed}")
    print(f"Errors: {total_errors}")
    
    if total_errors == 0:
        print("All files processed successfully ✓")
        
        if not args.verify_only:
            print("\nNext steps:")
            print("1. Review the generated .json and _summary.txt files")
            print("2. Copy snapshot data into your test files")
            print("3. Run pytest tests to verify everything works")
        
        return 0
    else:
        print("Some files had errors ❌")
        return 1


if __name__ == "__main__":
    sys.exit(main())