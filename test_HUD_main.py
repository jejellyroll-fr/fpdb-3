import pytest
from unittest.mock import MagicMock, patch
from PyQt5.QtWidgets import QApplication
import sys
import types

# Adjust sys.path to include the directory where HUD_main.pyw is located
sys.path.insert(0, 'C:/Users/jd/Documents/GitHub/fpdb-3')

# Create a mock 'WinTables' module
win_tables_module = types.ModuleType('WinTables')
win_tables_module.Table = MagicMock()

with patch.dict('sys.modules', {'WinTables': win_tables_module}):
    import HUD_main

@pytest.fixture
def app(qtbot):
    return QApplication.instance()

@pytest.fixture
def hud_main(app, qtbot):
    # Crate mock 
    options = MagicMock()
    options.dbname = 'test_db'
    options.config = None
    options.errorsToConsole = False
    options.xloc = None
    options.yloc = None

    import tempfile

    with patch('HUD_main.Configuration.Config') as mock_config, \
         patch('HUD_main.Configuration.set_logfile'), \
         patch('HUD_main.Database.Database'), \
         patch('HUD_main.ZMQReceiver'), \
         patch('sys.exit'), \
         patch('PyQt5.QtCore.QCoreApplication.quit'):

        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance

        mock_config_instance.dir_log = tempfile.gettempdir()
        mock_config_instance.os_family = 'Win7'  
        mock_config_instance.get_hud_ui_parameters.return_value = {
            'deck_type': 'default',
            'card_back': 'blue',
            'card_wd': 72,
            'card_ht': 96,
            'hud_days': 30,
            'h_hud_days': 90,
           
        }
        mock_config_instance.graphics_path = tempfile.gettempdir() 
        mock_config_instance.hhcs = {'test_site': MagicMock(converter='some_converter')}
        mock_config_instance.get_site_parameters.return_value = {
            'layout_set': 'some_layout',
            'param1': 'value1',
           
        }
        mock_config_instance.get_layout.return_value = 'some_layout'

        hm = HUD_main.HUD_main(options, db_name=options.dbname)
        qtbot.addWidget(hm.main_window)
        yield hm

        qtbot.waitExposed(hm.main_window)
        hm.main_window.close()






# Test pour vérifier que l'initialisation de HUD_main crée correctement tous les attributs nécessaires
def test_hud_main_initialization(hud_main):
    assert hud_main.db_name == 'test_db'
    assert hasattr(hud_main, 'config')
    assert hasattr(hud_main, 'db_connection')
    assert hasattr(hud_main, 'hud_dict')
    assert hasattr(hud_main, 'blacklist')
    assert hasattr(hud_main, 'hud_params')
    assert hasattr(hud_main, 'deck')
    assert hasattr(hud_main, 'cache')
    assert hasattr(hud_main, 'zmq_receiver')
    assert hasattr(hud_main, 'zmq_worker')
    assert hasattr(hud_main, 'main_window')

# Test pour vérifier que la méthode handle_message appelle correctement read_stdin
def test_handle_message(hud_main):
    with patch.object(hud_main, 'read_stdin') as mock_read_stdin:
        hud_main.handle_message('test_hand_id')
        mock_read_stdin.assert_called_once_with('test_hand_id')

# Test pour vérifier que la méthode destroy ferme correctement les connexions et arrête les processus
def test_destroy(hud_main):
    with patch.object(hud_main.zmq_receiver, 'close') as mock_close, \
         patch.object(hud_main.zmq_worker, 'stop') as mock_stop, \
         patch('PyQt5.QtCore.QCoreApplication.quit') as mock_quit:
        hud_main.destroy()
        mock_close.assert_called_once()
        mock_stop.assert_called_once()
        mock_quit.assert_called_once()

