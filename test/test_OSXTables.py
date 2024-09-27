import pytest
from unittest.mock import MagicMock, patch
import sys
import platform
from pathlib import Path

# Add the parent path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Only import if on macOS
if platform.system() == "Darwin":
    from OSXTables import Table, TableActivationObserver
    from AppKit import NSWorkspace

@pytest.mark.skipif(platform.system() != "Darwin", reason="Only runs on macOS")
@pytest.fixture
def mock_nsworkspace():
    nsworkspace_mock = MagicMock()
    patcher = patch('OSXTables.NSWorkspace', nsworkspace_mock)
    patcher.start()
    yield nsworkspace_mock
    patcher.stop()

@pytest.mark.skipif(platform.system() != "Darwin", reason="Only runs on macOS")
@pytest.fixture
def mock_table():
    table_mock = MagicMock(spec=Table)
    return table_mock

@pytest.mark.skipif(platform.system() != "Darwin", reason="Only runs on macOS")
def test_table_activation_observer_activation(mock_nsworkspace, mock_table):
    observer = TableActivationObserver.alloc().init()
    observer.table = mock_table

    # Simulate the window title to match the application name
    mock_table.get_window_title.return_value = 'Winamax'

    # Simulate the active application being the correct poker site
    mock_nsworkspace.sharedWorkspace().activeApplication.return_value = {'NSApplicationName': 'Winamax'}
    observer.check_active_app()

    # Verify the table on_activate method was called
    mock_table.on_activate.assert_called_once()
    mock_table.on_deactivate.assert_not_called()

@pytest.mark.skipif(platform.system() != "Darwin", reason="Only runs on macOS")
def test_table_activation_observer_deactivation(mock_nsworkspace, mock_table):
    observer = TableActivationObserver.alloc().init()
    observer.table = mock_table

    # Simulate the window title not matching the active application
    mock_table.get_window_title.return_value = 'Winamax'

    # Simulate the active application being a different one
    mock_nsworkspace.sharedWorkspace().activeApplication.return_value = {'NSApplicationName': 'OtherApp'}
    observer.check_active_app()

    # Verify the table on_deactivate method was called
    mock_table.on_activate.assert_not_called()
    mock_table.on_deactivate.assert_called_once()

@pytest.mark.skipif(platform.system() != "Darwin", reason="Only runs on macOS")
def test_table_get_process_name():
    table = Table(config="dummy_config", site="Winamax")
    
    # Check if it returns the correct process name for Winamax (account for lowercase)
    assert table.get_process_name().lower() == 'winamax'

    # Check for another supported site, e.g., PokerStars
    table.site = 'PokerStars'
    assert table.get_process_name().lower() == 'pokerstars'
