#!/usr/bin/env python
"""Tests for Hud.py.

Test suite for the HUD management system.
"""

import contextlib
import os
import sys
import unittest
from unittest.mock import Mock, patch

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_hud_mocks(original_modules: dict) -> None:
    """Install mocks for fpdb_3_legacy sub-modules required by Hud.py."""
    modules_to_mock = [
        "fpdb_3_legacy.Database",
        "fpdb_3_legacy.Hand",
        "fpdb_3_legacy.loggingFpdb",
    ]
    for module_name in modules_to_mock:
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]
        mock_mod = Mock()
        # loggingFpdb.get_logger is called at module-import time; make it
        # return a proper Mock logger so the module-level `log = get_logger(…)`
        # succeeds and `log.warning / log.exception` are callable.
        if module_name == "fpdb_3_legacy.loggingFpdb":
            mock_mod.get_logger = Mock(return_value=Mock())
        sys.modules[module_name] = mock_mod


def _teardown_hud_mocks(original_modules: dict) -> None:
    """Remove mocks installed by _setup_hud_mocks."""
    modules_to_mock = [
        "fpdb_3_legacy.Database",
        "fpdb_3_legacy.Hand",
        "fpdb_3_legacy.loggingFpdb",
    ]
    for module_name in modules_to_mock:
        if module_name in original_modules:
            sys.modules[module_name] = original_modules[module_name]
        elif module_name in sys.modules:
            del sys.modules[module_name]


class TestImportName(unittest.TestCase):
    """Test the importName utility function."""

    @classmethod
    def setUpClass(cls):
        """Set up mocks for HUD tests."""
        cls._original_modules = {}
        _setup_hud_mocks(cls._original_modules)

        # Evict a previously-cached Hud module so the mocks take effect.
        sys.modules.pop("fpdb_3_legacy.Hud", None)

        # Import the module to test after mocks are set up
        global Hud, importName
        from fpdb_3_legacy.Hud import Hud, importName

    @classmethod
    def tearDownClass(cls):
        """Clean up mocks after HUD tests."""
        _teardown_hud_mocks(cls._original_modules)

    def test_import_valid_module(self) -> None:
        """Test importing a valid module and class."""
        # Import a real module for testing
        result = importName("sys", "version")
        assert result is not None
        assert result == sys.version

    def test_import_invalid_module(self) -> None:
        """Test importing an invalid module."""
        with patch("fpdb_3_legacy.Hud.log") as mock_log:
            result = importName("nonexistent_module", "some_class")
            assert result is None
            # Reported once, after both the bare and the package-qualified name fail.
            mock_log.error.assert_called_once()

    def test_import_invalid_attribute(self) -> None:
        """Test importing a valid module but invalid attribute."""
        result = importName("sys", "nonexistent_attribute")
        with contextlib.suppress(AttributeError):
            assert result is None


