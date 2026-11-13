"""An export file that is truncated or recreated must not lose later hands (#729).

The importer remembers how far into each file it has read.  The 2026 Unibet
client may recreate a table's export smaller than before; reading on from the
old offset would then skip every new hand.  The cycle resets the offset when
the file shrank (hands already stored are duplicate-safe by hand id).

The same cycle must also survive what Windows does to a file the client still
holds open, and a UTF-8 file name.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.UnibetToFpdb import Unibet


def _importer(path, seen_size: int, offset: int) -> Importer:
    importer = Importer.__new__(Importer)
    tracked = SimpleNamespace(path=str(path), ftype="hh", fileId=7, site=SimpleNamespace(name="Unibet"))
    importer.filelist = {str(path): tracked}
    importer.dirlist = {}
    importer.updatedsize = {str(path): seen_size}
    importer.updatedtime = {str(path): 0}
    importer.pos_in_file = {str(path): offset}
    importer.removeFromFileList = {}
    importer.offsets_seen = []

    def despatch(_tracked):
        importer.offsets_seen.append(importer.pos_in_file.get(str(path)))
        return (1, 0, 0, 0, 0, 0.1, "Unibet")

    importer._import_despatch = despatch
    importer.logImport = MagicMock()
    importer.caller = MagicMock()
    importer.database = MagicMock()
    importer.runPostImport = MagicMock()
    return importer


def test_a_truncated_export_is_read_from_the_start(tmp_path) -> None:
    export = tmp_path / "H1 T99007080.txt"
    export.write_text("a new, shorter file\n", encoding="utf-8")
    importer = _importer(export, seen_size=5000, offset=5000)

    importer.runUpdated()

    assert importer.offsets_seen == [0]


def test_a_growing_export_keeps_its_offset(tmp_path) -> None:
    export = tmp_path / "H1 T99007080.txt"
    export.write_text("x" * 6000, encoding="utf-8")
    importer = _importer(export, seen_size=5000, offset=5000)

    importer.runUpdated()

    assert importer.offsets_seen == [5000]


def test_a_utf8_file_name_is_tracked(tmp_path) -> None:
    export = tmp_path / "Mains été 99007080.txt"
    export.write_text("hand", encoding="utf-8")
    importer = _importer(export, seen_size=0, offset=0)

    importer.runUpdated()

    assert importer.offsets_seen == [0]
    assert str(export) in importer.filelist


def test_a_file_the_client_still_locks_is_not_lost(tmp_path, monkeypatch) -> None:
    """On Windows the open fails while the client holds the file: no hands, no crash."""
    export = tmp_path / "locked.txt"
    export.write_text("Unibet Hand #1 - 0.03/0.05 - Pot Limit Omaha - UTC 13:23:13 2026/11/07\n", encoding="utf-8")
    real_open = open

    def locked(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if os.fspath(path) == str(export) and "b" in mode:
            raise PermissionError(13, "The process cannot access the file")
        return real_open(path, *args, **kwargs)

    converter = Unibet.__new__(Unibet)
    converter.in_path = str(export)
    converter.filetype = "text"
    converter.index = 0
    converter.obs = None
    monkeypatch.setattr("builtins.open", locked)

    assert converter.readFile() is False
    assert converter.obs == ""
    assert converter.index == 0
