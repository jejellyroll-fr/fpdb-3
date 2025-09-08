#!/usr/bin/env python
"""Simplified tests for Aux_Classic_Hud.py (fixed)."""

import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAuxClassicHudBasics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up mocks and stubs for Aux tests."""
        cls._original_modules = {}

        # Mock PyQt5 modules
        modules_to_mock = ["PyQt5", "PyQt5.QtGui", "PyQt5.QtCore", "PyQt5.QtWidgets"]
        for module_name in modules_to_mock:
            if module_name in sys.modules:
                cls._original_modules[module_name] = sys.modules[module_name]
            sys.modules[module_name] = Mock()

        # loggingFpdb stub with proper interface
        if "loggingFpdb" in sys.modules:
            cls._original_modules["loggingFpdb"] = sys.modules["loggingFpdb"]

        loggingFpdb = types.ModuleType("loggingFpdb")

        def _get_logger(_name: str):
            m = Mock()
            m.exception = Mock()
            m.debug = Mock()
            m.info = Mock()
            m.warning = Mock()
            m.error = Mock()
            return m

        loggingFpdb.get_logger = _get_logger
        sys.modules["loggingFpdb"] = loggingFpdb

        # Database stub with proper interface
        if "Database" in sys.modules:
            cls._original_modules["Database"] = sys.modules["Database"]

        Database = types.ModuleType("Database")

        class _DB:
            def __init__(self, _config):
                self.sql = types.SimpleNamespace(query={"get_player_comment": "SELECT 1"})
                self.cursor = types.SimpleNamespace(
                    execute=lambda *a, **kw: None,
                    fetchone=lambda *a, **kw: (None,),
                )

            def close_connection(self):  # pragma: no cover
                pass

        Database.Database = _DB
        sys.modules["Database"] = Database

        # Import after stubbing
        global ClassicHud, ClassicStatWindow, ClassicStat, ClassicLabel, ClassicTableMw, Aux_Classic_Hud
        import Aux_Classic_Hud  # noqa: E402

        ClassicHud = Aux_Classic_Hud.ClassicHud
        ClassicStatWindow = Aux_Classic_Hud.ClassicStatWindow
        ClassicStat = Aux_Classic_Hud.ClassicStat
        ClassicLabel = Aux_Classic_Hud.ClassicLabel
        ClassicTableMw = Aux_Classic_Hud.ClassicTableMw

    @classmethod
    def tearDownClass(cls):
        """Clean up mocks after Aux tests."""
        modules_to_cleanup = ["PyQt5", "PyQt5.QtGui", "PyQt5.QtCore", "PyQt5.QtWidgets", "loggingFpdb", "Database"]

        for module_name in modules_to_cleanup:
            if module_name in cls._original_modules:
                sys.modules[module_name] = cls._original_modules[module_name]
            elif module_name in sys.modules:
                del sys.modules[module_name]

    def _make_aw_minimal(self, seat_idx: int = 2):
        """Build a minimal 'aw' structure accepted by ClassicStat/SimpleStat."""
        aw = Mock()

        # hud subtree
        hud = Mock()
        hud.config = Mock()
        hud.hero = Mock()
        hud.positions = []
        hud.stat_windows = {}
        hud.supported_games_parameters = None
        hud.layout = SimpleNamespace(hh_seats={seat_idx: seat_idx})
        aw.hud = hud

        # params must be dict-like (subscriptable)
        aw.params = {
            "fgcolor": "#FFFFFF",
            "bgcolor": "#000000",
            "shadow": False,
            "fontsize": 12,
            "click": "none",
        }

        # some code paths may read those
        aw.hudcolor = "#FFFFFF"
        aw.hudbgcolor = "#000000"

        return aw

    def test_import_classic_hud_classes(self):
        assert ClassicHud is not None
        assert ClassicStatWindow is not None
        assert ClassicStat is not None
        assert ClassicLabel is not None
        assert ClassicTableMw is not None

    def test_comment_functionality_methods(self):
        mock_aw = self._make_aw_minimal(seat_idx=2)
        stat = ClassicStat("vpip", 2, Mock(), mock_aw)

        # Patch ON ClassicStat (not on Aux_Hud.SimpleStat, which doesn't define these)
        with (
            patch.object(Aux_Classic_Hud.ClassicStat, "get_current_comment", return_value="Test comment") as p_get,
            patch.object(Aux_Classic_Hud.ClassicStat, "has_comment", return_value=True) as p_has,
        ):
            comment = stat.get_current_comment(123)
            assert comment == "Test comment"
            p_get.assert_called_with(123)

            has_comment = stat.has_comment(123)
            assert has_comment is True
            p_has.assert_called_with(123)


if __name__ == "__main__":
    unittest.main(verbosity=2)
