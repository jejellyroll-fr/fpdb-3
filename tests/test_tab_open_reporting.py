"""The tab-open profiler must report the interval a user actually waits.

Issue #249: ``report()`` was called inline, on the line after the tab was
added, so Qt had not yet delivered a single Paint event. Every production
line read ``not-painted`` and stopped timing at the tab bar. The instrument
built to catch a slow tab could not observe one -- and it still answered,
which is worse than staying silent.

These tests pin the two properties that were violated: a report waits for the
paint, and it is emitted exactly once whether or not the paint arrives.
"""

from __future__ import annotations

import ast
import logging
from importlib import import_module
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel, QWidget

from fpdb_3_legacy.ui_instrumentation import TabOpenProfiler

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _load_fpdb_method(name: str):
    """Compile one method out of fpdb.pyw without building the Qt main window."""
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    method = next(node for node in fpdb_class.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    compiled = compile(module, str(SOURCE), "exec")
    code = next(item for item in compiled.co_consts if isinstance(item, CodeType) and item.co_name == name)
    namespace = {
        "TabOpenProfiler": TabOpenProfiler,
        "import_module": import_module,
        "log": logging.getLogger("test-open-tab"),
    }
    function = FunctionType(code, namespace, name)
    # Keyword defaults live on the function object, not on its code, so a
    # function built this way demands every keyword-only argument at every call
    # site. Read them off the same AST rather than restating open_tab's
    # signature here, which would go stale the next time it grows a keyword.
    function.__kwdefaults__ = {
        arg.arg: ast.literal_eval(default)
        for arg, default in zip(method.args.kwonlyargs, method.args.kw_defaults, strict=True)
        if default is not None
    }
    return function


def _tab_methods() -> list[ast.FunctionDef]:
    """Every method of ``fpdb`` that opens a tab."""
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    return [node for node in fpdb_class.body if isinstance(node, ast.FunctionDef) and node.name.startswith("tab")]


def _calls(method: ast.FunctionDef, attr: str) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr
        for node in ast.walk(method)
    )


def test_every_tab_is_instrumented() -> None:
    """Lead 4 of #249: only 3 of ~12 tabs carried a profiler.

    A tab that opens without going through ``open_tab`` produces no timing at
    all, so if the lag were on that tab the log would be silent by
    construction. Opening a tab and measuring it are now the same call.
    """
    unmeasured = [
        method.name
        for method in _tab_methods()
        if _calls(method, "add_and_display_tab") and not _calls(method, "open_tab")
    ]

    assert unmeasured == [], f"ces onglets s'ouvrent sans être mesurés : {unmeasured}"


def test_no_tab_imports_its_page_itself() -> None:
    """A lazy import must go through ``open_tab``, which times it on its own.

    Lead 7 of #249 is whether the wait is the module coming out of the
    PyOxidizer blob or the widget being built. A tab that imports inside its
    own ``build`` folds both into ``construct=``, and the line can no longer
    tell them apart -- which is the shape the original report was captured in.
    """
    offenders = [
        method.name
        for method in _tab_methods()
        if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(method))
    ]

    assert offenders == [], f"ces onglets importent eux-mêmes, hors de la phase mesurée : {offenders}"


def test_no_tab_reports_inline() -> None:
    """An inline report() is the #249 defect; open_tab defers to the paint."""
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    offenders = [
        node.name
        for node in fpdb_class.body
        if isinstance(node, ast.FunctionDef) and _calls(node, "report") and node.name != "open_tab"
    ]

    assert offenders == []


class _RecordingLogger(logging.Logger):
    """Captures the formatted [PERF] lines instead of emitting them."""

    def __init__(self) -> None:
        super().__init__("test-tab-open")
        self.lines: list[str] = []
        self.levels: list[int] = []

    # Capture whichever call the profiler makes: it reports through log() now,
    # because only a slow open is a WARNING. A stub that intercepts one method
    # name says nothing about the code once it uses the other.
    def log(self, level, msg, *args, **kwargs) -> None:
        self.levels.append(level)
        self.lines.append(msg % args if args else msg)

    def warning(self, msg, *args, **kwargs) -> None:  # noqa: A002 - mirrors logging API
        self.log(logging.WARNING, msg, *args, **kwargs)


def test_reopening_a_single_instance_tab_builds_nothing() -> None:
    """A tab already open must not be rebuilt, watched, or waited on.

    ``add_and_display_tab`` discards the page when ``allow_multiple=False``
    and the tab exists, so building one would leave the paint watcher on a
    widget that is never shown: no paint would arrive, and the backstop would
    log a misleading ``not-painted total=10000ms`` ten seconds later.
    """
    open_tab = _load_fpdb_method("open_tab")
    built = []

    window = SimpleNamespace(
        nb_tab_names=["Version"],
        threads=[],
        add_and_display_tab=MagicMock(),
    )

    def build():
        built.append("called")
        return QLabel("contenu")

    result = open_tab(window, "Version", build, allow_multiple=False)

    assert result is None
    assert built == [], "la page ne doit pas être construite pour un onglet déjà ouvert"
    window.add_and_display_tab.assert_called_once_with(None, "Version", allow_multiple=False)


@pytest.mark.qt
def test_a_single_instance_tab_is_built_the_first_time(qtbot) -> None:
    """The early return must not swallow the genuine first open."""
    open_tab = _load_fpdb_method("open_tab")
    page = QLabel("contenu")
    qtbot.addWidget(page)

    window = SimpleNamespace(
        nb_tab_names=[],
        threads=[],
        add_and_display_tab=MagicMock(),
    )

    result = open_tab(window, "Version", lambda: page, allow_multiple=False)

    assert result is page
    window.add_and_display_tab.assert_called_once_with(page, "Version", allow_multiple=False)


