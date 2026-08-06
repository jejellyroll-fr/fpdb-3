"""iPoker Duplicate Session Files Cleanup Tool.

Scans an iPoker hand history directory tree, identifies duplicate XML session files
containing game codes already present in earlier session files, and removes them deterministically.
"""

from __future__ import annotations

import argparse
import os
import xml.etree.ElementTree as ET
from pathlib import Path


def extract_ipoker_gamecodes(file_path: Path) -> set[str]:
    """Extract game codes from an iPoker XML session file."""
    gamecodes: set[str] = set()
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if "<game" not in content:
            return gamecodes
        root = ET.fromstring(content)
        for game in root.findall(".//game"):
            code = game.get("gamecode")
            if code:
                gamecodes.add(code)
    except Exception:
        pass
    return gamecodes


def find_duplicate_ipoker_files(directory_path: str | Path) -> list[Path]:
    """Recursively scan directory_path for duplicate iPoker session files.

    Guarantees deterministic execution across platforms by explicitly sorting
    all discovered session files by path before processing.
    """
    directory_path = Path(directory_path)
    seen_gamecodes: set[str] = set()
    duplicates_to_remove: list[Path] = []

    all_files: list[Path] = []
    for root, dirnames, filenames in os.walk(directory_path):
        dirnames.sort()
        filenames.sort()
        for filename in filenames:
            if filename.lower().endswith(".xml"):
                all_files.append(Path(root) / filename)

    all_files.sort()

    for file_path in all_files:
        gamecodes = extract_ipoker_gamecodes(file_path)
        if not gamecodes:
            continue

        if gamecodes.issubset(seen_gamecodes):
            duplicates_to_remove.append(file_path)
        else:
            seen_gamecodes.update(gamecodes)

    return duplicates_to_remove


def clean_duplicate_ipoker_files(directory_path: str | Path, dry_run: bool = False) -> list[Path]:
    """Find and remove duplicate iPoker session files."""
    duplicates = find_duplicate_ipoker_files(directory_path)
    if not dry_run:
        for file_path in duplicates:
            try:
                file_path.unlink()
            except OSError:
                pass
    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean duplicate iPoker session XML files.")
    parser.add_argument("directory", help="Path to iPoker hand history directory")
    parser.add_argument("--dry-run", action="store_true", help="List duplicate files without deleting them")
    args = parser.parse_args()

    duplicates = clean_duplicate_ipoker_files(args.directory, dry_run=args.dry_run)
    action = "Found" if args.dry_run else "Removed"
    print(f"{action} {len(duplicates)} duplicate iPoker file(s):")
    for dup in duplicates:
        print(f"  {dup}")


if __name__ == "__main__":
    main()
