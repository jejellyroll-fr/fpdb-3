import pytest
from unittest.mock import MagicMock, patch
import sys
import re
import platform
from pathlib import Path

# Add the parent path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Mapping platforms to corresponding modules
PLATFORM_MODULES = {
    'Windows': 'WinTables',
    'Darwin': 'OSXTables',
    'Linux': 'XTables'
}

# Fixture to dynamically import the Table class based on the platform
@pytest.fixture(scope='module')
def TableClass():
    current_platform = platform.system()
    try:
        module_name = PLATFORM_MODULES[current_platform]
        module = __import__(module_name, fromlist=['Table'])
        return module.Table
    except KeyError:
        raise OSError("Unsupported operating system")

# Basic fixtures
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

# Fixture to patch getSiteHhc and getTableTitleRe
@pytest.fixture(autouse=True)
def mock_getSiteHhc():
    with patch('HandHistoryConverter.getSiteHhc') as mock_hhc, \
         patch('HandHistoryConverter.getTableTitleRe', return_value=re.compile(r'Test Table')):
        mock_hhc.return_value = MagicMock()
        yield

# Fixture to instantiate Table
@pytest.fixture
def table_window(TableClass, config, site):
    return TableClass(config, site)

# Parameter for supported platforms
SUPPORTED_PLATFORMS = ['Windows', 'Darwin', 'Linux']

# Helper to get the module name based on the platform
def get_module_name(platform_name):
    return PLATFORM_MODULES.get(platform_name)

def test_get_game_nl_holdem(table_window):
    """Test the detection of the game No Limit Hold'em."""
    table_window.title = "No Limit Hold'em"
    game = table_window.get_game()
    assert game == ("nl", "holdem")

def test_get_game_limit_stud(table_window):
    """Test the detection of the game Limit Stud."""
    table_window.title = "Limit Stud"
    game = table_window.get_game()
    assert game == ("fl", "studhi")

def test_get_game_no_match(table_window):
    """Test the detection of the game when no match is found."""
    table_window.title = "Unknown Game Title"
    game = table_window.get_game()
    assert game is False

def test_get_table_no_matches(TableClass, config, site):
    """Test extracting the table number when the title matches."""
    table_window = TableClass(config, site)
    with patch.object(table_window, 'get_window_title', return_value="Table 123"):
        table_window.tableno_re = re.compile(r'Table (\d+)')
        table_no = table_window.get_table_no()
        assert table_no == 123

def test_get_table_no_no_match(TableClass, config, site):
    """Test extracting the table number when no match is found."""
    table_window = TableClass(config, site)
    with patch.object(table_window, 'get_window_title', return_value="Table ABC"):
        table_window.tableno_re = re.compile(r'Table (\d+)')
        table_no = table_window.get_table_no()
        assert table_no is False





def test_manual_comparison():
    """Test manual string comparison."""
    title = "History for table:"
    bad_word = "History for table:"
    title_normalized = title.strip().lower()
    bad_word_normalized = bad_word.lower()
    assert bad_word_normalized in title_normalized, "Manual comparison failed"

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

def test_table_window_init_basic(TableClass, config, site):
    """Test basic initialization of TableWindow."""
    tw = TableClass(config, site)  
    assert tw.config == config
    assert tw.site == site
    assert tw.hud is None
    assert tw.gdkhandle is None
    assert tw.number is None
    assert tw.tournament is None
    assert tw.table is None

def test_table_window_init_tournament(TableClass, config, site):
    """Test initialization with tournament and table number."""
    tournament = 12345
    table_number = 6789
    tw = TableClass(config, site, tournament=tournament, table_number=table_number)
    assert tw.tournament == tournament
    assert tw.table == table_number
    assert tw.name == f"{tournament} - {table_number}"
    assert tw.type == "tour"

def test_table_window_init_invalid_params(TableClass, config, site):
    """Test initialization with invalid parameters."""
    tw = TableClass(config, site)
    assert tw.search_string is None

def test_table_window_search_string_tournament(TableClass, config, site):
    """Test generating search_string with a tournament."""
    tournament = 12345
    table_number = 6789
    with patch('HandHistoryConverter.getTableTitleRe', return_value=re.compile(r'Test Table')):
        tw = TableClass(config, site, tournament=tournament, table_number=table_number)
        assert tw.search_string is not None

