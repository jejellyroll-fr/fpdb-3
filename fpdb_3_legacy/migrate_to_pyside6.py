#!/usr/bin/env python3
from __future__ import annotations
"""
Script de Migration Automatique PyQt5 → PySide6

Ce script automatise la migration de FPDB-3 de PyQt5 vers PySide6.

Usage:
    python migrate_to_pyside6.py [options]

Options:
    --dry-run       Afficher les changements sans les appliquer
    --file FILE     Migrer un fichier spécifique
    --all           Migrer tous les fichiers
    --backup        Créer backup avant migration (défaut)
    --no-backup     Ne pas créer backup

Auteur: Claude (Assistant IA)
Date: 2025-11-11
Version: 1.0
"""

import argparse
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import sys

PYSIDE6_MIGRATION_ERRORS = (OSError, UnicodeDecodeError, re.error)


class Colors:
    """ANSI color codes."""

    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"  # No Color


class PySide6Migrator:
    """Migrates PyQt5 code to PySide6."""

    # Mapping PyQt5 → PySide6 (most are direct replacements)
    IMPORT_REPLACEMENTS = {
        "from PyQt5.QtCore import": "from PySide6.QtCore import",
        "from PyQt5.QtGui import": "from PySide6.QtGui import",
        "from PyQt5.QtWidgets import": "from PySide6.QtWidgets import",
        "from PyQt5.QtPrintSupport import": "from PySide6.QtPrintSupport import",
        "from PyQt5.QtSvg import": "from PySide6.QtSvg import",
        "from PyQt5 import QtCore": "from PySide6 import QtCore",
        "from PyQt5 import QtGui": "from PySide6 import QtGui",
        "from PyQt5 import QtWidgets": "from PySide6 import QtWidgets",
        "from PyQt5 import QtPrintSupport": "from PySide6 import QtPrintSupport",
        "from PyQt5 import QtSvg": "from PySide6 import QtSvg",
        "import PyQt5.QtCore": "import PySide6.QtCore",
        "import PyQt5.QtGui": "import PySide6.QtGui",
        "import PyQt5.QtWidgets": "import PySide6.QtWidgets",
        "import PyQt5.QtPrintSupport": "import PySide6.QtPrintSupport",
        "import PyQt5.QtSvg": "import PySide6.QtSvg",
    }

    # Signal/Slot changes (PyQt5 → PySide6)
    SIGNAL_SLOT_CHANGES = [
        # PyQt5 uses pyqtSignal, PySide6 uses Signal
        (r"\bpyqtSignal\b", "Signal"),
        (r"\bpyqtSlot\b", "Slot"),
        (r"\bpyqtProperty\b", "Property"),
    ]

    # QVariant removed in PySide6 (was already deprecated in PyQt5)
    #
    # WARNING: the previous version of this list stripped *any* no-argument
    # `.toInt()`, `.toString()` and `.toBool()` call. Those names are not unique
    # to QVariant (e.g. `QDateTime.toString()`, `QColor.toRgb()`-style helpers),
    # so the broad rules silently deleted legitimate Qt calls. The conversion of a
    # QVariant accessor cannot be done safely with a regex (it depends on the
    # target type), so it is left to manual review.
    QVARIANT_CHANGES = [
        (r"QVariant\(\s*([^)]+)\s*\)", r"\1"),  # QVariant(x) → x
    ]

    # exec_() → exec() (PySide6 style)
    EXEC_CHANGES = [
        (r"\.exec_\(\)", ".exec()"),
    ]

    def __init__(self, dry_run: bool = False, backup: bool = True):
        """Initialize migrator.

        Args:
            dry_run: If True, don't modify files, just show changes
            backup: If True, create .bak files before modifying
        """
        self.dry_run = dry_run
        self.backup = backup
        self.stats = {
            "files_processed": 0,
            "files_modified": 0,
            "imports_replaced": 0,
            "signals_replaced": 0,
            "qvariant_removed": 0,
            "exec_replaced": 0,
        }

    def find_pyqt5_files(self, directory: Path = Path(".")) -> List[Path]:
        """Find all Python files using PyQt5.

        Args:
            directory: Directory to search in

        Returns:
            List of Path objects for files using PyQt5
        """
        pyqt5_files = []

        for py_file in directory.glob("*.py"):
            if py_file.name.startswith("migrate_to_pyside6"):
                continue  # Skip this script

            try:
                content = py_file.read_text(encoding="utf-8")
                if "PyQt5" in content:
                    pyqt5_files.append(py_file)
            except PYSIDE6_MIGRATION_ERRORS as e:
                print(f"{Colors.RED}Error reading {py_file}: {e}{Colors.NC}")

        return sorted(pyqt5_files)

    def migrate_file(self, file_path: Path) -> Tuple[bool, int]:
        """Migrate a single file from PyQt5 to PySide6.

        Args:
            file_path: Path to file to migrate

        Returns:
            Tuple of (was_modified, num_changes)
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            original_content = content
            changes_count = 0

            # 1. Replace imports
            for old_import, new_import in self.IMPORT_REPLACEMENTS.items():
                if old_import in content:
                    count = content.count(old_import)
                    content = content.replace(old_import, new_import)
                    changes_count += count
                    self.stats["imports_replaced"] += count

            # 2. Replace signal/slot decorators
            for pattern, replacement in self.SIGNAL_SLOT_CHANGES:
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    count = len(matches)
                    changes_count += count
                    self.stats["signals_replaced"] += count

            # 3. Remove QVariant (if present)
            for pattern, replacement in self.QVARIANT_CHANGES:
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    count = len(matches)
                    changes_count += count
                    self.stats["qvariant_removed"] += count

            # 4. Replace exec_() with exec()
            for pattern, replacement in self.EXEC_CHANGES:
                matches = re.findall(pattern, content)
                if matches:
                    content = re.sub(pattern, replacement, content)
                    count = len(matches)
                    changes_count += count
                    self.stats["exec_replaced"] += count

            # Check if file was modified
            was_modified = content != original_content

            if was_modified:
                if not self.dry_run:
                    # Create backup if requested
                    if self.backup:
                        backup_path = file_path.with_suffix(file_path.suffix + ".pyqt5.bak")
                        shutil.copy2(file_path, backup_path)

                    # Write modified content
                    file_path.write_text(content, encoding="utf-8")

                self.stats["files_modified"] += 1

            self.stats["files_processed"] += 1

            return was_modified, changes_count

        except PYSIDE6_MIGRATION_ERRORS as e:
            print(f"{Colors.RED}Error migrating {file_path}: {e}{Colors.NC}")
            return False, 0

    def show_file_changes(self, file_path: Path, num_changes: int):
        """Display changes made to a file.

        Args:
            file_path: Path to modified file
            num_changes: Number of changes made
        """
        status = "would change" if self.dry_run else "changed"
        print(f"{Colors.GREEN}✓{Colors.NC} {file_path.name:<40} {status} {num_changes} lines")

    def print_summary(self):
        """Print migration summary statistics."""
        print("\n" + "=" * 70)
        print(f"{Colors.BOLD}Migration Summary{Colors.NC}")
        print("=" * 70)
        print(f"Files processed:     {self.stats['files_processed']}")
        print(f"Files modified:      {Colors.GREEN}{self.stats['files_modified']}{Colors.NC}")
        print(f"\nChanges made:")
        print(f"  - Imports replaced:    {self.stats['imports_replaced']}")
        print(f"  - Signals replaced:    {self.stats['signals_replaced']}")
        print(f"  - QVariant removed:    {self.stats['qvariant_removed']}")
        print(f"  - exec_() → exec():    {self.stats['exec_replaced']}")

        total_changes = (
            self.stats["imports_replaced"]
            + self.stats["signals_replaced"]
            + self.stats["qvariant_removed"]
            + self.stats["exec_replaced"]
        )
        print(f"\n{Colors.BOLD}Total changes: {total_changes}{Colors.NC}")

        if self.dry_run:
            print(f"\n{Colors.YELLOW}DRY RUN - No files were actually modified{Colors.NC}")
        else:
            print(f"\n{Colors.GREEN}✓ Migration completed successfully{Colors.NC}")
            if self.backup:
                print(f"{Colors.CYAN}ℹ Backups saved with .pyqt5.bak extension{Colors.NC}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate FPDB-3 from PyQt5 to PySide6",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would change
  python migrate_to_pyside6.py --dry-run --all

  # Migrate all files with backup
  python migrate_to_pyside6.py --all

  # Migrate specific file
  python migrate_to_pyside6.py --file fpdb.pyw

  # Migrate without backup (not recommended)
  python migrate_to_pyside6.py --all --no-backup
        """,
    )

    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")

    parser.add_argument("--file", type=str, help="Migrate specific file")

    parser.add_argument("--all", action="store_true", help="Migrate all PyQt5 files")

    parser.add_argument("--backup", action="store_true", default=True, help="Create backup before migration (default)")

    parser.add_argument("--no-backup", action="store_true", help="Do not create backup")

    args = parser.parse_args()

    # Validate arguments
    if not args.file and not args.all:
        parser.error("Must specify either --file or --all")

    # Determine backup setting
    backup = not args.no_backup

    # Create migrator
    migrator = PySide6Migrator(dry_run=args.dry_run, backup=backup)

    print(f"{Colors.BOLD}{'=' * 70}{Colors.NC}")
    print(f"{Colors.BOLD}FPDB-3 PyQt5 → PySide6 Migration{Colors.NC}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.NC}\n")

    if args.dry_run:
        print(f"{Colors.YELLOW}Running in DRY RUN mode (no files will be modified){Colors.NC}\n")

    # Get files to migrate
    if args.all:
        files_to_migrate = migrator.find_pyqt5_files()
        print(f"Found {len(files_to_migrate)} files using PyQt5\n")
    else:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"{Colors.RED}Error: File not found: {args.file}{Colors.NC}")
            sys.exit(1)
        files_to_migrate = [file_path]

    if not files_to_migrate:
        print(f"{Colors.YELLOW}No PyQt5 files found{Colors.NC}")
        sys.exit(0)

    # Migrate files
    print(f"{Colors.BOLD}Migrating files...{Colors.NC}\n")

    for file_path in files_to_migrate:
        was_modified, num_changes = migrator.migrate_file(file_path)
        if was_modified:
            migrator.show_file_changes(file_path, num_changes)

    # Print summary
    migrator.print_summary()

    # Next steps
    if not args.dry_run and migrator.stats["files_modified"] > 0:
        print(f"\n{Colors.BOLD}Next Steps:{Colors.NC}")
        print("1. Update pyproject.toml to use PySide6")
        print("2. Install PySide6: pip install PySide6")
        print("3. Run tests: python test_migration.py")
        print("4. Test application: python fpdb.pyw")
        print("5. If issues, restore from .pyqt5.bak files")


if __name__ == "__main__":
    main()
