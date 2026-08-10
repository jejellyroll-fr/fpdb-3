"""Unit test for Windows FastFold table window resolution."""

from unittest.mock import MagicMock, patch

from fpdb.infrastructure.platform.protocol import TableInfo
from fpdb_3_legacy import winamax_ax_seats


def test_is_supported_returns_true_on_windows_and_darwin():
    """Verify is_supported includes Windows as well as Darwin."""
    with patch("platform.system", return_value="Windows"):
        assert winamax_ax_seats.is_supported() is True

    with patch("platform.system", return_value="Darwin"):
        assert winamax_ax_seats.is_supported() is True


def test_winamax_ax_seat_reader_finds_window_on_windows():
    """Verify that WinamaxAXSeatReader resolves table window on Windows."""
    mock_table = TableInfo(
        window_id=123456,
        title="Winamax Colorado 3",
        geometry=None,
    )
    mock_detector = MagicMock()
    mock_detector.find_tables.return_value = [mock_table]

    reader = winamax_ax_seats.WinamaxAXSeatReader(table_detector=mock_detector)

    with patch("fpdb_3_legacy.winamax_ax_seats.is_supported", return_value=True):
        window = reader.find_table_window("3")
        assert window is not None
        assert window.title == "Winamax Colorado 3"
        assert window.window_id == 123456
        assert window.table_name == "Colorado 3"