class TestHudInitialization(unittest.TestCase):
    """Test HUD initialization."""

    @classmethod
    def setUpClass(cls):
        """Ensure Hud is importable (mocks installed by TestImportName.setUpClass)."""
        global Hud, importName
        from fpdb_3_legacy.Hud import Hud, importName

    def setUp(self) -> None:
        """Set up test environment."""
        # Mock the parent object
        self.mock_parent = Mock()
        self.mock_parent.hud_params = {"test_param": "value"}

        # Mock the table object
        self.mock_table = Mock()
        self.mock_table.site = "PokerStars"

        # Mock the config object
        self.mock_config = Mock()
        self.mock_config.get_site_parameters.return_value = {"site_param": "value"}
        self.mock_config.get_supported_games_parameters.return_value = {
            "aux": "ClassicHud",
            "stat_set": "holdem_6max_pro",
        }
        mock_layout = Mock()
        mock_layout.location = {i: (100 + i * 10, 200 + i * 10) for i in range(1, 7)}  # Mock positions
        self.mock_config.get_layout.return_value = Mock()
        self.mock_config.get_layout.return_value.layout = {
            6: mock_layout,  # Mock layout for 6-max
        }
        self.mock_config.get_aux_parameters.return_value = Mock()
        self.mock_config.get_aux_parameters.return_value.__getitem__ = Mock(
            side_effect=lambda x: {"module": "Aux_Classic_Hud", "class": "Hud"}[x],
        )

    def test_hud_initialization_success(self) -> None:
        """Test successful HUD initialization."""
        with patch("fpdb_3_legacy.Hud.importName") as mock_import:
            mock_import.return_value = Mock()

            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            # Check basic attributes
            assert hud.parent == self.mock_parent
            assert hud.table == self.mock_table
            assert hud.config == self.mock_config
            assert hud.poker_game == "holdem"
            assert hud.game_type == "ring"
            assert hud.max == 6
            assert hud.site == "PokerStars"
            assert hud.is_loading is False

            # Check that hud_params is a copy, not reference
            assert hud.hud_params == self.mock_parent.hud_params
            assert hud.hud_params is not self.mock_parent.hud_params

            # Check that config methods were called
            self.mock_config.get_site_parameters.assert_called_once_with("PokerStars")
            self.mock_config.get_supported_games_parameters.assert_called_once_with("holdem", "ring")
            self.mock_config.get_layout.assert_called_once_with("PokerStars", "ring")

    def test_hud_initialization_applies_matching_table_profile_override(self) -> None:
        """A HUD restart keeps this table's profile without changing defaults."""
        default_stat_set = Mock(name="DefaultStatSet")
        override_stat_set = Mock(name="OverrideStatSet")
        self.mock_table.key = "table-42"
        self.mock_parent._table_stat_set_overrides = {
            "table-42": ("holdem", "ring", "OverrideStatSet"),
        }
        self.mock_parent.get_table_stat_set_override.return_value = "OverrideStatSet"
        self.mock_config.stat_sets = {"OverrideStatSet": override_stat_set}
        self.mock_config.get_supported_games_parameters.return_value = {
            "aux": "",
            "game_stat_set": default_stat_set,
        }

        hud = Hud(
            parent=self.mock_parent,
            table=self.mock_table,
            max_players=6,
            poker_game="holdem",
            game_type="ring",
            config=self.mock_config,
        )

        assert hud.supported_games_parameters["game_stat_set"] is override_stat_set
        self.mock_parent.get_table_stat_set_override.assert_called_once_with("table-42", "holdem", "ring")

    def test_hud_initialization_no_supported_games(self) -> None:
        """Test HUD initialization when no supported games config exists."""
        self.mock_config.get_supported_games_parameters.return_value = None

        with patch("fpdb_3_legacy.Hud.log") as mock_log:
            Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            mock_log.warning.assert_called_once()
            assert "No <game_stat_set> found" in mock_log.warning.call_args[0][0]

    def test_hud_initialization_no_layout(self) -> None:
        """Test HUD initialization when no layout exists."""
        self.mock_config.get_layout.return_value = None

        with patch("fpdb_3_legacy.Hud.log") as mock_log:
            Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            mock_log.warning.assert_called_once()
            assert "No layout found" in mock_log.warning.call_args[0][0]

    def test_hud_initialization_no_max_layout(self) -> None:
        """Test HUD initialization when no layout exists for max players."""
        self.mock_config.get_layout.return_value.layout = {9: Mock()}  # Only 9-max layout

        with patch("fpdb_3_legacy.Hud.log") as mock_log:
            Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,  # Requesting 6-max but only 9-max available
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            mock_log.warning.assert_called_once()
            # Check that the warning was called with the expected format string and arguments
            args, kwargs = mock_log.warning.call_args
            assert args[0] == "No layout found for %d-max %s games for site %s.\n"
            assert args[1] == 6  # max players
            assert args[2] == "ring"  # game type

    def test_aux_windows_initialization(self) -> None:
        """Test that aux windows are properly initialized."""
        with patch("fpdb_3_legacy.Hud.importName") as mock_import:
            mock_aux_class = Mock()
            mock_import.return_value = mock_aux_class
            mock_aux_instance = Mock()
            mock_aux_class.return_value = mock_aux_instance

            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            # Check that aux was imported and instantiated
            mock_import.assert_called_once_with("Aux_Classic_Hud", "Hud")
            mock_aux_class.assert_called_once_with(
                hud,
                self.mock_config,
                self.mock_config.get_aux_parameters.return_value,
            )
            assert mock_aux_instance in hud.aux_windows

    def test_multiple_aux_windows(self) -> None:
        """Test initialization with multiple aux windows."""
        self.mock_config.get_supported_games_parameters.return_value = {
            "aux": "ClassicHud, mucked",
            "stat_set": "holdem_6max_pro",
        }

        def mock_get_aux_params(aux_name):
            mock_result = Mock()
            if aux_name.strip() == "ClassicHud":
                mock_result.__getitem__ = Mock(side_effect=lambda x: {"module": "Aux_Classic_Hud", "class": "Hud"}[x])
            else:
                mock_result.__getitem__ = Mock(side_effect=lambda x: {"module": "Mucked", "class": "Mucked"}[x])
            return mock_result

        self.mock_config.get_aux_parameters.side_effect = mock_get_aux_params

        with patch("fpdb_3_legacy.Hud.importName") as mock_import:
            mock_import.side_effect = [Mock(), Mock()]

            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            # Should have imported and created 2 aux windows
            assert mock_import.call_count == 2
            assert len(hud.aux_windows) == 2

    def test_empty_aux_parameter(self) -> None:
        """Test initialization with empty aux parameter."""
        self.mock_config.get_supported_games_parameters.return_value = {
            "aux": [""],  # Empty aux list
            "stat_set": "holdem_6max_pro",
        }

        hud = Hud(
            parent=self.mock_parent,
            table=self.mock_table,
            max_players=6,
            poker_game="holdem",
            game_type="ring",
            config=self.mock_config,
        )

        # Should have no aux windows
        assert len(hud.aux_windows) == 0

    def test_failed_aux_import(self) -> None:
        """Test initialization when aux import fails."""
        with patch("fpdb_3_legacy.Hud.importName") as mock_import:
            mock_import.return_value = None  # Import failed

            hud = Hud(
                parent=self.mock_parent,
                table=self.mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=self.mock_config,
            )

            # Should handle failed import gracefully
            mock_import.assert_called_once()
            assert len(hud.aux_windows) == 0


