"""Unit test for WinTables resolved_window support."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fpdb.infrastructure.platform.protocol import TableGeometry
from fpdb_3_legacy import WinTables


def test_wintables_uses_resolved_window():
    """Verify that find_table_parameters reuses a pre-resolved window if provided."""
    mock_geometry = TableGeometry(x=10, y=20, width=800, height=600)
    mock_detector = MagicMock()
    mock_detector.get_window_geometry.return_value = mock_geometry

    resolved_window = SimpleNamespace(window_id=12345, title="Winamax Go Fast - Table 1")

    t = object.__new__(WinTables.Table)
    t._resolved_window = resolved_window
    t._detector = mock_detector
    t.search_string = "Winamax"
    t.check_bad_words = MagicMock(return_value=False)

    t.find_table_parameters()

    assert t.number == 12345
    assert t.title == "Winamax Go Fast - Table 1"
    assert t._table_geometry == mock_geometry
    mock_detector.get_window_geometry.assert_called_once_with(12345)
    mock_detector.find_tables.assert_not_called()


def test_wintables_init_pops_resolved_window():
    """Verify that Table.__init__ stores resolved_window attribute."""
    resolved_window = SimpleNamespace(window_id=999, title="FastFold Table")

    with patch("fpdb_3_legacy.TableWindow.Table_Window.__init__", return_value=None):
        table = WinTables.Table(MagicMock(), "Winamax", resolved_window=resolved_window)
        assert table._resolved_window == resolved_window
