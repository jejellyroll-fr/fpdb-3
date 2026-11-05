"""The compact HUD options: on a table, and as saved defaults from fpdb (#693).

Real widgets are clicked and edited, because Qt swallows what goes wrong in a slot.
Every Config is built from a copy of the shipped file.
"""

from __future__ import annotations

import builtins
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QLabel, QPushButton, QSpinBox

from fpdb_3_legacy import Aux_Base
from fpdb_3_legacy.Aux_Hud import SimpleTablePopupMenu
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.hud_main_huds import HudMainHudsMixin
from fpdb_3_legacy.hud_options_panel import OPTION_FIELDS, HudOptionsDialog
from fpdb_3_legacy.ThemeManager import ThemeManager

pytestmark = pytest.mark.qt

SHIPPED = Path(__file__).resolve().parents[1] / "HUD_config.xml"
STAT_SETS = ["set_a", "set_b"]


@pytest.fixture(scope="module", autouse=True)
def app():
    # Read when the application is created, so nothing lands on a developer's screen.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def params() -> dict:
    return {
        "new_max_seats": None,
        "agg_bb_mult": 3,
        "seats_style": "A",
        "seats_cust_nums_low": 6,
        "seats_cust_nums_high": 10,
        "stat_range": "A",
        "hud_days": 90,
        "h_agg_bb_mult": 1,
        "h_seats_style": "A",
        "h_seats_cust_nums_low": 6,
        "h_seats_cust_nums_high": 10,
        "h_stat_range": "S",
        "h_hud_days": 30,
    }


@pytest.fixture
def config_file(tmp_path) -> Path:
    mine = tmp_path / "HUD_config.xml"
    shutil.copy(SHIPPED, mine)
    return mine


def _menu(params: dict, table_x: int = 10, table_y: int = 10, stat_sets: list[str] | None = None):
    parent = SimpleNamespace(
        menu_label="fpdb",
        menu_is_popped=True,
        popup_menu=None,
        aw=SimpleNamespace(xshift=0, yshift=0, game_params=SimpleNamespace(name="set_a")),
        hud=SimpleNamespace(
            table=SimpleNamespace(x=table_x, y=table_y, key="table"),
            hud_params=params,
            parent=MagicMock(),
            save_layout=MagicMock(),
            layout_set=SimpleNamespace(layout={6: None, 9: None}),
            config=SimpleNamespace(get_stat_sets=lambda: STAT_SETS if stat_sets is None else stat_sets),
        ),
    )
    parent.popup_menu = SimpleTablePopupMenu(parent)
    return parent.popup_menu


def _combo(window, field: str) -> QComboBox:
    return window.findChild(QComboBox, field)


def _spinner(window, field: str) -> QSpinBox:
    return window.findChild(QSpinBox, field)


def _dialog_button(dialog: HudOptionsDialog, which: QDialogButtonBox.StandardButton) -> QPushButton:
    return dialog.buttons.button(which)


def _save_as_fpdb_would(config_file: Path, values: dict) -> None:
    config = Config(file=str(config_file))
    config.set_hud_ui_parameters(values)
    config.save()
    # The HUD's fingerprint is (mtime, size): make the change visible within one clock tick.
    stat = config_file.stat()
    os.utime(config_file, (stat.st_atime, stat.st_mtime + 2))


# --------------------------------------------------------------------------
# The table menu
# --------------------------------------------------------------------------


def test_the_table_menu_is_compact(params) -> None:
    menu = _menu(params)

    # The menu this replaced took about 735x374 with the same controls.
    assert menu.width() < 500
    assert menu.height() < 220
    menu.close()


def test_the_actions_share_one_row(params) -> None:
    menu = _menu(params)

    assert len({button.y() for button in menu.findChildren(QPushButton)}) == 1
    menu.close()


def test_the_panel_edits_each_side_on_its_own(params) -> None:
    menu = _menu(params)

    _combo(menu, "h_agg_bb_mult").setCurrentIndex(4)
    _combo(menu, "stat_range").setCurrentIndex(1)

    assert params["h_agg_bb_mult"] == 10000
    assert params["agg_bb_mult"] == 3
    assert params["stat_range"] == "S"
    assert params["h_stat_range"] == "S"
    menu.close()


def test_the_combos_open_on_the_current_values(params) -> None:
    menu = _menu(params)

    assert _combo(menu, "agg_bb_mult").currentIndex() == 2
    assert _combo(menu, "h_stat_range").currentIndex() == 1
    menu.close()


@pytest.mark.parametrize(
    ("combo", "index", "spinners"),
    [
        ("h_seats_style", 1, ("h_seats_cust_nums_low", "h_seats_cust_nums_high")),
        ("seats_style", 1, ("seats_cust_nums_low", "seats_cust_nums_high")),
        ("h_stat_range", 2, ("h_hud_days",)),
        ("stat_range", 2, ("hud_days",)),
    ],
)
def test_spinners_appear_only_when_they_apply(params, combo, index, spinners) -> None:
    menu = _menu(params)
    assert all(_spinner(menu, name).isVisibleTo(menu) is False for name in spinners)

    _combo(menu, combo).setCurrentIndex(index)
    assert all(_spinner(menu, name).isVisibleTo(menu) for name in spinners)

    _combo(menu, combo).setCurrentIndex(0)
    assert all(_spinner(menu, name).isVisibleTo(menu) is False for name in spinners)
    menu.close()