# Test pour vérifier que check_tables appelle les bonnes méthodes en fonction du statut de la table
@pytest.mark.parametrize("status, expected_method", [
    ("client_destroyed", "client_destroyed"),
    ("client_moved", "client_moved"),
    ("client_resized", "client_resized"),
])
def test_check_tables(hud_main, status, expected_method):
    mock_hud = MagicMock()
    mock_hud.table.check_table.return_value = status
    hud_main.hud_dict = {'test_table': mock_hud}
    
    with patch.object(hud_main, expected_method) as mock_method:
        hud_main.check_tables()
        mock_method.assert_called_once_with(None, mock_hud)

# Test pour vérifier que create_HUD crée correctement un nouveau HUD et l'ajoute au dictionnaire
def test_create_hud(hud_main):
    with patch.object(HUD_main.Hud, 'Hud') as mock_hud, \
         patch.object(hud_main, 'idle_create') as mock_idle_create, \
         patch.object(hud_main.config, 'get_site_parameters', return_value={'layout_set': 'some_layout', 'param1': 'value1'}), \
         patch.object(hud_main.config, 'get_layout', return_value='some_layout'):

        mock_table = MagicMock()
        mock_table.site = 'test_site'  
        hud_main.create_HUD('new_hand_id', mock_table, 'temp_key', 9, 'poker_game', 'cash', {}, {})

        assert 'temp_key' in hud_main.hud_dict
        mock_hud.assert_called_once()
        mock_idle_create.assert_called_once()




# Test pour vérifier que update_HUD appelle correctement idle_update
def test_update_hud(hud_main):
    with patch.object(hud_main, 'idle_update') as mock_idle_update:
        hud_main.update_HUD('new_hand_id', 'table_name', hud_main.config)
        mock_idle_update.assert_called_once_with('new_hand_id', 'table_name', hud_main.config)

# Test pour vérifier que read_stdin traite correctement les données en cache et appelle update_HUD
def test_read_stdin_cached(hud_main):
    # Configuration env
    hud_main.config = MagicMock()
    hud_main.config.get_supported_sites.return_value = ['test_site']
    hud_main.config.supported_sites = {'test_site': MagicMock(screen_name='test_hero')}
    test_hand_id = 'test_hand_id'
    hud_main.cache[test_hand_id] = (
        'table_name', 9, 'poker_game', 'cash', False, 1, 'test_site', 9, 'tour_number', 'tab_number'
    )
    temp_key = 'table_name'
    hud_main.hud_dict[temp_key] = MagicMock()
    hud_main.hud_dict[temp_key].hud_params = {'hud_days': 30, 'h_hud_days': 90}
    hud_main.hud_dict[temp_key].poker_game = 'poker_game'
    hud_main.hud_dict[temp_key].max = 9
    hud_main.hud_dict[temp_key].aux_windows = []

    with patch.object(hud_main.db_connection, 'get_site_id', return_value=[(1,)]), \
         patch.object(hud_main.db_connection, 'get_player_id', return_value=123), \
         patch.object(hud_main.db_connection, 'init_hud_stat_vars'), \
         patch.object(hud_main.db_connection, 'get_stats_from_hand', return_value={'player1': {'screen_name': 'test_hero'}}), \
         patch.object(hud_main, 'get_cards', return_value={}), \
         patch.object(hud_main, 'update_HUD') as mock_update_hud:
        hud_main.read_stdin(test_hand_id)
        assert mock_update_hud.called, "update_HUD n'a pas été appelé"