class TestHudMethods(unittest.TestCase):
    """Test HUD methods."""

    @classmethod
    def setUpClass(cls):
        """Ensure Hud is importable (mocks installed by TestImportName.setUpClass)."""
        global Hud, importName
        from fpdb_3_legacy.Hud import Hud, importName

    def setUp(self) -> None:
        """Set up test HUD instance."""
        # Create a minimal HUD instance for testing
        self.mock_parent = Mock()
        self.mock_parent.hud_params = {}

        self.mock_table = Mock()
        self.mock_table.site = "PokerStars"
        self.mock_table.width = 1000
        self.mock_table.height = 750

        self.mock_config = Mock()
        self.mock_config.get_site_parameters.return_value = {}
        self.mock_config.get_supported_games_parameters.return_value = {"aux": "", "stat_set": "holdem_6max_pro"}
        self.mock_config.get_aux_parameters.return_value = Mock()
        self.mock_config.get_aux_parameters.return_value.__getitem__ = Mock(
            side_effect=lambda x: {"module": "TestAux", "class": "TestAux"}[x],
        )
        mock_layout = Mock()
        mock_layout.location = {i: (100 + i * 10, 200 + i * 10) for i in range(1, 7)}  # Mock positions
        mock_layout.width = 800
        mock_layout.height = 600
        mock_layout.common = (400, 300)
        self.mock_config.get_layout.return_value = Mock()
        self.mock_config.get_layout.return_value.layout = {6: mock_layout}

        # Create HUD instance
        self.hud = Hud(
            parent=self.mock_parent,
            table=self.mock_table,
            max_players=6,
            poker_game="holdem",
            game_type="ring",
            config=self.mock_config,
        )

        # Add mock aux windows for testing
        self.mock_aux1 = Mock()
        self.mock_aux2 = Mock()
        self.hud.aux_windows = [self.mock_aux1, self.mock_aux2]

    def test_move_table_position(self) -> None:
        """Test move_table_position method."""
        # Currently just a stub method, should not raise exception
        try:
            self.hud.move_table_position()
        except Exception as e:
            self.fail(f"move_table_position raised an exception: {e}")

    def test_kill_method(self) -> None:
        """Test kill method calls kill on all aux windows."""
        loading_window = Mock()
        self.hud.loading_window = loading_window

        self.hud.kill()

        # Check that kill was called on all aux windows
        self.mock_aux1.kill.assert_called_once()
        self.mock_aux2.kill.assert_called_once()
        loading_window.hide.assert_called_once_with()
        loading_window.close.assert_called_once_with()
        loading_window.deleteLater.assert_called_once_with()
        assert self.hud.loading_window is None

    def test_resize_windows(self) -> None:
        """Test resize_windows method."""
        self.hud.resize_windows()

        # Check that resize_windows was called on all aux windows
        self.mock_aux1.resize_windows.assert_called_once()
        self.mock_aux2.resize_windows.assert_called_once()

    def test_reposition_windows(self) -> None:
        """Test reposition_windows method."""
        self.hud.reposition_windows()

        # Check that reposition_windows was called on all aux windows
        self.mock_aux1.reposition_windows.assert_called_once()
        self.mock_aux2.reposition_windows.assert_called_once()

    def test_save_layout(self) -> None:
        """Test save_layout method."""
        mock_layout = Mock()
        self.hud.layout = mock_layout

        self.hud.save_layout()

        # Check that save_layout was called on all aux windows with layout
        self.mock_aux1.save_layout.assert_called_once_with(mock_layout)
        self.mock_aux2.save_layout.assert_called_once_with(mock_layout)

    def test_create_method(self) -> None:
        """Test create method."""
        hand_id = 12345
        stat_dict = {"player1": {"vpip": 25.0}}

        with patch.object(self.hud, "get_cards") as mock_get_cards:
            mock_get_cards.return_value = {"hand": "cards"}

            self.hud.create(hand_id, self.mock_config, stat_dict)

            # Check that get_cards was called
            mock_get_cards.assert_called_once_with(hand_id)

            # Window creation belongs to HUD_main.idle_create, which can isolate
            # failures per auxiliary. Hud.create only prepares the hand model.
            self.mock_aux1.create.assert_not_called()
            self.mock_aux2.create.assert_not_called()

            # Verify cards were set
            assert self.hud.cards == {"hand": "cards"}

    def test_update_method(self) -> None:
        """Test update method."""
        hand_id = 12345

        with patch.object(self.hud, "get_cards") as mock_get_cards:
            mock_get_cards.return_value = {"updated": "cards"}

            self.hud.update(hand_id, self.mock_config)

            # Check that get_cards was called
            mock_get_cards.assert_called_once_with(hand_id)

            # Check that update_gui was called on all aux windows
            self.mock_aux1.update_gui.assert_called_once_with(hand_id)
            self.mock_aux2.update_gui.assert_called_once_with(hand_id)

            # Verify cards were updated
            assert self.hud.cards == {"updated": "cards"}

    def test_update_rebuilds_the_hand_once(self) -> None:
        """One new hand is one rebuild, however many aux windows watch it.

        hand_factory reads the whole hand back out of the database; doing it
        per aux window, or twice per hand, is the cost this owns.
        """
        self.hud.db_hud_connection = Mock()

        with (
            patch.object(self.hud, "get_cards") as mock_get_cards,
            patch("fpdb_3_legacy.Hud.Hand.hand_factory") as mock_factory,
        ):
            self.hud.update(12345, self.mock_config)

        mock_factory.assert_called_once()
        mock_get_cards.assert_called_once_with(12345)

    def test_one_failing_aux_window_does_not_cost_the_others_their_update(self) -> None:
        """The isolation that makes this the only place aux windows refresh."""
        self.mock_aux1.update_gui.side_effect = RuntimeError("aux failed")

        with patch.object(self.hud, "get_cards"):
            self.hud.update(12345, self.mock_config)

        self.mock_aux1.update_gui.assert_called_once_with(12345)
        self.mock_aux2.update_gui.assert_called_once_with(12345)

    def test_a_failing_aux_window_is_named_in_the_log(self) -> None:
        # The caller used to report which window failed; that report belongs
        # here now, where the failure is caught.
        self.mock_aux1.update_gui.side_effect = RuntimeError("aux failed")

        with (
            patch.object(self.hud, "get_cards"),
            patch("fpdb_3_legacy.Hud.log") as mock_log,
        ):
            self.hud.update(12345, self.mock_config)

        assert mock_log.exception.called
        assert "%s" in mock_log.exception.call_args[0][0]

    def test_get_cards_with_database(self) -> None:
        """Test get_cards method with database connection."""
        hand_id = 12345

        # Mock database connection
        mock_db = Mock()
        mock_db.get_cards.return_value = {"hole": ["Ah", "Kh"]}
        mock_db.get_common_cards.return_value = {"common": ["Qh", "Jh", "Th"]}
        self.hud.db_hud_connection = mock_db

        result = self.hud.get_cards(hand_id)

        # Check that database methods were called
        mock_db.get_cards.assert_called_once_with(hand_id)
        mock_db.get_common_cards.assert_called_once_with(hand_id)
        assert result == {"hole": ["Ah", "Kh"], "common": ["Qh", "Jh", "Th"]}

    def test_get_cards_without_database(self) -> None:
        """Test get_cards method without database connection."""
        hand_id = 12345

        # No database connection
        self.hud.db_hud_connection = None

        result = self.hud.get_cards(hand_id)

        # Should return empty dict when no database
        assert result == {}

    def test_get_cards_database_exception(self) -> None:
        """Test get_cards method when database raises exception."""
        hand_id = 12345

        # Mock database that raises exception
        mock_db = Mock()
        mock_db.get_cards.side_effect = Exception("Database error")
        self.hud.db_hud_connection = mock_db

        with patch("fpdb_3_legacy.Hud.log") as mock_log:
            result = self.hud.get_cards(hand_id)

            # Should return empty dict and log error
            assert result == {}
            mock_log.exception.assert_called_once()


