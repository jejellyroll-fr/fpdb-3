#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script from legacy .hp files to modern .snapshot.json format.

This script:
1. Inventories all .hp files in the project
2. Generates corresponding .snapshot.json files
3. Validates invariants for each snapshot
4. Generates a migration report

Usage:
    # Dry run (no files written)
    python tools/migrate_hp_to_snapshots.py --dry-run

    # Migrate all .hp files
    python tools/migrate_hp_to_snapshots.py

    # Migrate specific directory
    python tools/migrate_hp_to_snapshots.py --directory regression-test-files/cash/Stars/Flop

    # Generate report only
    python tools/migrate_hp_to_snapshots.py --report-only
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import Configuration
import Database
import Importer
from tools.serialize_hand_for_snapshot import (
    serialize_hands_batch,
    verify_hand_invariants,
    validate_snapshot_for_db,
)


class MigrationReport:
    """Tracks migration statistics and issues."""

    def __init__(self):
        self.total_hp_files = 0
        self.total_txt_files = 0
        self.processed = 0
        self.succeeded = 0
        self.failed = 0
        self.skipped = 0
        self.errors: List[Dict[str, str]] = []
        self.invariant_violations: Dict[str, List[str]] = defaultdict(list)
        self.by_site: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "ok": 0, "fail": 0})

    def add_success(self, file_path: str, site: str):
        """Record successful migration."""
        self.succeeded += 1
        self.processed += 1
        self.by_site[site]["ok"] += 1
        self.by_site[site]["total"] += 1

    def add_failure(self, file_path: str, site: str, error: str):
        """Record failed migration."""
        self.failed += 1
        self.processed += 1
        self.errors.append({"file": file_path, "error": error, "site": site})
        self.by_site[site]["fail"] += 1
        self.by_site[site]["total"] += 1

    def add_skip(self, file_path: str, reason: str):
        """Record skipped file."""
        self.skipped += 1

    def add_invariant_violation(self, file_path: str, violations: List[str]):
        """Record invariant violations."""
        if violations:
            self.invariant_violations[file_path] = violations

    def print_summary(self):
        """Print migration summary to console."""
        print("\n" + "=" * 80)
        print("MIGRATION SUMMARY".center(80))
        print("=" * 80)
        print(f"Total .hp files found:     {self.total_hp_files}")
        print(f"Total .txt files found:    {self.total_txt_files}")
        print(f"Files processed:           {self.processed}")
        print(f"  ✅ Succeeded:            {self.succeeded}")
        print(f"  ❌ Failed:               {self.failed}")
        print(f"  ⏭️  Skipped:              {self.skipped}")
        print(f"Invariant violations:      {len(self.invariant_violations)}")

        print("\n" + "-" * 80)
        print("BY SITE".center(80))
        print("-" * 80)
        for site, stats in sorted(self.by_site.items()):
            success_rate = (stats["ok"] / stats["total"] * 100) if stats["total"] > 0 else 0
            print(f"{site:20s} : {stats['ok']:3d}/{stats['total']:3d} ({success_rate:5.1f}%)")

        if self.errors:
            print("\n" + "-" * 80)
            print(f"ERRORS ({len(self.errors)})".center(80))
            print("-" * 80)
            for error in self.errors[:10]:  # Show first 10
                print(f"  {error['file']}")
                print(f"    → {error['error'][:100]}")

        if self.invariant_violations:
            print("\n" + "-" * 80)
            print(f"INVARIANT VIOLATIONS ({len(self.invariant_violations)})".center(80))
            print("-" * 80)
            for file_path, violations in list(self.invariant_violations.items())[:5]:
                print(f"  {file_path}")
                for violation in violations[:3]:
                    print(f"    → {violation}")

        print("=" * 80 + "\n")

    def save_json_report(self, output_path: Path):
        """Save detailed JSON report."""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_hp_files": self.total_hp_files,
                "total_txt_files": self.total_txt_files,
                "processed": self.processed,
                "succeeded": self.succeeded,
                "failed": self.failed,
                "skipped": self.skipped,
                "invariant_violations": len(self.invariant_violations),
            },
            "by_site": dict(self.by_site),
            "errors": self.errors,
            "invariant_violations": dict(self.invariant_violations),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, sort_keys=True)

        print(f"📄 Detailed report saved to: {output_path}")


def detect_site_from_path(file_path: Path) -> str:
    """Detect poker site from file path."""
    path_str = str(file_path).lower()

    site_mappings = {
        "stars": "PokerStars",
        "pokerstars": "PokerStars",
        "ggpoker": "GGPoker",
        "winamax": "Winamax",
        "partypoker": "PartyPoker",
        "party": "PartyPoker",
        "888": "888poker",
        "pacific": "PacificPoker",
        "ftp": "Full Tilt Poker",
        "fulltilt": "Full Tilt Poker",
        "bovada": "Bovada",
        "merge": "Merge",
        "enet": "Enet",
        "everleaf": "Everleaf",
        "absolute": "Absolute",
        "cake": "Cake",
        "pkr": "PKR",
        "ipoker": "iPoker",
    }

    for keyword, site_name in site_mappings.items():
        if keyword in path_str:
            return site_name

    return "Unknown"


def find_hp_files(root_dir: Path) -> List[Path]:
    """Find all .hp files in directory tree."""
    return sorted(root_dir.rglob("*.hp"))


def find_txt_files(root_dir: Path) -> List[Path]:
    """Find all .txt hand history files."""
    txt_files = []
    for txt_file in root_dir.rglob("*.txt"):
        # Skip temp/summary files
        if any(skip in txt_file.name for skip in ["temp.snapshot", "summary", ".snapshot"]):
            continue
        txt_files.append(txt_file)
    return sorted(txt_files)


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


