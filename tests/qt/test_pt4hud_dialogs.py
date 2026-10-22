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


def shown(monkeypatch) -> list[tuple[str, str]]:
    """Every QMessageBox.information shown, as (title, text)."""
    boxes: list[tuple[str, str]] = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text, *a, **k: boxes.append((title, text)))
    return boxes


@pytest.mark.qt
def test_the_import_report_lists_every_untranslated_stat(qtbot, monkeypatch) -> None:
    from fpdb_3_legacy import pt4hud

    _xml, summary = pt4hud.to_package(str(FIXTURE))
    boxes = shown(monkeypatch)

    pt4hud_dialogs.show_import_summary(None, {**summary, "charts": ["Push Nash"], "popup": "x charts"})

    ((title, text),) = boxes
    assert title == "PT4 HUD imported"
    assert "30 stats translated" in text and "19 PT4 stats have no fpdb equivalent" in text
    assert "[BU 3h] T FvPROBE: Fold to T Probe Bet" in text


@pytest.mark.qt
def test_a_long_list_is_cut_with_a_count_of_the_rest(qtbot) -> None:
    stats = [{"label": f"S{i}", "section": "BU 3h", "pt4_name": f"Stat {i}", "formula": ""} for i in range(40)]

    text = pt4hud_dialogs.listed(stats)

    assert text.count("\n") == 25
    assert text.endswith("… and 15 more")


@pytest.mark.qt
def test_importing_a_converted_package_names_the_stats_it_left_out(qtbot, monkeypatch) -> None:
    from fpdb_3_legacy import pt4hud

    xml, _summary = pt4hud.to_package(str(FIXTURE))
    root = defusedxml.minidom.parseString(xml).documentElement
    boxes = shown(monkeypatch)

    pt4hud_dialogs.show_package_import(None, "GP 3H", root)

    ((title, text),) = boxes
    assert title == "Import Successful"
    assert "GP 3H" in text and "19 of its stats" in text
    assert "[BU 3h] T FvPROBE: Fold to T Probe Bet" in text


@pytest.mark.qt
def test_importing_an_ordinary_package_just_confirms(qtbot, monkeypatch) -> None:
    root = defusedxml.minidom.parseString('<fpdb_hud_package version="1.0"><ss name="mine"/></fpdb_hud_package>')
    boxes = shown(monkeypatch)

    pt4hud_dialogs.show_package_import(None, "mine", root.documentElement)

    assert boxes == [("Import Successful", "HUD profile 'mine' successfully imported!")]


@pytest.mark.qt
def test_converting_picks_a_layout_then_saves_the_package(qtbot, tmp_path, monkeypatch) -> None:
    target = tmp_path / "converted.fpdbhud"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(FIXTURE), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    shown(monkeypatch)

    assert pt4hud_dialogs.convert_to_package(None) == str(target)
    assert target.exists()


@pytest.mark.qt
def test_converting_nothing_when_no_layout_is_picked(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    assert pt4hud_dialogs.convert_to_package(None) is None
