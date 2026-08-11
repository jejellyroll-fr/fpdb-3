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


def test_windows_seat_read_selects_the_closest_duplicate_title(monkeypatch):
    """UIAutomation must read the window paired by geometry, not first match."""
    from types import SimpleNamespace

    reader = winamax_ax_seats.WinamaxAXSeatReader(
        table_detector=MagicMock(
            find_tables=lambda _pattern: [
                SimpleNamespace(window_id=101, bounds=(0, 0, 800, 600)),
                SimpleNamespace(window_id=202, bounds=(1200, 0, 800, 600)),
            ]
        )
    )
    read = MagicMock(return_value={0: "Hero"})
    monkeypatch.setattr(reader, "_read_window_windows", read)
    monkeypatch.setattr(winamax_ax_seats.platform, "system", lambda: "Windows")
    monkeypatch.setattr(winamax_ax_seats, "is_ax_available", lambda: True)

    slots = reader.read_window("Winamax Colorado 3", table_pos=(1200, 0))

    assert slots == {0: "Hero"}
    read.assert_called_once_with(202, 6)