def test_a_spinner_edits_its_value(params) -> None:
    menu = _menu(params)
    _combo(menu, "stat_range").setCurrentIndex(2)

    _spinner(menu, "hud_days").setValue(14)

    assert params["hud_days"] == 14
    menu.close()


def test_the_window_follows_its_content(params) -> None:
    menu = _menu(params)
    compact = menu.width()

    _combo(menu, "h_seats_style").setCurrentIndex(1)
    grown = menu.width()
    _combo(menu, "h_seats_style").setCurrentIndex(0)

    assert grown > compact
    assert menu.width() == compact
    menu.close()


def test_the_menu_stays_on_screen_at_the_edge_of_the_screen(params) -> None:
    screen = QApplication.primaryScreen().availableGeometry()

    menu = _menu(params, table_x=screen.right() - 5, table_y=screen.bottom() - 5)

    assert screen.contains(menu.frameGeometry())
    menu.close()


def test_the_menu_stays_on_screen_when_a_spinner_widens_it(params) -> None:
    screen = QApplication.primaryScreen().availableGeometry()
    menu = _menu(params, table_x=screen.right() - 5, table_y=screen.bottom() - 5)

    _combo(menu, "h_seats_style").setCurrentIndex(1)
    _combo(menu, "seats_style").setCurrentIndex(1)

    assert screen.contains(menu.frameGeometry())
    menu.close()


def test_the_menu_can_be_dragged_by_its_handle(params) -> None:
    menu = _menu(params, table_x=10, table_y=10)
    start = menu.pos()
    grip = next(label for label in menu.findChildren(QLabel) if label.text() == "≡")
    QApplication.processEvents()

    press_at = grip.rect().center()
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press_at)
    assert Aux_Base._drag_active is True
    QTest.mouseMove(grip, press_at + QPoint(40, 25))
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, press_at + QPoint(40, 25))

    assert menu.pos() == start + QPoint(40, 25)
    assert Aux_Base._drag_active is False
    menu.close()


def test_closing_the_menu_mid_drag_does_not_leave_the_hud_believing_in_a_drag(params) -> None:
    menu = _menu(params)
    grip = next(label for label in menu.findChildren(QLabel) if label.text() == "≡")
    QTest.mousePress(grip, Qt.MouseButton.LeftButton)

    menu.close()

    assert Aux_Base._drag_active is False


def test_a_single_stat_set_is_named_rather_than_offered(params) -> None:
    menu = _menu(params, stat_sets=["set_a"])

    assert any(label.text() == "set_a" for label in menu.findChildren(QLabel))
    assert not hasattr(menu, "stat_set_combo")
    menu.close()


def test_the_force_layout_choice_is_kept_on_the_table(params) -> None:
    menu = _menu(params)
    force_layout = next(combo for combo in menu.findChildren(QComboBox) if combo.itemText(0) == "Force layout...")

    force_layout.setCurrentText("9-max")

    assert params["new_max_seats"] == 9
    menu.close()


def test_everything_the_menu_shows_goes_through_translation(params, monkeypatch) -> None:
    monkeypatch.setattr(builtins, "_", lambda text: f"«{text}»", raising=False)

    menu = _menu(params)

    data = {"≡", *STAT_SETS, "6-max", "9-max"}
    shown = [label.text() for label in menu.findChildren(QLabel)]
    shown += [button.text() for button in menu.findChildren(QPushButton)]
    shown += [button.toolTip() for button in menu.findChildren(QPushButton)]
    for combo in menu.findChildren(QComboBox):
        shown += [combo.itemText(index) for index in range(combo.count())]
    shown.append(menu.windowTitle())
    untranslated = [text for text in shown if text and text not in data and not text.startswith("«")]

    assert untranslated == []
    menu.close()


# --------------------------------------------------------------------------
# The dialog in fpdb's main window
# --------------------------------------------------------------------------


def test_the_dialog_offers_the_options_and_no_table_action(params) -> None:
    dialog = HudOptionsDialog(params)

    labels = {button.text() for button in dialog.findChildren(QPushButton)}

    assert not labels & {"Restart", "Save layout", "Stop"}
    assert _combo(dialog, "h_stat_range") is not None
    dialog.close()


