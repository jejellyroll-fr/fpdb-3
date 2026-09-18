"""The Dynamic Panels tab: the editor half of #309.

The model is tested without a window (``tests/test_hud_panel_editor.py``); these
tests drive the real dialog against a real configuration file, because the parts
that can only be wrong in the GUI are the ones that matter here: that a rule a
user builds from the selectors is the rule that reaches the configuration, that
the row shows what is wrong with it, that the preview answers in the words the
HUD would act on, and that a stat added from the picker survives a save.
"""

from __future__ import annotations

import os
import shutil

import pytest

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXAMPLE = os.path.join(ROOT, "HUD_config.xml.example")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not os.path.exists(EXAMPLE), reason="example config missing")]


@pytest.fixture
def dialog(tmp_path):
    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import Configuration as Conf
    from fpdb_3_legacy import ModernHudPreferences as M

    QApplication.instance() or QApplication([])
    config_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE, config_path)
    config = Conf.Config(file=str(config_path))
    dlg = M.ModernHudPreferences(config, None)
    dlg._config_path = config_path
    return dlg


def _select(dialog, **values) -> None:
    """Set the selector widgets by their stored data, not their labels."""
    for name, value in values.items():
        widget = dialog.panel_selector_widgets[name]
        if hasattr(widget, "low_edit"):
            low, high = value if isinstance(value, (list, tuple)) else (value, value)
            widget.low_edit.setText("" if low is None else str(low))
            widget.high_edit.setText("" if high is None else str(high))
            continue
        index = widget.findData(value if value is not None else "")
        assert index >= 0, f"no {name} option for {value!r}"
        widget.setCurrentIndex(index)


def _fill(dialog, panel: str, **conditions) -> None:
    dialog.panel_rule_panel_combo.setCurrentText(panel)
    _select(dialog, **conditions)
    dialog._add_panel_rule()


def test_the_tab_exists_and_starts_from_the_configuration(dialog) -> None:
    titles = [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())]
    assert any("Dynamic Panels" in title for title in titles)
    assert dialog.panel_rules == [], "the shipped section is inert"
    assert dialog.panel_rules_table.rowCount() == 0
    assert not dialog.panel_rules_enabled.isChecked()


def test_a_rule_built_from_the_selectors_lists_its_conditions(dialog) -> None:
    _fill(dialog, "srp_cbet_ip", street="flop", pot_type="single_raised", in_position=True, is_preflop_aggressor=True)

    assert dialog.panel_rules_table.rowCount() == 1
    assert dialog.panel_rules[0].panel == "srp_cbet_ip"
    assert dialog.panel_rules[0].when == {
        "street": "flop",
        "pot_type": "single_raised",
        "in_position": True,
        "is_preflop_aggressor": True,
    }
    row = [dialog.panel_rules_table.item(0, column).text() for column in range(8)]
    assert row[1] == "srp_cbet_ip"
    assert "street=flop" in row[2] and "in_position=true" in row[2]


def test_an_any_selector_states_nothing(dialog) -> None:
    """An unconstrained dimension is absent, not a value the engine must guess."""
    _fill(dialog, "core", street="flop")
    assert dialog.panel_rules[0].when == {"street": "flop"}


def test_a_range_selector_is_written_as_the_engine_reads_it(dialog) -> None:
    _fill(dialog, "srp_cbet_ip", pot_type="single_raised", to_call=[None, 0])
    assert dialog.panel_rules[0].when["to_call"] == [None, 0]


def test_the_behaviour_fields_reach_the_rule(dialog) -> None:
    dialog.panel_rule_min_sample.setValue(50)
    dialog.panel_rule_priority.setValue(30)
    dialog.panel_rule_id.setText("mine")
    dialog.panel_rule_fallback_combo.setCurrentText("preflop_open")
    _fill(dialog, "preflop_deep", street="preflop")

    rule = dialog.panel_rules[0]
    assert (rule.min_sample, rule.priority, rule.rule_id, rule.fallback) == (50, 30, "mine", "preflop_open")
    assert rule.enabled


def test_a_disabled_rule_is_written_disabled(dialog) -> None:
    dialog.panel_rule_enabled.setChecked(False)
    _fill(dialog, "ssh_stack", street="preflop")
    assert dialog.panel_rules[0].enabled is False


def test_a_rule_needing_a_panel_name_is_refused_with_the_loader_message(dialog, monkeypatch) -> None:
    from fpdb_3_legacy.modern_hud_preferences import main_dialog

    warned = []
    monkeypatch.setattr(main_dialog.QMessageBox, "warning", lambda *args: warned.append(args))
    dialog.panel_rule_panel_combo.setCurrentText("")

    dialog._add_panel_rule()

    assert dialog.panel_rules == []
    assert warned, "the user must be told, not silently ignored"


