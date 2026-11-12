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
    dialog._select_item(ref)
    assert dialog._selected_item is ref, "item not in the panel"


def _stat(container, name: str) -> dict:
    return next(stat for stat in container["stats"] if stat["stat"] == name)


# --- Available Stats -----------------------------------------------------------
def test_available_stats_takes_the_place_of_the_items_list(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "holdem_ring")
    assert not dialog.stat_catalog_widget.isHidden()
    assert not hasattr(dialog, "group_items_list")
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
    """Fill the dialog and press OK; the stat goes to the free cell of FLAT_WITH_HOLE."""

    def answer(dlg) -> int:
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


def test_another_stat_in_the_dialog_takes_its_whole_binding(tmp_path, monkeypatch) -> None:
    """The cell's own data_* values belonged to the old stat, not to the one picked."""
    xml = (
        '<ss name="tuned" rows="1" cols="1">'
        '<stat _rowcol="(1,1)" _stat_name="fold_to_3bet_preflop" data_source="analytics"'
        ' data_definition="fold_to_3bet_preflop" data_format="count" data_min_sample="100"/>'
        "</ss>"
    )
    dialog, modals, _path = _editor(tmp_path, monkeypatch, xml)
    profile = select_profile(dialog, "tuned")
    cell = profile["stats"][0]
    _select(dialog, cell)
    entry = dialog._stat_catalog().get("analytics:fold_to_cbet_flop")
    assert entry is not None

    def keep(dlg) -> int:
        dlg.click_input.setText("tooltip")
        dlg.accept()
        return dlg.result()

    modals.dialogs.append(keep)
    dialog.edit_stat()
    assert (cell["data_format"], cell["data_min_sample"]) == ("count", "100")

    def switch(dlg) -> int:
        dlg.stat_input.setCurrentText("fold_to_cbet_flop (analytics)")
        dlg.accept()
        return dlg.result()

    modals.dialogs.append(switch)
    dialog.edit_stat()
    assert cell["stat"] == "fold_to_cbet_flop"
    assert {key: cell[key] for key in entry.attributes} == dict(entry.attributes)


UNINSTALLED = (
    '<ss name="uninstalled" rows="1" cols="2">'
    '<stat _rowcol="(1,1)" _stat_name="vpip" data_source="analytics" data_definition="not_installed"'
    ' data_format="count"/>'
    "</ss>"
)


def test_an_analytics_cell_whose_definition_is_missing_is_left_alone(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch, UNINSTALLED)
    profile = select_profile(dialog, "uninstalled")
    cell = profile["stats"][0]
    _select(dialog, cell)
    assert dialog.ip_stat.currentText() == "vpip"

    dialog._item_prop_changed()  # focus leaving the list
    assert (cell["data_source"], cell["data_definition"]) == ("analytics", "not_installed")

    def keep(dlg) -> int:
        dlg.click_input.setText("tooltip")
        dlg.accept()
        return dlg.result()

    modals.dialogs.append(keep)
    dialog.edit_stat()
    assert (cell["data_definition"], cell["click"]) == ("not_installed", "tooltip")
    _save(dialog, modals)
    saved = reload_stat_set(path, "uninstalled").stats[(0, 0)]
    assert (saved.stat_name, saved.data_definition, saved.data_format) == ("vpip", "not_installed", "count")


def test_picking_the_classic_stat_from_the_list_replaces_the_missing_binding(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, UNINSTALLED)
    profile = select_profile(dialog, "uninstalled")
    cell = profile["stats"][0]
    _select(dialog, cell)
    dialog.ip_stat.setCurrentIndex(dialog.ip_stat.findText("vpip"))
    dialog.ip_stat.activated.emit(dialog.ip_stat.currentIndex())
    assert cell["stat"] == "vpip"
    assert not cell["data_source"] and not cell["data_definition"]