def test_ok_returns_the_edited_options(params) -> None:
    dialog = HudOptionsDialog(params)
    dialog.show()
    _combo(dialog, "stat_range").setCurrentIndex(2)
    _spinner(dialog, "hud_days").setValue(45)

    QTest.mouseClick(_dialog_button(dialog, QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)

    assert dialog.result() == HudOptionsDialog.DialogCode.Accepted
    assert dialog.option_values()["stat_range"] == "T"
    assert dialog.option_values()["hud_days"] == 45
    assert set(dialog.option_values()) == set(OPTION_FIELDS)


def test_cancel_leaves_the_saved_options_alone(params) -> None:
    before = dict(params)
    dialog = HudOptionsDialog(params)
    dialog.show()
    _combo(dialog, "stat_range").setCurrentIndex(2)

    QTest.mouseClick(_dialog_button(dialog, QDialogButtonBox.StandardButton.Cancel), Qt.MouseButton.LeftButton)

    assert dialog.result() == HudOptionsDialog.DialogCode.Rejected
    assert params == before


def test_options_saved_from_fpdb_survive_a_reload_and_touch_nothing_else(config_file) -> None:
    config = Config(file=str(config_file))
    before = config.get_hud_ui_parameters()
    dialog = HudOptionsDialog(before)
    _combo(dialog, "h_agg_bb_mult").setCurrentIndex(4)
    _combo(dialog, "seats_style").setCurrentIndex(1)
    _combo(dialog, "stat_range").setCurrentIndex(2)
    _spinner(dialog, "seats_cust_nums_low").setValue(3)
    _spinner(dialog, "seats_cust_nums_high").setValue(7)
    _spinner(dialog, "hud_days").setValue(45)

    config.set_hud_ui_parameters(dialog.option_values())
    config.save()
    after = Config(file=str(config_file)).get_hud_ui_parameters()

    assert after["h_agg_bb_mult"] == 10000
    assert after["seats_style"] == "C"
    assert after["seats_cust_nums_low"] == 3
    assert after["seats_cust_nums_high"] == 7
    assert after["stat_range"] == "T"
    assert after["hud_days"] == 45
    changed = {"h_agg_bb_mult", "seats_style", "seats_cust_nums_low", "seats_cust_nums_high", "stat_range", "hud_days"}
    assert {key: value for key, value in after.items() if key not in changed} == {
        key: value for key, value in before.items() if key not in changed
    }


def test_opening_the_dialog_and_saving_changes_no_option(config_file) -> None:
    config = Config(file=str(config_file))
    before = config.get_hud_ui_parameters()

    config.set_hud_ui_parameters(HudOptionsDialog(before).option_values())
    config.save()

    assert Config(file=str(config_file)).get_hud_ui_parameters() == before


# --------------------------------------------------------------------------
# Reaching the HUD
# --------------------------------------------------------------------------


def _running_hud(config_file: Path) -> HudMainHudsMixin:
    hud = object.__new__(HudMainHudsMixin)
    hud.config = Config(file=str(config_file))
    hud.hud_params = hud.config.get_hud_ui_parameters()
    hud.hud_dict = {}
    hud._table_stat_set_overrides = {}
    hud._config_fingerprint = hud._read_config_fingerprint()
    return hud


def test_a_running_hud_starts_new_tables_on_the_saved_options(config_file) -> None:
    hud = _running_hud(config_file)

    _save_as_fpdb_would(config_file, {"hud_days": 45, "stat_range": "T"})
    hud.refresh_profiles_from_config()

    assert hud.hud_params["hud_days"] == 45
    assert hud.hud_params["stat_range"] == "T"


def test_saved_options_do_not_change_an_open_table(config_file) -> None:
    hud = _running_hud(config_file)
    table = MagicMock(hud_context=None, hud_params=dict(hud.hud_params))
    hud.hud_dict["table-a"] = table
    table_options = dict(table.hud_params)

    _save_as_fpdb_would(config_file, {"hud_days": 45, "stat_range": "T"})
    hud.refresh_profiles_from_config()

    assert table.hud_params == table_options


# --------------------------------------------------------------------------
# What fpdb saves later must not undo this
# --------------------------------------------------------------------------


@pytest.fixture
def theme_manager(monkeypatch) -> ThemeManager:
    monkeypatch.setattr(ThemeManager, "_instance", None)
    monkeypatch.setattr(ThemeManager, "AVAILABLE_QT_THEMES", None)
    return ThemeManager()


def test_a_theme_change_keeps_options_saved_since_fpdb_started(config_file, theme_manager) -> None:
    theme_manager.initialize(config=Config(file=str(config_file)))

    _save_as_fpdb_would(config_file, {"hud_days": 45})
    assert theme_manager.set_qt_material_theme("dark_teal.xml", save=True, apply_to_ui=False)

    saved = Config(file=str(config_file))
    assert saved.get_hud_ui_parameters()["hud_days"] == 45
    assert saved.general["qt_material_theme"] == "dark_teal.xml"


def test_a_theme_change_does_not_overwrite_an_unreadable_config(config_file, theme_manager) -> None:
    theme_manager.initialize(config=Config(file=str(config_file)))
    config_file.write_text("<FreePokerToolsConfig><broken", encoding="utf-8")
    unreadable = config_file.read_bytes()

    theme_manager.set_qt_material_theme("dark_teal.xml", save=True, apply_to_ui=False)

    assert config_file.read_bytes() == unreadable
