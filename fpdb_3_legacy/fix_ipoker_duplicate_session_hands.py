"""iPoker Duplicate Session Files Cleanup Tool.

Scans an iPoker hand history directory tree, identifies duplicate XML session files
containing game codes already present in earlier session files, and removes them deterministically.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import defusedxml.ElementTree
from defusedxml.common import DefusedXmlException

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("ipoker_duplicate_cleanup")

# A session file comes from the poker room, so it is parsed with the hardened
# parser like every other hand history fpdb reads: the stock one honours entity
# declarations, which turns a hand history into a file-read primitive.
READ_ERRORS = (OSError, defusedxml.ElementTree.ParseError, DefusedXmlException)


def extract_ipoker_gamecodes(file_path: Path) -> set[str]:
    """Extract game codes from an iPoker XML session file.

    A file that cannot be read or parsed yields no game codes, which keeps it
    out of the duplicate list -- this tool deletes files, so anything it does
    not fully understand has to be left alone. The reason is logged rather than
    swallowed, otherwise a directory full of unreadable files looks exactly
    like a directory with nothing to clean.
    """
    gamecodes: set[str] = set()
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if "<game" not in content:
            return gamecodes
        root = defusedxml.ElementTree.fromstring(content)
        for game in root.findall(".//game"):
            code = game.get("gamecode")
            if code:
                gamecodes.add(code)
    except READ_ERRORS as exc:
        log.warning("Skipping %s, it could not be read as an iPoker session: %s", file_path, exc)
        return set()
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


def clean_duplicate_ipoker_files(directory_path: str | Path, *, dry_run: bool = False) -> list[Path]:
    """Find and remove duplicate iPoker session files.

    Returns the files that were actually removed -- or, on a dry run, the ones
    that would be. A file whose deletion fails is reported, not counted: this
    is the difference between telling a player their hand histories were
    cleaned up and telling them they still have to deal with it.

    ``dry_run`` is keyword-only on purpose. This function deletes files, and a
    positional flag is the kind of thing that gets passed the wrong way round.
    """
    duplicates = find_duplicate_ipoker_files(directory_path)
    if dry_run:
        return duplicates

    removed: list[Path] = []
    for file_path in duplicates:
        try:
            file_path.unlink()
        except OSError as exc:
            log.warning("Could not remove duplicate %s: %s", file_path, exc)
        else:
            removed.append(file_path)
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean duplicate iPoker session XML files.")
    parser.add_argument("directory", help="Path to iPoker hand history directory")
    parser.add_argument("--dry-run", action="store_true", help="List duplicate files without deleting them")
    args = parser.parse_args()

    handled = clean_duplicate_ipoker_files(args.directory, dry_run=args.dry_run)
    action = "Found" if args.dry_run else "Removed"
    print(f"{action} {len(handled)} duplicate iPoker file(s):")
    for dup in handled:
        print(f"  {dup}")


if __name__ == "__main__":
    main()
