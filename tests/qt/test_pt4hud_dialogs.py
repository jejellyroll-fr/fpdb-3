"""The PT4 HUD import report and its Save as .fpdbhud package action (#614)."""

from __future__ import annotations

from pathlib import Path

import defusedxml.minidom
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402 - after the Qt availability probe

from fpdb_3_legacy import pt4hud_dialogs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "test" / "fixtures" / "generationpoker_3h.pt4hud"


def test_each_untranslated_stat_is_one_readable_line() -> None:
    lines = pt4hud_dialogs.untranslated_lines(
        [
            {"label": "3B", "section": "BU 3h", "pt4_name": "3Bet vs CO", "formula": ""},
            {"label": "", "section": "Villain Info 3H", "pt4_name": "sum(if[" + "x" * 300 + "])", "formula": ""},
        ]
    )

    assert lines[0] == "[BU 3h] 3B: 3Bet vs CO"
    assert lines[1].startswith("[Villain Info 3H] sum(if[")
    assert lines[1].endswith("…") and len(lines[1]) < 160


@pytest.mark.qt
def test_saving_the_package_writes_it_and_names_what_it_leaves_out(qtbot, tmp_path, monkeypatch) -> None:
    target = tmp_path / "out.fpdbhud"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, _title, text: shown.append(text))

    assert pt4hud_dialogs.save_package(None, str(FIXTURE)) == str(target)

    assert target.read_text(encoding="utf-8").lstrip().startswith("<?xml")
    (text,) = shown
    assert "19 PT4 stats" in text
    assert "Push Nash, Call Nash, DEF Explain" in text


@pytest.mark.qt
def test_a_cancelled_save_writes_nothing(qtbot, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))

    assert pt4hud_dialogs.save_package(None, str(FIXTURE)) is None
    assert list(tmp_path.iterdir()) == []


def shown_box(monkeypatch) -> list[QMessageBox]:
    boxes: list[QMessageBox] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: boxes.append(self) or 0)
    return boxes


@pytest.mark.qt
def test_importing_a_converted_package_names_the_stats_it_left_out(qtbot, tmp_path, monkeypatch) -> None:
    from fpdb_3_legacy import pt4hud

    xml, summary = pt4hud.to_package(str(FIXTURE))
    root = defusedxml.minidom.parseString(xml).documentElement
    boxes = shown_box(monkeypatch)

    pt4hud_dialogs.show_package_import(None, "GP 3H", root)

    (box,) = boxes
    assert "GP 3H" in box.text() and "19 of its stats" in box.text()
    assert box.detailedText().count("\n") == len(summary["untranslated"]) - 1
    assert "[BU 3h] T FvPROBE: Fold to T Probe Bet" in box.detailedText()


@pytest.mark.qt
def test_importing_an_ordinary_package_just_confirms(qtbot, monkeypatch) -> None:
    root = defusedxml.minidom.parseString('<fpdb_hud_package version="1.0"><ss name="mine"/></fpdb_hud_package>')
    boxes = shown_box(monkeypatch)

    pt4hud_dialogs.show_package_import(None, "mine", root.documentElement)

    (box,) = boxes
    assert "mine" in box.text() and "PokerTracker" not in box.text()
    assert box.detailedText() == ""
