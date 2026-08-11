#!/usr/bin/env python3
"""Render fpdb's screens to PNG for the wiki, from the demo database.

Screenshots taken with a screen-capture tool carry whatever else was on the
desktop and have to be retaken by hand every release. Qt can draw a widget into
an image directly, so this builds each view against the demo database and grabs
it -- no window manager, no desktop chrome, no cursor, and the same result every
run.

    python tools/make_demo_db.py                     # once
    python tools/capture_wiki_screenshots.py         # then this

Output lands in ``--out`` (default ``wiki-images/``), one PNG per view, ready to
drop into the wiki's ``Images/`` directory.

Every player in these images is invented -- see ``tools/make_demo_db.py`` -- so
nothing here needs redacting. That is the whole point of going through the demo
database rather than the user's own.

Views that cannot be built headlessly are skipped with a reason rather than
failing the run: the useful output is the set that did render.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from time import monotonic, sleep

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)

# Qt must render somewhere. "offscreen" keeps windows off the user's display
# while still producing real pixels for grab().
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DEFAULT_CONFIG = Path.home() / "fpdb-demo" / "HUD_config.xml"
DEFAULT_OUT = REPO / "wiki-images"
SIZE = (1400, 820)


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


def build_views(config, sql, window):  # noqa: C901 - each small branch is one independent screenshot factory
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

    return [
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="demo HUD_config.xml")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the PNGs")
    parser.add_argument("--only", help="substring: capture only views whose filename contains it")
    parser.add_argument("--theme", default="dark_purple.xml", help="qt_material theme used for every capture")
    args = parser.parse_args(argv)

    if not args.config.is_file():
        print(f"no demo configuration at {args.config}", file=sys.stderr)
        print("run tools/make_demo_db.py first", file=sys.stderr)
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
    for filename, factory in build_views(config, sql, window):
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
