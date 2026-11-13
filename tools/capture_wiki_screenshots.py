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

# One screenshot per Study Explorer surface (#371), each named by the study
# and the panel behind it so a filename and the screen it shows cannot drift.
# These are the spot-first path: the landing page, two study overviews, the
# four visualisations, the range grid, and the hands behind a comparison.
STUDY_SHOTS: Final[tuple[tuple[str, str, str], ...]] = (
    ("study-preflop-overview.png", "preflop_rfi", "overview"),
    ("study-srp-overview.png", "srp_pfr_ip_flop", "overview"),
    ("study-sizing.png", "preflop_rfi", "sizing"),
    ("study-position-matrix.png", "preflop_facing_open", "position"),
    ("study-board-heatmap.png", "srp_pfr_ip_flop", "board"),
    ("study-range-grid.png", "preflop_rfi", "range"),
    ("study-hand-strength.png", "srp_pfr_ip_flop", "strength"),
    ("study-profit.png", "preflop_rfi", "profit"),
)

#: The study whose source hands are worth a picture: a comparison panel, so
#: the pane shows both sides rather than one population.
STUDY_HANDS: Final[tuple[str, str]] = ("srp_pfr_ip_flop", "overview")


# The view whose hands are worth showing beside it: a grouped result with a
# readable row count, and a group every workspace has.
DRILL_VIEW: Final = "table"
DRILL_GROUP: Final[dict[str, Any]] = {"street": "flop"}

# How long a screenshot waits for a worker thread. Long enough for a query over
# a full demo database on a slow machine, short enough that a wedged worker
# fails the run rather than hanging it.
WORKER_TIMEOUT: Final = 60.0


#: The themes ``--theme rotate`` cycles through, so the wiki shows fpdb under
#: several palettes rather than one palette 35 times. Dark ones only: several
#: views (the opponents report, the filter headings) carry styles written for a
#: dark background and are hard to read under a light theme. Stock qt_material
#: themes only: one from someone's ``~/.fpdb/themes`` would make the run differ
#: from one machine to the next.
ROTATION_THEMES: Final[tuple[str, ...]] = (
    "dark_purple.xml",
    "dark_teal.xml",
    "dark_blue.xml",
    "dark_amber.xml",
    "dark_cyan.xml",
    "dark_red.xml",
    "dark_pink.xml",
    "dark_lightgreen.xml",
    "dark_yellow.xml",
)


def theme_for(index: int, requested: str) -> str:
    """The theme of the ``index``-th capture: the requested one, or the rotation's."""
    if requested != "rotate":
        return requested
    return ROTATION_THEMES[index % len(ROTATION_THEMES)]


def theme_colors() -> dict[str, str]:
    """The graph colours of the theme currently applied, as the application derives them."""
    try:
        from fpdb_3_legacy.ThemeManager import ThemeManager

        return ThemeManager().get_theme_colors()
    except Exception:  # noqa: BLE001 - fall back to the application's default palette
        return default_theme_colors()


def default_theme_colors() -> dict[str, str]:
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


def wait_for_workers(view: Any, timeout: float = WORKER_TIMEOUT) -> None:
    """Spin the event loop until no database worker of the ring stats view runs.

    The ring stats dashboard is filled by database workers; grabbed before
    they answer, it shows zero hands. Their results then need a few more turns
    of the loop to reach the widgets.
    """
    from PySide6.QtWidgets import QApplication

    def running() -> bool:
        owners = (view.controller, view.stats_tabs)
        return any(worker.isRunning() for owner in owners for worker in getattr(owner, "_workers", ()))

    deadline = monotonic() + timeout
    while running() and monotonic() < deadline:
        QApplication.processEvents()
        sleep(0.01)
    for _ in range(5):
        QApplication.processEvents()


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
    from fpdb_3_legacy.ring_stats import GuiRingPlayerStats

    def ring_player_stats():
        view = GuiRingPlayerStats(config, sql, window)
        view.refreshStats()
        wait_for_workers(view)
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
        ("auto-notes-workbench.png", auto_notes),
        ("stats-guide.png", lambda: GuiStatsInfo.GuiStatsInfo(config, window)),
    ]
    return (
        views
        + build_editor_views(config, window)
        + build_research_views(config, sql, window, config_path)
        + build_study_views(config, sql, window, config_path)
        + build_release_views(config, sql, window, config_path)
    )


