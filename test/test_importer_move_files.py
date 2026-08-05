#!/usr/bin/env python3
"""Tests for Importer file-relocation after import (moveimported/movefailed files).

The old code hardcoded the two flags to False and moved files to Windows-only
paths (``c:\\fpdbimported``) using a fragile ``f[3:]`` slice with inverted
failed-file semantics. It is now driven by importer settings, portable, and
correct: successful imports go to the imported dir, files with errors to the
failed dir. These tests exercise the relocation helper directly (no DB needed).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.IdentifySite import FPDBFile
from fpdb_3_legacy.Importer import Importer


def _make_importer(settings):
    """Build an Importer shell without running its DB-connecting __init__."""
    imp = Importer.__new__(Importer)
    imp.settings = settings
    return imp


def _touch(path):
    with open(path, "w") as fh:
        fh.write("hh")


def test_no_move_when_disabled_by_default(tmp_path):
    """With no move settings, files stay put."""
    src = tmp_path / "hand1.txt"
    _touch(src)
    imp = _make_importer({})

    imp._relocate_processed_file(str(src), failed=False)
    imp._relocate_processed_file(str(src), failed=True)

    assert src.exists()  # untouched


def test_moves_imported_file_to_configured_dir(tmp_path):
    """A successful import is moved to moveImportedFilesDir (created if needed)."""
    src = tmp_path / "hand2.txt"
    _touch(src)
    dest_dir = tmp_path / "archive" / "imported"  # does not exist yet
    imp = _make_importer(
        {"moveimportedfiles": True, "moveImportedFilesDir": str(dest_dir)},
    )

    imp._relocate_processed_file(str(src), failed=False)

    assert not src.exists()
    assert (dest_dir / "hand2.txt").exists()  # basename preserved, dir created


def test_moves_failed_file_to_failed_dir(tmp_path):
    """A failed import goes to moveFailedFilesDir, not the imported dir."""
    src = tmp_path / "bad.txt"
    _touch(src)
    imported_dir = tmp_path / "imported"
    failed_dir = tmp_path / "failed"
    imp = _make_importer(
        {
            "moveimportedfiles": True,
            "moveImportedFilesDir": str(imported_dir),
            "movefailedfiles": True,
            "moveFailedFilesDir": str(failed_dir),
        },
    )

    imp._relocate_processed_file(str(src), failed=True)

    assert (failed_dir / "bad.txt").exists()
    assert not (imported_dir / "bad.txt").exists()


def test_move_disabled_when_flag_off_even_with_dir(tmp_path):
    """A configured dir alone does not move files; the flag must be on."""
    src = tmp_path / "hand3.txt"
    _touch(src)
    imp = _make_importer(
        {"moveimportedfiles": False, "moveImportedFilesDir": str(tmp_path / "imported")},
    )

    imp._relocate_processed_file(str(src), failed=False)

    assert src.exists()


def test_setters_populate_settings():
    """The setters wire the flags/dirs into settings for the GUI to drive."""
    imp = _make_importer({})
    imp.setMoveImportedFiles(True, "/data/imported")
    imp.setMoveFailedFiles(True, "/data/failed")

    assert imp.settings["moveimportedfiles"] is True
    assert imp.settings["moveImportedFilesDir"] == "/data/imported"
    assert imp.settings["movefailedfiles"] is True
    assert imp.settings["moveFailedFilesDir"] == "/data/failed"


def test_clear_file_list_resets_updated_time_tracking() -> None:
    """Regression: clearFileList must reset ``updatedtime``, not a misspelled shadow."""
    imp = _make_importer({})
    imp.updatedsize = {"hand.txt": 10}
    imp.updatedtime = {"hand.txt": 123.0}
    imp.pos_in_file = {"hand.txt": 5}
    imp.filelist = {"hand.txt": object()}

    imp.clearFileList()

    assert imp.updatedsize == {}
    assert imp.updatedtime == {}
    assert imp.pos_in_file == {}
    assert imp.filelist == {}
    assert not hasattr(imp, "updatetime")


def test_unidentified_file_cannot_be_registered() -> None:
    imp = _make_importer({})
    unidentified = FPDBFile("unknown-room.txt")

    with pytest.raises(ValueError, match="Cannot register unidentified file"):
        imp.addFileToList(unidentified)


def test_move_failure_is_swallowed(tmp_path):
    """A move that fails (missing source) is logged, not raised."""
    imp = _make_importer(
        {"moveimportedfiles": True, "moveImportedFilesDir": str(tmp_path / "imported")},
    )
    # Source does not exist -> shutil.move raises, helper must swallow it.
    imp._relocate_processed_file(str(tmp_path / "nope.txt"), failed=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
