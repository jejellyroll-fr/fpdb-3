import pytest
from unittest.mock import MagicMock, patch
import sys
import re
import platform
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

# Import TableWindow based on OS
if platform.system() == 'Windows':
    from WinTables import Table
elif platform.system() == 'Darwin':
    from OSXTables import Table
elif platform.system() == 'Linux':
    from XTables import Table
else:
    raise OSError("Unsupported operating system")

# Fixtures for config and site
@pytest.fixture
def config():
    mock_config = MagicMock()
    # Mock a fictitious converter
    mock_config.hhcs = {
        'test_site': MagicMock(converter='ValidConverterModule')
    }
    return mock_config

@pytest.fixture
def site():
    return 'test_site'

# Patch for getSiteHhc
@pytest.fixture(autouse=True)
def mock_getSiteHhc():
    with patch('HandHistoryConverter.getSiteHhc') as mock_hhc, \
         patch('HandHistoryConverter.getTableTitleRe', return_value=re.compile(r'Test Table')):
        mock_hhc.return_value = MagicMock()
        yield

@pytest.fixture
def table_window(config, site):
    return Table(config, site)

@patch('HandHistoryConverter.getTableTitleRe', return_value=re.compile(r'Test Table'))
def test_table_window_search_string_table_name(mock_get_table_title_re, config, site):
    """Test if search_string is properly generated with a table name."""
    table_name = "Test Table"
    tw = Table(config, site, table_name=table_name)
    assert isinstance(tw.search_string, re.Pattern)

# Windows-specific test
@pytest.mark.skipif(platform.system() != 'Windows', reason="Test for Windows only")
@patch('WinTables.Table.find_table_parameters')
def test_find_table_parameters_called_on_windows(mock_find_table_parameters, table_window):
    """Test if find_table_parameters is called on Windows."""
    table_window.find_table_parameters()
    mock_find_table_parameters.assert_called_once()

# macOS-specific test
@pytest.mark.skipif(platform.system() != 'Darwin', reason="Test for macOS only")
@patch('OSXTables.Table.find_table_parameters')
def test_find_table_parameters_called_on_macos(mock_find_table_parameters, table_window):
    """Test if find_table_parameters is called on macOS."""
    table_window.find_table_parameters()
    mock_find_table_parameters.assert_called_once()

# Linux-specific test
@pytest.mark.skipif(platform.system() != 'Linux', reason="Test for Linux only")
@patch('XTables.Table.find_table_parameters')
def test_find_table_parameters_called_on_linux(mock_find_table_parameters, table_window):
    """Test if find_table_parameters is called on Linux."""
    table_window.find_table_parameters()
    mock_find_table_parameters.assert_called_once()

# Test for No Limit Hold'em game detection
def test_get_game_nl_holdem(table_window):
    """Test game detection for No Limit Hold'em."""
    table_window.title = "No Limit Hold'em"
    game = table_window.get_game()
    assert game == ("nl", "holdem")

# Test for Limit Stud game detection
def test_get_game_limit_stud(table_window):
    """Test game detection for Limit Stud."""
    table_window.title = "Limit Stud"
    game = table_window.get_game()
    assert game == ("fl", "studhi")

# Test get_table_no when the title matches
@patch('WinTables.Table.get_window_title')
def test_get_table_no_matches(mock_get_window_title, table_window):
    """Test table number extraction when the title matches."""
    mock_get_window_title.return_value = "Table 123"
    table_window.tableno_re = re.compile(r'Table (\d+)')
    table_no = table_window.get_table_no()
    assert table_no == 123

# Test get_table_no when no match is found
@patch('WinTables.Table.get_window_title')
def test_get_table_no_no_match(mock_get_window_title, table_window):
    """Test table number extraction when no match is found."""
    mock_get_window_title.return_value = "Table ABC"
    table_window.tableno_re = re.compile(r'Table (\d+)')
    table_no = table_window.get_table_no()
    assert table_no is False

# Test check_table calls check_size and check_loc
@patch('WinTables.Table.check_size')
@patch('WinTables.Table.check_loc')
def test_check_table_calls_check_size_and_check_loc(mock_check_loc, mock_check_size, table_window):
    """Test if check_table calls check_size and check_loc."""
    mock_check_size.return_value = False
    mock_check_loc.return_value = False
    result = table_window.check_table()
    mock_check_size.assert_called_once()
    mock_check_loc.assert_called_once()
    assert result is False

# Test check_size detects resizing
@patch('WinTables.Table.get_geometry')
def test_check_size_detects_resize(mock_get_geometry, table_window):
    """Test if check_size detects client resizing."""
    mock_get_geometry.return_value = {'width': 800, 'height': 600}
    table_window.width = 1024
    table_window.height = 768
    result = table_window.check_size()
    assert result == "client_resized"

# Test check_loc detects moving
@patch('WinTables.Table.get_geometry')
def test_check_loc_detects_move(mock_get_geometry, table_window):
    """Test if check_loc detects client movement."""
    mock_get_geometry.return_value = {'x': 100, 'y': 200}
    table_window.x = 0
    table_window.y = 0
    result = table_window.check_loc()
    assert result == "client_moved"

