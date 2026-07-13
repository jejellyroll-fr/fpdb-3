#!/usr/bin/env python3
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication

# Ensure QApplication is initialized for widgets
app = QApplication.instance() or QApplication([])

from fpdb_3_legacy.GuiGraphViewer import GuiGraphViewer
from fpdb_3_legacy.GuiRingPlayerStats import GuiRingPlayerStats
from fpdb_3_legacy.GuiSessionViewer import GuiSessionViewer
from fpdb_3_legacy.GuiTourneyGraphViewer import GuiTourneyGraphViewer
from fpdb_3_legacy.GuiTourneyPlayerStats import GuiTourneyPlayerStats


class TestEmptyDataPopups(unittest.TestCase):
    def setUp(self):
        # Create standard mocks for db, config, sql
        self.mock_cursor = MagicMock()
        self.mock_cursor.description = [("hgametypeid",)]
        self.mock_cursor.fetchall.return_value = []

        self.mock_db = MagicMock()
        self.mock_db.cursor = self.mock_cursor
        self.mock_db.backend = 4
        self.mock_db.MYSQL_INNODB = 2
        self.mock_db.PGSQL = 3
        self.mock_db.SQLITE = 4
        self.mock_db.get_player_id.return_value = 8
        self.mock_db.get_player_site_id.return_value = 2

        self.mock_conf = MagicMock()
        self.mock_conf.get_db_parameters.return_value = {
            "db-backend": "sqlite",
            "db-server": "sqlite",
            "db-database": ":memory:",
            "db-user": "",
            "db-password": "",
            "db-host": "",
            "db-port": ""
        }
        self.mock_conf.get_import_parameters.return_value = {}
        self.mock_conf.get_default_paths.return_value = {}
        self.mock_conf.get_gui_cash_stat_params.return_value = [
            ["pname", "Player", True, True, "%s", "str", 0.0],
            ["plposition", "Position", True, True, "%s", "str", 0.0],
            ["rfi", "RFI", True, True, "%s", "float", 0.0],
            ["steals", "Steals", True, True, "%s", "float", 0.0],
            ["game", "Game", True, True, "%s", "str", 0.0],
            ["hand", "Hand", True, True, "%s", "str", 0.0],
        ]
        self.mock_conf.get_gui_tourney_stat_params.return_value = []

        self.mock_sql = MagicMock()
        self.mock_sql.query = {
            "sessionStats": "SELECT 1",
            "playerDetailedStats": "SELECT 1",
            "tourneyPlayerDetailedStats": "SELECT 1",
            "getRingProfitAllHandsPlayerIdSiteInDollars": "SELECT 1",
        }

        self.mock_colors = {
            "background": "#000000",
            "foreground": "#ffffff",
            "grid": "#444444",
            "line_down": "red",
            "line_up": "green",
            "line_showdown": "blue",
            "line_ev": "orange",
            "line_hands": "green",
        }

        # Apply global patch for Database.Database constructor
        self.database_patcher = patch("fpdb_3_legacy.Database.Database", return_value=self.mock_db)
        self.database_patcher.start()

    def tearDown(self):
        self.database_patcher.stop()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_graph_viewer_empty(self, mock_exec):
        """Test GuiGraphViewer shows QMessageBox and returns early when data is empty."""
        viewer = GuiGraphViewer(self.mock_sql, self.mock_conf, None, self.mock_colors)

        # Mock filters and getRingProfitGraph
        viewer.filters = MagicMock()
        viewer.filters.getSites.return_value = ["PokerStars"]
        viewer.filters.getHeroes.return_value = {"PokerStars": "jeje_sat"}
        viewer.filters.getSiteIds.return_value = {"PokerStars": 2}
        viewer.filters.getLimits.return_value = ["All"]
        viewer.filters.getGames.return_value = []
        viewer.filters.getCurrencies.return_value = []
        viewer.filters.getGraphOps.return_value = ["$"]

        # Mock getRingProfitGraph to return empty/None
        viewer.getRingProfitGraph = MagicMock(return_value=(None, None, None, None))

        # Run generateGraph
        viewer.generateGraph(None)

        # Assert QMessageBox was shown
        mock_exec.assert_called_once()
        viewer.db.rollback.assert_called()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_tourney_graph_viewer_empty(self, mock_exec):
        """Test GuiTourneyGraphViewer shows QMessageBox and returns early when data is empty."""
        viewer = GuiTourneyGraphViewer(self.mock_sql, self.mock_conf, None, self.mock_colors)

        # Mock filters and getData
        viewer.filters = MagicMock()
        viewer.filters.getSites.return_value = ["PokerStars"]
        viewer.filters.getHeroes.return_value = {"PokerStars": "jeje_sat"}
        viewer.filters.getSiteIds.return_value = {"PokerStars": 2}
        viewer.filters.getGames.return_value = []

        # Mock getData to return None (empty data)
        viewer.getData = MagicMock(return_value=None)

        # Run generateGraph
        viewer.generateGraph(None)

        # Assert QMessageBox was shown
        mock_exec.assert_called_once()
        viewer.db.rollback.assert_called()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_session_viewer_empty(self, mock_exec):
        """Test GuiSessionViewer shows QMessageBox and returns early when data is empty."""
        viewer = GuiSessionViewer(self.mock_conf, self.mock_sql, None, None, self.mock_colors)

        # Mock filters
        viewer.filters = MagicMock()
        viewer.filters.getSites.return_value = ["PokerStars"]
        viewer.filters.getHeroes.return_value = {"PokerStars": "jeje_sat"}
        viewer.filters.getSiteIds.return_value = {"PokerStars": 2}
        viewer.filters.getGames.return_value = ["holdem"]
        viewer.filters.getCurrencies.return_value = ["USD"]
        viewer.filters.getLimits.return_value = ["All"]
        viewer.filters.getSeats.return_value = None

        # Mock generateDatasets to return empty lists
        viewer.generateDatasets = MagicMock(return_value=([], []))

        # Mock clearGraphData
        viewer.clearGraphData = MagicMock()

        # Run createStatsPane
        viewer.createStatsPane(
            MagicMock(),
            [8],
            [2],
            ["holdem"],
            ["USD"],
            ["All"],
            None,
        )

        # Assert QMessageBox was shown and graph cleared
        mock_exec.assert_called_once()
        viewer.clearGraphData.assert_called_once()
        viewer.db.rollback.assert_called()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_ring_player_stats_empty(self, mock_exec):
        """Test GuiRingPlayerStats raises ValueError and catches it to show QMessageBox and rollback."""
        viewer = GuiRingPlayerStats(self.mock_conf, self.mock_sql, None)

        # Mock filters
        viewer.filters = MagicMock()
        viewer.filters.getSites.return_value = ["PokerStars"]
        viewer.filters.getHeroes.return_value = {"PokerStars": "jeje_sat"}
        viewer.filters.getSiteIds.return_value = {"PokerStars": 2}
        viewer.filters.getLimits.return_value = ["All"]
        viewer.filters.getSeats.return_value = None
        viewer.filters.getGroups.return_value = []
        viewer.filters.getDates.return_value = ("2000-01-01", "2030-01-01")
        viewer.filters.getGames.return_value = []
        viewer.filters.getCurrencies.return_value = []
        viewer.filters.getNumHands.return_value = 0
        viewer.filters.get_limits_where_clause.return_value = "1=1"

        # Run refreshStats
        viewer.refreshStats(None)

        # Assert QMessageBox was shown
        mock_exec.assert_called_once()
        viewer.db.rollback.assert_called()

    @patch("PySide6.QtWidgets.QDialog.exec", return_value=0)
    def test_gui_ring_player_stats_detail_filters(self, mock_exec):
        """Test showDetailFilter runs and doesn't raise NameError."""
        viewer = GuiRingPlayerStats(self.mock_conf, self.mock_sql, None)
        viewer.showDetailFilter(None)
        mock_exec.assert_called_once()

    @patch("PySide6.QtWidgets.QDialog.exec", return_value=0)
    def test_gui_ring_player_stats_column_config(self, mock_exec):
        """Test showColumnConfig runs and doesn't raise NameError."""
        viewer = GuiRingPlayerStats(self.mock_conf, self.mock_sql, None)
        viewer.showColumnConfig()
        mock_exec.assert_called_once()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_tourney_player_stats_empty(self, mock_exec):
        """Test GuiTourneyPlayerStats raises ValueError and catches it to show QMessageBox and rollback."""
        # Note: GuiTourneyPlayerStats takes db in constructor
        viewer = GuiTourneyPlayerStats(self.mock_conf, self.mock_db, self.mock_sql, None)

        # Mock filters
        viewer.filters = MagicMock()
        viewer.filters.getSites.return_value = ["PokerStars"]
        viewer.filters.getHeroes.return_value = {"PokerStars": "jeje_sat"}
        viewer.filters.getSiteIds.return_value = {"PokerStars": 2}
        viewer.filters.getSeats.return_value = None
        viewer.filters.getDates.return_value = ("2000-01-01", "2030-01-01")
        viewer.filters.getTourneyTypes.return_value = []
        viewer.filters.getNumTourneys.return_value = 0

        # Run refreshStats
        viewer.refreshStats()

        # Assert QMessageBox was shown
        mock_exec.assert_called_once()
        viewer.db.rollback.assert_called()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_hand_viewer_empty(self, mock_exec):
        """Test GuiHandViewer shows QMessageBox when no hands found."""
        from fpdb_3_legacy.GuiHandViewer import GuiHandViewer
        viewer = GuiHandViewer(self.mock_conf, self.mock_sql, None)
        viewer.filters = MagicMock()
        viewer.filters.getDates.return_value = ("2000-01-01", "2030-01-01")

        # Mock get_hand_ids_from_date_range to return empty
        viewer.get_hand_ids_from_date_range = MagicMock(return_value=[])

        viewer.loadHands(None)
        mock_exec.assert_called_once()

    @patch("PySide6.QtWidgets.QMessageBox.exec")
    def test_gui_tour_hand_viewer_empty(self, mock_exec):
        """Test TourHandViewer shows QMessageBox when no hands found."""
        from fpdb_3_legacy.GuiTourHandViewer import TourHandViewer
        viewer = TourHandViewer(self.mock_conf, self.mock_sql, None)
        viewer.filters = MagicMock()
        viewer.filters.getDates.return_value = ("2000-01-01", "2030-01-01")

        # Mock get_hand_ids_from_date_range to return empty
        viewer.get_hand_ids_from_date_range = MagicMock(return_value=[])

        viewer.loadHands(None)
        mock_exec.assert_called_once()

    def test_gui_stats_info_guide(self):
        """Test GuiStatsInfo instantiates and filters statistics correctly."""
        from fpdb_3_legacy.GuiStatsInfo import STATS_DATA, GuiStatsInfo

        # Instantiate guide
        guide = GuiStatsInfo(self.mock_conf, None)

        # Check that it populated some stats
        total_stats = sum(len(stats) for stats in STATS_DATA.values())
        self.assertGreater(guide.list_widget.count(), total_stats)

        # Test filtering/searching
        guide.filter_stats("VPIP")
        self.assertGreater(guide.list_widget.count(), 0)

        first_item = guide.list_widget.item(0)
        self.assertIn("VPIP", first_item.text())

        # Test detail display
        guide.list_widget.setCurrentItem(first_item)
        self.assertIn("Voluntarily Put In Pot", guide.text_browser.toHtml())

    def test_filters_get_hero_ids_variant(self):
        """Test that get_hero_ids correctly maps site variant to player ID."""
        from fpdb_3_legacy.Filters import Filters
        filters = Filters(self.mock_db)

        # Mock site variants
        heroes = {"PokerStars": "jeje_sat"}

        # Call get_hero_ids
        hero_ids = filters.get_hero_ids(heroes)

        # Assert get_player_id was called with site variant logic and resolved correct ID
        self.mock_db.get_player_id.assert_called_once_with(self.mock_db.config, "PokerStars", "jeje_sat")
        self.assertEqual(hero_ids, [8])

    def test_filters_get_actual_site_id(self):
        """Test that get_actual_site_id resolves variant site ID correctly."""
        from fpdb_3_legacy.Filters import Filters
        filters = Filters(self.mock_db)
        filters.siteid = {"PokerStars": 2}

        # Test fallback works and maps to site 33 (e.g. PokerStars.FR)
        actual_id = filters.get_actual_site_id("PokerStars", "jeje_sat")
        self.assertEqual(actual_id, 2)  # Since mock returns 2 (mock site variant)

    def test_filters_get_hero_for_site(self):
        """Test that get_hero_for_site robustly maps site variants to configured heroes."""
        from fpdb_3_legacy.Filters import Filters
        filters = Filters(self.mock_db)

        # Mock getHeroes return value
        filters.getHeroes = MagicMock(return_value={"PokerStars": "jeje_sat", "Unibet Poker": "jejesat"})

        # Test exact match
        self.assertEqual(filters.get_hero_for_site("PokerStars"), "jeje_sat")
        # Test variant prefix match
        self.assertEqual(filters.get_hero_for_site("PokerStars.FR"), "jeje_sat")
        self.assertEqual(filters.get_hero_for_site("PokerStars.EU"), "jeje_sat")
        # Test parent matching variant
        self.assertEqual(filters.get_hero_for_site("Unibet"), "jejesat")
        # Test non-existent site returns None
        filters.getHeroes = MagicMock(return_value={"PokerStars": "jeje_sat"})
        self.assertEqual(filters.get_hero_for_site("Winamax"), "jeje_sat")  # Since only one hero is configured, returns it as fallback

    def test_filters_update_sites_for_hero(self):
        """Test that update_sites_for_hero correctly checks parent site for variant."""
        from PySide6.QtWidgets import QCheckBox

        from fpdb_3_legacy.Filters import Filters
        filters = Filters(self.mock_db)

        # Mock cbSites
        cb_ps = QCheckBox()
        cb_ub = QCheckBox()
        filters.cbSites = {"PokerStars": cb_ps, "Unibet": cb_ub}

        # Call with variant PokerStars.FR
        filters.update_sites_for_hero("jeje_sat", "PokerStars.FR")

        self.assertTrue(cb_ps.isChecked())
        self.assertFalse(cb_ub.isChecked())


