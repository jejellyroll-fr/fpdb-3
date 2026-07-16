from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy.Importer import Importer


def _updated_importer(hand_file):
    importer = Importer.__new__(Importer)
    tracked_file = SimpleNamespace(fileId=7, site=SimpleNamespace(name="PokerStars"))
    importer.dirlist = {}
    importer.filelist = {str(hand_file): tracked_file}
    importer.updatedsize = {str(hand_file): 0}
    importer.updatedtime = {str(hand_file): 0}
    importer.removeFromFileList = {}
    importer._import_despatch = MagicMock(return_value=(1, 0, 0, 0, 0, 0.1, "PokerStars"))
    importer.logImport = MagicMock()
    importer.caller = MagicMock()
    importer.database = MagicMock()
    importer.runPostImport = MagicMock()
    return importer, tracked_file


def test_run_updated_uses_stable_tracked_file_reference(tmp_path) -> None:
    hand_file = tmp_path / "hand-123456.txt"
    hand_file.write_text("hand", encoding="utf-8")
    importer, tracked_file = _updated_importer(hand_file)

    importer.runUpdated()

    importer._import_despatch.assert_called_once_with(tracked_file)
    importer.caller.addText.assert_called_once_with("\nPokerStars - 123456 OK (1 stored)", "import")
    assert importer.updatedsize[str(hand_file)] == hand_file.stat().st_size


def test_run_updated_does_not_hide_callback_key_errors(tmp_path) -> None:
    hand_file = tmp_path / "hand-123456.txt"
    hand_file.write_text("hand", encoding="utf-8")
    importer, _tracked_file = _updated_importer(hand_file)
    importer.caller.addText.side_effect = KeyError("broken callback")

    with pytest.raises(KeyError, match="broken callback"):
        importer.runUpdated()