# Nouveau test pour vérifier le cas où les données ne sont pas en cache
def test_read_stdin_not_cached(hud_main):

    hud_main.config = MagicMock()
    hud_main.config.get_supported_sites.return_value = ['test_site']
    hud_main.config.supported_sites = {'test_site': MagicMock(screen_name='test_hero')}
    hud_main.config.get_site_parameters.return_value = {'aux_enabled': True}
    

    hud_main.Tables = MagicMock()
    hud_main.Tables.Table.return_value = MagicMock()
    test_hand_id = 'test_hand_id'


    hud_main.cache = {}


    table_info = (
        'table_name', 9, 'poker_game', 'tour', False, 1, 'test_site', 9, 123456, 'Table 789'
    )

    with patch.object(hud_main.db_connection, 'get_site_id', return_value=[(1,)]), \
         patch.object(hud_main.db_connection, 'get_player_id', return_value=123), \
         patch.object(hud_main.db_connection, 'get_table_info', return_value=table_info), \
         patch.object(hud_main.db_connection, 'init_hud_stat_vars'), \
         patch.object(hud_main.db_connection, 'get_stats_from_hand', return_value={'player1': {'screen_name': 'test_hero'}}), \
         patch.object(hud_main, 'get_cards', return_value={}), \
         patch.object(hud_main.Tables, 'Table', return_value=MagicMock()) as mock_table, \
         patch.object(hud_main, 'create_HUD') as mock_create_hud:

        hud_main.read_stdin(test_hand_id)
        assert mock_create_hud.called, "create_HUD n'a pas été appelé"







# Test pour vérifier que get_cards récupère correctement les cartes du joueur et les cartes communes
def test_get_cards(hud_main):
    mock_db = MagicMock()
    mock_db.get_cards.return_value = {'player1': ['As', 'Kh']}
    mock_db.get_common_cards.return_value = {'common': ['Jd', 'Qc', 'Tc']}
    hud_main.db_connection = mock_db

    cards = hud_main.get_cards('test_hand_id', 'holdem')
    assert 'player1' in cards
    assert 'common' in cards

# Test pour vérifier que idle_kill supprime correctement un HUD du dictionnaire et nettoie les widgets associés
def test_idle_kill(hud_main):
    mock_hud = MagicMock()
    hud_main.hud_dict['test_table'] = mock_hud
    hud_main.vb = MagicMock()
    
    hud_main.idle_kill('test_table')
    
    assert 'test_table' not in hud_main.hud_dict
    mock_hud.kill.assert_called_once()
    hud_main.vb.removeWidget.assert_called_once()

# Test pour vérifier la gestion des exceptions avec side_effect
def test_read_stdin_exception_handling(hud_main):

    hud_main.config = MagicMock()
    hud_main.config.get_supported_sites.return_value = ['test_site']
    hud_main.config.get_site_parameters.return_value = {'aux_enabled': True}
    hud_main.hero = {}
    hud_main.hero_ids = {}


    hud_main.cache = {}


    test_hand_id = 'test_hand_id'

    with patch.object(hud_main.db_connection, 'get_table_info', side_effect=Exception("Database error")), \
         patch.object(hud_main, 'destroy') as mock_destroy:

        hud_main.read_stdin(test_hand_id)


    mock_destroy.assert_not_called()

###TEST Class ZMQReceiver


###TEST Class ZMQWorker

def test_zmqworker_stop():
    zmq_receiver = MagicMock()
    worker = HUD_main.ZMQWorker(zmq_receiver)
    worker.wait = MagicMock()
    worker.is_running = True

    worker.stop()
    assert not worker.is_running
    worker.wait.assert_called_once()

### Test Methods table_title_changed and table_is_stale
def test_table_title_changed_calls_kill_hud(hud_main):
    mock_hud = MagicMock()
    mock_hud.table.key = 'test_table'
    hud_main.hud_dict['test_table'] = mock_hud

    with patch.object(hud_main, 'kill_hud') as mock_kill_hud:
        hud_main.table_title_changed(None, mock_hud)
        mock_kill_hud.assert_called_once_with(None, 'test_table')

def test_table_is_stale_calls_kill_hud(hud_main):
    mock_hud = MagicMock()
    mock_hud.table.key = 'test_table'
    hud_main.hud_dict['test_table'] = mock_hud

    with patch.object(hud_main, 'kill_hud') as mock_kill_hud:
        hud_main.table_is_stale(mock_hud)
        mock_kill_hud.assert_called_once_with(None, 'test_table')


### Test Methods blacklist_hud


### Test Methods close_event_handler