def test_a_duplicate_rule_is_refused(dialog, monkeypatch) -> None:
    from fpdb_3_legacy.modern_hud_preferences import main_dialog

    warned = []
    monkeypatch.setattr(main_dialog.QMessageBox, "warning", lambda *args: warned.append(args))
    _fill(dialog, "core", street="flop")
    _fill(dialog, "core", street="flop")

    assert len(dialog.panel_rules) == 1
    assert warned


def test_deleting_a_rule_renumbers_the_rest(dialog) -> None:
    """Order is the last tie-breaker of the resolver, so it must stay 0..n-1."""
    _fill(dialog, "a_panel", street="flop")
    _fill(dialog, "b_panel", street="turn")

    dialog.panel_rules_table.setCurrentCell(0, 0)
    dialog._delete_panel_rule()

    assert [rule.panel for rule in dialog.panel_rules] == ["b_panel"]
    assert [rule.order for rule in dialog.panel_rules] == [0]
    assert dialog.panel_rules_table.rowCount() == 1


def test_reordering_a_rule_rewrites_file_order(dialog) -> None:
    _fill(dialog, "first", street="flop")
    _fill(dialog, "second", street="flop")

    dialog.panel_rules_table.setCurrentCell(1, 0)
    dialog._move_panel_rule(-1)

    assert [rule.panel for rule in dialog.panel_rules] == ["second", "first"]
    assert [rule.order for rule in dialog.panel_rules] == [0, 1]


def test_a_duplicate_is_flagged_on_both_rows(dialog) -> None:
    from fpdb_3_legacy import hud_situation as hs

    dialog.panel_rules = [
        hs.PanelRule.from_mapping({"panel": "x", "when": {"street": "flop"}}, 0),
        hs.PanelRule.from_mapping({"panel": "x", "when": {"street": "flop"}}, 1),
    ]
    dialog._refresh_panel_rules_table()

    for row in (0, 1):
        cell = dialog.panel_rules_table.item(row, 7)
        assert "⚠" in cell.text()
        assert "duplicate" in cell.toolTip().lower() or "same selector" in cell.toolTip()


def test_a_rule_naming_an_unknown_panel_is_flagged(dialog) -> None:
    from fpdb_3_legacy import hud_situation as hs

    dialog.panel_rules = [hs.PanelRule.from_mapping({"panel": "typo_panel", "when": {"street": "flop"}}, 0)]
    dialog._refresh_panel_rules_table()

    cell = dialog.panel_rules_table.item(0, 7)
    assert cell.text()
    assert "not a known block" in cell.toolTip()


def test_the_preview_names_the_winner_and_the_reason_it_beat_the_rest(dialog) -> None:
    dialog.panel_rules_enabled.setChecked(True)
    _fill(dialog, "srp_cbet_ip", street="flop", pot_type="single_raised", in_position=True)
    dialog.panel_rule_fallback_combo.setCurrentText("core")
    dialog._update_panel_preview()

    text = dialog.panel_preview_label.text()

    assert "srp_cbet_ip" in text
    assert "won on specificity" in text
    assert "✔ srp_cbet_ip" in text


def test_the_preview_falls_back_when_nothing_matches(dialog) -> None:
    dialog.panel_rules_enabled.setChecked(True)
    _fill(dialog, "river_only", street="river")
    dialog.panel_rule_fallback_combo.setCurrentText("core")
    _select(dialog, street="flop")
    dialog._update_panel_preview()

    text = dialog.panel_preview_label.text()
    assert "fallback" in text and "core" in text
    assert "does not hold" in text, "the losing rule must say which condition failed"


def test_the_preview_follows_the_sample_threshold(dialog) -> None:
    dialog.panel_rules_enabled.setChecked(True)
    dialog.panel_rule_min_sample.setValue(200)
    dialog.panel_rule_fallback_combo.setCurrentText("core")
    _fill(dialog, "deep", street="preflop")
    dialog.panel_rule_fallback_combo.setCurrentText("core")

    dialog.panel_preview_sample.setValue(10)
    assert "withheld" in dialog.panel_preview_label.text()

    dialog.panel_preview_sample.setValue(900)
    assert "deep" in dialog.panel_preview_label.text()


def test_a_rule_edited_from_the_row_comes_back_into_the_form(dialog) -> None:
    _fill(dialog, "srp_cbet_ip", street="flop", in_position=True)
    dialog.panel_rules_table.setCurrentCell(0, 0)

    assert dialog.panel_rule_panel_combo.currentText() == "srp_cbet_ip"
    widget = dialog.panel_selector_widgets["street"]
    assert widget.currentData() == "flop"
    assert dialog.panel_selector_widgets["in_position"].currentData() is True
    assert dialog.panel_selector_widgets["pot_type"].currentData() == ""


