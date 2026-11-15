"""The frameless main window's title bar must be its top row (#823).

On Linux and Windows fpdb draws its own title bar. The menu bar used to be
installed with ``QLayout.setMenuBar``, which reserves a strip *above* the layout
contents, so the menu bar sat over the title bar: the window buttons were not on
the top row and the row users drag had no move handler.

Building the whole ``fpdb`` window needs a profile and a database, so the test
compiles the real ``CustomTitleBar`` class and the ``fpdb`` window-chrome
methods out of ``fpdb.pyw`` and runs them on a bare ``QMainWindow``.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import CellType, CodeType, FunctionType, SimpleNamespace

import pytest
from PySide6 import QtCore, QtWidgets

pytestmark = pytest.mark.qt

# Read when the QApplication is created, not when PySide6 is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _namespace(platform: str) -> dict:
    """Globals for the extracted code: the Qt names it uses and a fake ``sys``."""
    namespace = {name: getattr(QtWidgets, name) for name in dir(QtWidgets) if name.startswith("Q")}
    namespace.update(Qt=QtCore.Qt, QPoint=QtCore.QPoint, sys=SimpleNamespace(platform=platform), _=lambda text: text)
    return namespace


_WINDOW_METHODS = ("_add_title_and_menu_bars", "menuBar")


def _class_def(name: str) -> ast.ClassDef:
    return next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == name)


def _build_class(name: str, base: type, methods: list[ast.FunctionDef], namespace: dict) -> type:
    """Make a ``base`` subclass whose methods are compiled from ``fpdb.pyw``.

    The methods are compiled inside a class body so zero-argument ``super()``
    gets its ``__class__`` cell, then turned into functions from their code
    objects, without running the module or class body.
    """
    class_node = ast.ClassDef(
        name=name,
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
        type_params=[],
    )
    module = ast.fix_missing_locations(ast.Module(body=[class_node], type_ignores=[]))
    compiled = compile(module, str(SOURCE), "exec")
    body_code = next(item for item in compiled.co_consts if isinstance(item, CodeType) and item.co_name == name)

    class_cell = CellType()
    nodes = {method.name: method for method in methods}
    attributes = {}
    for code in (item for item in body_code.co_consts if isinstance(item, CodeType)):
        assert set(code.co_freevars) <= {"__class__"}, code.co_freevars
        node = nodes[code.co_name]
        defaults = tuple(ast.literal_eval(default) for default in node.args.defaults) or None
        closure = (class_cell,) if code.co_freevars else None
        attributes[code.co_name] = FunctionType(code, namespace, code.co_name, defaults, closure)
    assert set(attributes) == set(nodes)

    cls = type(name, (base,), attributes)
    class_cell.cell_contents = cls
    return cls


def _window_class(platform: str) -> type[QtWidgets.QMainWindow]:
    """A ``QMainWindow`` carrying the real ``CustomTitleBar`` and chrome methods."""
    namespace = _namespace(platform)
    title_bar_methods = [node for node in _class_def("CustomTitleBar").body if isinstance(node, ast.FunctionDef)]
    namespace["CustomTitleBar"] = _build_class("CustomTitleBar", QtWidgets.QWidget, title_bar_methods, namespace)

    window_methods = [
        node for node in _class_def("fpdb").body if isinstance(node, ast.FunctionDef) and node.name in _WINDOW_METHODS
    ]
    assert sorted(method.name for method in window_methods) == sorted(_WINDOW_METHODS)
    return _build_class("_Window", QtWidgets.QMainWindow, window_methods, namespace)


def _build_window(platform: str) -> QtWidgets.QMainWindow:
    """Lay the window out the way ``fpdb.__init__`` does, down to the tab widget."""
    window = _window_class(platform)()
    window.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint)
    window.central_widget = QtWidgets.QWidget(window)
    window.central_layout = QtWidgets.QVBoxLayout(window.central_widget)
    window.central_layout.setContentsMargins(0, 0, 0, 0)
    window.central_layout.setSpacing(0)

    window._add_title_and_menu_bars()

    window.central_layout.addWidget(QtWidgets.QTabWidget())
    window.setCentralWidget(window.central_widget)
    # createMenuBar fills whatever menuBar() returns, after the layout is set up.
    window.menuBar().addMenu("Main")
    window.menuBar().addMenu("Viewers")
    window.resize(800, 600)
    window.show()
    QtWidgets.QApplication.processEvents()
    return window


@pytest.fixture
def window():
    win = _build_window("linux")
    yield win
    win.close()
    win.deleteLater()
    QtWidgets.QApplication.processEvents()


def _top_in_window(window: QtWidgets.QMainWindow, widget: QtWidgets.QWidget) -> int:
    return widget.mapTo(window, QtCore.QPoint(0, 0)).y()


def test_title_bar_sits_above_the_menu_bar(window) -> None:
    title_bar = window.custom_title_bar
    menu_bar = window.menuBar()

    assert _top_in_window(window, title_bar) == 0
    assert _top_in_window(window, menu_bar) >= title_bar.height()
    assert window.central_layout.indexOf(title_bar) == 0
    assert window.central_layout.indexOf(menu_bar) == 1


def test_the_filled_menu_bar_is_the_one_under_the_title_bar(window) -> None:
    # Moving QMainWindow's own menu bar into the layout makes menuBar() create
    # a second one at the top of the window, and the menus went there.
    menu_bars = window.findChildren(QtWidgets.QMenuBar)
    assert menu_bars == [window.menuBar()]
    assert [action.text() for action in window.menuBar().actions()] == ["Main", "Viewers"]
    assert window.central_layout.indexOf(window.menuBar()) == 1


def test_top_row_belongs_to_the_title_bar(window) -> None:
    # The row along the top edge is the one users grab to move the window, and
    # only the title bar has a move handler.
    title_bar = window.custom_title_bar
    for x in (2, window.width() // 2, window.width() - 80):
        hit = window.childAt(QtCore.QPoint(x, 2))
        assert hit is not None
        assert hit is title_bar or title_bar.isAncestorOf(hit), f"x={x}: {hit!r} is on the top row"


def test_window_buttons_are_on_the_top_row(window) -> None:
    title_bar = window.custom_title_bar
    menu_top = _top_in_window(window, window.menuBar())
    for button in (title_bar.btn_minimize, title_bar.btn_maximize, title_bar.btn_close):
        assert _top_in_window(window, button) < menu_top


def test_macos_branch_leaves_the_menu_bar_to_the_window() -> None:
    # macOS shows the native menu bar, so the menu bar stays out of the layout.
    win = _build_window("darwin")
    try:
        assert win.central_layout.indexOf(win.custom_title_bar) == 0
        assert win.central_layout.indexOf(win.menuBar()) == -1
    finally:
        win.close()
        win.deleteLater()
        QtWidgets.QApplication.processEvents()