def build_editor_views(config, window):
    """The HUD editor's two design tabs (#786): Statistics, then Popup Windows."""
    from fpdb_3_legacy.modern_hud_preferences import ModernHudPreferences

    def hud_preferences():
        """The Statistics tab on a profile made of panels, one of its stats selected."""
        dialog = ModernHudPreferences(config, window)
        show_hud_editor(dialog)
        return dialog

    def hud_preferences_popups():
        """The Popup Windows tab on a classic popup, one of its stats selected."""
        dialog = ModernHudPreferences(config, window)
        index = tab_index(dialog.tabs, "Popup")
        if index is not None:
            dialog.tabs.setCurrentIndex(index)
        show_popup_editor(dialog)
        return dialog

    return [("hud-preferences.png", hud_preferences), ("hud-preferences-popups.png", hud_preferences_popups)]


def editor_profile(profiles: dict[str, Any]) -> str | None:
    """The profile the HUD editor's picture shows: the first made of panels, else the first.

    A profile of panels is the one whose screen holds everything the editor
    offers -- the panel list, Group Properties, a panel on the canvas.
    """
    names = list(profiles)
    return next((name for name in names if (profiles[name] or {}).get("blocks")), names[0] if names else None)


def editor_popup(popups: dict[str, Any], minimum: int = 4) -> str | None:
    """The popup the editor's picture shows: the first classic one with ``minimum`` stats."""
    for name in sorted(popups):
        popup = popups[name] or {}
        if popup.get("class") != "BlockPopup" and len(popup.get("stats", [])) >= minimum:
            return name
    return None


def show_hud_editor(dialog: Any) -> None:
    """Select the picture's profile and the first stat of its shown panel."""
    name = editor_profile(dialog.hud_profiles or {})
    if name is None:
        return
    dialog.profile_combo.setCurrentText(name)
    canvas = dialog._design_canvases[-1] if dialog._design_canvases else None
    chip = next((c for c in canvas.chips if c.kind == "stat"), None) if canvas is not None else None
    if chip is not None:
        chip.clicked.emit()


def show_popup_editor(dialog: Any) -> None:
    """Select the picture's popup and its third stat, so the inspector has something to show."""
    name = editor_popup(dialog.popup_windows or {})
    if name is None:
        return
    dialog.popup_combo.setCurrentText(name)
    chips = dialog.popup_canvas.chips
    if chips:
        chips[min(2, len(chips) - 1)].clicked.emit()


# Dialogs are drawn at their own size: stretched to the full SIZE they read as
# mostly empty space.
DIALOG_SIZE: Final = (900, 620)

#: The folder the wizard's first picture shows: where PokerTracker 4 keeps its
#: archive by default, with no user name in it.
PT4_ARCHIVE_EXAMPLE: Final = r"C:\PokerTracker 4\Processed"