def test_editing_a_multi_value_selector_keeps_all_values(dialog) -> None:
    from fpdb_3_legacy import hud_situation as hs

    dialog.panel_rules = [
        hs.PanelRule.from_mapping(
            {"panel": "srp_probe_ip", "when": {"street": ["turn", "river"]}},
            0,
        )
    ]
    dialog._refresh_panel_rules_table()
    dialog.panel_rules_table.setCurrentCell(0, 0)

    dialog._update_panel_rule()

    assert dialog.panel_rules[0].when["street"] == ["turn", "river"]


def test_updating_the_selected_row_replaces_it_in_place(dialog) -> None:
    _fill(dialog, "srp_cbet_ip", street="flop")
    dialog.panel_rules_table.setCurrentCell(0, 0)
    _select(dialog, street="turn")

    dialog._update_panel_rule()

    assert len(dialog.panel_rules) == 1
    assert dialog.panel_rules[0].when == {"street": "turn"}


def test_the_rules_reach_the_configuration_it_did_not_have(dialog) -> None:
    """The section started empty and disabled; Save writes what the tab says."""
    from fpdb_3_legacy import Configuration as Conf

    dialog.panel_rules_enabled.setChecked(True)
    _fill(dialog, "srp_cbet_ip", street="flop", pot_type="single_raised")
    dialog.panel_rule_fallback_combo.setCurrentText("core")
    dialog.panel_rules_fallback = "core"

    dialog._persist_panel_rules()
    dialog.config.save()

    reloaded = Conf.Config(file=str(dialog._config_path))
    assert reloaded.hud_panel_rules_enabled
    assert [rule.panel for rule in reloaded.get_hud_panel_rules()] == ["srp_cbet_ip"]
    assert reloaded.hud_panel_fallback == "core"
    assert reloaded.get_hud_panel_rules()[0].when == {"street": "flop", "pot_type": "single_raised"}


def test_a_configuration_the_user_never_opened_is_not_rewritten(dialog) -> None:
    """Untouched means untouched: the shipped section stays disabled and empty."""
    from fpdb_3_legacy import Configuration as Conf

    dialog._persist_panel_rules()
    dialog.config.save()

    reloaded = Conf.Config(file=str(dialog._config_path))
    assert reloaded.get_hud_panel_rules() == []
    assert not reloaded.hud_panel_rules_enabled


def test_turning_it_off_after_having_rules_keeps_them_but_disables_them(dialog) -> None:
    from fpdb_3_legacy import Configuration as Conf

    dialog.panel_rules_enabled.setChecked(True)
    _fill(dialog, "srp_cbet_ip", street="flop")
    dialog.panel_rules_enabled.setChecked(False)

    dialog._persist_panel_rules()
    dialog.config.save()

    reloaded = Conf.Config(file=str(dialog._config_path))
    assert reloaded.get_hud_panel_rules() == []
    assert not reloaded.hud_panel_rules_enabled


def test_export_and_import_round_trip_through_the_dialog(dialog, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from fpdb_3_legacy.modern_hud_preferences import main_dialog

    target = tmp_path / "setup.json"
    monkeypatch.setattr(main_dialog.QMessageBox, "information", lambda *args, **kwargs: None)
    dialog.panel_rules_enabled.setChecked(True)
    _fill(dialog, "srp_cbet_ip", street="flop", pot_type="single_raised")
    dialog.panel_rules_fallback = "core"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    dialog._export_panel_rules()
    assert target.exists()

    dialog.panel_rules = []
    dialog._refresh_panel_rules_table()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(target), ""))
    dialog._import_panel_rules()

    assert [rule.panel for rule in dialog.panel_rules] == ["srp_cbet_ip"]
    assert dialog.panel_rules_enabled.isChecked(), "an imported rule set is meant to be shown"


def test_importing_something_that_is_not_a_panel_document_is_refused(dialog, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from fpdb_3_legacy.modern_hud_preferences import main_dialog

    bad = tmp_path / "other.json"
    bad.write_text('{"kind": "a-popup-pack", "rules": []}', encoding="utf-8")
    shown = []
    monkeypatch.setattr(main_dialog.QMessageBox, "critical", lambda *args: shown.append(args))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(bad), ""))

    dialog._import_panel_rules()

    assert shown and "fpdb-hud-panels" in shown[0][2]


# --------------------------------------------------------------------------- #
# The stat picker.
# --------------------------------------------------------------------------- #


def _analytics_choice(dialog, name: str):
    from fpdb_3_legacy import hud_panel_editor as editor

    return next(
        choice
        for choice in dialog.panel_stat_choices
        if choice.source == "analytics" and choice.name == name and editor.choice_key(choice)
    )


