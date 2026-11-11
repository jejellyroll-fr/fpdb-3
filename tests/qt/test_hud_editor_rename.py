"""Renaming a profile, the unsaved-changes mark and closing the editor (#761).

The real HUD Preferences dialog, offscreen, on a temporary copy of the example
configuration; every modal is answered through ``tests.helpers.hud_editor``.
"""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import EXAMPLE, config_copy, open_editor, select_profile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]


def _editor(tmp_path, monkeypatch):
    path = config_copy(tmp_path)
    dialog, modals = open_editor(path, monkeypatch)
    return dialog, modals, path


def _reload(path):
    from fpdb_3_legacy import Configuration

    return Configuration.Config(file=str(path))


def _stat_set_names(config) -> list[str]:
    return [node.getAttribute("name") for node in config.doc.getElementsByTagName("ss")]


def _game_bindings(config) -> list[str]:
    return [node.getAttribute("stat_set") for node in config.doc.getElementsByTagName("game_stat_set")]


def _rename(dialog, modals, new_name: str, ok: bool = True) -> None:
    modals.texts.append((new_name, ok))
    dialog.rename_profile()


def _add_rule_for(dialog, profile: str) -> None:
    from fpdb_3_legacy.hud_situation import PanelRule

    dialog.rule_profile_combo.setCurrentIndex(dialog.rule_profile_combo.findData(profile))
    dialog.rule_site_combo.setCurrentIndex(1)
    dialog._add_profile_rule()
    dialog.panel_rules.append(PanelRule(panel="Core", profile=profile))
    dialog.panel_rules.append(PanelRule(panel="Post", profile="all"))
    dialog.panel_rules_enabled.setChecked(True)


# --- Rename ------------------------------------------------------------------
def test_renaming_keeps_the_place_and_the_data_and_marks_a_change(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    data = select_profile(dialog, "draw_default")
    order = list(dialog.hud_profiles)
    _rename(dialog, modals, "  draw_bob  ")
    assert list(dialog.hud_profiles) == [("draw_bob" if n == "draw_default" else n) for n in order]
    assert dialog.hud_profiles["draw_bob"] is data
    assert dialog.profile_combo.currentText() == "draw_bob"
    assert dialog.profile_combo.findText("draw_default") < 0
    assert "draw_bob" in dialog.status_label.text()
    assert dialog.has_unsaved_changes()
    assert not modals.messages


def test_the_rules_naming_a_renamed_profile_follow_it(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "draw_default")
    _add_rule_for(dialog, "draw_default")
    _rename(dialog, modals, "draw_bob")
    assert [rule.profile for rule in dialog.profile_rules] == ["draw_bob"]
    assert [rule.profile for rule in dialog.panel_rules] == ["draw_bob", "all"]
    # The rule pickers offer the new name, and the table does not flag the rule.
    assert dialog.rule_profile_combo.findData("draw_bob") >= 0
    assert dialog.rule_profile_combo.findData("draw_default") < 0
    assert dialog.panel_rule_profile_combo.findData("draw_bob") >= 0
    assert "⚠" not in dialog.profile_rules_table.item(0, 7).text()


def test_saving_a_renamed_profile_renames_its_stat_set_and_what_names_it(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    before = _stat_set_names(_reload(path))
    original = select_profile(dialog, "draw_default")
    _add_rule_for(dialog, "draw_default")
    _rename(dialog, modals, "draw_bob")
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] in ("critical", "warning")], modals.messages
    assert not dialog.has_unsaved_changes()

    saved = _reload(path)
    # Renamed in place: same position, no stray copy, no orphan.
    assert _stat_set_names(saved) == [("draw_bob" if n == "draw_default" else n) for n in before]
    assert saved.stat_sets["draw_bob"].rows == original["rows"]
    # The game defaults and both kinds of rule name the new profile.
    assert "draw_default" not in _game_bindings(saved)
    assert "draw_bob" in _game_bindings(saved)
    assert [rule.profile for rule in saved.get_hud_profile_rules()] == ["draw_bob"]
    assert [rule.profile for rule in saved.hud_panel_rules] == ["draw_bob", "all"]

    from fpdb_3_legacy.config_migrations import reference_errors

    assert not [e for e in reference_errors(saved.doc) if "draw" in e]


def test_a_second_save_after_a_rename_writes_the_same_stat_set(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "draw_default")
    _rename(dialog, modals, "draw_bob")
    dialog.save_changes()
    dialog.hud_profiles["draw_bob"]["rows"] = 5
    dialog.save_changes()
    names = _stat_set_names(_reload(path))
    assert names.count("draw_bob") == 1
    assert "draw_default" not in names
    assert _reload(path).stat_sets["draw_bob"].rows == 5


