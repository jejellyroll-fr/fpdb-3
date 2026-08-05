"""The logger dev window: the tool you reach for when a log has gone quiet.

It lists every registered logger, lets a level be changed on the spot, and
saves or exports the result. None of that is exercised by the rest of the
suite, and a dev tool that lies about levels is worse than none.

The window is not itself a QWidget: it holds its QDialog and its controls as
attributes, so the dialog is what qtbot is given.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt

import fpdb_3_legacy.loggingFpdb as logging_fpdb

pytestmark = pytest.mark.qt


@pytest.fixture(autouse=True)
def isolate_logger_config(tmp_path_factory, monkeypatch):
    """Keep the window's Save out of the configuration of whoever runs this."""
    real_log_config = logging_fpdb.LogConfig
    sandbox = tmp_path_factory.mktemp("logger-config")

    def in_sandbox(config_dir: str | None = None):
        return real_log_config(config_dir=config_dir or str(sandbox))

    monkeypatch.setattr(logging_fpdb, "LogConfig", in_sandbox)
    monkeypatch.setattr(logging_fpdb, "_log_config", in_sandbox())
    monkeypatch.setattr(logging_fpdb._logger_registry, "_config", in_sandbox())
    return sandbox


@pytest.fixture(autouse=True)
def preserve_logger_levels():
    """Restore every level the tool changes."""
    saved = {
        name: lg.level
        for name, lg in logging.root.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }
    yield
    for name, level in saved.items():
        existing = logging.root.manager.loggerDict.get(name)
        if isinstance(existing, logging.Logger):
            existing.setLevel(level)


@pytest.fixture
def tool(qtbot, isolate_logger_config) -> Any:
    window = logging_fpdb.LoggerDevTool()
    window.config = logging_fpdb.LogConfig(config_dir=str(isolate_logger_config))
    qtbot.addWidget(window.dialog)
    return window


def rows(tool: Any) -> list[str]:
    return [
        tool.tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
        for index in range(tool.tree.topLevelItemCount())
    ]


def visible_rows(tool: Any) -> list[str]:
    return [
        tool.tree.topLevelItem(index).data(0, Qt.ItemDataRole.UserRole)
        for index in range(tool.tree.topLevelItemCount())
        if not tool.tree.topLevelItem(index).isHidden()
    ]


def test_the_window_lists_the_registered_loggers(tool) -> None:
    assert rows(tool)
    assert set(rows(tool)) <= set(logging_fpdb.get_logger_registry().get_all_loggers())


def test_searching_hides_everything_that_does_not_match(tool) -> None:
    tool.search_edit.setText("no-logger-is-called-this")

    tool._filter_loggers()

    assert visible_rows(tool) == []


def test_clearing_the_search_brings_every_logger_back(tool) -> None:
    tool.search_edit.setText("no-logger-is-called-this")
    tool._filter_loggers()

    tool.search_edit.setText("")
    tool._filter_loggers()

    assert visible_rows(tool) == rows(tool)


def test_searching_keeps_the_loggers_that_match(tool) -> None:
    target = rows(tool)[0]
    tool.search_edit.setText(target)

    tool._filter_loggers()

    assert target in visible_rows(tool)


def test_refreshing_rebuilds_the_list(tool) -> None:
    before = rows(tool)

    tool._refresh_loggers()

    assert rows(tool) == before


def test_changing_a_level_reaches_the_logger(tool) -> None:
    # The whole point of the window: a level set here must take effect.
    target = rows(tool)[0]

    tool._change_logger_level(target, "DEBUG")

    assert logging.getLogger(target).level == logging.DEBUG


def test_an_unknown_level_name_falls_back_rather_than_crashing(tool) -> None:
    target = rows(tool)[0]

    tool._change_logger_level(target, "NOT-A-LEVEL")

    assert logging.getLogger(target).level == logging.INFO


def test_resetting_puts_every_logger_back(tool) -> None:
    target = rows(tool)[0]
    tool._change_logger_level(target, "DEBUG")

    from PySide6.QtWidgets import QMessageBox

    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), patch.object(
        QMessageBox, "information"
    ):
        tool._reset_all_loggers()

    assert logging.getLogger(target).level != logging.DEBUG


def test_the_configuration_can_be_saved(tool) -> None:
    with patch.object(logging_fpdb.QMessageBox, "information") as told, patch.object(
        logging_fpdb.QMessageBox, "warning"
    ) as failed:
        tool._save_config()

    assert told.called
    assert not failed.called


def test_exporting_writes_the_configuration_as_json(tool, tmp_path) -> None:
    target = tmp_path / "exported.json"

    with patch.object(logging_fpdb.QFileDialog, "getSaveFileName", return_value=(str(target), "")), patch.object(
        logging_fpdb.QMessageBox, "information"
    ), patch.object(logging_fpdb.QMessageBox, "critical"):
        tool._export_config()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["loggers"]
    assert "exported_from" in payload


def test_cancelling_the_export_writes_nothing(tool, tmp_path) -> None:
    with patch.object(logging_fpdb.QFileDialog, "getSaveFileName", return_value=("", "")), patch.object(
        logging_fpdb.QMessageBox, "information"
    ):
        tool._export_config()

    assert list(tmp_path.iterdir()) == []


def test_an_exported_configuration_can_be_imported_back(tool, tmp_path) -> None:
    target = tmp_path / "exported.json"
    with patch.object(logging_fpdb.QFileDialog, "getSaveFileName", return_value=(str(target), "")), patch.object(
        logging_fpdb.QMessageBox, "information"
    ), patch.object(logging_fpdb.QMessageBox, "critical"):
        tool._export_config()

    with patch.object(logging_fpdb.QFileDialog, "getOpenFileName", return_value=(str(target), "")), patch.object(
        logging_fpdb.QMessageBox, "information"
    ) as told, patch.object(logging_fpdb.QMessageBox, "warning") as failed:
        tool._import_config()

    assert told.called
    assert not failed.called


def test_importing_a_file_that_is_not_there_is_reported(tool, tmp_path) -> None:
    absent = tmp_path / "nowhere.json"

    with patch.object(logging_fpdb.QFileDialog, "getOpenFileName", return_value=(str(absent), "")), patch.object(
        logging_fpdb.QMessageBox, "information"
    ) as told, patch.object(logging_fpdb.QMessageBox, "warning") as failed:
        tool._import_config()

    assert failed.called
    assert not told.called


def test_showing_the_window_runs_until_it_is_closed(tool) -> None:
    # show() is dialog.exec(): it blocks until the dialog closes, so the close
    # has to be queued before it is called.
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    QTimer.singleShot(0, tool.dialog.accept)

    assert tool.show() == QDialog.DialogCode.Accepted


def test_the_helper_builds_and_shows_the_window(qtbot, isolate_logger_config) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    def close_it() -> None:
        for widget in QApplication.topLevelWidgets():
            if widget.isVisible() and widget.isModal():
                widget.accept()

    QTimer.singleShot(0, close_it)

    assert logging_fpdb.show_logger_dev_tool() is not None
