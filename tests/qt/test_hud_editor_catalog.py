"""The stat catalogue in the HUD Preferences editor, and stats and popups picked from lists (#773, B15)."""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import EXAMPLE, config_copy, open_editor, reload_stat_set, select_profile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]

ANALYTICS = "analytics:fold_to_3bet_preflop"

FLAT_WITH_HOLE = (
    '<ss name="hole" rows="2" cols="2">'
    '<stat _rowcol="(1,1)" _stat_name="vpip" popup="default"/>'
    '<stat _rowcol="(1,2)" _stat_name="pfr" popup="gone"/>'
    '<stat _rowcol="(2,2)" _stat_name="not_a_stat"/>'
    "</ss>"
)
TWO_BLOCKS = (
    '<ss name="two_blocks" rows="2" cols="2">'
    '<block label="Core" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="vpip"/></block>'
    '<block label="Post" rows="1" cols="2"><stat _rowcol="(1,1)" _stat_name="cb1"/>'
    '<text _rowcol="(1,2)" label="POST"/></block>'
    "</ss>"
)


def _editor(tmp_path, monkeypatch, *extra_xml: str):
    import defusedxml.minidom

    nodes = [defusedxml.minidom.parseString(xml).documentElement for xml in extra_xml]
    path = config_copy(tmp_path, nodes)
    dialog, modals = open_editor(path, monkeypatch)
    return dialog, modals, path


def _save(dialog, modals) -> None:
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages


def _select(dialog, ref) -> None:
    for row, (_kind, item) in enumerate(dialog._group_item_refs):
        if item is ref:
            dialog.group_items_list.setCurrentRow(row)
            return
    raise AssertionError("item not in the panel")


def _stat(container, name: str) -> dict:
    return next(stat for stat in container["stats"] if stat["stat"] == name)


# --- Available Stats -----------------------------------------------------------
def test_available_stats_takes_the_place_of_the_items_list(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "holdem_ring")
    assert not dialog.stat_catalog_widget.isHidden()
    assert dialog.group_items_list.isHidden()
    assert len(dialog.stat_catalog_widget.catalog) > 250


