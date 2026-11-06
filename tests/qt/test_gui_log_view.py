"""Help ▸ Log Messages, driven for real (#456): open it, filter, copy."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")

from fpdb_3_legacy.GuiLogView import GuiLogView  # noqa: E402

pytestmark = pytest.mark.qt


def _write_log(path, records) -> None:
    path.write_text(
        "".join(
            json.dumps({"asctime": f"2026-10-31 18:00:0{n}", "funcName": "run", **record}) + "\n"
            for n, record in enumerate(records)
        ),
        encoding="utf-8",
    )


@pytest.fixture
def window(qtbot, tmp_path):
    _write_log(
        tmp_path / "fpdb-log.txt",
        [
            {"levelname": "INFO", "module": "Importer", "message": "imported 3 hands"},
            {"levelname": "DEBUG", "module": "Importer", "message": "cursor opened"},
            {"levelname": "ERROR", "module": "HUD_main", "message": "table lost"},
        ],
    )
    _write_log(tmp_path / "HUD-log.txt", [{"levelname": "WARNING", "module": "Hud", "message": "late seat"}])
    os.utime(tmp_path / "HUD-log.txt", (1_700_000_000, 1_700_000_000))

    view = GuiLogView(SimpleNamespace(dir_log=str(tmp_path)), None, None)
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: view.proxy_model.rowCount() == 3)
    return view


def _shown(view) -> list[str]:
    model = view.proxy_model
    return [model.data(model.index(row, 4)) for row in range(model.rowCount())]


def test_it_opens_on_the_newest_log_with_every_record(window) -> None:
    assert window.logfile.endswith("fpdb-log.txt")
    assert sorted(_shown(window)) == ["cursor opened", "imported 3 hands", "table lost"]


def test_the_hud_log_is_offered_too(window, qtbot) -> None:
    labels = [window.logfile_combo.itemText(i) for i in range(window.logfile_combo.count())]
    assert [label.split(" (")[0] for label in labels] == ["fpdb-log.txt", "HUD-log.txt"]

    window.logfile_combo.setCurrentIndex(1)

    qtbot.waitUntil(lambda: _shown(window) == ["late seat"])


def test_unticking_a_level_and_typing_a_module_filter_the_rows(window) -> None:
    window.filter_debug.setChecked(False)
    assert sorted(_shown(window)) == ["imported 3 hands", "table lost"]

    window.module_filter_edit.setText("hud")
    assert _shown(window) == ["table lost"]


def test_the_selection_is_copied_tab_separated(window) -> None:
    from PySide6.QtWidgets import QApplication

    window.module_filter_edit.setText("hud")
    window.listview.selectAll()

    window.copy_to_clipboard()

    assert QApplication.clipboard().text() == "ERROR\t2026-10-31 18:00:02\tHUD_main\trun\ttable lost\n"
