"""Offscreen interaction checks for the Hand Viewer starting-hand picker."""

from fpdb_3_legacy.GuiHandViewer import StartingHandPickerDialog


def test_starting_hand_picker_exposes_all_169_classes_and_shortcuts(qtbot):
    dialog = StartingHandPickerDialog()
    qtbot.addWidget(dialog)

    assert len(dialog._buttons) == 169
    dialog._select_matching(lambda hand: len(hand) == 2)
    assert len(dialog.selected_hands()) == 13

    dialog._select_matching(lambda hand: hand.endswith("s"))
    assert len(dialog.selected_hands()) == 78

    dialog._select_matching(lambda hand: hand[0] in "AKQJT" and hand[1] in "AKQJT")
    assert len(dialog.selected_hands()) == 25


def test_starting_hand_picker_restores_current_selection(qtbot):
    dialog = StartingHandPickerDialog({"AA", "AKs"})
    qtbot.addWidget(dialog)

    assert dialog.selected_hands() == {"AA", "AKs"}
    assert dialog._buttons["AA"].isChecked()
    assert not dialog._buttons["AKo"].isChecked()
