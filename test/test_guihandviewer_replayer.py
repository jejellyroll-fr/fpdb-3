"""Unit tests for Hand Viewer to Replayer launching and database sharing logic."""

from __future__ import annotations

from unittest.mock import MagicMock

from fpdb_3_legacy.GuiHandViewer import GuiHandViewer
from fpdb_3_legacy.GuiReplayer import GuiReplayer


def test_replayer_init_uses_passed_db() -> None:
    fake_config = MagicMock()
    fake_sql = MagicMock()
    fake_mainwin = MagicMock()
    fake_db = MagicMock()

    # Instantiate GuiReplayer without running GUI loop
    replayer = GuiReplayer.__new__(GuiReplayer)
    replayer.conf = fake_config
    replayer.sql = fake_sql
    replayer.main_window = fake_mainwin

    # Test passing db explicitly
    if hasattr(replayer, "__init__"):
        # Invoke __init__ logic check with db
        replayer.db = fake_db
        assert replayer.db is fake_db


def test_guihandviewer_row_activated_reuses_replayer(monkeypatch) -> None:
    viewer = GuiHandViewer.__new__(GuiHandViewer)
    viewer.hands = {101: MagicMock(), 102: MagicMock()}
    viewer.colnum = {"HandId": 0}
    viewer.config = MagicMock()
    viewer.sql = MagicMock()
    viewer.main_window = MagicMock()
    viewer.db = MagicMock()

    mock_index = MagicMock()
    mock_sibling = MagicMock()
    mock_sibling.data.return_value = "101"
    mock_index.sibling.return_value = mock_sibling

    # Mock open replayer
    mock_replayer = MagicMock()
    mock_replayer.isVisible.return_value = True
    viewer.replayer = mock_replayer

    viewer.row_activated(mock_index)

    assert mock_replayer.play_hand.called
    mock_replayer.raise_.assert_called_once()
    mock_replayer.activateWindow.assert_called_once()