def build_release_views(config, sql, window, config_path: Path):
    """The 3.10.0 screens: the tracker migration wizard, the pack gallery and the language menu.

    The wizard is shown on the page that says where a tracker keeps its hands,
    the one a reader needs first. The gallery is the project's real one, read
    over the network; its cache, its record of what is installed and its pack
    folder live in the workspace, never in the user's ``~/.fpdb``. Offline, that
    view is skipped like any other.
    """
    workspace = config_path.parent

    def tracker_wizard():
        from fpdb_3_legacy.GuiTrackerMigration import GuiTrackerMigration

        wizard = GuiTrackerMigration({}, config, sql, window)
        wizard.resize(*DIALOG_SIZE)
        wizard.show()
        wizard.next()  # tracker -> where the hand histories are
        # Only the picture needs a folder, and it must not show the path of
        # whoever ran the capture: PT4's usual archive folder stands in.
        wizard.source_page.folder.setText(PT4_ARCHIVE_EXAMPLE)
        return wizard, DIALOG_SIZE

    def pack_gallery():
        from fpdb_3_legacy.pack_gallery_dialog import PackGalleryDialog

        gallery_dir = workspace / "pack-gallery"
        dialog = PackGalleryDialog(
            config,
            window,
            cache_dir=gallery_dir / "cache",
            record=gallery_dir / "installed.json",
            packs_dir=gallery_dir / "packs",
        )
        if not dialog.index.entries:
            msg = "the pack gallery could not be read (offline?)"
            raise RuntimeError(msg)
        dialog.table.selectRow(0)
        return dialog, DIALOG_SIZE

    def language_menu():
        """*View ▸ Language*: every catalogue fpdb ships, with how much of it is translated.

        Built from the same helpers the main window's submenu uses
        (``menu_layout.language_options`` and ``language_label``, fed by
        ``i18n_compile.completion``), so the percentages are the ones a user sees.
        """
        from PySide6.QtCore import QLocale
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        from fpdb_3_legacy import menu_layout
        from fpdb_3_legacy.i18n_compile import available_locales, completion

        locale_dir = REPO / "locale"
        menu = QMenu(menu_layout.translate("Language"), window)
        for code, checked in menu_layout.language_options(available_locales(locale_dir), "en"):
            if code == menu_layout.SYSTEM_LANGUAGE:
                label = menu_layout.translate("System default")
            elif code == menu_layout.SOURCE_LANGUAGE:
                label = "English"
            else:
                name = QLocale(code).nativeLanguageName().capitalize() or code
                label = menu_layout.language_label(name, completion(locale_dir / f"fpdb-{code}.po"))
            action = QAction(label, menu, checkable=True)
            action.setChecked(checked)
            menu.addAction(action)
        menu.ensurePolished()
        hint = menu.sizeHint()
        return menu, (max(hint.width(), 320), hint.height())

    return [
        ("tracker-migration.png", tracker_wizard),
        ("pack-gallery.png", pack_gallery),
        ("language-menu.png", language_menu),
    ]


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


def build_study_views(config, sql, window, _config_path: Path):  # noqa: C901 - view factories share one deterministic setup.
    """``(filename, factory)`` for the Study Explorer surfaces (#371).

    The spot-first path is what the docs lead with, so it is what the pictures
    have to show: the landing page a reader opens, a study read through each of
    its panels, the differences page, and the hands behind a comparison. Every
    one is built from the shipped studies and the demo database, so a picture
    is the product rather than a mock-up of it.
    """
    from fpdb_3_legacy import Database
    from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
    from fpdb_3_legacy.GuiStudyDifferences import GuiStudyDifferences
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies
    from fpdb_3_legacy.research_study_explorer import StudyExplorerModel

    state: dict[str, Any] = {}

    def study_db():
        if "db" not in state:
            state["db"] = Database.Database(config, sql=sql)
        return state["db"]

    def settle_dashboard(dashboard: Any) -> bool:
        """Wait for the panel and its source hands, then stop everything.

        A dashboard left running holds worker threads, and the next capture
        builds another one: closing each in turn is what keeps a run of ten
        pictures to one dashboard at a time.
        """
        from PySide6.QtWidgets import QApplication

        deadline = monotonic() + WORKER_TIMEOUT
        while monotonic() < deadline:
            QApplication.processEvents()
            if dashboard._results and dashboard.source_hands.page is not None:
                return True
            sleep(0.02)
        QApplication.processEvents()
        return bool(dashboard._results and dashboard.source_hands.page is not None)

    def dashboard_for(study_id: str, panel_id: str, *, history=None):
        explorer = StudyExplorerModel(builtin_studies(), history)
        selection = explorer.open_study(study_id, remember=False)
        dashboard = GuiStudyDashboard(config, sql, window, db=study_db(), selection=selection)
        # The demo corpus is a few thousand hands, so the shipped minimums --
        # written for a database of real volume -- would hide every row. A
        # screenshot of an empty panel teaches nothing.
        dashboard.model.set_min_sample(0)
        dashboard.model.set_active_panel(panel_id)
        dashboard.refresh()
        if not settle_dashboard(dashboard):
            dashboard.close()
            raise RuntimeError(f"the {study_id!r} dashboard did not finish")
        return dashboard

    def explorer_landing():
        return GuiStudyExplorer(config, sql, window, db=study_db())

    def differences():
        widget = GuiStudyDifferences(config, sql, window, db=study_db())
        # The shipped minimums are written for a database of real volume; the
        # demo is a few thousand hands, and a screenshot of "no rows above the
        # threshold" would teach the wrong thing about the page.
        widget.hero_sample_spin.setValue(20)
        widget.field_sample_spin.setValue(40)
        widget.run_report()
        if not settle(widget, "_worker"):
            raise RuntimeError("the differences report did not finish")
        return widget

    views = [
        ("study-explorer-landing.png", explorer_landing),
        ("study-differences.png", differences),
    ]
    views += [
        (filename, partial(dashboard_for, study_id, panel_id))
        for filename, study_id, panel_id in STUDY_SHOTS
    ]
    views.append(
        ("study-source-hands.png", partial(dashboard_for, *STUDY_HANDS)),
    )
    return views