def _window_showing(page) -> SimpleNamespace:
    """A stand-in main window whose add_and_display_tab shows the page."""
    return SimpleNamespace(
        nb_tab_names=[],
        threads=[],
        add_and_display_tab=MagicMock(side_effect=lambda *_args, **_kwargs: page.show()),
    )


@pytest.mark.qt
def test_the_import_is_timed_apart_from_the_construction(qtbot) -> None:
    """Lead 7 of #249 needs the two costs separated, not summed.

    The evidence in the report carried ``import=`` and ``construct=`` as
    distinct figures; folding the lazy import into ``build`` lost that split,
    and with it the only way to say from a log whether a translocated bundle
    is paying for resolving the module out of its embedded blob.
    """
    open_tab = _load_fpdb_method("open_tab")
    recorder = _RecordingLogger()
    open_tab.__globals__["log"] = recorder
    page = QLabel("contenu")
    qtbot.addWidget(page)
    received = []

    def build(module):
        received.append(module)
        return page

    result = open_tab(_window_showing(page), "Graphs", build, module="json")

    qtbot.waitUntil(lambda: bool(recorder.lines), timeout=5000)

    assert result is page
    assert received == [import_module("json")], "le module importé doit être passé à build"
    line = recorder.lines[0]
    assert "import=" in line
    assert line.index("import=") < line.index("construct=")


@pytest.mark.qt
def test_a_tab_without_a_lazy_module_reports_no_import_phase(qtbot) -> None:
    """Tabs imported at startup pay nothing here, and must not claim a phase."""
    open_tab = _load_fpdb_method("open_tab")
    recorder = _RecordingLogger()
    open_tab.__globals__["log"] = recorder
    page = QLabel("contenu")
    qtbot.addWidget(page)

    open_tab(_window_showing(page), "Hand Viewer", lambda: page)

    qtbot.waitUntil(lambda: bool(recorder.lines), timeout=5000)

    assert "import=" not in recorder.lines[0]
    assert "construct=" in recorder.lines[0]


@pytest.mark.qt
def test_reporting_inline_cannot_see_the_paint(qtbot) -> None:
    """The regression itself, stated as a test.

    This is what every production call site did. It is kept as a test so the
    difference with report_when_painted is visible rather than asserted.
    """
    widget = QWidget()
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()

    # No event-loop turn between show() and report(): exactly the old shape.
    timing = profiler.result()

    assert timing.first_paint_ms is None
    assert "not-painted" in timing.format()


@pytest.mark.qt
def test_report_when_painted_waits_for_the_first_paint(qtbot) -> None:
    log = _RecordingLogger()
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()
    profiler.report_when_painted(log)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)

    assert len(log.lines) == 1
    assert "first_paint=" in log.lines[0]
    assert "not-painted" not in log.lines[0]


@pytest.mark.qt
def test_a_widget_that_never_paints_still_reports_once(qtbot) -> None:
    """The backstop: a tab that never draws is the symptom, not a reason to go quiet."""
    log = _RecordingLogger()
    widget = QWidget()  # jamais show(), donc jamais peint
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    profiler.report_when_painted(log, timeout_ms=50)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)

    assert len(log.lines) == 1
    assert "not-painted" in log.lines[0]


@pytest.mark.qt
def test_the_report_is_not_emitted_twice(qtbot) -> None:
    """Paint and timeout can both fire; only one line may be written."""
    log = _RecordingLogger()
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    widget.show()
    profiler.report_when_painted(log, timeout_ms=10)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)
    qtbot.wait(120)  # laisse le backstop expirer après le paint

    assert len(log.lines) == 1


@pytest.mark.qt
def test_a_tab_closed_before_it_paints_does_not_crash(qtbot) -> None:
    """The backstop must die with the widget it was waiting on.

    A free-standing QTimer.singleShot outlives the tab and fires into a
    deleted C++ object, which aborted the interpreter instead of logging.
    """
    log = _RecordingLogger()
    widget = QWidget()
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_first_paint(widget)
    profiler.report_when_painted(log, timeout_ms=30)

    widget.deleteLater()
    widget.setParent(None)
    del widget
    qtbot.wait(120)  # le backstop aurait expiré ici

    # Rien n'est journalisé, et surtout rien ne plante.
    assert log.lines == []


@pytest.mark.qt
def test_stall_monitor_is_folded_into_the_same_line(qtbot) -> None:
    """Lead 2 of #249: the stall figure was only ever produced inside tests."""
    log = _RecordingLogger()
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Graphs")
    profiler.watch_ui_stalls(interval_ms=10)
    profiler.watch_first_paint(widget)
    widget.show()
    profiler.report_when_painted(log)

    qtbot.waitUntil(lambda: bool(log.lines), timeout=5000)

    assert "max_stall=" in log.lines[0]


@pytest.mark.qt
@pytest.mark.parametrize("with_monitor", [False, True])
def test_format_stays_greppable(qtbot, with_monitor: bool) -> None:
    widget = QLabel("contenu")
    qtbot.addWidget(widget)

    profiler = TabOpenProfiler("Ring Player Stats")
    if with_monitor:
        profiler.watch_ui_stalls(interval_ms=10)
    with profiler.phase("construct"):
        pass
    profiler.watch_first_paint(widget)
    widget.show()
    qtbot.waitUntil(lambda: profiler.result().first_paint_ms is not None, timeout=5000)

    line = profiler.result().format()

    assert line.startswith("tab='Ring Player Stats'")
    assert "construct=" in line
    assert "total=" in line
    assert ("max_stall=" in line) is with_monitor
