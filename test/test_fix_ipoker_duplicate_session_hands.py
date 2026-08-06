"""Unit tests for iPoker duplicate session files cleanup script."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from fpdb_3_legacy.fix_ipoker_duplicate_session_hands import (
    clean_duplicate_ipoker_files,
    extract_ipoker_gamecodes,
    find_duplicate_ipoker_files,
)

SAMPLE_XML_1 = """<session sessioncode="1001">
<game gamecode="10001"><general><startdate>2026-08-04</startdate></general></game>
<game gamecode="10002"><general><startdate>2026-08-04</startdate></general></game>
</session>"""

SAMPLE_XML_2 = """<session sessioncode="1002">
<game gamecode="10002"><general><startdate>2026-08-04</startdate></general></game>
</session>"""

SAMPLE_XML_3 = """<session sessioncode="1003">
<game gamecode="10003"><general><startdate>2026-08-04</startdate></general></game>
</session>"""


def test_extract_ipoker_gamecodes(tmp_path: Path) -> None:
    file_path = tmp_path / "session.xml"
    file_path.write_text(SAMPLE_XML_1, encoding="utf-8")
    codes = extract_ipoker_gamecodes(file_path)
    assert codes == {"10001", "10002"}


def test_find_and_clean_duplicate_ipoker_files(tmp_path: Path) -> None:
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    file1 = dir_a / "session_01.xml"
    file2 = dir_a / "session_02.xml"
    file3 = dir_b / "session_03.xml"

    file1.write_text(SAMPLE_XML_1, encoding="utf-8")
    file2.write_text(SAMPLE_XML_2, encoding="utf-8")  # Duplicate of gamecode 10002
    file3.write_text(SAMPLE_XML_3, encoding="utf-8")  # Unique gamecode 10003

    duplicates = find_duplicate_ipoker_files(tmp_path)
    assert duplicates == [file2]

    # Dry run shouldn't delete file
    clean_duplicate_ipoker_files(tmp_path, dry_run=True)
    assert file2.exists()

    # Actual clean should delete file2
    cleaned = clean_duplicate_ipoker_files(tmp_path, dry_run=False)
    assert cleaned == [file2]
    assert not file2.exists()
    assert file1.exists()
    assert file3.exists()


def test_filesystem_traversal_order_independence(tmp_path: Path) -> None:
    """Verify that results are 100% deterministic regardless of OS/FS walk order."""
    dir_z = tmp_path / "z_dir"
    dir_a = tmp_path / "a_dir"
    dir_z.mkdir()
    dir_a.mkdir()

    f1 = dir_z / "b_session.xml"
    f2 = dir_a / "a_session.xml"

    f1.write_text(SAMPLE_XML_1, encoding="utf-8")
    f2.write_text(SAMPLE_XML_2, encoding="utf-8")

    # Order 1: Standard os.walk
    res1 = find_duplicate_ipoker_files(tmp_path)

    # Order 2: Reverse order mock of os.walk
    original_walk = os.walk

    def reversed_walk(top, **kwargs):
        for root, dirs, files in original_walk(top, **kwargs):
            yield root, list(reversed(dirs)), list(reversed(files))

    with patch("os.walk", side_effect=reversed_walk):
        res2 = find_duplicate_ipoker_files(tmp_path)

    assert res1 == res2, f"Results differed across traversal orders: {res1} vs {res2}"
