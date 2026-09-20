#!/usr/bin/env python3
"""Render fpdb's screens to PNG for the wiki, from the demo database.

Screenshots taken with a screen-capture tool carry whatever else was on the
desktop and have to be retaken by hand every release. Qt can draw a widget into
an image directly, so this builds each view against the demo database and grabs
it -- no window manager, no desktop chrome, no cursor, and the same result every
run.

    python tools/make_demo_workspace.py              # once, builds the workspace
    python tools/capture_wiki_screenshots.py --config ~/fpdb-demo/HUD_config.xml

A workspace built by ``tools/make_demo_db.py`` alone still works: it has the
database but no ``demo_examples.json``, and the Research screenshots then fall
back to the example questions the workspace tool ships.

Output lands in ``--out`` (default ``wiki-images/``), one PNG per view, ready to
drop into the wiki's ``Images/`` directory.

#333 added the analytics screens: the Research workbench's first-open state, one
result per view, the hands behind a row, and HUD Preferences on its dynamic
panel tab. Those are captured by driving the real widgets -- ``_fill_builder``
plus ``run_query`` is what clicking a preset does -- so the picture is of the
path a user takes. The example question for each Research view is read from the
workspace's own ``demo_examples.json``, so a screenshot cannot end up showing a
question the workspace does not document.

Two screens are deliberately out of reach of a headless grab, and the run says
so rather than pretending otherwise:

* a **live HUD** or a **popup** needs a table window with seats to hang from, so
  those are captured by hand against the same workspace, following the same
  instructions the README gives;
* the **dynamic panel** that results from a live hand needs the hand feed, so the
  headless shot shows the editor and its preview instead, which is what a reader
  can act on anyway.

Every player in these images is invented -- see ``tools/make_demo_db.py`` -- so
nothing here needs redacting. That is the whole point of going through the demo
database rather than the user's own.

Views that cannot be built headlessly are skipped with a reason rather than
failing the run: the useful output is the set that did render.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from functools import partial
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Final

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)

# Qt must render somewhere. "offscreen" keeps windows off the user's display
# while still producing real pixels for grab().
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DEFAULT_CONFIG = Path.home() / "fpdb-demo" / "HUD_config.xml"
DEFAULT_OUT = REPO / "wiki-images"
SIZE = (1400, 820)

# One screenshot per Research view (#331), paired with the view id the
# workbench offers. The filenames are what the wiki and the README link to, so
# the order here is the order a reader meets them.
RESEARCH_SHOTS: Final[tuple[tuple[str, str], ...]] = (
    ("research-summary.png", "summary"),
    ("research-table.png", "table"),
    ("research-frequencies.png", "frequencies"),
    ("research-sizing.png", "sizing"),
    ("research-position.png", "position"),
    ("research-board.png", "board"),
    ("research-range.png", "range"),
    ("research-hand-strength.png", "hand_strength"),
    ("research-profit.png", "profit"),
)

# The view whose hands are worth showing beside it: a grouped result with a
# readable row count, and a group every workspace has.
DRILL_VIEW: Final = "table"
DRILL_GROUP: Final[dict[str, Any]] = {"street": "flop"}

# How long a screenshot waits for a worker thread. Long enough for a query over
# a full demo database on a slow machine, short enough that a wedged worker
# fails the run rather than hanging it.
WORKER_TIMEOUT: Final = 60.0


def theme_colors() -> dict[str, str]:
    """The colour set the graph views expect, matching the application default."""
    return {
        "background": "#1E222A",
        "foreground": "#C8CDD4",
        "grid": "#3A4049",
        "line_showdown": "#4ADE80",
        "line_nonshowdown": "#FF6B6B",
        "line_ev": "#4CC9F0",
        "line_hands": "#F2C14E",
        "line_up": "#4ADE80",
        "line_down": "#FF6B6B",
    }


def make_stub_window(config, sql):
    """A stand-in main window for views that call back into their parent.

    It has to be a real ``QWidget``: the views subclass ``QSplitter`` and hand
    this straight to Qt as their parent.
    """
    from PySide6.QtWidgets import QMainWindow

    class StubMainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.config = config
            self.sql = sql
            self.threads: list = []

        def get_theme_colors(self) -> dict[str, str]:
            return theme_colors()

        def add_and_display_tab(self, *_args, **_kwargs) -> None:
            pass

        def release_global_lock(self, *_args, **_kwargs) -> None:
            pass

    return StubMainWindow()


def settle(widget: Any, attribute: str, timeout: float = WORKER_TIMEOUT) -> bool:
    """Spin the event loop until ``widget``'s worker attribute is gone.

    Returns whether it went away. The screenshots run on one thread, so the
    worker's signal is only delivered while this loop keeps handing control
    back to Qt -- waiting on the thread object alone would deadlock the grab.
    """
    from PySide6.QtWidgets import QApplication

    deadline = monotonic() + timeout
    while getattr(widget, attribute, None) is not None and monotonic() < deadline:
        QApplication.processEvents()
        sleep(0.01)
    QApplication.processEvents()
    return getattr(widget, attribute, None) is None


def view_index(widget: Any, view_id: str) -> int:
    """The view picker's index for one view id, or ``-1`` when it has none."""
    for index in range(widget.view_combo.count()):
        if widget.view_combo.itemData(index) == view_id:
            return index
    return -1


