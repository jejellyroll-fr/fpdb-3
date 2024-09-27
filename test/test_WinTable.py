import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
import platform

sys.path.append(str(Path(__file__).parent.parent))

# Skip the whole file if not on Windows
pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Tests only run on Windows systems")

# Import WinTables inside the test function
if platform.system() == "Windows":
    from WinTables import Table

# Fixtures for config and site
@pytest.fixture
def config():
    mock_config = MagicMock()
    return mock_config

@pytest.fixture
def site():
    return 'test_site'

@pytest.fixture
def table_window(config, site):
    if platform.system() == "Windows":
        return Table(config, site)
    return None  # Handle non-Windows platforms gracefully

# Test that find_table_parameters doesn't find a match
@patch('WinTables.EnumWindows', return_value=True)
@patch('WinTables.GetWindowText', return_value="Non-matching Window")
@patch('WinTables.IsWindowVisible', return_value=True)
@patch('WinTables.GetParent', return_value=0)
def test_find_table_parameters_no_match(mock_get_parent, mock_is_window_visible, mock_get_window_text, mock_enum_windows, table_window):
    if table_window is None:
        pytest.skip("Skipping test on non-Windows systems")
    
    table_window.search_string = "Winamax"
    table_window.find_table_parameters()
    assert table_window.number is None

# Test get_geometry successfully retrieves geometry
@patch('WinTables.IsWindow', return_value=True)
@patch('WinTables.GetWindowRect', return_value=0)
def test_get_geometry_success(mock_get_window_rect, mock_is_window, table_window):
    if table_window is None:
        pytest.skip("Skipping test on non-Windows systems")
    
    mock_get_window_rect.return_value = 1  # Simulate successful GetWindowRect
    table_window.number = 123  # Fake window handle
    geo = table_window.get_geometry()
    assert geo is not None
    assert 'x' in geo
    assert 'y' in geo
    assert 'width' in geo
    assert 'height' in geo

# Test get_geometry with an invalid window
@patch('WinTables.IsWindow', return_value=False)
def test_get_geometry_invalid_window(mock_is_window, table_window):
    if table_window is None:
        pytest.skip("Skipping test on non-Windows systems")
    
    table_window.number = 123
    geo = table_window.get_geometry()
    assert geo is None

# Test moving and resizing a window
@patch('WinTables.MoveWindow')
def test_move_and_resize_window(mock_move_window, table_window):
    if table_window is None:
        pytest.skip("Skipping test on non-Windows systems")
    
    table_window.number = 123  # Fake window handle
    table_window.move_and_resize_window(100, 100, 800, 600)
    mock_move_window.assert_called_once_with(123, 100, 100, 800, 600, True)

# Test moving and resizing without a valid window handle
def test_move_and_resize_window_no_window(table_window):
    if table_window is None:
        pytest.skip("Skipping test on non-Windows systems")
    
    table_window.number = None
    table_window.move_and_resize_window(100, 100, 800, 600)
    # No call to MoveWindow expected as number is None

# Test topify function for window layering
@patch('WinTables.QWindow.fromWinId')
def test_topify(mock_from_winid, table_window):
    if table_window is None:
        pytest.skip("Skipping test on non-Windows systems")
    
    mock_window = MagicMock()
    table_window.number = 123
    table_window.topify(mock_window)
    mock_from_winid.assert_called_once_with(123)
    mock_window.windowHandle().setTransientParent.assert_called_once()
    mock_window.windowHandle().setFlags.assert_called_once()