class TestHudImportExport(unittest.TestCase):
    def setUp(self):
        import xml.dom.minidom
        self.temp_files = []

        # Create a mock configuration with a valid DOM tree
        self.xml_content = """<?xml version="1.0" ?>
        <FreePokerToolsConfig>
            <stat_sets>
                <ss name="test_profile" rows="2" cols="2">
                    <stat _rowcol="(1,1)" _stat_name="vpip" popup="test_popup"/>
                    <stat _rowcol="(1,2)" _stat_name="pfr" popup="default"/>
                </ss>
            </stat_sets>
            <popup_windows>
                <pu pu_name="test_popup" pu_class="Submenu">
                    <pu_stat pu_stat_name="vpip" pu_stat_submenu="sub_popup"/>
                </pu>
                <pu pu_name="sub_popup" pu_class="default">
                    <pu_stat pu_stat_name="pfr"/>
                </pu>
            </popup_windows>
            <layout_sets>
                <ls name="ps_default">
                    <layout max="9" height="500" width="700">
                        <location seat="1" x="100" y="100"/>
                    </layout>
                </ls>
            </layout_sets>
        </FreePokerToolsConfig>
        """
        self.doc = xml.dom.minidom.parseString(self.xml_content)

        self.mock_config = MagicMock()
        self.mock_config.doc = self.doc
        self.mock_config.hud_profiles = None
        self.mock_config.stat_sets = {}
        self.mock_config.popup_windows = {}
        self.mock_config.layout_sets = {"ps_default": MagicMock()}

    def tearDown(self):
        import os
        for f in self.temp_files:
            if os.path.exists(f):
                os.remove(f)

    @patch("PySide6.QtWidgets.QFileDialog.getSaveFileName")
    @patch("PySide6.QtWidgets.QMessageBox.question")
    @patch("PySide6.QtWidgets.QMessageBox.information")
    def test_hud_export(self, mock_info, mock_question, mock_save):
        import os
        import tempfile
        import xml.dom.minidom

        from PySide6.QtWidgets import QDialog, QMessageBox

        from fpdb_3_legacy.ModernHudPreferences import ModernHudPreferences

        # Setup temp file path
        fd, temp_path = tempfile.mkstemp(suffix=".xml")
        os.close(fd)
        self.temp_files.append(temp_path)

        # Mock file dialog to return our temp path
        mock_save.return_value = (temp_path, "XML Files (*.xml)")
        # Mock layout selection prompt to say Yes
        mock_question.return_value = QMessageBox.StandardButton.Yes

        # Instantiate ModernHudPreferences with mock config
        prefs = ModernHudPreferences(self.mock_config)

        # Set hud_profiles explicitly to avoid KeyError or MagicMock behavior
        prefs.hud_profiles = {
            "test_profile": {
                "rows": 2,
                "cols": 2,
                "stats": [
                    {"row": 0, "col": 0, "stat": "vpip", "popup": "test_popup"},
                    {"row": 0, "col": 1, "stat": "pfr", "popup": "default"}
                ]
            }
        }
        # Mock profile combo box
        prefs.profile_combo.clear()
        prefs.profile_combo.addItem("test_profile")
        prefs.profile_combo.setCurrentIndex(0)

        # Mock LayoutSelectionDialog exec to accept and return ps_default
        with patch("fpdb_3_legacy.ModernHudPreferences.LayoutSelectionDialog") as MockDlgClass:
            mock_dlg = MockDlgClass.return_value
            mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
            mock_dlg.get_selected_layouts.return_value = ["ps_default"]

            # Run export
            prefs.export_profile()

        # Verify file exists and has correct tags
        self.assertTrue(os.path.exists(temp_path))
        exported_doc = xml.dom.minidom.parse(temp_path)
        root = exported_doc.documentElement

        self.assertEqual(root.tagName, "fpdb_hud_package")

        # Check ss tag
        ss_nodes = root.getElementsByTagName("ss")
        self.assertEqual(len(ss_nodes), 1)
        self.assertEqual(ss_nodes[0].getAttribute("name"), "test_profile")

        # Check popup tags (should gather test_popup and sub_popup recursively)
        pu_nodes = root.getElementsByTagName("pu")
        self.assertEqual(len(pu_nodes), 2)
        pu_names = [pu.getAttribute("pu_name") for pu in pu_nodes]
        self.assertIn("test_popup", pu_names)
        self.assertIn("sub_popup", pu_names)

        # Check layout set tags
        ls_nodes = root.getElementsByTagName("ls")
        self.assertEqual(len(ls_nodes), 1)
        self.assertEqual(ls_nodes[0].getAttribute("name"), "ps_default")

    @patch("PySide6.QtWidgets.QFileDialog.getOpenFileName")
    @patch("PySide6.QtWidgets.QMessageBox.exec")
    @patch("PySide6.QtWidgets.QInputDialog.getText")
    @patch("PySide6.QtWidgets.QMessageBox.information")
    def test_hud_import(self, mock_info, mock_input, mock_msg_exec, mock_open):
        import os
        import tempfile

        from fpdb_3_legacy.ModernHudPreferences import ModernHudPreferences

        # Create a package XML to import
        package_content = """<?xml version="1.0" ?>
        <fpdb_hud_package version="1.0">
            <ss name="imported_profile" rows="1" cols="1">
                <stat _rowcol="(1,1)" _stat_name="vpip" popup="imp_popup"/>
            </ss>
            <popup_windows>
                <pu pu_name="imp_popup" pu_class="default">
                    <pu_stat pu_stat_name="vpip"/>
                </pu>
            </popup_windows>
            <layout_sets>
                <ls name="imp_layout">
                    <layout max="6" height="400" width="600">
                        <location seat="1" x="50" y="50"/>
                    </layout>
                </ls>
            </layout_sets>
        </fpdb_hud_package>
        """
        fd, temp_path = tempfile.mkstemp(suffix=".xml")
        with os.fdopen(fd, "w") as f:
            f.write(package_content)
        self.temp_files.append(temp_path)

        # Mock file dialog to return package
        mock_open.return_value = (temp_path, "XML Files (*.xml)")

        # Instantiate preferences
        prefs = ModernHudPreferences(self.mock_config)
        prefs.hud_profiles = {}

        # Mock load methods and reload parent config
        prefs.load_profiles = MagicMock()
        prefs.load_popup_windows = MagicMock()
        prefs.reload_parent_config = MagicMock()

        # Run import
        prefs.import_profile()

        # Verify that nodes were added to the active doc
        ss_nodes = self.mock_config.doc.getElementsByTagName("ss")
        ss_names = [ss.getAttribute("name") for ss in ss_nodes]
        self.assertIn("imported_profile", ss_names)

        pu_nodes = self.mock_config.doc.getElementsByTagName("pu")
        pu_names = [pu.getAttribute("pu_name") for pu in pu_nodes]
        self.assertIn("imp_popup", pu_names)

        ls_nodes = self.mock_config.doc.getElementsByTagName("ls")
        ls_names = [ls.getAttribute("name") for ls in ls_nodes]
        self.assertIn("imp_layout", ls_names)

        # Check calls
        self.mock_config.save.assert_called_once()
        self.mock_config.reload.assert_called_once()
        prefs.load_profiles.assert_called_once()
        prefs.load_popup_windows.assert_called_once()

    @patch("PySide6.QtWidgets.QMessageBox.information")
    def test_hud_general_settings(self, mock_info):
        from fpdb_3_legacy.ModernHudPreferences import ModernHudPreferences

        # Setup mock return for get_hud_ui_parameters
        self.mock_config.get_hud_ui_parameters.return_value = {
            "player_profiling": "True",
            "profile_in_name": "False",
            "profile_min_hands": "25"
        }

        # Instantiate preferences
        prefs = ModernHudPreferences(self.mock_config)

        # Check that UI loaded values correctly
        self.assertTrue(prefs.profiling_checkbox.isChecked())
        self.assertFalse(prefs.profile_in_name_checkbox.isChecked())
        self.assertEqual(prefs.profile_min_hands_spin.value(), 25)

        # Modify the UI values
        prefs.profiling_checkbox.setChecked(False)
        prefs.profile_in_name_checkbox.setChecked(True)
        prefs.profile_min_hands_spin.setValue(40)

        # Verify has_unsaved_changes is True
        self.assertTrue(prefs.has_unsaved_changes())

        # Mock load methods to avoid exceptions during accept
        prefs.load_profiles = MagicMock()
        prefs.load_popup_windows = MagicMock()
        prefs.accept = MagicMock()

        # Run save_changes
        prefs.save_changes()

        # Verify set_hud_ui_parameters was called with new values
        self.mock_config.set_hud_ui_parameters.assert_called_once_with({
            "player_profiling": "False",
            "profile_in_name": "True",
            "profile_min_hands": "40"
        })
        self.mock_config.save.assert_called_once()



if __name__ == "__main__":
    unittest.main()