def tab_index(tabs: Any, needle: str) -> int | None:
    """The first tab whose label contains ``needle``, or ``None``."""
    for index in range(tabs.count()):
        if needle.lower() in tabs.tabText(index).lower():
            return index
    return None


def grab(widget, path: Path, size: tuple[int, int] = SIZE) -> None:
    """Lay the widget out at ``size`` and write its pixels to ``path``."""
    from PySide6.QtWidgets import QApplication

    widget.resize(*size)
    widget.show()
    # Two passes: the first lets deferred layout and any queued model refresh
    # run, the second lets whatever that produced be laid out in turn.
    for _ in range(2):
        QApplication.processEvents()
    widget.grab().save(str(path))
    widget.hide()


def build_views(config, sql, window, config_path: Path):  # noqa: C901 - each small branch is one independent screenshot factory
    """``(filename, factory)`` for every view worth a picture.

    Factories are lazy so one view failing to import or build does not take the
    rest of the run with it.
    """
    from fpdb_3_legacy import (
        Database,
        GuiAutoNotesWorkbench,
        GuiGraphViewer,
        GuiHandViewer,
        GuiOpponentsReport,
        GuiReplayer,
        GuiSessionViewer,
        GuiStatsInfo,
    )
    from fpdb_3_legacy.modern_hud_preferences import ModernHudPreferences
    from fpdb_3_legacy.ring_stats import GuiRingPlayerStats

    def ring_player_stats():
        view = GuiRingPlayerStats(config, sql, window)
        view.refreshStats()
        return view

    def graph_viewer():
        view = GuiGraphViewer.GuiGraphViewer(sql, config, window, colors=theme_colors())
        view.generateGraph(None)
        return view

    def session_viewer():
        view = GuiSessionViewer.GuiSessionViewer(config, sql, window, window, colors=theme_colors())
        view.refreshStats(None)
        return view

    def opponents_report():
        view = GuiOpponentsReport.GuiOpponentsReport(config, sql, window)
        view.refreshStats()
        return view

    def hand_viewer():
        view = GuiHandViewer.GuiHandViewer(config, sql, window)
        view.loadHands(None)
        return view

    def hand_replayer():
        database = Database.Database(config, sql=sql)
        database.cursor.execute(
            """
            SELECT ha.handId
            FROM HandsActions ha
            JOIN Players p ON p.id = ha.playerId
            WHERE p.name = ?
            GROUP BY ha.handId
            ORDER BY MAX(ha.amount) DESC
            LIMIT 1
            """,
            ("Hero",),
        )
        row = database.cursor.fetchone()
        if row is None:
            raise RuntimeError("the demo database has no replayable hero hand")

        view = GuiReplayer.GuiReplayer(config, sql, window, [int(row[0])], db=database)
        view.play_hand(0)

        # Stop on a hero decision facing a bet so the decision card contains
        # useful pot-odds/equity information instead of merely showing the deal.
        target = 0
        for index, state in enumerate(view.states):
            frame = view._frame_from_state(state)
            hero = next((player for player in frame.players if player.name == view.Heroes), None)
            max_chips = max((player.chips for player in frame.players if player.action != "folds"), default=0)
            if view._next_actor_name(index) == view.Heroes and hero is not None and max_chips > hero.chips:
                target = index
                break
        view.stateSlider.setValue(target)
        view.update()
        return view

    def hud_preferences():
        return ModernHudPreferences(config, window)

    def auto_notes():
        from PySide6.QtWidgets import QApplication

        view = GuiAutoNotesWorkbench.GuiAutoNotesWorkbench(config, window)
        view.db_limit_spin.setValue(200)
        view.run_database_dry_run()
        deadline = monotonic() + 30
        while view.worker_thread is not None and view.worker_thread.isRunning() and monotonic() < deadline:
            QApplication.processEvents()
            sleep(0.01)
        QApplication.processEvents()
        return view

    views = [
        ("ring-player-stats.png", ring_player_stats),
        ("graphs.png", graph_viewer),
        ("session-stats.png", session_viewer),
        ("opponents-report.png", opponents_report),
        ("hand-viewer.png", hand_viewer),
        ("hand-replayer.png", hand_replayer),
        ("hud-preferences.png", hud_preferences),
        ("auto-notes-workbench.png", auto_notes),
        ("stats-guide.png", lambda: GuiStatsInfo.GuiStatsInfo(config, window)),
    ]
    return views + build_research_views(config, sql, window, config_path)


def workspace_questions(config_path: Path) -> dict[str, dict[str, Any]]:
    """The question the workspace records for each view, by view id (#333).

    A workspace is built once and photographed later, and the catalogue can move
    in between. Driving the view alone would then photograph a question the
    workspace never measured, which is the thing the screenshots are supposed to
    document. A workspace built by ``tools/make_demo_db.py`` alone has no such
    file, and the shipped view is what gets photographed there.
    """
    path = Path(config_path).expanduser().resolve().parent / "demo_examples.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload.get("views") if isinstance(payload, dict) else None
    return {
        str(entry["view"]): dict(entry["preset"])
        for entry in entries or ()
        if isinstance(entry, dict) and entry.get("view") and isinstance(entry.get("preset"), dict)
    }


