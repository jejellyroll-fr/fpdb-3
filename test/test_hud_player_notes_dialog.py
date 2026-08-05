"""Tests for Aux_Classic_Hud player notes dialog with visual cards."""

from __future__ import annotations

import os
import pytest

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_hud_player_notes_dialog_structure(qtbot, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog
    from fpdb_3_legacy.Aux_Classic_Hud import ClassicStat

    QApplication.instance() or QApplication([])

    stat = object.__new__(ClassicStat)
    stat.stat = "player_note"
    stat.aw = type("DummyAw", (), {"hud": type("DummyHud", (), {"config": None})()})()

    monkeypatch.setattr(stat, "get_player_id", lambda: 42)
    monkeypatch.setattr(stat, "get_player_name", lambda pid: "TestPlayer")
    monkeypatch.setattr(stat, "get_current_comment", lambda pid: "Manual test note")
    monkeypatch.setattr(
        stat,
        "get_generated_notes_list",
        lambda pid: [
            {
                "createdTs": "2026-08-03 20:44:41",
                "ruleId": "aof_omaha_all_in_shown",
                "noteText": "TestPlayer: all-in with a straight",
                "evidenceText": "flop=Th 9s Jd; hole=8h 7h 7d 2s; river=5c 4s",
            }
        ],
    )

    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(stat, "save_comment", lambda pid, comment: None)

    stat.open_comment_dialog(None)
