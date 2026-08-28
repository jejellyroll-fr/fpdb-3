"""A file that disappears must not take the whole auto-import cycle with it.

``autoSummaryGrab()`` stat'd every file it tracked as "both" without checking it
was still there, and ``ImportThread`` runs it *before* ``runUpdated()`` -- which
is the only thing that purges a vanished file from ``filelist``. So deleting a
tracked file wedged auto-import permanently: the stat raised, the cycle never
reached the purge, and the next cycle stat'd the same missing file and failed
the same way. Nothing was imported again, every interval, until FPDB was
restarted.

``addImportDirectory()`` carries the same shape more briefly: ``os.walk`` lists
a name, the client rotates it away, and the stat a few lines later took down the
cycle for every other file too.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fpdb_3_legacy.Importer import Importer


def _tracked(path, ftype: str) -> SimpleNamespace:
    return SimpleNamespace(path=str(path), ftype=ftype, fileId=7, site=SimpleNamespace(name="Merge"))


def _summary_importer(files) -> Importer:
    """An Importer holding only what autoSummaryGrab reads."""
    importer = Importer.__new__(Importer)
    importer.filelist = {str(path): tracked for path, tracked in files}
    importer._import_summary_file = MagicMock()
    return importer


def test_a_deleted_summary_does_not_abort_the_grab(tmp_path) -> None:
    gone = tmp_path / "tourney-gone.txt"
    importer = _summary_importer([(gone, _tracked(gone, "both"))])

    importer.autoSummaryGrab(force=True)

    importer._import_summary_file.assert_not_called()


def test_the_files_still_there_are_grabbed_anyway(tmp_path) -> None:
    """The wedge was worst here: one deleted file stopped every other one."""
    gone = tmp_path / "tourney-gone.txt"
    present = tmp_path / "tourney-present.txt"
    present.write_text("summary", encoding="utf-8")
    kept = _tracked(present, "both")
    # Dict order puts the missing file first, which is the order that used to raise.
    importer = _summary_importer([(gone, _tracked(gone, "both")), (present, kept)])

    importer.autoSummaryGrab(force=True)

    importer._import_summary_file.assert_called_once_with(kept)
    assert kept.ftype == "hh"


def test_the_cycle_reaches_the_purge_and_imports_the_rest(tmp_path) -> None:
    """The regression that matters: the whole cycle, in the order the GUI runs it.

    The deleted entry is dropped from filelist by runUpdated -- which only gets
    to run because autoSummaryGrab no longer raises -- and the hand history file
    beside it is imported as usual.
    """
    gone = tmp_path / "tourney-gone.txt"
    hand_file = tmp_path / "hand-123456.txt"
    hand_file.write_text("hand", encoding="utf-8")

    importer = _summary_importer(
        [(gone, _tracked(gone, "both")), (hand_file, _tracked(hand_file, "hh"))],
    )
    importer.dirlist = {}
    importer.updatedsize = {str(hand_file): 0}
    importer.updatedtime = {str(hand_file): 0}
    importer.removeFromFileList = {}
    importer._import_despatch = MagicMock(return_value=(1, 0, 0, 0, 0, 0.1, "Merge"))
    importer.logImport = MagicMock()
    importer.caller = MagicMock()
    importer.database = MagicMock()
    importer.runPostImport = MagicMock()

    importer.autoSummaryGrab()
    importer.runUpdated()

    assert str(gone) not in importer.filelist
    assert str(hand_file) in importer.filelist
    importer._import_despatch.assert_called_once()


def _directory_importer() -> Importer:
    importer = Importer.__new__(Importer)
    importer.monitor = False
    importer.dirlist = {}
    importer.failed_files = MagicMock()
    importer.failed_files.failed.return_value = False
    importer._is_valid_import_file = MagicMock(return_value=True)
    importer.addImportFile = MagicMock()
    return importer


def test_a_file_rotated_away_mid_scan_is_skipped(tmp_path) -> None:
    """os.walk listed it; it is gone by the time we stat it."""
    vanishing = tmp_path / "rotated.txt"
    surviving = tmp_path / "current.txt"
    for path in (vanishing, surviving):
        path.write_text("hand", encoding="utf-8")

    importer = _directory_importer()
    real_stat = os.stat

    def stat(path, *args, **kwargs):
        if str(path) == str(vanishing):
            msg = "[WinError 2] The system cannot find the file specified"
            raise FileNotFoundError(msg)
        return real_stat(path, *args, **kwargs)

    with patch("fpdb_3_legacy.Importer.os.stat", side_effect=stat):
        importer.addImportDirectory(str(tmp_path))

    added = [call.args[0] for call in importer.addImportFile.call_args_list]
    assert added == [str(surviving)]