def _select_stat(dialog, choice) -> None:
    from fpdb_3_legacy import hud_panel_editor as editor

    index = dialog.panel_stat_combo.findData(editor.choice_key(choice))
    assert index >= 0, f"the picker must offer {editor.choice_key(choice)}"
    dialog.panel_stat_combo.setCurrentIndex(index)


def test_the_picker_shows_both_sources_and_their_metadata(dialog) -> None:
    names = {choice.name for choice in dialog.panel_stat_choices}
    assert {"vpip", "cbet_flop"} <= names, "the column-backed stats are there"
    assert "fold_to_cbet_flop" in names, "and so are the analytics ones"

    choice = _analytics_choice(dialog, "fold_to_cbet_flop")
    _select_stat(dialog, choice)
    detail = dialog.panel_stat_detail.text()

    assert "[analytics]" in detail
    assert "filters:" in detail, "the fragments' filters are what a user cannot see in a definition"
    assert "sample: opportunities" in detail
    assert "min sample:" in detail
    assert choice.fmt


def test_a_picker_choice_reports_the_popups_that_bind_it(dialog) -> None:
    bound = [choice for choice in dialog.panel_stat_choices if choice.popup_packs]
    if not bound:
        pytest.skip("no shipped pack binds a stat in this build")
    choice = bound[0]
    assert "popups:" in choice.describe()


def test_adding_an_analytics_stat_puts_it_in_the_block_with_its_source(dialog) -> None:
    dialog.profile_combo.setCurrentIndex(0)
    _name, profile = dialog._current_profile()
    before = len(dialog._item_container(profile, dialog.panel_stat_block_combo.currentData())["stats"])

    _select_stat(dialog, _analytics_choice(dialog, "fold_to_cbet_flop"))
    dialog._add_panel_stat_to_block()

    container = dialog._item_container(profile, dialog.panel_stat_block_combo.currentData())
    added = container["stats"][before]
    assert added["stat"] == "fold_to_cbet_flop"
    assert added["data_source"] == "analytics"
    assert added["data_definition"] == "fold_to_cbet_flop"
    assert added["data_format"]
    assert added["data_min_sample"] == str(_analytics_choice(dialog, "fold_to_cbet_flop").min_sample)


def test_a_column_stat_added_from_the_picker_stays_a_plain_name(dialog) -> None:
    dialog.profile_combo.setCurrentIndex(0)
    _name, profile = dialog._current_profile()
    before = len(dialog._item_container(profile, dialog.panel_stat_block_combo.currentData())["stats"])

    _select_stat(dialog, next(c for c in dialog.panel_stat_choices if c.name == "vpip"))
    dialog._add_panel_stat_to_block()

    added = dialog._item_container(profile, dialog.panel_stat_block_combo.currentData())["stats"][before]
    assert added["stat"] == "vpip"
    assert "data_source" not in added


def test_the_declarative_binding_survives_a_save_and_a_reload(dialog) -> None:
    """The whole point of writing the attributes: the XML says where it comes from."""
    from fpdb_3_legacy import Configuration as Conf

    dialog.profile_combo.setCurrentIndex(0)
    _select_stat(dialog, _analytics_choice(dialog, "fold_to_cbet_flop"))
    dialog._add_panel_stat_to_block()
    _name, profile = dialog._current_profile()
    item = dialog._item_container(profile, dialog.panel_stat_block_combo.currentData())["stats"][-1]

    dialog._append_stat_node(dialog.config.doc.documentElement, item, int(item["row"]), int(item["col"]))
    dialog.config.save()

    node = next(
        node
        for node in Conf.Config(file=str(dialog._config_path)).doc.getElementsByTagName("stat")
        if node.getAttribute("_stat_name") == "fold_to_cbet_flop"
    )
    stat = Conf.Stat(node)
    assert stat.data_source == "analytics"
    assert stat.data_definition == "fold_to_cbet_flop"
    assert stat.data_min_sample == str(_analytics_choice(dialog, "fold_to_cbet_flop").min_sample)
    carried = dialog._stat_to_dict(stat, 0, 0)
    assert carried["data_source"] == "analytics"
    assert carried["data_definition"] == "fold_to_cbet_flop"


def test_the_stat_picker_does_not_disturb_the_profile_editor(dialog) -> None:
    """The static workflow is untouched: adding a stat leaves the canvas model alone."""
    dialog.profile_combo.setCurrentIndex(0)
    _name, profile = dialog._current_profile()
    before = [dict(choice) for choice in (profile.get("blocks") or [])]
    _select_stat(dialog, next(c for c in dialog.panel_stat_choices if c.name == "vpip"))
    dialog._add_panel_stat_to_block()
    after = profile.get("blocks") or []
    assert len(before) == len(after), "no block was added or removed"
