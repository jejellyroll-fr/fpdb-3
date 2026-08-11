"""Open three real tabs in one application and measure the event loop.

The third tab a user opens is reported as slow while every SQL timing behind
it comes back in tenths of a second. That gap is the point of this file: the
measurements that exonerated the queries were taken around the queries, and a
frozen window is not a slow query -- it is a Qt event loop that has not run.

So this builds the real thing. A real SQLite database from a throwaway
configuration, a real ``QTabWidget`` on screen, the three viewers the report
names, constructed and added exactly the way the menu handlers do it, with a
50 ms heartbeat running throughout. What the heartbeat records is how long the
loop went unable to run, which is the number a user would call a freeze.

Module imports are warmed before the measurement starts. Importing Matplotlib
and scanning the system fonts costs seconds once per process, is already
deliberately deferred out of startup, and would otherwise be the only thing
this test ever measured.
"""

from __future__ import annotations

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.ui_instrumentation import UI_STALL_BUDGET_MS, TabOpenProfiler, UiStallMonitor

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_TEMPLATE = os.path.join(REPO_ROOT, "HUD_config.xml")

pytestmark = pytest.mark.qt

#: Ceiling the known budget overrun is carried under until Filters is fixed.
#:
#: Deliberately loose. An event-loop stall measures everything the machine is
#: doing, not only this process: the same code measures ~150 ms alone and
#: comfortably past 300 ms inside a full suite run on a busy laptop. A guard
#: that fires on load is a guard that gets deleted, so this one only catches a
#: gross regression -- the honest, tight number is the budget above, which is
#: xfailed with its measurement rather than quietly widened.
KNOWN_STALL_CEILING_MS = 1000.0


@pytest.fixture
def config(tmp_path):
    """A throwaway configuration on its own SQLite database.

    Never the user's own HUD_config.xml: opening these tabs writes to the
    database the configuration points at.
    """
    cfg_path = tmp_path / "HUD_config.xml"
    shutil.copy(CONFIG_TEMPLATE, cfg_path)
    cfg = Configuration.Config(file=str(cfg_path))
    cfg.dir_database = str(tmp_path)
    cfg.add_db_parameters(db_name="tabs.db3", db_server="sqlite")
    cfg.db_selected = "tabs.db3"
    return cfg


@pytest.fixture
def sql(config):
    """The query list every viewer is constructed with."""
    from fpdb_3_legacy import SQL, Database

    database = Database.Database(config)
    queries = SQL.Sql(db_server="sqlite")
    yield queries
    database.disconnect()


def _viewers():
    """The three tab openings under test, warmed and ready to construct.

    Returned as callables taking the shared arguments, so the measured section
    contains construction and nothing else.
    """
    from fpdb_3_legacy import GuiGraphViewer, GuiRingPlayerStats, GuiSessionViewer

    return (
        ("Graphs", lambda config, sql, window, colors: GuiGraphViewer.GuiGraphViewer(sql, config, window, colors)),
        (
            "Ring Player Stats",
            lambda config, sql, window, _colors: GuiRingPlayerStats.GuiRingPlayerStats(config, sql, window),
        ),
        (
            "Session Stats",
            lambda config, sql, window, colors: GuiSessionViewer.GuiSessionViewer(
                config,
                sql,
                window,
                window,
                colors=colors,
            ),
        ),
    )


@pytest.fixture
def tab_host(qtbot):
    """A shown QTabWidget standing in for the main window's notebook."""
    from PySide6.QtWidgets import QTabWidget

    widget = QTabWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 600)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _open_three_tabs(qtbot, tab_host, config, sql):
    """Open the three tabs in order, returning their timings and the monitor."""
    colors = {
        "background": "#000000",
        "foreground": "#ffffff",
        "grid": "#444444",
        "line_up": "#00ff00",
        "line_down": "#ff0000",
        "line_showdown": "#00ffff",
        "line_nonshowdown": "#ffff00",
        "line_ev": "#ff00ff",
        "line_hands": "#ffffff",
    }
    viewers = _viewers()  # warms the imports outside the measured section

    monitor = UiStallMonitor()
    monitor.start()
    qtbot.wait(200)  # a quiet baseline: these ticks must all be on time

    timings = []
    for name, build in viewers:
        profiler = TabOpenProfiler(name)
        with profiler.phase("construct"):
            page = build(config, sql, tab_host, colors)
        profiler.watch_first_paint(page)
        with profiler.phase("add_tab"):
            index = tab_host.addTab(page, name)
            tab_host.setCurrentIndex(index)
        qtbot.waitUntil(lambda p=page: p.isVisible(), timeout=5000)
        qtbot.wait(300)  # let the first paint and any deferred work happen
        timings.append(profiler.result())

    monitor.stop()
    return timings, monitor