# The view each Research screenshot is taken on. Named once here and used by
# ``build_research_views``, so a filename and the screen behind it cannot drift.
RESEARCH_SHOT_VIEWS: Final[dict[str, str]] = dict(RESEARCH_SHOTS)


def use_english(config) -> None:
    """Draw every capture in English, with English number and money formats.

    The wiki is in English, and the demo configuration is copied from the
    repository's ``HUD_config.xml``, whose ``ui_language`` is whatever the last
    developer chose. Without this a capture comes out half translated.
    """
    import gettext

    from fpdb_3_legacy.localized_formats import set_format_locale

    config.general["ui_language"] = "en"
    gettext.NullTranslations().install()
    set_format_locale("en")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="demo HUD_config.xml")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the PNGs")
    parser.add_argument("--only", help="substring: capture only views whose filename contains it")
    parser.add_argument(
        "--theme",
        default="rotate",
        help="qt_material theme for every capture, or 'rotate' (default) for a different one each time",
    )
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
    themes = ThemeManager()
    if args.theme != "rotate" and not themes.set_qt_material_theme(args.theme, save=False, apply_to_ui=True):
        print(f"unable to apply theme {args.theme}", file=sys.stderr)
        return 1
    config = Config(file=str(args.config))
    use_english(config)
    params = config.get_db_parameters()
    sql = SQL.Sql(db_server=params["db-server"])
    window = make_stub_window(config, sql)

    captured, skipped = 0, 0
    for index, (filename, factory) in enumerate(build_views(config, sql, window, args.config)):
        if args.only and args.only not in filename:
            continue
        theme = theme_for(index, args.theme)
        if args.theme == "rotate" and not themes.set_qt_material_theme(theme, save=False, apply_to_ui=True):
            print(f"  skipped {filename}: unable to apply theme {theme}")
            skipped += 1
            continue
        try:
            built = factory()
            # A factory returns a widget, or ``(widget, size)`` for a dialog.
            widget, size = built if isinstance(built, tuple) else (built, SIZE)
            grab(widget, out_dir / filename, size)
        except Exception as exc:  # noqa: BLE001 - a view that will not build is data, not a crash
            print(f"  skipped {filename}: {type(exc).__name__}: {exc}")
            if os.environ.get("CAPTURE_DEBUG"):
                traceback.print_exc()
            skipped += 1
            continue
        size = (out_dir / filename).stat().st_size
        print(f"  {filename}  ({size // 1024} KB, {theme})")
        captured += 1

    print(f"\n{captured} captured, {skipped} skipped -> {out_dir}")
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