# Test has_table_title_changed returns True when the table number changes
@patch('WinTables.Table.get_table_no')
def test_has_table_title_changed_returns_true(mock_get_table_no, table_window):
    """Test if has_table_title_changed returns True when the table number changes."""
    mock_get_table_no.return_value = 100 
    table_window.table = 50 
    result = table_window.has_table_title_changed(None)
    assert table_window.table == 100 
    assert result is True  

# Test check_bad_words detects bad words
def test_check_bad_words_detects_bad_word(table_window):
    """Test if check_bad_words detects forbidden words."""
    title = "History for table:"
    result = table_window.check_bad_words(title)
    assert result is True  

def test_check_bad_words_with_space(table_window):
    """Test if check_bad_words detects forbidden words with extra spaces."""
    title = " History for table: "
    result = table_window.check_bad_words(title) 
    assert result is True  

# Manual comparison test
def test_manual_comparison():
    """Test manual string comparison."""
    title = "History for table:"
    bad_word = "History for table:"
    title_normalized = title.strip().lower()
    bad_word_normalized = bad_word.lower()
    assert bad_word_normalized in title_normalized, "Manual comparison failed"

# Test check_bad_words detects no bad words when none exist
def test_check_bad_words_no_bad_word(table_window):
    """Test if check_bad_words detects no bad words."""
    result = table_window.check_bad_words("PokerStars Table 1")
    assert result is False

# Test __str__ method
def test_table_window_str_method(table_window):
    """Test the __str__ method of TableWindow."""
    table_window.number = 123
    table_window.title = "Test Table"
    table_window.site = "test_site"
    table_window.width = 800
    table_window.height = 600
    table_window.x = 100
    table_window.y = 200
    result = str(table_window)
    assert "number = 123" in result
    assert "title = Test Table" in result
    assert "site = test_site" in result
    assert "width = 800" in result
    assert "height = 600" in result
    assert "x = 100" in result
    assert "y = 200" in result

# Test get_game when no match is found
def test_get_game_no_match(table_window):
    """Test game detection when no match is found."""
    table_window.title = "Unknown Game Title"
    game = table_window.get_game()
    assert game is False  

# Test get_table_no with missing tableno_re (AttributeError case)
@patch('WinTables.Table.get_window_title', new_callable=MagicMock)
@pytest.mark.skipif(platform.system() != 'Windows', reason="Test specific to Windows")
def test_get_table_no_no_regex_windows(mock_get_window_title, table_window):
    """Test get_table_no returns False when tableno_re is missing."""
    mock_get_window_title.return_value = "Table ABC"
    table_window.tableno_re = None  
    table_no = table_window.get_table_no()
    assert table_no is False  

# Basic initialization test
def test_table_window_init_basic(config, site):
    """Test basic initialization of TableWindow."""
    tw = Table(config, site)  
    assert tw.config == config
    assert tw.site == site
    assert tw.hud is None
    assert tw.gdkhandle is None
    assert tw.number is None
    assert tw.tournament is None
    assert tw.table is None

# Initialization test with table name (cash game)
def test_table_window_init_table_name(config, site):
    """Test initialization with a table name (cash game)."""
    table_name = "Test Table"
    tw = Table(config, site, table_name=table_name)
    assert tw.name == table_name
    assert tw.type == "cash"
    assert tw.tournament is None  
    assert tw.table is None      

# Initialization test with tournament and table number
def test_table_window_init_tournament(config, site):
    """Test initialization with tournament and table number."""
    tournament = 12345
    table_number = 6789
    tw = Table(config, site, tournament=tournament, table_number=table_number)
    assert tw.tournament == tournament
    assert tw.table == table_number
    assert tw.name == f"{tournament} - {table_number}"
    assert tw.type == "tour"

# Initialization test with invalid parameters (neither table name nor tournament/table number)
def test_table_window_init_invalid_params(config, site):
    """Test initialization with invalid parameters (missing table name and tournament/table number)."""
    tw = Table(config, site)
    assert tw.search_string is None

# Test generation of search_string with table name
def test_table_window_search_string_table_name(config, site):
    """Test search_string generation with table name."""
    table_name = "Test Table"
    tw = Table(config, site, table_name=table_name)
    assert tw.search_string is not None

# Test generation of search_string with tournament
def test_table_window_search_string_tournament(config, site):
    """Test search_string generation with tournament."""
    tournament = 12345
    table_number = 6789
    tw = Table(config, site, tournament=tournament, table_number=table_number)
    assert tw.search_string is not None

# Test invalid tournament parameters (non-numeric values)
def test_table_window_init_invalid_tournament_params(config, site):
    """Test initialization with invalid tournament parameters (non-numeric values)."""
    with pytest.raises(ValueError):
        tw = Table(config, site, tournament="invalid", table_number="invalid")