def test_activating_a_stat_fills_the_first_free_cell(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    dialog.stat_catalog_widget.stat_activated.emit("classic:wtsd")

    added = _stat(profile, "wtsd")
    assert (added["row"], added["col"], added["popup"]) == (1, 0, "default")
    assert dialog._current_item()[1] is added
    assert dialog.has_unsaved_changes()

    _save(dialog, modals)
    saved = reload_stat_set(path, "hole")
    assert saved.stats[(1, 0)].stat_name == "wtsd"


def test_an_analytics_stat_brings_its_data_attributes(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    dialog.stat_catalog_widget.stat_activated.emit(ANALYTICS)

    added = _stat(profile, "fold_to_3bet_preflop")
    assert (added["data_source"], added["data_definition"]) == ("analytics", "fold_to_3bet_preflop")
    _save(dialog, modals)
    saved = reload_stat_set(path, "hole").stats[(1, 0)]
    assert (saved.stat_name, saved.data_source) == ("fold_to_3bet_preflop", "analytics")


def test_the_stat_goes_to_the_panel_shown_in_design(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    dialog.group_list.setCurrentRow(1)
    dialog.stat_catalog_widget.stat_activated.emit("classic:pfr")

    core, post = profile["blocks"]
    assert [s["stat"] for s in core["stats"]] == ["vpip"]
    assert [(s["stat"], s["row"], s["col"]) for s in post["stats"]] == [("cb1", 0, 0), ("pfr", 1, 0)]
    assert post["rows"] == 2


def test_an_unknown_key_adds_nothing(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    dialog.stat_catalog_widget.stat_activated.emit("classic:no_such_stat")
    assert len(profile["stats"]) == 3
    assert not dialog.has_unsaved_changes()


# --- Item Properties -------------------------------------------------------------
def test_a_stat_shows_the_statistic_list_and_a_label_the_text_field(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, TWO_BLOCKS)
    profile = select_profile(dialog, "two_blocks")
    dialog.group_list.setCurrentRow(1)
    post = profile["blocks"][1]
    form = dialog.item_props_form

    _select(dialog, post["stats"][0])
    assert form.isRowVisible(dialog.ip_stat) and not form.isRowVisible(dialog.ip_text)
    assert dialog.ip_stat.currentText() == "cb1"

    _select(dialog, post["texts"][0])
    assert form.isRowVisible(dialog.ip_text) and not form.isRowVisible(dialog.ip_stat)
    assert dialog.ip_text.text() == "POST"
    assert not dialog.ip_popup.isEnabled()


def test_picking_another_stat_renames_the_cell(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    vpip = _stat(profile, "vpip")
    _select(dialog, vpip)

    dialog.ip_stat.setCurrentText("fold_to_3bet_preflop (analytics)")
    dialog._item_prop_changed()
    assert (vpip["stat"], vpip["data_source"]) == ("fold_to_3bet_preflop", "analytics")

    dialog.ip_stat.setCurrentText("wtsd")
    dialog._item_prop_changed()
    assert vpip["stat"] == "wtsd"
    assert not vpip["data_source"] and not vpip["data_definition"]


def test_a_name_the_catalogue_lacks_is_refused(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    vpip = _stat(profile, "vpip")
    _select(dialog, vpip)

    dialog.ip_stat.setCurrentText("vpipp")
    dialog._item_prop_changed()
    assert vpip["stat"] == "vpip"
    assert dialog.ip_stat.currentText() == "vpip"
    assert "vpipp" in dialog.status_label.text()
    assert not dialog.has_unsaved_changes()


def test_an_unknown_stat_already_in_the_file_is_kept(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    odd = _stat(profile, "not_a_stat")
    _select(dialog, odd)
    assert dialog.ip_stat.currentText() == "not_a_stat"
    dialog._item_prop_changed()
    assert odd["stat"] == "not_a_stat"
    assert not dialog.has_unsaved_changes()


def test_the_popup_is_picked_from_the_configuration(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    vpip = _stat(profile, "vpip")
    _select(dialog, vpip)

    values = [dialog.ip_popup.itemData(i) for i in range(dialog.ip_popup.count())]
    assert values[0] == "" and "default" in values and "holdring_main" in values
    assert dialog.ip_popup.value() == "default"

    dialog.ip_popup.setCurrentIndex(dialog.ip_popup.findData("holdring_main"))
    assert vpip["popup"] == "holdring_main"
    _save(dialog, modals)
    assert reload_stat_set(path, "hole").stats[(0, 0)].popup == "holdring_main"


def test_a_missing_popup_is_shown_and_kept(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    pfr = _stat(profile, "pfr")
    _select(dialog, pfr)
    assert dialog.ip_popup.currentText() == "gone (missing)"
    dialog._item_prop_changed()
    assert pfr["popup"] == "gone"
    assert not dialog.has_unsaved_changes()


# --- Add/Edit Statistic ------------------------------------------------------------
def _answer_with(text: str, popup: str | None = None):
    """Fill the dialog for the free cell of FLAT_WITH_HOLE and press OK."""

    def answer(dlg) -> int:
        dlg.row_input.setCurrentText("1")
        dlg.col_input.setCurrentText("0")
        dlg.stat_input.setCurrentText(text)
        if popup is not None:
            dlg.popup_input.setCurrentIndex(dlg.popup_input.findData(popup))
        dlg.accept()
        return dlg.result()

    return answer


def test_the_dialog_offers_the_catalogue_and_the_popups(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    modals.dialogs.append(_answer_with("fold_to_3bet_preflop (analytics)", popup="holdring_main"))
    dialog.add_stat()

    added = _stat(profile, "fold_to_3bet_preflop")
    assert added["data_source"] == "analytics"
    assert added["popup"] == "holdring_main"


def test_the_dialog_refuses_an_unknown_stat(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    modals.dialogs.append(_answer_with("vpipp"))
    dialog.add_stat()

    assert len(profile["stats"]) == 3
    assert any(kind == "warning" and "vpipp" in text for kind, text in modals.messages)


def test_editing_an_unknown_stat_without_renaming_it_is_allowed(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch, FLAT_WITH_HOLE)
    profile = select_profile(dialog, "hole")
    odd = _stat(profile, "not_a_stat")
    _select(dialog, odd)

    def answer(dlg) -> int:
        assert dlg.stat_input.currentText() == "not_a_stat"
        dlg.click_input.setText("tooltip")
        dlg.accept()
        return dlg.result()

    modals.dialogs.append(answer)
    dialog.edit_stat()
    assert (odd["stat"], odd["click"]) == ("not_a_stat", "tooltip")
    assert not [m for m in modals.messages if m[0] == "warning"]
