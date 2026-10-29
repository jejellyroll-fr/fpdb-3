"""Export the hands in view for solver review, as one whole-hand document (#448)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSortFilterProxyModel, Qt  # noqa: E402 - after the Qt availability probe
from PySide6.QtGui import QStandardItem, QStandardItemModel  # noqa: E402

from fpdb_3_legacy import hand_review_dialog  # noqa: E402
from fpdb_3_legacy.GuiHandViewer import GuiHandViewer  # noqa: E402
from fpdb_3_legacy.hand_review_payload import BatchExport  # noqa: E402

pytestmark = pytest.mark.qt


def test_the_report_says_how_many_were_exported_and_why_the_others_were_not(qtbot) -> None:
    report = hand_review_dialog.batch_report(BatchExport("/tmp/r.json", 480, {"unsupported_board": 20}))

    assert "480 hands exported to /tmp/r.json." in report
    assert "20 hands could not be described exactly" in report and "unsupported_board: 20" in report


def test_the_dialog_writes_where_the_user_chose_and_reports_it(qtbot, monkeypatch, tmp_path) -> None:
    target = tmp_path / "chosen.json"
    shown = []
    monkeypatch.setattr(hand_review_dialog.QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(target), ""))
    monkeypatch.setattr(hand_review_dialog.QMessageBox, "information", lambda _p, _t, text: shown.append(text))
    monkeypatch.setattr(
        hand_review_dialog, "export_hands", lambda hands, path, **_k: BatchExport(str(path), len(hands), {})
    )

    export = hand_review_dialog.export_hands_dialog(["hand"] * 3)

    assert export == BatchExport(str(target), 3, {}) and shown == ["3 hands exported to " + str(target) + "."]


def test_nothing_in_view_or_a_cancelled_save_writes_nothing(qtbot, monkeypatch) -> None:
    shown = []
    monkeypatch.setattr(hand_review_dialog.QMessageBox, "information", lambda _p, _t, text: shown.append(text))
    monkeypatch.setattr(hand_review_dialog.QFileDialog, "getSaveFileName", lambda *_a, **_k: ("", ""))

    assert hand_review_dialog.export_hands_dialog([]) is None and shown == ["No hands are in view to export."]
    assert hand_review_dialog.export_hands_dialog(["hand"]) is None


def test_the_hands_in_view_are_the_rows_the_filters_leave_in_their_order(qtbot) -> None:
    model = QStandardItemModel()
    for hand_id in (11, 12, 13):
        model.appendRow([QStandardItem(str(hand_id))])
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setFilterFixedString("1")  # every row
    proxy.sort(0, Qt.SortOrder.DescendingOrder)
    proxy.setFilterRegularExpression("^1[13]$")  # 12 filtered out
    viewer = SimpleNamespace(colnum={"HandId": 0}, filterModel=proxy, hands={11: "h11", 12: "h12", 13: "h13"})

    assert GuiHandViewer.hands_in_view(viewer) == ["h13", "h11"]
