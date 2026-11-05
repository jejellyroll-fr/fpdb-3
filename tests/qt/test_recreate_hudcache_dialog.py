"""Clicking through the Rebuild HUD Cache dialog's date pickers.

Both "Cal" buttons were dead. PySide6 connects a ``functools.partial`` to the
argument-less ``clicked()`` overload, so ``__calendar_dialog`` never received the
``widget`` it required, and the TypeError vanished into Qt. Behind that, "Done"
pointed at a ``__get_date`` that an old cleanup had removed. Only a real click
shows either, so these tests click.

The methods come out of ``fpdb.pyw`` by AST, like the file's other tests: importing
it pulls in the whole application. ``exec()`` is replaced by a script, so a dialog
can never block the suite.
"""

from __future__ import annotations

import ast
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from types import CodeType, FunctionType, MethodType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

pytestmark = pytest.mark.qt

SOURCE = Path(__file__).resolve().parents[2] / "fpdb_3_legacy" / "fpdb.pyw"
METHODS = {"dia_recreate_hudcache", "__calendar_dialog", "__get_date"}
CACHE_START = QDate(2026, 1, 15)
PICKED = QDate(2026, 3, 9)

Script = Callable[[QDialog], None]


def _load_methods(scripts: list[Script]) -> dict[str, FunctionType]:
    """Return the dialog's methods from ``class fpdb``, under their mangled names."""

    class ScriptedDialog(QDialog):
        """Runs the next script instead of an event loop, then reports the result."""

        def exec(self) -> int:
            self.show()
            scripts.pop(0)(self)
            return self.result()

    namespace: dict[str, Any] = {
        "_": str,
        "log": logging.getLogger(__name__),
        "partial": partial,
        "QCalendarWidget": QCalendarWidget,
        "QDate": QDate,
        "QDateEdit": QDateEdit,
        "QDialog": ScriptedDialog,
        "QDialogButtonBox": QDialogButtonBox,
        "QHBoxLayout": QHBoxLayout,
        "QLabel": QLabel,
        "QPushButton": QPushButton,
        "QVBoxLayout": QVBoxLayout,
    }
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    source_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    source_class.bases = []
    source_class.body = [
        node for node in source_class.body if isinstance(node, ast.FunctionDef) and node.name in METHODS
    ]
    compiled = compile(ast.Module(body=[source_class], type_ignores=[]), str(SOURCE), "exec")
    class_code = next(item for item in compiled.co_consts if isinstance(item, CodeType))
    return {
        f"_fpdb{code.co_name}" if code.co_name.startswith("__") else code.co_name: FunctionType(
            code, namespace, code.co_name
        )
        for code in class_code.co_consts
        if isinstance(code, CodeType) and code.co_name in METHODS
    }


class _Window:
    """The main window, reduced to what the dialog's methods touch."""

    dia_recreate_hudcache: Callable[..., None]

    def __init__(self, scripts: list[Script]) -> None:
        self.db = SimpleNamespace(
            get_hero_hudcache_start=lambda: CACHE_START.toString("yyyy-MM-dd"),
            rebuild_cache=Mock(),
        )
        self.obtain_global_lock = Mock(return_value=True)
        self.release_global_lock = Mock()
        for name, method in _load_methods(scripts).items():
            setattr(self, name, MethodType(method, self))


def _click(button: QPushButton) -> None:
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def _buttons(dialog: QDialog, text: str) -> list[QPushButton]:
    return [button for button in dialog.findChildren(QPushButton) if button.text() == text]


def _confirm(dialog: QDialog) -> None:
    box = dialog.findChild(QDialogButtonBox)
    _click(box.button(QDialogButtonBox.StandardButton.Yes))


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        pytest.param(0, ("2026-03-09", "2026-01-15"), id="hero"),
        pytest.param(1, ("2026-01-15", "2026-03-09"), id="villains"),
    ],
)
@pytest.mark.usefixtures("qapp")
def test_picked_date_reaches_the_rebuild(row: int, expected: tuple[str, str]) -> None:
    """Each Cal button sets its own date, and the rebuild uses it."""
    calendars: list[QDialog] = []

    def confirm_dialog(dialog: QDialog) -> None:
        _click(_buttons(dialog, "Cal")[row])
        assert len(calendars) == 1, "the Cal button did not open a calendar"
        assert not calendars[0].isVisible(), "the Done button did not close the calendar"
        _confirm(dialog)

    def calendar_dialog(dialog: QDialog) -> None:
        calendars.append(dialog)
        dialog.findChild(QCalendarWidget).setSelectedDate(PICKED)
        _click(_buttons(dialog, "Done")[0])

    window = _Window([confirm_dialog, calendar_dialog])

    window.dia_recreate_hudcache(None, None)

    window.db.rebuild_cache.assert_called_once_with(*expected)
    window.release_global_lock.assert_called_once_with()


@pytest.mark.usefixtures("qapp")
def test_done_without_picking_keeps_the_date() -> None:
    """A new calendar selects today, which must not replace the cache's start."""
    opened: list[QDialog] = []

    def confirm_dialog(dialog: QDialog) -> None:
        _click(_buttons(dialog, "Cal")[0])
        assert len(opened) == 1, "the Cal button did not open a calendar"
        _confirm(dialog)

    def calendar_dialog(dialog: QDialog) -> None:
        opened.append(dialog)
        _click(_buttons(dialog, "Done")[0])

    window = _Window([confirm_dialog, calendar_dialog])

    window.dia_recreate_hudcache(None, None)

    window.db.rebuild_cache.assert_called_once_with("2026-01-15", "2026-01-15")


@pytest.mark.usefixtures("qapp")
def test_leaving_the_calendar_without_done_keeps_the_date() -> None:
    """Escape or the window's close button is the way out without choosing."""

    def confirm_dialog(dialog: QDialog) -> None:
        _click(_buttons(dialog, "Cal")[0])
        _confirm(dialog)

    def calendar_dialog(dialog: QDialog) -> None:
        dialog.findChild(QCalendarWidget).setSelectedDate(PICKED)
        dialog.reject()

    window = _Window([confirm_dialog, calendar_dialog])

    window.dia_recreate_hudcache(None, None)

    window.db.rebuild_cache.assert_called_once_with("2026-01-15", "2026-01-15")
