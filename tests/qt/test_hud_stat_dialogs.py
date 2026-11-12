"""The HUD Preferences dialogs, offscreen (#763: B1, B3).

``AddStatDialog`` returns only what the user set, keeps thresholds that are
decimal, negative or above 100, and leaves a stat without colours without them.
The Color Ranges tab of Item Properties follows the same rules. The smaller
dialogs of ``dialogs.py`` are driven here too.
"""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import (
    EXAMPLE,
    config_copy,
    open_editor,
    reload_stat_set,
    select_profile,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.qt

ACCEPT = 1

PLAIN = {"row": 0, "col": 1, "stat": "pfr", "click": "", "popup": "default"}
RANGED = {
    **PLAIN,
    "stat": "wtsd",
    "stat_loth": "12.5",
    "stat_hith": "140",
    "stat_locolor": "#FF0000",
    "stat_hicolor": "#00ff00",
    "stat_midcolor": "",
}


@pytest.fixture
def dialogs(qtbot):
    """Build dialogs that pytest-qt closes and deletes after the test."""
    from fpdb_3_legacy.modern_hud_preferences import dialogs as module

    def make(cls_name: str, *args, **kwargs):
        dialog = getattr(module, cls_name)(*args, **kwargs)
        qtbot.addWidget(dialog)
        return dialog

    return make


@pytest.fixture
def colour_picker(monkeypatch):
    """Answers QColorDialog.getColor with the colours queued in the list."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    queued: list[str] = []
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *_a, **_k: QColor(queued.pop(0))))
    return queued


# --- AddStatDialog: editing ----------------------------------------------------
@pytest.mark.parametrize("stat", [PLAIN, RANGED], ids=["no thresholds", "decimal and above 100"])
def test_an_unchanged_stat_comes_back_unchanged(dialogs, stat) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(stat))
    assert dialog.get_stat() == {}


def test_a_stat_without_thresholds_shows_them_off_and_no_colours(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(PLAIN))
    assert not dialog.use_thresholds.isChecked()
    assert not dialog.loth_input.isEnabled()
    assert not dialog.locolor_btn.isEnabled()
    assert (dialog.locolor, dialog.hicolor, dialog.midcolor) == ("", "", "")


def test_decimal_and_large_thresholds_are_shown_as_they_are(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    assert dialog.use_thresholds.isChecked()
    assert (dialog.loth_input.value(), dialog.hith_input.value()) == (12.5, 140.0)
    assert dialog.hith_input.maximum() > 100


def test_changing_one_field_returns_only_that_field(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED), popup_names=["default", "Multicol"])
    dialog.popup_input.setCurrentIndex(dialog.popup_input.findData("Multicol"))
    assert dialog.get_stat() == {"popup": "Multicol"}


def test_changing_a_threshold_keeps_the_other_string(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    dialog.hith_input.setValue(250.75)
    assert dialog.get_stat() == {"stat_hith": "250.75"}


def test_a_threshold_moved_and_moved_back_is_unchanged(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    dialog.loth_input.setValue(30)
    dialog.loth_input.setValue(12.5)
    assert dialog.get_stat() == {}


def test_a_negative_threshold_is_accepted(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    dialog.loth_input.setValue(-5)
    assert dialog.get_stat() == {"stat_loth": "-5"}


def test_turning_thresholds_off_clears_them_only(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    dialog.use_thresholds.setChecked(False)
    assert dialog.get_stat() == {"stat_loth": "", "stat_hith": ""}


def test_turning_thresholds_on_sets_them_and_the_usual_colours(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(PLAIN))
    dialog.use_thresholds.setChecked(True)
    assert dialog.loth_input.isEnabled()
    assert dialog.get_stat() == {
        "stat_loth": "20",
        "stat_hith": "60",
        "stat_locolor": "#ff0000",
        "stat_hicolor": "#00ff00",
    }


def test_turning_thresholds_on_keeps_the_stored_colours(dialogs) -> None:
    stat = {**PLAIN, "stat_locolor": "#123456", "stat_hicolor": "#654321"}
    dialog = dialogs("AddStatDialog", stat=stat)
    dialog.use_thresholds.setChecked(True)
    assert dialog.get_stat() == {"stat_loth": "20", "stat_hith": "60"}


def test_the_mid_colour_is_set_by_its_checkbox(dialogs, colour_picker) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    assert not dialog.midcolor_btn.isEnabled()
    dialog.use_midcolor.setChecked(True)
    assert dialog.midcolor_btn.isEnabled()
    assert dialog.get_stat() == {"stat_midcolor": "#ffff00"}
    colour_picker.append("#abcdef")
    dialog.choose_color("mid")
    assert dialog.get_stat() == {"stat_midcolor": "#abcdef"}
    dialog.use_midcolor.setChecked(False)
    assert dialog.get_stat() == {}


def test_a_stored_mid_colour_is_shown_and_can_be_removed(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat={**RANGED, "stat_midcolor": "#0000ff"})
    assert dialog.use_midcolor.isChecked()
    assert dialog.midcolor_btn.isEnabled()
    assert dialog.color_preview.use_mid_color
    dialog.use_midcolor.setChecked(False)
    assert dialog.get_stat() == {"stat_midcolor": ""}


def test_picking_the_low_and_high_colours(dialogs, colour_picker) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    colour_picker.extend(["#111111", "#222222"])
    dialog.choose_color("low")
    dialog.choose_color("high")
    assert dialog.get_stat() == {"stat_locolor": "#111111", "stat_hicolor": "#222222"}
    assert dialog.locolor_btn.text() == ""


def test_a_cancelled_colour_pick_changes_nothing(dialogs, monkeypatch) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *_a, **_k: QColor()))
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    dialog.choose_color("low")
    assert dialog.get_stat() == {}


def test_an_unset_colour_button_says_none(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(PLAIN))
    assert dialog.locolor_btn.text() == "(none)"
    assert dialog.locolor_btn.styleSheet() == ""


def test_the_preview_fits_a_threshold_above_100(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat=dict(RANGED))
    start, end, low, high = dialog.color_preview.positions()
    assert start == 0.0
    assert end > 140
    assert 0.0 < low < high < 1.0
    dialog.color_preview.grab()  # paints without a Qt gradient warning


def test_the_preview_paints_a_mid_colour(dialogs) -> None:
    dialog = dialogs("AddStatDialog", stat={**RANGED, "stat_midcolor": "#0000ff"})
    assert not dialog.color_preview.grab().isNull()


# --- AddStatDialog: adding -----------------------------------------------------
def test_a_new_stat_has_no_colour_range_unless_asked(dialogs) -> None:
    dialog = dialogs("AddStatDialog")
    dialog.stat_input.setCurrentText("vpip")
    assert dialog.get_stat() == {"stat": "vpip", "click": "", "popup": ""}


def test_a_new_stat_with_a_colour_range(dialogs) -> None:
    dialog = dialogs("AddStatDialog")
    dialog.stat_input.setCurrentText("vpip")
    dialog.use_thresholds.setChecked(True)
    dialog.loth_input.setValue(12.5)
    dialog.hith_input.setValue(140)
    stat = dialog.get_stat()
    assert {key: stat[key] for key in ("stat_loth", "stat_hith", "stat_locolor", "stat_hicolor")} == {
        "stat_loth": "12.5",
        "stat_hith": "140",
        "stat_locolor": "#ff0000",
        "stat_hicolor": "#00ff00",
    }
    assert "stat_midcolor" not in stat


# --- The smaller dialogs -------------------------------------------------------
def test_block_properties_round_trip(dialogs, colour_picker) -> None:
    block = {"label": "Core", "position": "UTG+1", "cell_width": 40, "bgcolor": "#000000"}
    dialog = dialogs("BlockPropertiesDialog", block)
    assert dialog.pos_combo.currentText() == "UTG+1"
    colour_picker.append("#ff00ff")
    dialog._pick("bordercolor")
    props = dialog.get_props()
    assert props["label"] == "Core"
    assert props["cell_width"] == 40
    assert props["bgcolor"] == "#000000"
    assert props["bordercolor"] == "#ff00ff"
    assert props["fgcolor"] == ""


def test_layout_selection_checks_custom_layouts(dialogs) -> None:
    dialog = dialogs("LayoutSelectionDialog", ["default", "9-max", "mucked_6"])
    assert dialog.get_selected_layouts() == ["9-max"]
    dialog.select_all()
    assert dialog.get_selected_layouts() == ["9-max", "default", "mucked_6"]
    dialog.select_none()
    assert dialog.get_selected_layouts() == []


def test_popup_stat_edit_dialog(dialogs) -> None:
    dialog = dialogs("PopupStatEditDialog", {"stat_name": "vpip", "submenu": "pre", "category": "preflop"})
    assert dialog.get_stat_data() == {"stat_name": "vpip", "submenu": "pre", "category": "preflop"}
    dialog.category_combo.setCurrentText("auto")
    assert dialog.get_stat_data() == {"stat_name": "vpip", "submenu": "pre"}


def test_popup_edit_dialog_adds_and_removes_stats(dialogs) -> None:
    from PySide6.QtWidgets import QTableWidgetItem

    popup = {"name": "mine", "class": "Submenu", "stats": [{"stat_name": "vpip"}, {"stat_name": "pfr", "submenu": "x"}]}
    dialog = dialogs("PopupEditDialog", popup)
    dialog.add_stat()
    dialog.stats_table.setItem(2, 0, QTableWidgetItem("wtsd"))
    dialog.stats_table.setCurrentCell(0, 0)
    dialog.remove_stat()
    assert dialog.get_popup_data() == {
        "name": "mine",
        "class": "Submenu",
        "stats": [{"stat_name": "pfr", "submenu": "x"}, {"stat_name": "wtsd", "submenu": ""}],
    }


# --- The Color Ranges tab of Item Properties -------------------------------------
FLAT = (
    '<ss name="ranges" rows="2" cols="2">'
    '<stat _rowcol="(1,1)" _stat_name="vpip"/>'
    '<stat _rowcol="(1,2)" _stat_name="wtsd" stat_loth="12.5" stat_hith="140" stat_locolor="#FF0000"'
    ' stat_hicolor="#00ff00"/>'
    "</ss>"
)


def _editor(tmp_path, monkeypatch):
    import defusedxml.minidom

    if not EXAMPLE.exists():
        pytest.skip("example config missing")
    path = config_copy(tmp_path, [defusedxml.minidom.parseString(FLAT).documentElement])
    dialog, modals = open_editor(path, monkeypatch)
    return dialog, modals, path, select_profile(dialog, "ranges")


def _select_item(dialog, ref) -> None:
    dialog._select_item(ref)
    assert dialog._selected_item is ref, "item not in the shown profile"


def _stat(profile, name):
    return next(s for s in profile["stats"] if s["stat"] == name)


def test_the_tab_shows_decimal_and_large_thresholds(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path, profile = _editor(tmp_path, monkeypatch)
    _select_item(dialog, _stat(profile, "wtsd"))
    assert dialog.ip_use_thresholds.isChecked()
    assert (dialog.ip_loth.value(), dialog.ip_hith.value()) == (12.5, 140.0)
    assert dialog.ip_loth.isEnabled()


def test_the_tab_leaves_a_stat_without_thresholds_alone(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path, profile = _editor(tmp_path, monkeypatch)
    ref = _stat(profile, "vpip")
    _select_item(dialog, ref)
    assert not dialog.ip_use_thresholds.isChecked()
    assert not dialog.ip_loth.isEnabled()
    dialog.ip_align.setCurrentText("right")
    assert ref["align"] == "right"
    assert not any(ref.get(key) for key in ("stat_loth", "stat_hith", "stat_locolor", "stat_hicolor"))


def test_the_tab_writes_a_changed_threshold_and_restores_it(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path, profile = _editor(tmp_path, monkeypatch)
    ref = _stat(profile, "wtsd")
    _select_item(dialog, ref)
    dialog.ip_hith.setValue(150.5)
    assert (ref["stat_loth"], ref["stat_hith"]) == ("12.5", "150.5")
    dialog.ip_hith.setValue(140)
    assert (ref["stat_loth"], ref["stat_hith"]) == ("12.5", "140")


def test_the_tab_turns_thresholds_off_and_on(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path, profile = _editor(tmp_path, monkeypatch)
    ref = _stat(profile, "wtsd")
    _select_item(dialog, ref)
    dialog.ip_use_thresholds.setChecked(False)
    assert (ref["stat_loth"], ref["stat_hith"]) == ("", "")
    assert not dialog.ip_hith.isEnabled()
    dialog.ip_use_thresholds.setChecked(True)
    assert (ref["stat_loth"], ref["stat_hith"]) == ("12.5", "140")
    assert ref["stat_locolor"] == "#FF0000"


def test_the_tab_gives_a_new_range_its_colours(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path, profile = _editor(tmp_path, monkeypatch)
    ref = _stat(profile, "vpip")
    _select_item(dialog, ref)
    dialog.ip_use_thresholds.setChecked(True)
    assert (ref["stat_loth"], ref["stat_hith"]) == ("20", "60")
    assert (ref["stat_locolor"], ref["stat_hicolor"]) == ("#ff0000", "#00ff00")
    assert dialog.ip_locolor.text() == "#ff0000"


def test_the_tab_is_off_for_a_text_label(tmp_path, monkeypatch) -> None:
    dialog, modals, _path, profile = _editor(tmp_path, monkeypatch)
    modals.texts.append(("HEADER", True))
    dialog.add_text_label()
    profile = dialog.hud_profiles["ranges"]
    label = profile["blocks"][0]["texts"][0]
    _select_item(dialog, label)
    assert not dialog.ip_use_thresholds.isEnabled()
    assert not dialog.ip_loth.isEnabled()


def test_edit_stat_saves_only_the_changed_threshold(tmp_path, monkeypatch) -> None:
    dialog, modals, path, profile = _editor(tmp_path, monkeypatch)
    ref = _stat(profile, "wtsd")
    _select_item(dialog, ref)

    def raise_low(d) -> int:
        d.loth_input.setValue(-3.25)
        return ACCEPT

    modals.dialogs.append(raise_low)
    dialog.edit_stat()
    assert (ref["stat_loth"], ref["stat_hith"]) == ("-3.25", "140")
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages
    saved = reload_stat_set(path, "ranges")
    wtsd = next(s for s in saved.stats.values() if s.stat_name == "wtsd")
    assert (wtsd.stat_loth, wtsd.stat_hith, wtsd.stat_locolor, wtsd.stat_midcolor) == ("-3.25", "140", "#FF0000", "")
    vpip = next(s for s in saved.stats.values() if s.stat_name == "vpip")
    assert (vpip.stat_loth, vpip.stat_locolor) == ("", "")