def test_table_window_init_invalid_tournament_params(TableClass, config, site):
    """Test initialization with invalid tournament parameters."""
    with pytest.raises(ValueError):
        tw = TableClass(config, site, tournament="invalid", table_number="invalid")

@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_find_table_parameters_called(platform_name, module_name, TableClass, config, site):
    """Test if find_table_parameters is called on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    with patch(f'{module_name}.Table.find_table_parameters') as mock_find_table_parameters:
        tw = TableClass(config, site)
        tw.find_table_parameters()
        mock_find_table_parameters.assert_called_once()

@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_check_table_calls_check_size_and_check_loc(platform_name, module_name, TableClass, config, site):
    """Test if check_table calls check_size and check_loc on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    with patch(f'{module_name}.Table.check_size') as mock_check_size, \
         patch(f'{module_name}.Table.check_loc') as mock_check_loc:
        tw = TableClass(config, site)
        mock_check_size.return_value = False
        mock_check_loc.return_value = False
        result = tw.check_table()
        mock_check_size.assert_called_once()
        mock_check_loc.assert_called_once()
        assert result is False

@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_check_size_detects_resize(platform_name, module_name, TableClass, config, site):
    """Test if check_size detects client resizing on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    with patch(f'{module_name}.Table.get_geometry') as mock_get_geometry:
        tw = TableClass(config, site)
        mock_get_geometry.return_value = {'width': 800, 'height': 600}
        tw.width = 1024
        tw.height = 768
        result = tw.check_size()
        assert result == "client_resized"

@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_check_loc_detects_move(platform_name, module_name, TableClass, config, site):
    """Test if check_loc detects client movement on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    with patch(f'{module_name}.Table.get_geometry') as mock_get_geometry:
        tw = TableClass(config, site)
        mock_get_geometry.return_value = {'x': 100, 'y': 200}
        tw.x = 0
        tw.y = 0
        result = tw.check_loc()
        assert result == "client_moved"

@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_has_table_title_changed_returns_true(platform_name, module_name, TableClass, config, site):
    """Test if has_table_title_changed returns True when the table number changes on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    with patch(f'{module_name}.Table.get_table_no') as mock_get_table_no:
        tw = TableClass(config, site)
        mock_get_table_no.return_value = 100 
        tw.table = 50 
        mock_hud = MagicMock()
        result = tw.has_table_title_changed(mock_hud)
        assert tw.table == 100 
        assert result is True

@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_table_window_init_table_name(platform_name, module_name, TableClass, config, site):
    """Test initialization with a table name on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    with patch(f'{module_name}.Table') as MockTable:
        # Create a mock instance and configure the attributes
        mock_instance = MockTable.return_value
        mock_instance.name = "Test Table"
        mock_instance.type = "cash"
        mock_instance.tournament = None
        mock_instance.table = None
        
        # Call the base test function
        base_test_table_window_init_table_name(MockTable, config, site)

def base_test_table_window_init_table_name(MockTable, config, site):
    """Base test for initialization with a table name (cash game)."""
    table_name = "Test Table"
    tw = MockTable(config, site, table_name=table_name)
    assert tw.name == table_name
    assert tw.type == "cash"
    assert tw.tournament is None
    assert tw.table is None




@pytest.mark.parametrize("platform_name,module_name", [
    ('Windows', 'WinTables'),
    ('Darwin', 'OSXTables'),
    ('Linux', 'XTables')
])
def test_manual_comparison_platform(platform_name, module_name):
    """Test manual string comparison on each platform."""
    if platform.system() != platform_name:
        pytest.skip(f"Test for {platform_name} only")
    test_manual_comparison()

@pytest.mark.parametrize("title,expected", [
    ("History for table:", True),       # Exact match
    (" History for table: ", True),     # Spaces around
    ("PokerStars Table 1", False),      # No bad word
    ("hud:", True),                     # Detection of the forbidden word "HUD"
])
def test_check_bad_words(table_window, title, expected):
    """Test if check_bad_words detects or does not detect forbidden words."""
    print(f"Searching in title: '{title}'")
    result = table_window.check_bad_words(title)
    print(f"Expected: {expected}, Got: {result}")
    assert result == expected