class TestHudIntegration(unittest.TestCase):
    """Test HUD integration scenarios."""

    @classmethod
    def setUpClass(cls):
        """Ensure Hud is importable (mocks installed by TestImportName.setUpClass)."""
        global Hud, importName
        from fpdb_3_legacy.Hud import Hud, importName

    def test_full_hud_lifecycle(self) -> None:
        """Test complete HUD lifecycle from creation to destruction."""
        # Setup
        mock_parent = Mock()
        mock_parent.hud_params = {"param1": "value1"}

        mock_table = Mock()
        mock_table.site = "PokerStars"
        mock_table.width = 1000
        mock_table.height = 750

        mock_config = Mock()
        mock_config.get_site_parameters.return_value = {"site_setting": "value"}
        mock_config.get_supported_games_parameters.return_value = {"aux": "ClassicHud", "stat_set": "holdem_6max_pro"}
        mock_layout_item = Mock()
        mock_layout_item.location = {i: (100 + i * 10, 200 + i * 10) for i in range(1, 7)}  # Mock positions
        mock_layout_item.width = 800
        mock_layout_item.height = 600
        mock_layout_item.common = (400, 300)
        mock_layout = Mock()
        mock_layout.layout = {6: mock_layout_item}
        mock_config.get_layout.return_value = mock_layout
        mock_config.get_aux_parameters.return_value = {"module": "Aux_Classic_Hud", "class": "Hud"}

        with patch("fpdb_3_legacy.Hud.importName") as mock_import:
            mock_aux_class = Mock()
            mock_aux_instance = Mock()
            mock_aux_class.return_value = mock_aux_instance
            mock_import.return_value = mock_aux_class

            # 1. Create HUD
            hud = Hud(
                parent=mock_parent,
                table=mock_table,
                max_players=6,
                poker_game="holdem",
                game_type="ring",
                config=mock_config,
            )

            # Verify initialization
            assert len(hud.aux_windows) == 1
            assert mock_aux_instance in hud.aux_windows

            # 2. Prepare/update cycle. HUD_main owns native window creation so
            # it can isolate failures and guarantee exactly one create call.
            hand_id = 12345
            stat_dict = {"player1": {"vpip": 25.0}}

            with patch.object(hud, "get_cards") as mock_get_cards:
                mock_get_cards.return_value = {"cards": "data"}

                hud.create(hand_id, mock_config, stat_dict)
                mock_aux_instance.create.assert_not_called()

                hud.update(hand_id, mock_config)
                mock_aux_instance.update_gui.assert_called_once_with(hand_id)

            # 3. Layout operations
            hud.resize_windows()
            mock_aux_instance.resize_windows.assert_called_once()

            hud.reposition_windows()
            mock_aux_instance.reposition_windows.assert_called_once()

            hud.save_layout()
            mock_aux_instance.save_layout.assert_called_once()

            # 4. Cleanup
            hud.kill()
            mock_aux_instance.kill.assert_called_once()