def build_research_views(config, sql, window, config_path: Path):  # noqa: C901 - one small factory per screenshot
    """``(filename, factory)`` for the analytics screens (#333).

    Kept apart from the rest of the list because of what it needs that they do
    not: a database connection held across several widgets, and an example
    question per view, read from the workspace the configuration points at.
    """
    from fpdb_3_legacy import Database, GuiResearchBrowser
    from fpdb_3_legacy.modern_hud_preferences import ModernHudPreferences

    state: dict[str, Any] = {}
    recorded = workspace_questions(config_path)

    def research_db():
        """One connection shared by every Research screenshot.

        Each factory builds its own widget, and a widget handed no database
        would open its own: sharing one keeps the run to a single connection
        instead of one per picture.
        """
        if "db" not in state:
            state["db"] = Database.Database(config, sql=sql)
        return state["db"]

    def research_view(view: str, *, hands: bool = False):
        """A browser on one of the workbench's own views (#331), answered.

        Choosing the view in the picker is what a user does, and it is also what
        keeps this tool honest: a picture of a view is a picture of the screen
        the view actually produces, not of a result assembled for the camera.
        """
        widget = GuiResearchBrowser.GuiResearchBrowser(config, sql, window, db=research_db())
        index = view_index(widget, view)
        if index < 0:
            raise RuntimeError(f"the workbench offers no {view!r} view")
        widget.view_combo.setCurrentIndex(index)
        if not settle(widget, "_worker"):
            raise RuntimeError(f"the {view!r} view did not finish")
        preset = recorded.get(view)
        if preset is not None:
            # The workspace's own question, run the way the workbench runs one:
            # the builder IS the query, so filling it and running it is the same
            # path a user takes after choosing the view.
            widget._fill_builder(preset)
            widget.run_query()
            if not settle(widget, "_worker"):
                raise RuntimeError(f"the {view!r} view did not finish")
        if hands:
            widget._load_drill(dict(DRILL_GROUP))
            if not settle(widget, "_drill_worker"):
                raise RuntimeError("the drill-down did not finish")
        return widget

    def research_landing():
        """The first-open screen: what the tab says before anything is asked."""
        return GuiResearchBrowser.GuiResearchBrowser(config, sql, window, db=research_db())

    def hud_preferences_dynamic():
        """HUD Preferences on its dynamic panel tab, with the demo's rules loaded."""
        dialog = ModernHudPreferences(config, window)
        index = tab_index(dialog.tabs, "Dynamic")
        if index is not None:
            dialog.tabs.setCurrentIndex(index)
        return dialog

    views = [("research-landing.png", research_landing)]
    views += [(filename, partial(research_view, view)) for filename, view in RESEARCH_SHOTS]
    views += [
        ("research-hands.png", partial(research_view, DRILL_VIEW, hands=True)),
        ("hud-preferences-dynamic-panels.png", hud_preferences_dynamic),
    ]
    return views


# The view each Research screenshot is taken on. Named once here and used by
# ``build_research_views``, so a filename and the screen behind it cannot drift.
RESEARCH_SHOT_VIEWS: Final[dict[str, str]] = dict(RESEARCH_SHOTS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="demo HUD_config.xml")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the PNGs")
    parser.add_argument("--only", help="substring: capture only views whose filename contains it")
    parser.add_argument("--theme", default="dark_purple.xml", help="qt_material theme used for every capture")
    args = parser.parse_args(argv)

    if not args.config.is_file():
        print(f"no demo configuration at {args.config}", file=sys.stderr)
        print("run tools/make_demo_workspace.py first", file=sys.stderr)
        return 1

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication

    from fpdb_3_legacy import SQL
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.ThemeManager import ThemeManager

    app = QApplication.instance() or QApplication([])
    if not ThemeManager().set_qt_material_theme(args.theme, save=False, apply_to_ui=True):
        print(f"unable to apply theme {args.theme}", file=sys.stderr)
        return 1
    config = Config(file=str(args.config))
    params = config.get_db_parameters()
    sql = SQL.Sql(db_server=params["db-server"])
    window = make_stub_window(config, sql)

    captured, skipped = 0, 0
    for filename, factory in build_views(config, sql, window, args.config):
        if args.only and args.only not in filename:
            continue
        try:
            grab(factory(), out_dir / filename)
        except Exception as exc:  # noqa: BLE001 - a view that will not build is data, not a crash
            print(f"  skipped {filename}: {type(exc).__name__}: {exc}")
            if os.environ.get("CAPTURE_DEBUG"):
                traceback.print_exc()
            skipped += 1
            continue
        size = (out_dir / filename).stat().st_size
        print(f"  {filename}  ({size // 1024} KB)")
        captured += 1

    print(f"\n{captured} captured, {skipped} skipped -> {out_dir}")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
