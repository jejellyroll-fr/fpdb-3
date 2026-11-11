"""The profile presentation controls of the HUD Preferences editor (#764), offscreen."""

from __future__ import annotations

import os

import pytest

from tests.helpers.hud_editor import EXAMPLE, config_copy, open_editor, reload_stat_set, select_profile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = [pytest.mark.qt, pytest.mark.skipif(not EXAMPLE.exists(), reason="example config missing")]


def _editor(tmp_path, monkeypatch, path=None):
    path = path or config_copy(tmp_path)
    dialog, modals = open_editor(path, monkeypatch)
    return dialog, modals, path


def _save(dialog, modals) -> None:
    dialog.save_changes()
    assert not [m for m in modals.messages if m[0] == "critical"], modals.messages


def _cell_texts(dialog) -> list[str]:
    from PySide6.QtWidgets import QLabel

    return [label.text() for label in dialog.preview.hud_window.findChildren(QLabel)]


def test_a_rich_text_profile_shows_its_settings(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "plo_pro_html")
    assert dialog.presentation_mode_combo.currentData() == "rich"
    assert dialog.font_size_spin.value() == 10
    assert "PLO4Hud (fusion)" in dialog.hud_handler_label.text()
    assert "set per game" in dialog.hud_handler_label.text()
    assert dialog.preview.rich_text
    assert dialog.preview.hud_font_size == 10
    # Showing a profile is not an edit.
    assert not dialog.has_unsaved_changes()


def test_a_standard_profile_names_the_window_default_font(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "holdem_ring")
    assert dialog.presentation_mode_combo.currentData() == "standard"
    assert dialog.font_size_spin.value() == 0
    assert dialog.font_size_spin.text() == "Default (8 pt)"
    assert dialog.xpad_spin.value() == 1
    assert dialog.ypad_spin.value() == 0
    assert "ClassicHud (holdem, 2_holdem, irish" in dialog.hud_handler_label.text()
    assert not dialog.preview.rich_text
    assert not dialog.has_unsaved_changes()


def test_the_preview_follows_the_mode_and_the_font_size(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "holdem_ring")
    assert not any("font-weight:700" in text for text in _cell_texts(dialog))

    dialog.presentation_mode_combo.setCurrentIndex(dialog.presentation_mode_combo.findData("rich"))
    assert dialog.preview.rich_text
    assert any("font-weight:700" in text for text in _cell_texts(dialog))

    dialog.font_size_spin.setValue(13)
    assert dialog.preview.hud_font_size == 13
    dialog.font_size_spin.setValue(0)
    assert dialog.preview.hud_font_size == 8


def test_changing_a_control_is_an_unsaved_change(tmp_path, monkeypatch) -> None:
    dialog, _modals, _path = _editor(tmp_path, monkeypatch)
    profile = select_profile(dialog, "holdem_ring")
    dialog.ypad_spin.setValue(3)
    assert profile["ypad"] == 3
    assert dialog.has_unsaved_changes()
    dialog.ypad_spin.setValue(0)
    assert not dialog.has_unsaved_changes()


def test_rich_text_settings_are_saved_reloaded_and_cleared(tmp_path, monkeypatch) -> None:
    dialog, modals, path = _editor(tmp_path, monkeypatch)
    select_profile(dialog, "holdem_ring")
    dialog.presentation_mode_combo.setCurrentIndex(dialog.presentation_mode_combo.findData("rich"))
    dialog.font_size_spin.setValue(12)
    dialog.xpad_spin.setValue(3)
    dialog.ypad_spin.setValue(2)
    _save(dialog, modals)

    saved = reload_stat_set(path, "holdem_ring")
    assert (saved.rich_text, saved.font_size, saved.xpad, saved.ypad) == ("True", "12", 3, 2)

    dialog, modals, _path = _editor(tmp_path, monkeypatch, path)
    select_profile(dialog, "holdem_ring")
    assert dialog.presentation_mode_combo.currentData() == "rich"
    assert (dialog.font_size_spin.value(), dialog.xpad_spin.value(), dialog.ypad_spin.value()) == (12, 3, 2)
    assert not dialog.has_unsaved_changes()

    dialog.presentation_mode_combo.setCurrentIndex(dialog.presentation_mode_combo.findData("standard"))
    dialog.font_size_spin.setValue(0)
    _save(dialog, modals)
    import defusedxml.minidom

    doc = defusedxml.minidom.parse(str(path))
    node = next(n for n in doc.getElementsByTagName("ss") if n.getAttribute("name") == "holdem_ring")
    assert not node.hasAttribute("rich_text")
    assert not node.hasAttribute("font_size")
    assert node.getAttribute("xpad") == "3"


def test_the_rich_text_warning_shows_only_in_rich_mode(tmp_path, monkeypatch) -> None:
    path = config_copy(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('game_name="razz" aux="mucked, ClassicHud"', 'game_name="razz" aux="mucked, Simple_HUD"'),
        encoding="utf-8",
    )
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, path)
    select_profile(dialog, "stud_default")
    assert "Simple_HUD (razz)" in dialog.hud_handler_label.text()
    # Standard mode: the warning has no meaning and is hidden, not greyed.
    assert dialog.rich_text_support_label.isHidden()
    assert not dialog.font_size_spin.isHidden()
    assert dialog.font_size_spin.isEnabled()

    dialog.presentation_mode_combo.setCurrentIndex(dialog.presentation_mode_combo.findData("rich"))
    assert not dialog.rich_text_support_label.isHidden()
    assert "Simple_HUD" in dialog.rich_text_support_label.text()
    assert "ClassicHud (" not in dialog.rich_text_support_label.text()


def test_a_profile_no_game_uses_says_so(tmp_path, monkeypatch) -> None:
    import defusedxml.minidom

    node = defusedxml.minidom.parseString(
        '<ss name="orphan" rows="1" cols="1"><stat _rowcol="(1,1)" _stat_name="vpip"/></ss>'
    ).documentElement
    dialog, _modals, _path = _editor(tmp_path, monkeypatch, config_copy(tmp_path, [node]))
    select_profile(dialog, "orphan")
    assert "no game is mapped" in dialog.hud_handler_label.text()