class TestHudErrorHandling(unittest.TestCase):
    """Test HUD error handling scenarios."""

    @classmethod
    def setUpClass(cls):
        """Ensure Hud is importable (mocks installed by TestImportName.setUpClass)."""
        global Hud, importName
        from fpdb_3_legacy.Hud import Hud, importName

    def test_aux_method_exceptions(self) -> None:
        """Test that HUD handles exceptions in aux window methods gracefully."""
        # Setup HUD with mock aux that raises exceptions
        mock_parent = Mock()
        mock_parent.hud_params = {}

        mock_table = Mock()
        mock_table.site = "PokerStars"
        mock_table.width = 1000
        mock_table.height = 750

        mock_config = Mock()
        mock_config.get_site_parameters.return_value = {}
        mock_config.get_supported_games_parameters.return_value = {"aux": "", "stat_set": "test"}
        mock_config.get_aux_parameters.return_value = Mock()
        mock_config.get_aux_parameters.return_value.__getitem__ = Mock(
            side_effect=lambda x: {"module": "TestAux", "class": "TestAux"}[x],
        )
        mock_layout = Mock()
        mock_layout.location = {i: (100 + i * 10, 200 + i * 10) for i in range(1, 7)}  # Mock positions
        mock_layout.width = 800
        mock_layout.height = 600
        mock_layout.common = (400, 300)
        mock_config.get_layout.return_value = Mock()
        mock_config.get_layout.return_value.layout = {6: mock_layout}

        hud = Hud(
            parent=mock_parent,
            table=mock_table,
            max_players=6,
            poker_game="holdem",
            game_type="ring",
            config=mock_config,
        )

        # Add mock aux that raises exceptions
        mock_aux = Mock()
        mock_aux.kill.side_effect = Exception("Kill failed")
        mock_aux.resize_windows.side_effect = Exception("Resize failed")
        mock_aux.update.side_effect = Exception("Update failed")
        hud.aux_windows = [mock_aux]

        # Test that methods don't crash when aux methods fail
        with patch("fpdb_3_legacy.Hud.log"):
            # These should not raise exceptions
            try:
                hud.kill()
                hud.resize_windows()
                hud.update(12345, mock_config)
            except Exception as e:
                self.fail(f"HUD method should handle aux exceptions gracefully: {e}")