def migrate_single_file(
    txt_file: Path, importer, report: MigrationReport, dry_run: bool = False
) -> Tuple[bool, str]:
    """Migrate a single .txt file to .snapshot.json."""
    site = detect_site_from_path(txt_file)
    snapshot_path = txt_file.with_suffix(txt_file.suffix + ".snapshot.json")

    # Skip if snapshot already exists
    if snapshot_path.exists() and not dry_run:
        report.add_skip(str(txt_file), "Snapshot already exists")
        return True, "Skipped: snapshot exists"

    try:
        # Clear previous imports
        importer.clearFileList()

        # Import the file
        file_added = importer.addBulkImportImportFileOrDir(str(txt_file), site=site)
        if not file_added:
            report.add_failure(str(txt_file), site, "Could not add file to importer")
            return False, "Import failed"

        # Run import
        (stored, dups, partial, skipped, errs, ttime) = importer.runImport()

        if errs > 0:
            report.add_failure(str(txt_file), site, f"{errs} parsing errors")
            return False, f"{errs} parsing errors"

        # Get processed hands
        hhc = importer.getCachedHHC()
        if not hhc:
            report.add_failure(str(txt_file), site, "No HHC available")
            return False, "No HHC"

        handlist = hhc.getProcessedHands() or []
        if not handlist:
            report.add_skip(str(txt_file), "No hands processed")
            return True, "No hands"

        # Serialize hands
        serialized_hands = serialize_hands_batch(handlist)

        # Validate invariants
        total_violations = 0
        all_violations = []
        for i, hand_data in enumerate(serialized_hands):
            if "error" not in hand_data:
                invariant_violations = verify_hand_invariants(hand_data)
                schema_violations = validate_snapshot_for_db(hand_data)
                violations = invariant_violations + schema_violations

                if violations:
                    all_violations.extend(violations)
                    total_violations += len(violations)

        if all_violations:
            report.add_invariant_violation(str(txt_file), all_violations)

        # Save snapshot (unless dry run)
        if not dry_run:
            snapshot_data = {
                "_metadata": {
                    "source_file": txt_file.name,
                    "site": site,
                    "migration_date": datetime.now().isoformat(),
                    "validation_level": "auto",
                    "invariant_violations": total_violations,
                },
                "serialized_snapshot_name": f"snapshot_{txt_file.stem}",
                "snapshot": serialized_hands,
            }

            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot_data, f, indent=2, sort_keys=True)

        report.add_success(str(txt_file), site)
        return True, f"OK ({len(handlist)} hands, {total_violations} violations)"

    except Exception as e:
        error_msg = str(e)[:200]
        report.add_failure(str(txt_file), site, error_msg)
        return False, error_msg


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate legacy .hp files to modern .snapshot.json format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("regression-test-files"),
        help="Directory to scan for .hp files (default: regression-test-files)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write any files, just report what would be done",
    )

    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Just generate inventory report, don't migrate",
    )

    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("migration-report.json"),
        help="Output path for JSON report (default: migration-report.json)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to process (for testing)",
    )

    args = parser.parse_args()

    if not args.directory.exists():
        print(f"❌ Directory not found: {args.directory}")
        return 1

    print("🔍 Scanning for .hp and .txt files...")
    hp_files = find_hp_files(args.directory)
    txt_files = find_txt_files(args.directory)

    report = MigrationReport()
    report.total_hp_files = len(hp_files)
    report.total_txt_files = len(txt_files)

    print(f"Found {len(hp_files)} .hp files")
    print(f"Found {len(txt_files)} .txt files")

    if args.report_only:
        print("\n📊 Generating inventory report...")
        # Group by site
        hp_by_site = defaultdict(list)
        for hp_file in hp_files:
            site = detect_site_from_path(hp_file)
            hp_by_site[site].append(str(hp_file))

        inventory = {
            "timestamp": datetime.now().isoformat(),
            "total_hp_files": len(hp_files),
            "total_txt_files": len(txt_files),
            "hp_by_site": {site: sorted(files) for site, files in hp_by_site.items()},
        }

        with open("hp-inventory.json", "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2, sort_keys=True)

        print("✅ Inventory saved to hp-inventory.json")
        return 0

    # Get list of .txt files that have corresponding .hp files
    txt_with_hp = []
    for hp_file in hp_files:
        txt_file = hp_file.with_suffix("")  # Remove .hp extension
        if txt_file.exists():
            txt_with_hp.append(txt_file)

    if not txt_with_hp:
        print("⚠️  No .txt files found with corresponding .hp files")
        return 0

    print(f"\n📦 Found {len(txt_with_hp)} .txt files with .hp companions")

    if args.dry_run:
        print("🔍 DRY RUN MODE - No files will be written")

    if args.limit:
        txt_with_hp = txt_with_hp[: args.limit]
        print(f"⚠️  Limited to {args.limit} files")

    # Setup test environment
    print("\n⚙️  Setting up test environment...")
    try:
        importer, db, config = setup_test_environment()
        print("✅ Test environment ready")
    except Exception as e:
        print(f"❌ Failed to setup test environment: {e}")
        return 1

    # Process files
    print(f"\n🚀 Starting migration of {len(txt_with_hp)} files...\n")

    for i, txt_file in enumerate(txt_with_hp, 1):
        rel_path = txt_file.relative_to(args.directory)
        print(f"[{i}/{len(txt_with_hp)}] {rel_path}...", end=" ")

        success, message = migrate_single_file(txt_file, importer, report, dry_run=args.dry_run)

        if success:
            print(f"✅ {message}")
        else:
            print(f"❌ {message}")

    # Print summary
    report.print_summary()

    # Save detailed report
    report.save_json_report(args.output_report)

    # Return exit code
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
