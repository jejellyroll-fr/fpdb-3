"""A watched folder the system refuses to list must be reported, not read as empty.

macOS keeps another app's sandbox container (Bwin.fr's ``History/Data/Tables``)
out of reach of an app that was not given Full Disk Access. fpdb launched from
Terminal.app imported the Bwin.fr hands; the same fpdb launched from a VS Code
terminal imported none, and its HUD showed nothing: ``os.walk`` swallowed the
refusal, so auto-import ran every cycle, found "no new file" and said nothing.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

from fpdb_3_legacy.Importer import Importer, cannot_list_directory


def _directory_importer() -> Importer:
    """An Importer holding only what addImportDirectory reads."""
    importer = Importer.__new__(Importer)
    importer.monitor = False
    importer.dirlist = {}
    importer.failed_files = MagicMock()
    importer.failed_files.failed.return_value = False
    importer._is_valid_import_file = MagicMock(return_value=True)
    importer.addImportFile = MagicMock()
    return importer


def _refusing_listdir(refused: set[str]):
    real_listdir = os.listdir
    real_scandir = os.scandir

    def listdir(path="."):
        if str(path) in refused:
            raise PermissionError(1, "Operation not permitted", str(path))
        return real_listdir(path)

    def scandir(path="."):
        if str(path) in refused:
            raise PermissionError(1, "Operation not permitted", str(path))
        return real_scandir(path)

    return listdir, scandir


def _refused_warnings(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.getMessage().startswith("Cannot list ")]


def test_a_refused_folder_is_named_in_a_warning(tmp_path, caplog) -> None:
    importer = _directory_importer()
    listdir, scandir = _refusing_listdir({str(tmp_path)})

    with (
        caplog.at_level(logging.WARNING),
        patch("os.scandir", side_effect=scandir),
        patch("os.listdir", side_effect=listdir),
    ):
        importer.addImportDirectory(str(tmp_path))

    warnings = _refused_warnings(caplog)
    assert len(warnings) == 1
    assert str(tmp_path) in warnings[0].getMessage()
    assert "Full Disk Access" in warnings[0].getMessage()
    importer.addImportFile.assert_not_called()


def test_every_cycle_after_the_first_stays_quiet(tmp_path, caplog) -> None:
    """Auto-import walks each watched folder every few seconds: one warning is enough."""
    importer = _directory_importer()
    listdir, scandir = _refusing_listdir({str(tmp_path)})

    with (
        caplog.at_level(logging.WARNING),
        patch("os.scandir", side_effect=scandir),
        patch("os.listdir", side_effect=listdir),
    ):
        for _cycle in range(3):
            importer.addImportDirectory(str(tmp_path))

    assert len(_refused_warnings(caplog)) == 1


def test_a_refusal_after_access_came_back_is_reported_again(tmp_path, caplog) -> None:
    importer = _directory_importer()
    listdir, scandir = _refusing_listdir({str(tmp_path)})

    with caplog.at_level(logging.WARNING):
        with patch("os.scandir", side_effect=scandir), patch("os.listdir", side_effect=listdir):
            importer.addImportDirectory(str(tmp_path))
        importer.addImportDirectory(str(tmp_path))
        with patch("os.scandir", side_effect=scandir), patch("os.listdir", side_effect=listdir):
            importer.addImportDirectory(str(tmp_path))

    assert len(_refused_warnings(caplog)) == 2


def test_a_readable_folder_raises_no_warning(tmp_path, caplog) -> None:
    (tmp_path / "hand-123456.txt").write_text("hand", encoding="utf-8")
    importer = _directory_importer()

    with caplog.at_level(logging.WARNING):
        importer.addImportDirectory(str(tmp_path))

    assert _refused_warnings(caplog) == []
    importer.addImportFile.assert_called_once()


def test_cannot_list_directory_tells_a_refused_folder_from_an_empty_or_missing_one(tmp_path) -> None:
    assert cannot_list_directory(str(tmp_path)) is False
    assert cannot_list_directory(str(tmp_path / "missing")) is False

    listdir, _scandir = _refusing_listdir({str(tmp_path)})
    with patch("os.listdir", side_effect=listdir):
        assert cannot_list_directory(str(tmp_path)) is True