def test_three_tabs_open_in_one_application(qtbot, tab_host, config, sql) -> None:
    """All three viewers really exist as tabs, and each one paints."""
    timings, _monitor = _open_three_tabs(qtbot, tab_host, config, sql)

    assert tab_host.count() == 3
    assert [tab_host.tabText(i) for i in range(3)] == ["Graphs", "Ring Player Stats", "Session Stats"]
    unpainted = [timing.name for timing in timings if timing.first_paint_ms is None]
    assert not unpainted, f"tabs added but never painted: {unpainted}"


@pytest.mark.xfail(
    reason=(
        "Known: opening these tabs blocks the Qt event loop for ~110-150ms. Measured cause is "
        "Filters.Filters(db), 84ms of GuiGraphViewer's 97ms construction, built synchronously by "
        "each of the three tabs. Not strict because the stall straddles the budget and passes on a "
        "fast run. Delete this marker with the fix; test_opening_three_tabs_does_not_get_worse "
        "guards the meantime."
    ),
    strict=False,
)
def test_opening_three_tabs_never_freezes_the_ui(qtbot, tab_host, config, sql) -> None:
    """No single stretch of frozen UI while the three tabs are opened.

    The threshold is the one in ``ui_instrumentation``: past about 100 ms a
    click stops feeling answered. Failure prints the phase breakdown, because
    a regression here is only actionable with the phase that caused it.
    """
    timings, monitor = _open_three_tabs(qtbot, tab_host, config, sql)

    over_budget = monitor.stalls_over(UI_STALL_BUDGET_MS)
    breakdown = "\n".join(timing.format() for timing in timings)
    assert not over_budget, (
        f"UI event loop blocked for {[f'{stall:.0f}ms' for stall in over_budget]} "
        f"(budget {UI_STALL_BUDGET_MS:.0f}ms, worst {monitor.max_stall_ms:.0f}ms)\n{breakdown}"
    )


def test_opening_three_tabs_does_not_get_worse(qtbot, tab_host, config, sql) -> None:
    """The known block must not grow while it is being carried.

    The budget above is the goal and is not met today. This is the line that
    has to stay green: a change that turns the measured ~150 ms into whole
    seconds is a regression even though the budget was already missed. See
    ``KNOWN_STALL_CEILING_MS`` for why it is set as loosely as it is.
    """
    timings, monitor = _open_three_tabs(qtbot, tab_host, config, sql)

    breakdown = "\n".join(timing.format() for timing in timings)
    assert monitor.max_stall_ms <= KNOWN_STALL_CEILING_MS, (
        f"UI block grew to {monitor.max_stall_ms:.0f}ms, past the {KNOWN_STALL_CEILING_MS:.0f}ms "
        f"ceiling the known {UI_STALL_BUDGET_MS:.0f}ms overrun is carried under\n{breakdown}"
    )


def test_third_tab_is_not_slower_than_the_first_two(qtbot, tab_host, config, sql) -> None:
    """Opening the third tab must not cost more than the two before it.

    This is the shape of the original report: the first two tabs open, the
    third one hangs. A per-tab budget would only encode today's hardware, so
    what is asserted is the relation the report describes.
    """
    timings, _monitor = _open_three_tabs(qtbot, tab_host, config, sql)

    first_two = timings[0].total_ms + timings[1].total_ms
    third = timings[2].total_ms
    breakdown = "\n".join(timing.format() for timing in timings)
    assert third <= first_two, f"the third tab alone cost more than the first two together\n{breakdown}"