def test_two_profiles_can_swap_names(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    draw_rows = select_profile(dialog, "draw_default")["rows"]
    stud_rows = dialog.hud_profiles["stud_default"]["rows"]
    _rename(dialog, modals, "tmp")
    select_profile(dialog, "stud_default")
    _rename(dialog, modals, "draw_default")
    select_profile(dialog, "tmp")
    _rename(dialog, modals, "stud_default")
    dialog.save_changes()
    saved = _reload(path)
    assert saved.stat_sets["stud_default"].rows == draw_rows
    assert saved.stat_sets["draw_default"].rows == stud_rows
    assert "tmp" not in saved.stat_sets


def test_a_new_profile_on_a_vacated_name_is_saved_apart(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    draw_rows = select_profile(dialog, "draw_default")["rows"]
    _rename(dialog, modals, "draw_bob")

    def name_it(new_dialog) -> int:
        from PySide6.QtWidgets import QLineEdit

        new_dialog.findChild(QLineEdit).setText("draw_default")
        return 1

    modals.dialogs.append(name_it)
    dialog.add_profile()
    _rename(dialog, modals, "draw_carol")
    dialog.save_changes()
    saved = _reload(path)
    assert saved.stat_sets["draw_bob"].rows == draw_rows
    assert "draw_carol" in saved.stat_sets
    assert "draw_default" not in saved.stat_sets
    assert "draw_bob" in _game_bindings(saved)
    assert "draw_carol" not in _game_bindings(saved)


def test_a_rename_onto_a_taken_name_says_why_and_changes_nothing(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "draw_default")
    order = list(dialog.hud_profiles)
    _rename(dialog, modals, "stud_default")
    _rename(dialog, modals, "   ")
    assert list(dialog.hud_profiles) == order
    assert [kind for kind, _text in modals.messages] == ["warning", "warning"]
    assert '"stud_default" already exists' in modals.messages[0][1]
    assert "needs a name" in modals.messages[1][1]
    assert not dialog.has_unsaved_changes()


@pytest.mark.parametrize(("name", "ok"), [("draw_default", True), ("draw_bob", False)])
def test_keeping_the_name_or_cancelling_changes_nothing(tmp_path, monkeypatch, name, ok) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "draw_default")
    _rename(dialog, modals, name, ok)
    assert "draw_default" in dialog.hud_profiles
    assert not modals.messages
    assert not dialog.has_unsaved_changes()


def test_rename_is_in_the_narrow_window_menu(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    assert dialog.rename_profile_btn in dialog._profile_action_buttons()
    texts = [action.text() for action in dialog.profile_actions_menu.actions()]
    assert dialog.rename_profile_btn.text() in texts


# --- Unsaved changes (B8) and the status bar ---------------------------------
def test_the_status_bar_says_when_something_is_unsaved(tmp_path, monkeypatch) -> None:
    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    assert dialog.unsaved_label.isHidden()
    dialog.profiling_checkbox.toggle()
    assert not dialog.unsaved_label.isHidden()
    assert "general settings" in dialog.unsaved_label.toolTip()
    dialog.profiling_checkbox.toggle()
    assert dialog.unsaved_label.isHidden()

    select_profile(dialog, "draw_default")
    _rename(dialog, modals, "draw_bob")
    assert not dialog.unsaved_label.isHidden()
    dialog.save_changes()
    assert dialog.unsaved_label.isHidden()


def test_turning_dynamic_panels_on_is_an_unsaved_change(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    dialog.panel_rules_enabled.setChecked(not dialog.panel_rules_enabled.isChecked())
    assert dialog.has_unsaved_changes()
    assert "dynamic panels" in dialog.unsaved_label.toolTip()


def test_a_new_panel_rule_is_an_unsaved_change(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    dialog.panel_rule_panel_combo.setCurrentText("Core")
    dialog._add_panel_rule()
    assert dialog.panel_rules
    assert dialog.has_unsaved_changes()
    assert "panel rules" in dialog.unsaved_label.toolTip()


# --- Closing (B7) ------------------------------------------------------------
def test_cancel_without_edits_closes_without_asking(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog

    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_cancel_then_discard_closes_without_saving(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog, QMessageBox

    dialog, modals, path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "draw_default")["rows"] = 9
    modals.questions.append(QMessageBox.StandardButton.Discard)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert _reload(path).stat_sets["draw_default"].rows != 9


def test_cancel_then_save_saves_and_accepts(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QDialog, QMessageBox

    dialog, modals, path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "draw_default")["rows"] = 9
    modals.questions.append(QMessageBox.StandardButton.Save)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert _reload(path).stat_sets["draw_default"].rows == 9


def test_cancel_then_cancel_keeps_the_editor_and_the_edits(tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog, modals, _path = _editor(tmp_path, monkeypatch)
    dialog.show()
    select_profile(dialog, "draw_default")["rows"] = 9
    modals.questions.append(QMessageBox.StandardButton.Cancel)
    dialog.reject()
    assert dialog.isVisible()
    assert dialog.has_unsaved_changes()
