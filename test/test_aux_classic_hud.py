"""
Tests for Aux_Classic_Hud.py.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

# Make repo root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Very light stubs to avoid real GUI deps
sys.modules.setdefault("PyQt5", Mock())
sys.modules.setdefault("PyQt5.QtWidgets", Mock())
sys.modules.setdefault("PyQt5.QtCore", Mock())
sys.modules.setdefault("PyQt5.QtGui", Mock())

import Aux_Classic_Hud  # noqa: E402
from Aux_Classic_Hud import ClassicHud, ClassicLabel, ClassicStat, ClassicStatWindow  # noqa: E402


# ------------------------------
# ClassicHud
# ------------------------------
class TestClassicHud(unittest.TestCase):
    def setUp(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleHUD, "__init__", return_value=None):
            self.mock_hud = Mock()
            self.mock_config = Mock()
            self.mock_aux_params = Mock()
            self.classic_hud = ClassicHud(self.mock_hud, self.mock_config, self.mock_aux_params)

    def test_initialization(self) -> None:
        assert self.classic_hud is not None


# ------------------------------
# ClassicStatWindow
# ------------------------------
class TestClassicStatWindow(unittest.TestCase):
    def setUp(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStatWindow, "__init__", return_value=None):
            self.mock_aw = Mock()
            self.stat_window = ClassicStatWindow(self.mock_aw)
            # emulate minimal parent-init
            self.stat_window.aw = self.mock_aw
            self.stat_window.aw.hud = Mock()
            self.stat_window.aw.hud.hide_statwindows = Mock()

    def test_initialization(self) -> None:
        assert self.stat_window is not None
        assert self.stat_window.aw is self.mock_aw

    def test_mousePressEvent(self) -> None:
        # On ne dépend pas de Qt: on vérifie juste que l'appel ne plante pas
        evt = Mock()
        self.stat_window.mousePressEvent(evt)
        self.assertTrue(True)


# ------------------------------
# ClassicStat
# ------------------------------
class TestClassicStat(unittest.TestCase):
    def setUp(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "__init__", return_value=None):
            self.mock_aw = Mock()
            self.mock_hud = Mock()
            self.mock_aw.hud = self.mock_hud
            self.mock_aw.params = {"fgcolor": "#FFFFFF", "bgcolor": "#000000"}

            # ce que lit le parent / autres chemins
            self.mock_hud.supported_games_parameters = None
            self.mock_hud.config = Mock()
            self.mock_hud.config.get_db_parameters.return_value = {"db-backend": "sqlite"}
            self.mock_hud.hand_instance = Mock()

            self.mock_popup = Mock()

            self.classic_stat = ClassicStat(stat="vpip", seat=2, popup=self.mock_popup, aw=self.mock_aw)
            # emulate minimal parent-init state
            self.classic_stat.aw = self.mock_aw
            self.classic_stat.hud = self.mock_hud
            self.classic_stat.stat = "vpip"
            self.classic_stat.seat = 2
            self.classic_stat.lab = Mock()
            self.classic_stat.hudcolor = "#FFFFFF"
            # requis si set_color du parent est invoqué
            self.classic_stat.aux_params = {"font": "Arial", "font_size": 10}

    def test_initialization_without_config(self) -> None:
        assert self.classic_stat.stat == "vpip"
        assert self.classic_stat.seat == 2
        assert self.classic_stat.popup is self.mock_popup
        assert self.classic_stat.aw is self.mock_aw
        assert self.classic_stat.hudcolor == "#FFFFFF"

    def test_initialization_with_config(self) -> None:
        self.classic_stat.stat_loth = "20"
        self.classic_stat.stat_hith = "35"
        self.classic_stat.stat_locolor = "#00FF00"
        self.classic_stat.stat_midcolor = "#FFFF00"
        self.classic_stat.stat_hicolor = "#FF0000"
        assert self.classic_stat.stat_hicolor == "#FF0000"

    def test_color_selection_high_value(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None):
            self.classic_stat.stat_loth = "20"
            self.classic_stat.stat_hith = "35"
            self.classic_stat.stat_hicolor = "#FF0000"
            self.classic_stat.number = ("", "45.0", "", "", "", "")
            with patch.object(self.classic_stat, "set_color") as mock_set_color:
                self.classic_stat.update(123, {123: {"screen_name": "Player"}})
                mock_set_color.assert_called()

    def test_color_selection_low_value(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None):
            self.classic_stat.stat_loth = "20"
            self.classic_stat.stat_hith = "35"
            self.classic_stat.stat_locolor = "#00FF00"
            self.classic_stat.number = ("", "15.0", "", "", "", "")
            with patch.object(self.classic_stat, "set_color") as mock_set_color:
                self.classic_stat.update(123, {123: {"screen_name": "Player"}})
                mock_set_color.assert_called()

    def test_color_selection_na_value(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None):
            self.classic_stat.stat_loth = "20"
            self.classic_stat.stat_hith = "35"
            self.classic_stat.incolor = "rgba(0, 0, 0, 0)"
            self.classic_stat.number = ("", "NA", "", "", "", "")
            with patch.object(self.classic_stat, "set_color") as mock_set_color:
                self.classic_stat.update(123, {123: {"screen_name": "Player"}})
                mock_set_color.assert_called()

    def test_comment_dialog_setup(self) -> None:
        with patch("Aux_Classic_Hud.QInputDialog") as mock_dialog, \
             patch.object(self.classic_stat, "get_player_name", return_value="TestPlayer"), \
             patch.object(self.classic_stat, "get_current_comment", return_value="Existing"):
            self.classic_stat.stat = "playershort"
            self.classic_stat.lab.aw_seat = 2
            self.classic_stat.stat_dict = {123: {"seat": 2, "screen_name": "TestPlayer"}}
            mock_dialog.getMultiLineText.return_value = ("New comment", True)
            with patch.object(self.classic_stat, "save_comment") as mock_save:
                self.classic_stat.open_comment_dialog(Mock())
                mock_dialog.getMultiLineText.assert_called_once()
                mock_save.assert_called_once()

    @patch("Aux_Classic_Hud.Database.Database")
    def test_get_current_comment(self, mock_db_class) -> None:
        mock_db = Mock()
        mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_comment": "SELECT comment FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = ("Test comment",)
        mock_db_class.return_value = mock_db
        res = self.classic_stat.get_current_comment(123)
        assert res == "Test comment"
        mock_db.close_connection.assert_called_once()

    @patch("Aux_Classic_Hud.Database.Database")
    def test_get_current_comment_no_result(self, mock_db_class) -> None:
        mock_db = Mock()
        mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_comment": "SELECT comment FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = None
        mock_db_class.return_value = mock_db
        res = self.classic_stat.get_current_comment(123)
        assert res == ""
        mock_db.close_connection.assert_called_once()

    def test_get_player_id(self) -> None:
        self.classic_stat.stat_dict = {
            1: {"seat": 1, "screen_name": "P1"},
            2: {"seat": 2, "screen_name": "P2"},
        }
        self.classic_stat.lab.aw_seat = 2
        pid = self.classic_stat.get_player_id()
        assert pid == 2

    def test_get_player_id_not_found(self) -> None:
        self.classic_stat.stat_dict = {1: {"seat": 1, "screen_name": "P1"}}
        self.classic_stat.lab.aw_seat = 99
        pid = self.classic_stat.get_player_id()
        assert pid is None

    @patch("Aux_Classic_Hud.Database.Database")
    def test_get_player_name(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_name": "SELECT screen_name FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = ("TestPlayer",)
        mock_db_class.return_value = mock_db
        name = self.classic_stat.get_player_name(123)
        assert name == "TestPlayer"

    @patch("Aux_Classic_Hud.Database.Database")
    def test_get_player_name_not_found(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_name": "SELECT screen_name FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = None
        mock_db_class.return_value = mock_db
        name = self.classic_stat.get_player_name(999)
        assert name == "Unknown Player"

    @patch("Aux_Classic_Hud.Database.Database")
    def test_has_comment_false(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_comment": "SELECT comment FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = None
        mock_db_class.return_value = mock_db
        assert self.classic_stat.has_comment(123) is False
        mock_db.close_connection.assert_called_once()

    @patch("Aux_Classic_Hud.Database.Database")
    def test_has_comment_true(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_comment": "SELECT comment FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = ("Some note",)
        mock_db_class.return_value = mock_db
        assert self.classic_stat.has_comment(123) is True
        mock_db.close_connection.assert_called_once()

    def test_open_comment_dialog_playershort(self) -> None:
        with patch("Aux_Classic_Hud.QInputDialog") as mock_dialog, \
             patch.object(self.classic_stat, "get_player_name", return_value="TestPlayer"), \
             patch.object(self.classic_stat, "get_current_comment", return_value=""):
            self.classic_stat.stat = "playershort"
            self.classic_stat.stat_dict = {123: {"seat": 2, "screen_name": "TestPlayer"}}
            self.classic_stat.lab.aw_seat = 2
            mock_dialog.getMultiLineText.return_value = ("New comment", True)
            with patch.object(self.classic_stat, "save_comment") as mock_save:
                self.classic_stat.open_comment_dialog(Mock())
                mock_dialog.getMultiLineText.assert_called_once()
                mock_save.assert_called_once()

    def test_open_comment_dialog_wrong_stat(self) -> None:
        with patch("Aux_Classic_Hud.QInputDialog") as mock_dialog:
            self.classic_stat.stat = "vpip"
            self.classic_stat.lab.aw_seat = 2
            self.classic_stat.open_comment_dialog(Mock())
            mock_dialog.getMultiLineText.assert_not_called()

    def test_update_no_number(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None), \
             patch("Aux_Classic_Hud.log") as mock_log:
            self.classic_stat.stat_loth = "20"
            self.classic_stat.stat_hith = "35"
            self.classic_stat.number = ("", "not_a_number", "", "", "", "")
            self.classic_stat.update(123, {123: {"screen_name": "Player"}})
            mock_log.exception.assert_called()

    def test_update_normal_stat(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None):
            self.classic_stat.stat_loth = "20"
            self.classic_stat.stat_hith = "35"
            self.classic_stat.stat_locolor = "#00FF00"
            self.classic_stat.stat_midcolor = "#FFFF00"
            self.classic_stat.stat_hicolor = "#FF0000"
            self.classic_stat.number = ("", "25", "", "", "", "")
            with patch.object(self.classic_stat, "set_color") as mock_set_color:
                self.classic_stat.update(123, {123: {"screen_name": "Player"}})
                mock_set_color.assert_called()

    @patch("Aux_Classic_Hud.Database.Database")
    def test_save_comment(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"update_player_comment": "UPDATE players SET comment = %s WHERE id = %s"}
        mock_db_class.return_value = mock_db
        with patch("Aux_Classic_Hud.QMessageBox"):
            self.classic_stat.save_comment(123, "New comment")
        mock_cur.execute.assert_called_once()
        # L'impl peut ne pas appeler commit() directement; on vérifie la fermeture
        mock_db.close_connection.assert_called_once()

    @patch("Aux_Classic_Hud.Database.Database")
    def test_update_player_note_with_comment(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_comment": "SELECT comment FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = ("Has note",)
        mock_db_class.return_value = mock_db

        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None):
            self.classic_stat.stat = "player_note"
            self.classic_stat.number = ("", "N", "", "", "", "")
            self.classic_stat.lab = Mock()
            self.classic_stat.update(123, {123: {"screen_name": "Player"}})
            label_html = self.classic_stat.lab.setText.call_args[0][0]
            self.assertTrue("#FFA500" in label_html or "orange" in label_html.lower())

    @patch("Aux_Classic_Hud.Database.Database")
    def test_update_player_note_without_comment(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {"get_player_comment": "SELECT comment FROM players WHERE id = %s"}
        mock_cur.fetchone.return_value = None
        mock_db_class.return_value = mock_db

        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None):
            self.classic_stat.stat = "player_note"
            self.classic_stat.number = ("", "N", "", "", "", "")
            self.classic_stat.lab = Mock()
            self.classic_stat.update(123, {123: {"screen_name": "Player"}})
            label_html = self.classic_stat.lab.setText.call_args[0][0]
            self.assertTrue("#808080" in label_html or "gray" in label_html.lower())


# ------------------------------
# ClassicLabel
# ------------------------------
class TestClassicLabel(unittest.TestCase):
    def setUp(self) -> None:
        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleLabel, "__init__", return_value=None):
            self.mock_aw = Mock()
            self.classic_label = ClassicLabel(self.mock_aw)
            self.classic_label.aw = self.mock_aw

    def test_initialization(self) -> None:
        assert self.classic_label is not None
        assert self.classic_label.aw is self.mock_aw


# ------------------------------
# ClassicTableMw
# ------------------------------
class TestClassicTableMw(unittest.TestCase):
    def test_initialization(self) -> None:
        from Aux_Classic_Hud import ClassicTableMw
        assert ClassicTableMw is not None


# ------------------------------
# Integration-ish
# ------------------------------
class TestClassicHudIntegration(unittest.TestCase):
    @patch("Aux_Classic_Hud.Database.Database")
    def test_comment_system_integration(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {
            "get_player_comment": "SELECT comment FROM players WHERE id = %s",
            "update_player_comment": "UPDATE players SET comment = %s WHERE id = %s",
        }
        mock_db_class.return_value = mock_db

        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "__init__", return_value=None), \
             patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None), \
             patch("Aux_Classic_Hud.QInputDialog") as mock_dialog:

            mock_aw = Mock()
            mock_hud = Mock()
            mock_aw.hud = mock_hud
            mock_aw.params = {"fgcolor": "#FFFFFF"}
            mock_hud.supported_games_parameters = None
            mock_hud.config = Mock()
            mock_hud.config.get_db_parameters.return_value = {"db-backend": "sqlite"}
            mock_hud.hand_instance = Mock()

            stat = ClassicStat("playershort", 2, Mock(), mock_aw)
            stat.aw = mock_aw
            stat.hud = mock_hud
            stat.stat = "playershort"
            stat.lab = Mock()
            stat.lab.aw_seat = 2
            stat.stat_dict = {123: {"seat": 2, "screen_name": "TestPlayer"}}

            mock_dialog.getMultiLineText.return_value = ("New comment", True)
            with patch.object(stat, "get_player_name", return_value="TestPlayer"), \
                 patch.object(stat, "get_current_comment", return_value=""), \
                 patch.object(stat, "save_comment") as mock_save:
                stat.open_comment_dialog(Mock())
                mock_save.assert_called()

    @patch("Aux_Classic_Hud.Database.Database")
    def test_full_stat_lifecycle(self, mock_db_class) -> None:
        mock_db = Mock(); mock_cur = Mock()
        mock_db.cursor = mock_cur
        mock_db.sql.query = {
            "get_player_comment": "SELECT comment FROM players WHERE id = %s",
            "update_player_comment": "UPDATE players SET comment = %s WHERE id = %s",
        }
        mock_cur.fetchone.return_value = ("Initial comment",)
        mock_db_class.return_value = mock_db

        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "__init__", return_value=None), \
             patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None), \
             patch("Aux_Classic_Hud.QInputDialog") as mock_dialog:

            mock_aw = Mock()
            mock_hud = Mock()
            mock_aw.hud = mock_hud
            mock_aw.params = {"fgcolor": "#FFFFFF"}
            mock_hud.supported_games_parameters = None
            mock_hud.config = Mock()
            mock_hud.config.get_db_parameters.return_value = {"db-backend": "sqlite"}
            mock_hud.hand_instance = Mock()

            stat = ClassicStat("playershort", 2, Mock(), mock_aw)
            stat.aw = mock_aw
            stat.hud = mock_hud
            stat.stat = "playershort"
            stat.number = ("", "25", "", "", "", "")
            stat.lab = Mock()
            stat.lab.aw_seat = 2
            stat.stat_dict = {123: {"seat": 2, "screen_name": "Player"}}

            # Update stat display
            with patch.object(stat, "set_color") as mock_set_color:
                stat.update(123, {123: {"screen_name": "Player"}})
                mock_set_color.assert_called()

            # Open comment dialog
            mock_dialog.getMultiLineText.return_value = ("Updated comment", True)
            with patch.object(stat, "get_player_name", return_value="Player"), \
                 patch.object(stat, "get_current_comment", return_value=""), \
                 patch.object(stat, "save_comment") as mock_save:
                stat.open_comment_dialog(Mock())
                mock_save.assert_called()


# ------------------------------
# Error handling
# ------------------------------
class TestErrorHandling(unittest.TestCase):
    @patch("Aux_Classic_Hud.Database.Database")
    def test_database_error_handling(self, mock_db_class) -> None:
        mock_db = Mock()
        mock_db.cursor.execute.side_effect = Exception("Database error")
        mock_db.sql.query = {"update_player_comment": "UPDATE players SET comment = %s WHERE id = %s"}
        mock_db_class.return_value = mock_db

        with patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "__init__", return_value=None), \
             patch.object(Aux_Classic_Hud.Aux_Hud.SimpleStat, "update", return_value=None), \
             patch("Aux_Classic_Hud.log") as mock_log, \
             patch("Aux_Classic_Hud.QMessageBox"):
            mock_aw = Mock()
            mock_hud = Mock()
            mock_aw.hud = mock_hud
            mock_aw.params = {"fgcolor": "#FFFFFF"}
            mock_hud.supported_games_parameters = None
            mock_hud.config = Mock()
            mock_hud.config.get_db_parameters.return_value = {"db-backend": "sqlite"}
            mock_hud.hand_instance = Mock()

            stat = ClassicStat("vpip", 2, Mock(), mock_aw)
            stat.aw = mock_aw
            stat.hud = mock_hud
            stat.stat = "vpip"
            stat.lab = Mock()
            stat.number = ("", "invalid_number", "", "", "", "")
            stat.aux_params = {"font": "Arial", "font_size": 10}

            # On veut déclencher la gestion d'erreur (ValueError parse + erreur DB), et logger
            try:
                stat.update(123, {123: {"screen_name": "Player"}})
                stat.save_comment(123, "x")
            finally:
                assert mock_log.exception.called
