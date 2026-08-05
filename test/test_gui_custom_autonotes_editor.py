"""Qt unit tests for GuiCustomAutoNotesEditor UI component."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_custom_autonotes_editor_creation_and_rule_actions(qtbot, tmp_path: Path):
    from fpdb_3_legacy.GuiCustomAutoNotesEditor import GuiCustomAutoNotesEditor
    from fpdb_3_legacy.user_autonotes_parser import save_user_autonotes_data

    QApplication.instance() or QApplication([])

    # Seed temporary custom rules file
    custom_path = tmp_path / "user_autonotes.json"
    initial_data = {
        "version": 1,
        "custom_rule_sets": [
            {
                "rule_set_id": "custom_user_rules",
                "name": "User Custom Rules",
                "enabled": True,
                "rules": [
                    {
                        "rule_id": "rule_initial",
                        "version": 1,
                        "name": "Initial Test Rule",
                        "note_template": "{player} tested initial",
                        "enabled": True,
                        "conditions": {"operator": "AND", "rules": [{"field": "game.base", "operator": "eq", "value": "holdem"}]},
                        "evidence": {"capture_hole": True},
                    }
                ],
            }
        ],
    }
    save_user_autonotes_data(initial_data, custom_path)

    # Instantiate editor widget
    editor = GuiCustomAutoNotesEditor(config=None)
    qtbot.addWidget(editor)

    # Verify initial tree population
    assert editor.tree.topLevelItemCount() >= 1

    # Test adding a new rule
    editor.on_new_rule()
    assert editor.current_rule_dict is not None
    assert "Custom Rule #" in editor.current_rule_dict["name"]

    # Test adding condition row
    initial_rows = len(editor.condition_rows)
    editor.on_add_condition_row()
    assert len(editor.condition_rows) == initial_rows + 1

    # Test duplicating a rule
    editor.on_duplicate_rule()
    assert "(Copy)" in editor.current_rule_dict["name"]


def test_custom_autonotes_workbench_tab_integration(qtbot):
    from fpdb_3_legacy.GuiAutoNotesWorkbench import GuiAutoNotesWorkbench

    QApplication.instance() or QApplication([])

    bench = GuiAutoNotesWorkbench(None)
    qtbot.addWidget(bench)

    # Check 4th tab exists and is Custom Rules
    assert bench.tabs.count() == 4
    assert bench.tabs.tabText(3) == "Custom Rules"
    assert hasattr(bench, "custom_rules_editor")


def test_custom_autonotes_editor_sandbox_evaluation(qtbot):
    from fpdb_3_legacy.GuiCustomAutoNotesEditor import GuiCustomAutoNotesEditor

    QApplication.instance() or QApplication([])

    editor = GuiCustomAutoNotesEditor(config=None)
    qtbot.addWidget(editor)

    editor.on_new_rule()

    hh = """Poker Hand #TM2917910999: Hold'em No Limit ($0.05/$0.10) - 2026/06/19 09:30:00
Table 'NLHGold12' 6-max Seat #3 is the button
Seat 1: Villain1 ($10.00 in chips)
Seat 4: Hero ($1.20 in chips)
Seat 5: SBPlayer ($10.00 in chips)
Seat 6: BBPlayer ($10.00 in chips)
SBPlayer: posts small blind $0.05
BBPlayer: posts big blind $0.10
*** HOLE CARDS ***
Dealt to Hero [As Ks]
Hero: raises $0.85 to $1.20 and is all-in
*** SUMMARY ***
Total pot $2.55 | Rake $0.10
"""
    editor.txt_sandbox_hh.setPlainText(hh)
    editor.on_evaluate_sandbox()

    assert "MATCH" in editor.lbl_sandbox_status.text()