class TestMuckedCards(unittest.TestCase):
    """Test Mucked cards scaling and properties."""

    def test_mucked_cards_scaling(self) -> None:
        """Test that Flop_Mucked scales card width and height correctly."""
        from fpdb_3_legacy.Mucked import Flop_Mucked

        mock_parent = Mock()
        # Mock card dimensions in parent
        mock_parent.hud_params = {
            "card_ht": "78",
            "card_wd": "56",
            "mucked_cards_size": "70"  # 70% scale
        }

        mock_hud = Mock()
        mock_hud.parent = mock_parent
        mock_hud.table.x = 10
        mock_hud.table.y = 20

        mock_config = Mock()
        mock_config.get_layout.return_value = Mock()

        # Instantiate Flop_Mucked with parameters
        params = {"opacity": "0.7"}

        mucked = Flop_Mucked(mock_hud, mock_config, params)

        # Scale should be 0.7
        assert mucked.card_scale == 0.7

        # Dimensions should be 70% of 78 and 56
        assert mucked.card_width == int(56 * 0.7)  # 39
        assert mucked.card_height == int(78 * 0.7)  # 54

    def test_mucked_cards_positioned_under_hud(self) -> None:
        """Test that Flop_Mucked positions card container below the anchor HUD window."""
        from PySide6.QtCore import QRect
        from fpdb_3_legacy.Mucked import Flop_Mucked

        mock_parent = Mock()
        mock_parent.hud_params = {"card_ht": "50", "card_wd": "30"}
        mock_hud = Mock()
        mock_hud.parent = mock_parent
        mock_config = Mock()

        mucked = Flop_Mucked(mock_hud, mock_config, {})

        anchor_window = Mock()
        anchor_window.windowTitle.return_value = "HUD - stats"
        anchor_window.frameGeometry.return_value = QRect(100, 200, 150, 80)
        anchor_window.screen.return_value = None

        stat_aux = Mock()
        stat_aux.uses_timer = False
        stat_aux.m_windows = {1: anchor_window}

        mucked.hud.aux_windows = [mucked, stat_aux]

        hint = Mock()
        hint.width.return_value = 60
        hint.height.return_value = 40
        container = Mock()
        container.width.return_value = 60
        container.height.return_value = 40
        container.sizeHint.return_value = hint
        container.screen.return_value = None

        mucked._move_next_to_hud(container, 1)

        # Left = 100, Bottom = 200 + 80 - 1 = 279, Margin = 6 -> y = 285
        container.move.assert_called_once_with(100, 285)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestResizeWindowsRefLayout(unittest.TestCase):
    """resize_windows must not crash when Aux_Hud._ensure_reference has already
    frozen ref_layout_width/height (but not locations/common)."""

    def test_resize_windows_freezes_missing_ref_fields(self) -> None:
        import types

        from fpdb_3_legacy.Hud import Hud as HudClass

        h = HudClass.__new__(HudClass)
        h.max = 3
        h.layout = types.SimpleNamespace(
            width=792, height=546,
            location=[None, (681, 221), (2, 221), (162, 413)], common=(323, 232),
        )
        h.table = types.SimpleNamespace(width=1360, height=880)
        h.aux_windows = []
        # Only width/height pre-set (as _ensure_reference does); no locations.
        h.ref_layout_width = 792
        h.ref_layout_height = 546

        h.resize_windows()  # must not raise AttributeError

        self.assertTrue(hasattr(h, "ref_layout_locations"))
        self.assertEqual(h.layout.location[1], (1169, 356))  # (681,221) * 1360/792
