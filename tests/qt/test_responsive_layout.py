"""The screens the macOS report showed cut off must fit a laptop window.

The report was four screens whose controls were unreachable: forms that had
grown past the bottom of the window, panes squeezed until their own widgets
were hidden, and a dialog that refused to be made smaller than the screen.

These tests measure what the report described. Two kinds of assertion do the
work:

* the minimum size a screen demands, checked against a 1024 x 640 window, which
  is what a small laptop offers once the menu bar and the Dock are accounted
  for. A minimum larger than that is a control the reader cannot reach;
* the behaviour that keeps a smaller window usable -- fields reflowing to fewer
  columns, panes stacking, a folded section still stating what it holds, and
  the state of the screen surviving the change of shape.
"""

from __future__ import annotations

import os
import shutil

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.responsive_layout import (
    CONTEXT_BLOCK_FLOOR,
    CONTEXT_BLOCK_SHARE,
    CollapsibleSection,
    PaneSwitcher,
    ReflowGrid,
    ReportingSplitter,
    ResponsiveSplitter,
    cap_context_block,
    column_count,
    fit_window,
    wrap_in_scroll,
)

pytestmark = pytest.mark.qt

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXAMPLE_CONFIG = os.path.join(ROOT, "HUD_config.xml.example")

#: A small laptop window, in logical points, once the menu bar and the Dock
#: have taken their share of the screen.
FITS_WIDTH = 1024
FITS_HEIGHT = 640


def get_qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def qt_application() -> QApplication:
    """Every test here builds a widget, and Qt aborts without an application."""
    return get_qapp()


def assert_fits(widget: QWidget, width: int = FITS_WIDTH, height: int = FITS_HEIGHT) -> None:
    hint = widget.minimumSizeHint()
    name = type(widget).__name__
    assert hint.width() <= width, f"{name} needs {hint.width()} px of width, only {width} are available"
    assert hint.height() <= height, f"{name} needs {hint.height()} px of height, only {height} are available"


def process(app: QApplication) -> None:
    app.processEvents()
    app.processEvents()


def shrink_to(widget: QWidget, width: int, app: QApplication, height: int | None = None) -> None:
    """Narrow a window in steps, the way dragging its edge does.

    While the panes are side by side their minimum widths add up, and Qt clamps
    a single resize to that total *before* the layout that would stack them has
    run -- so one jump to a small width leaves the window at the old minimum.
    A drag never jumps, and neither does this.
    """
    while widget.width() > width:
        widget.resize(max(width, widget.width() - 200), height or widget.height())
        process(app)


# --------------------------------------------------------------------------- #
# The helpers
# --------------------------------------------------------------------------- #


def test_fit_window_keeps_the_preferred_size_when_the_screen_can_hold_it() -> None:
    window = QWidget()

    size = fit_window(window, 900, 600, available=QSize(1920, 1080))

    assert size == QSize(900, 600)
    assert (window.width(), window.height()) == (900, 600)


def test_fit_window_clamps_to_the_screen_it_was_given() -> None:
    window = QWidget()

    fit_window(window, 1400, 900, available=QSize(1024, 640))

    assert window.width() <= 1024
    assert window.height() <= 640


def test_fit_window_lowers_a_minimum_that_cannot_fit_the_screen() -> None:
    """The regression: a dialog that demands 1200 x 800 on a 1024 x 640 screen.

    An explicit minimum larger than the screen is a window the window manager
    will not let the user shrink, which is how the HUD preferences behaved.
    """
    window = QWidget()
    window.setMinimumSize(1200, 800)

    fit_window(window, 1400, 900, available=QSize(1024, 640))

    assert window.minimumSize().width() <= 1024
    assert window.minimumSize().height() <= 640


def test_fit_window_leaves_a_window_without_a_minimum_alone() -> None:
    """No explicit minimum means the layout's own minimum still governs."""
    window = QWidget()

    fit_window(window, 800, 500, available=QSize(1280, 720))

    assert window.minimumSize() == QSize(0, 0)


def test_fit_window_without_a_screen_keeps_the_preferred_size() -> None:
    """Headless and pre-initialisation runs must not shrink a window to nothing."""
    window = QWidget()

    size = fit_window(window, 800, 500, available=QSize())

    assert size == QSize(800, 500)


def test_column_count_reads_the_measured_breakpoints() -> None:
    breakpoints = ((1080, 3), (720, 2))

    assert column_count(1600, breakpoints) == 3
    assert column_count(1080, breakpoints) == 3
    assert column_count(1079, breakpoints) == 2
    assert column_count(720, breakpoints) == 2
    assert column_count(719, breakpoints) == 1


def test_wrap_in_scroll_reports_a_smaller_minimum_than_its_content(qtbot) -> None:
    """The property the whole fix rests on.

    A form keeps its natural height; the scroll area around it reports the
    small minimum of a viewport, so the window can be shorter than the form.
    """
    content = QWidget()
    content.setMinimumHeight(900)
    area = wrap_in_scroll(content)
    qtbot.addWidget(area)

    assert area.widget() is content
    assert area.widgetResizable() is True
    assert content.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
    assert area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert content.minimumHeight() == 900
    assert area.minimumSizeHint().height() < content.minimumHeight()


def test_wrap_in_scroll_can_leave_the_content_filling_the_viewport(qtbot) -> None:
    """Results and hands fill their pane; a form is pinned to the top of its."""
    content = QWidget()
    area = wrap_in_scroll(content, top_aligned=False)
    qtbot.addWidget(area)

    assert content.sizePolicy().verticalPolicy() != QSizePolicy.Policy.Maximum


def test_reflow_grid_lays_its_items_out_in_the_columns_it_is_given(qtbot) -> None:
    grid = ReflowGrid()
    host = QWidget()
    host.setLayout(grid)
    qtbot.addWidget(host)
    items = [QWidget() for _ in range(5)]
    grid.set_items(items)

    assert grid.reflow(3) == 3
    assert grid.columns() == 3
    assert [grid.getItemPosition(index)[:2] for index in range(grid.count())] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 1),
    ]

    grid.reflow(2)

    assert grid.columns() == 2
    assert [grid.getItemPosition(index)[:2] for index in range(grid.count())] == [
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (2, 0),
    ]
    assert grid.count() == 5, "reflowing must not drop an item"


def test_a_folded_section_still_states_what_it_holds(qtbot) -> None:
    section = CollapsibleSection("More filters", expanded=False)
    qtbot.addWidget(section)

    assert section.is_expanded() is False
    assert section.body().isVisibleTo(section) is False

    section.set_summary("player Hero · stake 10-50 BB")

    assert section.is_expanded() is False, "setting a summary must not unfold the section"
    assert "Hero" in section.summary()

    section.set_expanded(True)

    assert section.is_expanded() is True
    assert section.body().isVisibleTo(section) is True


def test_a_splitter_stacks_its_panes_when_the_width_runs_out(qtbot) -> None:
    app = get_qapp()
    splitter = ResponsiveSplitter(Qt.Orientation.Horizontal)
    qtbot.addWidget(splitter)
    for _ in range(3):
        pane = QWidget()
        pane.setMinimumSize(180, 120)
        splitter.addWidget(pane)
    splitter.set_narrow_below(900)
    splitter.set_narrow_sizes([100, 140, 100])
    splitter.resize(1200, 500)
    splitter.show()
    process(app)

    assert splitter.is_stacked() is False
    wide = splitter.sizes()

    splitter.resize(700, 500)
    process(app)

    assert splitter.is_stacked() is True
    assert splitter.orientation() == Qt.Orientation.Vertical

    splitter.resize(1200, 500)
    process(app)

    assert splitter.is_stacked() is False
    # ``setSizes`` restores the shares; Qt's integer rounding can move a pixel
    # between panes on the way, which is not a different arrangement.
    restored = splitter.sizes()
    assert len(restored) == len(wide)
    assert all(abs(after - before) <= 2 for after, before in zip(restored, wide))


def test_a_splitter_says_which_arrangement_is_in_force(qtbot) -> None:
    """The signal fires on a change of arrangement, not on every resize."""
    app = get_qapp()
    splitter = ResponsiveSplitter(Qt.Orientation.Horizontal)
    qtbot.addWidget(splitter)
    for _ in range(2):
        splitter.addWidget(QWidget())
    seen: list[bool] = []
    splitter.stacked_changed.connect(seen.append)
    splitter.set_narrow_below(900)
    splitter.resize(1200, 500)
    splitter.show()
    process(app)

    assert seen == [], "the width was already wide, so nothing changed"

    splitter.resize(700, 500)
    process(app)
    splitter.resize(600, 500)
    process(app)
    assert seen == [True], "a resize that keeps the arrangement must not re-announce it"

    splitter.resize(1200, 500)
    process(app)
    assert seen == [True, False]


def test_a_splitter_without_a_threshold_never_stacks(qtbot) -> None:
    app = get_qapp()
    splitter = ResponsiveSplitter(Qt.Orientation.Vertical)
    qtbot.addWidget(splitter)
    splitter.addWidget(QWidget())
    splitter.resize(400, 500)
    splitter.show()
    process(app)

    assert splitter.orientation() == Qt.Orientation.Vertical
    assert splitter.is_stacked() is False


def test_a_reporting_splitter_announces_its_own_extent(qtbot) -> None:
    """A parent's resize runs before the layout, so the extent must be reported."""
    app = get_qapp()
    splitter = ReportingSplitter(Qt.Orientation.Vertical)
    qtbot.addWidget(splitter)
    splitter.addWidget(QWidget())
    seen: list[int] = []
    splitter.resized.connect(lambda: seen.append(splitter.height()))
    splitter.resize(400, 500)
    splitter.show()
    process(app)

    assert seen, "the splitter never reported being laid out"
    splitter.resize(400, 300)
    process(app)
    assert seen[-1] == 300


def test_a_pane_switcher_shows_one_pane_at_a_time(qtbot) -> None:
    """The bar takes over when asked, and hands the arrangement back after."""
    app = get_qapp()
    owner = QWidget()
    qtbot.addWidget(owner)
    layout = QVBoxLayout(owner)
    splitter = QSplitter(Qt.Orientation.Vertical)
    layout.addWidget(splitter)
    panes = [QWidget(), QWidget()]
    for pane in panes:
        splitter.addWidget(pane)
    switcher = PaneSwitcher(owner, splitter, panes, ("First", "Second"), sizes=(300, 200))
    owner.resize(400, 500)
    owner.show()
    process(app)
    splitter.setSizes([300, 200])
    process(app)
    wide = splitter.sizes()

    assert switcher.is_switching() is False
    assert switcher.bar.isVisibleTo(owner) is False
    assert [pane.isVisibleTo(owner) for pane in panes] == [True, True]

    switcher.set_switching(True)
    process(app)
    assert switcher.bar.isVisibleTo(owner) is True
    assert [pane.isVisibleTo(owner) for pane in panes] == [True, False]

    switcher.set_active(1)
    process(app)
    assert [pane.isVisibleTo(owner) for pane in panes] == [False, True]

    switcher.set_switching(False)
    process(app)
    assert switcher.bar.isVisibleTo(owner) is False
    assert [pane.isVisibleTo(owner) for pane in panes] == [True, True]
    assert all(abs(after - before) <= 2 for after, before in zip(splitter.sizes(), wide))


def test_a_pane_switcher_hides_nothing_while_it_is_off_screen(qtbot) -> None:
    """A hidden pane whose bar is not shown either could never be reached again."""
    app = get_qapp()
    owner = QWidget()
    qtbot.addWidget(owner)
    splitter = QSplitter(Qt.Orientation.Vertical, owner)
    panes = [QWidget(), QWidget()]
    for pane in panes:
        splitter.addWidget(pane)
    switcher = PaneSwitcher(owner, splitter, panes, ("First", "Second"))

    switcher.set_switching(True)
    process(app)

    assert switcher.is_switching() is False, "nothing is switched while the widget is off screen"
    assert [pane.isVisibleTo(owner) for pane in panes] == [True, True]


def test_capping_a_context_block_leaves_the_room_to_what_grows(qtbot) -> None:
    """A block that scrolls must not claim its whole size hint from the pane below."""
    app = get_qapp()
    owner = QWidget()
    qtbot.addWidget(owner)
    layout = QVBoxLayout(owner)
    tall = QLabel("\n".join(f"context line {row}" for row in range(40)))
    block = wrap_in_scroll(tall)
    layout.addWidget(block)
    growing = QWidget()
    layout.addWidget(growing, 1)
    owner.resize(800, 700)
    owner.show()
    process(app)

    assert block.height() >= 300, "uncapped, the block claims the height it asks for"
    uncapped = block.height()

    cap_context_block(block, owner)
    process(app)
    assert block.height() == max(CONTEXT_BLOCK_FLOOR, owner.height() // CONTEXT_BLOCK_SHARE), (
        "the cap is the floor or the share of the window, whichever is larger"
    )
    assert block.height() < uncapped
    assert growing.height() > 400, "the pane that grows gets the window instead"

    owner.resize(800, 2000)
    cap_context_block(block, owner)
    process(app)
    assert block.height() == min(block.sizeHint().height(), 2000 // CONTEXT_BLOCK_SHARE), (
        "a tall window raises the cap until the block asks for less than it"
    )


# --------------------------------------------------------------------------- #
# The screens the report showed
# --------------------------------------------------------------------------- #


@pytest.fixture
def example_config(tmp_path):
    from fpdb_3_legacy import Configuration as Conf

    config_path = tmp_path / "HUD_config.xml"
    shutil.copy(EXAMPLE_CONFIG, config_path)
    config = Conf.Config(file=str(config_path))
    # Point the database at a throwaway file. These tests only build widgets,
    # but the shipped example names the user's real database, and a widget that
    # opens a connection would leave its side files there.
    db_file = tmp_path / "layout_test.sqlite3"
    params = config.get_db_parameters()
    params["db-server"] = "sqlite"
    params["db-backend"] = 4
    params["db-name"] = str(db_file)
    params["db-databaseName"] = str(db_file)
    params["db-path"] = ""
    config.get_db_parameters = lambda: params
    return config


def test_study_explorer_fits_a_laptop_window(qtbot, tmp_path) -> None:
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies

    get_qapp()
    explorer = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)

    assert_fits(explorer)


def test_study_explorer_reflows_its_fields_and_stacks_its_panes(qtbot, tmp_path) -> None:
    app = get_qapp()
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies

    explorer = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)
    explorer.show()

    explorer.resize(1280, 720)
    process(app)
    assert explorer.context_grid.columns() == 4
    assert explorer.category_grid.columns() == 3
    assert explorer.splitter.is_stacked() is False

    explorer.resize(660, 640)
    process(app)
    assert explorer.context_grid.columns() == 1
    assert explorer.category_grid.columns() == 1
    assert explorer.splitter.is_stacked() is True


def test_study_explorer_keeps_its_search_selection_and_filters_when_resized(qtbot, tmp_path) -> None:
    """Changing the shape of the window must not change the question."""
    app = get_qapp()
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies

    explorer = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)
    explorer.show()
    explorer.resize(1280, 720)
    process(app)
    explorer.search_edit.setText("c-bet")
    explorer.subject_combo.setCurrentIndex(explorer.subject_combo.findData(True))
    explorer.player_edit.setText("Hero")
    process(app)
    before = [
        (explorer.study_list.item(row).text(), str(explorer.study_list.item(row).data(256)))
        for row in range(explorer.study_list.count())
    ]
    assert before, "the search must match something for this test to mean anything"
    selected = explorer.study_list.currentRow()

    explorer.resize(700, 640)
    process(app)

    after = [
        (explorer.study_list.item(row).text(), str(explorer.study_list.item(row).data(256)))
        for row in range(explorer.study_list.count())
    ]
    assert after == before
    assert explorer.study_list.currentRow() == selected
    assert explorer.search_edit.text() == "c-bet"
    assert explorer.subject_combo.currentData() is True
    assert explorer.player_edit.text() == "Hero"
    assert "Hero" in explorer.advanced_fields.summary(), "the folded section must still say what is set"


def test_the_study_explorer_shows_one_pane_at_a_time_when_stacked(qtbot, tmp_path) -> None:
    """Stacked, the bar gives the studies the height instead of half of it."""
    app = get_qapp()
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies

    explorer = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)
    explorer.show()
    explorer.resize(1280, 720)
    process(app)

    switcher = explorer.pane_switcher
    panes = (explorer.study_list, explorer.study_detail)
    assert switcher.bar.isVisibleTo(explorer) is False, "side by side, the splitter is the better tool"
    assert [pane.isVisibleTo(explorer) for pane in panes] == [True, True]

    shrink_to(explorer, 700, app, 640)
    assert explorer.splitter.is_stacked() is True
    assert switcher.bar.isVisibleTo(explorer) is True
    assert [pane.isVisibleTo(explorer) for pane in panes] == [True, False]
    assert explorer.study_list.height() > 250, "the list gets the height, not a share of it"

    switcher.set_active(1)
    process(app)
    assert [pane.isVisibleTo(explorer) for pane in panes] == [False, True]
    assert explorer.study_detail.height() > 250

    explorer.resize(1280, 720)
    process(app)
    assert switcher.bar.isVisibleTo(explorer) is False
    assert [pane.isVisibleTo(explorer) for pane in panes] == [True, True]


def test_choosing_a_study_shows_its_detail_when_stacked(qtbot, tmp_path) -> None:
    """A click is what the detail pane answers; a rebuild of the list is not.

    The page selects a row itself every time the list is rebuilt -- on a search,
    a category, a game change -- and the detail must not take the screen then.
    """
    app = get_qapp()
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies

    explorer = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)
    explorer.show()
    explorer.resize(1280, 720)
    process(app)
    shrink_to(explorer, 700, app, 640)
    assert explorer.pane_switcher.active() == 0

    item = explorer.study_list.item(0)
    assert item is not None, "the list must hold something for this test to mean anything"
    explorer.study_list.itemClicked.emit(item)
    process(app)
    assert explorer.pane_switcher.active() == 1
    assert explorer.study_detail.isVisibleTo(explorer) is True
    assert explorer.study_list.isVisibleTo(explorer) is False

    explorer.pane_switcher.set_active(0)
    explorer._refresh_studies()
    process(app)
    assert explorer.pane_switcher.active() == 0, "a programmatic refresh must not take the screen"


def test_the_folded_advanced_filters_are_still_reachable(qtbot, tmp_path) -> None:
    """Folding a section must not be the same as removing it."""
    from fpdb_3_legacy.GuiStudyExplorer import GuiStudyExplorer
    from fpdb_3_legacy.research_studies import builtin_studies

    get_qapp()
    explorer = GuiStudyExplorer(registry=builtin_studies(), state_path=tmp_path / "history.json")
    qtbot.addWidget(explorer)

    assert explorer.advanced_fields.is_expanded() is False
    explorer.advanced_fields.set_expanded(True)

    assert explorer.player_edit.isVisibleTo(explorer) is True
    assert explorer.stake_min_edit.isVisibleTo(explorer) is True
    assert explorer.date_from_edit.isVisibleTo(explorer) is True


def test_research_browser_fits_a_laptop_window(qtbot, example_config) -> None:
    from fpdb_3_legacy.GuiResearchBrowser import GuiResearchBrowser

    get_qapp()
    browser = GuiResearchBrowser(example_config, None, None)
    qtbot.addWidget(browser)

    assert_fits(browser)


def test_research_browser_scrolls_its_panes_and_stacks_them_when_narrow(qtbot, example_config) -> None:
    app = get_qapp()
    from fpdb_3_legacy.GuiResearchBrowser import GuiResearchBrowser

    browser = GuiResearchBrowser(example_config, None, None)
    qtbot.addWidget(browser)
    browser.show()

    assert isinstance(browser.filters_pane, QScrollArea), "the filter list must scroll, not overflow"
    assert browser.splitter.count() == 3
    # The filter rows keep their own height: the leftover room goes to the
    # stretch below them, not into the rows.
    assert browser.filter_rows_widget.sizePolicy().verticalPolicy() != QSizePolicy.Policy.Maximum

    browser.resize(1400, 800)
    process(app)
    assert browser.splitter.is_stacked() is False

    shrink_to(browser, 900, app)
    assert browser.splitter.is_stacked() is True

    browser.shutdown_workers()


def test_the_research_browser_shows_one_pane_at_a_time_when_stacked(qtbot, example_config) -> None:
    """Stacked, the bar gives the chosen pane the whole height.

    Three panes sharing the height is a third each: the results table shows a
    few rows. The bar is what makes the stacked arrangement usable, and it must
    give way to the splitter as soon as the panes fit side by side.
    """
    app = get_qapp()
    from fpdb_3_legacy.GuiResearchBrowser import GuiResearchBrowser

    browser = GuiResearchBrowser(example_config, None, None)
    qtbot.addWidget(browser)
    browser.show()
    browser.resize(1400, 800)
    process(app)

    assert not browser.narrow_view_bar.isVisibleTo(browser), "side by side, the splitter is the better tool"
    assert [pane.isVisibleTo(browser) for pane in browser._panes()] == [True, True, True]

    shrink_to(browser, 900, app)
    assert browser.splitter.is_stacked() is True
    assert browser.narrow_view_bar.isVisibleTo(browser)
    assert [pane.isVisibleTo(browser) for pane in browser._panes()] == [True, False, False]

    browser.narrow_view_bar.setCurrentIndex(1)
    process(app)
    assert [pane.isVisibleTo(browser) for pane in browser._panes()] == [False, True, False]

    browser.resize(1400, 800)
    process(app)
    assert not browser.narrow_view_bar.isVisibleTo(browser)
    assert [pane.isVisibleTo(browser) for pane in browser._panes()] == [True, True, True]
    assert all(size > 0 for size in browser.splitter.sizes()), "no pane is left collapsed on the way back"

    browser.shutdown_workers()


def test_the_research_browser_sizes_its_panes_from_their_content(qtbot, example_config) -> None:
    """Side by side, each pane opens at the width its own content measured.

    The splitter used to hand every pane a third of whatever it had, so even at
    1600 px the filter pane still had 33 px of its rows out of sight: "Add
    breakdown" and "Save / Delete" sat permanently half outside it, on a screen
    wide enough to show them. The three panes are now opened at their measured
    widths, and the arrangement folds into the one-pane bar only once the window
    is narrower than the three of them together.
    """
    app = get_qapp()
    from fpdb_3_legacy.GuiResearchBrowser import PANE_WIDTHS, STACK_BELOW_WIDTH, GuiResearchBrowser

    assert STACK_BELOW_WIDTH == sum(PANE_WIDTHS) + 2 * 8, "the threshold is the three panes plus their handles"

    browser = GuiResearchBrowser(example_config, None, None)
    qtbot.addWidget(browser)
    browser.show()

    browser.resize(STACK_BELOW_WIDTH + 200, 800)
    process(app)
    assert browser.splitter.is_stacked() is False
    for size, measured in zip(browser.splitter.sizes(), PANE_WIDTHS):
        assert size >= measured, f"a pane was given {size} px where its content measured {measured}"
    assert browser.filters_pane.horizontalScrollBar().maximum() == 0, (
        "a screen that can hold the three panes shows the filter rows whole"
    )

    browser.resize(STACK_BELOW_WIDTH - 100, 700)
    process(app)
    assert browser.splitter.is_stacked() is True
    assert browser.narrow_view_bar.isVisibleTo(browser)

    browser.shutdown_workers()


def test_the_research_browser_keeps_the_wide_widths_across_a_stacking_round_trip(qtbot, example_config) -> None:
    """The widths to come back to are widths, not the heights of the stack.

    Stacked, the panes are laid out vertically and the splitter's own sizes are
    heights. A browser that remembered those would come back from a narrow window
    with the filter pane 210 px wide -- all scrollbar, the very problem the
    measured widths exist to solve.
    """
    app = get_qapp()
    from fpdb_3_legacy.GuiResearchBrowser import PANE_WIDTHS, GuiResearchBrowser

    browser = GuiResearchBrowser(example_config, None, None)
    qtbot.addWidget(browser)
    browser.show()
    browser.resize(1500, 800)
    process(app)

    wide = browser.splitter.sizes()
    assert browser.splitter.is_stacked() is False

    shrink_to(browser, 700, app)
    assert browser.splitter.is_stacked() is True

    browser.resize(1500, 800)
    process(app)
    assert browser.splitter.is_stacked() is False
    for after, before, measured in zip(browser.splitter.sizes(), wide, PANE_WIDTHS):
        assert abs(after - before) <= 2, f"the wide arrangement came back as {after} px instead of {before}"
        assert after >= measured - 2

    browser.shutdown_workers()


def test_the_filter_pane_scrolls_sideways_rather_than_clipping(qtbot, example_config) -> None:
    """A filter row stays reachable even in a window narrower than itself.

    Given its measured width the row fits, so the horizontal scrollbar is a
    safety net rather than the everyday case -- but a window narrower than the
    row itself must still reach every control on it. Without the scrollbar the
    controls past the edge are simply not there: the report's "commands
    unreachable", one pane over.
    """
    app = get_qapp()
    from fpdb_3_legacy.GuiResearchBrowser import GuiResearchBrowser

    browser = GuiResearchBrowser(example_config, None, None)
    qtbot.addWidget(browser)
    browser.show()
    browser.resize(1500, 800)
    process(app)
    shrink_to(browser, 520, app)

    pane = browser.filters_pane
    assert browser.splitter.is_stacked() is True
    assert pane.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert pane.horizontalScrollBar().maximum() > 0, "the controls past the pane edge must be reachable"

    browser.shutdown_workers()


def test_study_dashboard_fits_a_laptop_window(qtbot, example_config, tmp_path) -> None:
    from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
    from fpdb_3_legacy.research_studies import builtin_studies
    from fpdb_3_legacy.research_study_explorer import StudyExplorerModel

    get_qapp()
    model = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = model.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(example_config, None, None, selection=selection)
    qtbot.addWidget(dashboard)

    assert_fits(dashboard)

    dashboard.shutdown_workers()


def test_study_dashboard_keeps_the_panels_and_the_hands_resizable(qtbot, example_config, tmp_path) -> None:
    """The panels and the hands share the height, and the reader decides how."""
    from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
    from fpdb_3_legacy.research_studies import builtin_studies
    from fpdb_3_legacy.research_study_explorer import StudyExplorerModel

    get_qapp()
    model = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = model.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(example_config, None, None, selection=selection)
    qtbot.addWidget(dashboard)

    assert dashboard.splitter.count() == 2
    assert dashboard.splitter.widget(1) is dashboard.source_hands
    assert dashboard.splitter.childrenCollapsible() is False, "a collapsed pane would hide the hands entirely"
    # The variables stay one click away and the header states how many are set.
    assert dashboard.variables_section.summary()
    dashboard.variables_section.set_expanded(False)
    assert dashboard.variables_section.body().isVisibleTo(dashboard) is False

    dashboard.shutdown_workers()


def test_the_study_dashboard_shows_one_zone_at_a_time_when_the_height_runs_out(qtbot, example_config, tmp_path) -> None:
    """A short window shows the panels or the hands, never half of each.

    The two zones want 360 px and 330 between them, and a 1080 x 691 window
    leaves the splitter 420: side by side that was a panel area pinned at its
    200 px floor and a table of 228. The bar gives the chosen zone the lot, and
    steps aside on a window tall enough for both.
    """
    app = get_qapp()
    from fpdb_3_legacy.GuiStudyDashboard import SWITCH_BELOW_HEIGHT, ZONE_HEIGHTS, GuiStudyDashboard
    from fpdb_3_legacy.research_studies import builtin_studies
    from fpdb_3_legacy.research_study_explorer import StudyExplorerModel

    assert SWITCH_BELOW_HEIGHT == sum(ZONE_HEIGHTS) + 8, "the threshold is the two zones plus their handle"

    model = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = model.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(example_config, None, None, selection=selection)
    qtbot.addWidget(dashboard)
    dashboard.show()

    switcher = dashboard.pane_switcher
    panels = dashboard.splitter.widget(0)
    hands = dashboard.splitter.widget(1)

    dashboard.resize(1080, 691)
    process(app)
    assert switcher.bar.isVisibleTo(dashboard) is True
    assert [pane.isVisibleTo(dashboard) for pane in (panels, hands)] == [True, False]
    assert panels.height() > 300, "the panel zone gets the height, not the 200 px floor"

    switcher.set_active(1)
    process(app)
    assert [pane.isVisibleTo(dashboard) for pane in (panels, hands)] == [False, True]
    assert hands.height() > 300

    # Tall enough for both: the bar steps aside and the splitter comes back.
    dashboard.resize(1400, 1200)
    process(app)
    assert switcher.bar.isVisibleTo(dashboard) is False
    assert [pane.isVisibleTo(dashboard) for pane in (panels, hands)] == [True, True]

    dashboard.shutdown_workers()


def test_the_study_dashboard_context_does_not_crowd_out_the_zones(qtbot, example_config, tmp_path) -> None:
    """The header scrolls, so it must not take the room the zones grow into."""
    app = get_qapp()
    from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
    from fpdb_3_legacy.research_studies import builtin_studies
    from fpdb_3_legacy.research_study_explorer import StudyExplorerModel

    model = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = model.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(example_config, None, None, selection=selection)
    qtbot.addWidget(dashboard)
    dashboard.show()
    dashboard.resize(1080, 691)
    process(app)

    assert dashboard.header_area.sizeHint().height() > 300, "the block asks for more than it may take"
    cap = max(CONTEXT_BLOCK_FLOOR, dashboard.height() // CONTEXT_BLOCK_SHARE)
    assert dashboard.header_area.height() <= cap
    assert dashboard.splitter.height() > 300

    dashboard.shutdown_workers()


def test_hud_preferences_fits_a_laptop_window(qtbot, example_config) -> None:
    from fpdb_3_legacy import ModernHudPreferences as M

    get_qapp()
    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)

    assert_fits(dialog)
    assert dialog.minimumSize().width() <= FITS_WIDTH
    assert dialog.minimumSize().height() <= FITS_HEIGHT


def test_the_long_hud_preferences_tabs_scroll(qtbot, example_config) -> None:
    """The tab bodies that asked for 880 px of height are the ones that scroll."""
    from fpdb_3_legacy import ModernHudPreferences as M

    get_qapp()
    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    pages = {dialog.tabs.tabText(index): dialog.tabs.widget(index) for index in range(dialog.tabs.count())}

    for title in ("Dynamic Panels", "Profile Select", "Reference HUDs"):
        page = next(page for name, page in pages.items() if title in name)
        assert isinstance(page, QScrollArea), f"{title} must scroll instead of clipping its last section"
        assert page.minimumSizeHint().height() <= FITS_HEIGHT


def test_the_hud_preferences_controls_survive_a_narrow_window(qtbot, example_config) -> None:
    """Every control the report showed clipped must still be there and usable."""
    app = get_qapp()
    from fpdb_3_legacy import ModernHudPreferences as M

    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.resize(FITS_WIDTH, FITS_HEIGHT)
    process(app)

    for control in (
        dialog.import_profile_btn,
        dialog.export_profile_btn,
        dialog.add_profile_btn,
        dialog.dup_profile_btn,
        dialog.del_profile_btn,
        dialog.profile_combo,
    ):
        assert control.isVisibleTo(dialog), f"{control.objectName() or type(control).__name__} is not reachable"

    assert dialog.import_profile_btn.isEnabled()
    # Save and Cancel stay visible: they are how the tab's edits reach the file.
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    assert button_box.button(QDialogButtonBox.StandardButton.Save).isVisibleTo(dialog)
    assert button_box.button(QDialogButtonBox.StandardButton.Cancel).isVisibleTo(dialog)


def test_the_hud_profile_actions_fold_into_one_menu_when_the_window_is_narrow(qtbot, example_config) -> None:
    """Five buttons set the dialog's minimum width; one menu gives it back.

    A reader who wants the preferences beside their table needs a window the
    five buttons cannot fit in. The same five actions move behind one menu below
    the width that holds them, which is what lowers the dialog's minimum.
    """
    app = get_qapp()
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy.modern_hud_preferences.main_dialog import NARROW_HEADER_WIDTH

    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.resize(1400, 900)
    process(app)
    assert dialog.add_profile_btn.isVisibleTo(dialog)
    assert not dialog.profile_actions_btn.isVisibleTo(dialog)

    dialog.resize(800, FITS_HEIGHT)
    process(app)
    assert dialog.width() < NARROW_HEADER_WIDTH, "the window must actually be able to be this narrow"
    assert not dialog.add_profile_btn.isVisibleTo(dialog)
    assert dialog.profile_actions_btn.isVisibleTo(dialog)
    assert dialog.minimumSizeHint().width() < NARROW_HEADER_WIDTH
    # The menu carries the same five actions, in the same order.
    assert [action.text() for action in dialog.profile_actions_menu.actions()] == [
        button.text() for button in dialog._profile_action_buttons()
    ]

    dialog.resize(1400, 900)
    process(app)
    assert dialog.add_profile_btn.isVisibleTo(dialog)
    assert not dialog.profile_actions_btn.isVisibleTo(dialog)


def _dynamic_panels_page(dialog) -> QScrollArea:
    pages = {dialog.tabs.tabText(index): dialog.tabs.widget(index) for index in range(dialog.tabs.count())}
    return next(page for name, page in pages.items() if "Dynamic Panels" in name)


def _open_dynamic_panels(dialog) -> None:
    """Show the dialog on the Dynamic Panels tab.

    A page that is not the current tab is hidden, and a hidden widget is not
    visible to its dialog -- so the reachability assertions below would fail on
    a control that is perfectly reachable to the reader.
    """
    dialog.show()
    dialog.tabs.setCurrentIndex(
        next(index for index in range(dialog.tabs.count()) if "Dynamic Panels" in dialog.tabs.tabText(index))
    )


def test_the_dynamic_panels_editor_reflows_its_fields(qtbot, example_config) -> None:
    """The 32 selectors follow the window width instead of a fixed four columns.

    They used to be a four-column grid inside a second scroll area, so a narrow
    window showed four squeezed columns and the group kept a 190 px floor of its
    own. The columns must now follow the width the dialog actually has, and no
    selector may be dropped on the way.
    """
    from fpdb_3_legacy import ModernHudPreferences as M
    from fpdb_3_legacy import hud_panel_editor as editor
    from fpdb_3_legacy.modern_hud_preferences.main_dialog import PANEL_FIELD_BREAKPOINTS

    app = get_qapp()
    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    _open_dynamic_panels(dialog)

    expected = len(editor.selector_fields())
    assert len(dialog.panel_selector_grid.items()) == expected
    assert len(dialog.panel_selector_widgets) == expected
    assert len(dialog.panel_behaviour_grid.items()) == 7

    for width in (1400, 1100, FITS_WIDTH, 900):
        dialog.resize(width, FITS_HEIGHT)
        process(app)
        # The columns follow the width the dialog actually has, which its own
        # minimum can clamp: the assertion is against that, not the requested
        # width, so it holds on every screen the tests run on.
        columns = column_count(dialog.width(), PANEL_FIELD_BREAKPOINTS)
        assert dialog.panel_selector_grid.columns() == columns
        assert dialog.panel_behaviour_grid.columns() == columns
        assert len(dialog.panel_selector_grid.items()) == expected, f"a selector was lost at {width} px"

    assert dialog.panel_selector_grid.columns() >= 3, "a laptop window still gets several columns"

    # Below the narrowest breakpoint a single column keeps the combos readable.
    dialog._reflow_panel_fields(500)
    assert dialog.panel_selector_grid.columns() == 1
    assert dialog.panel_behaviour_grid.columns() == 1


def test_the_dynamic_panels_editor_has_no_second_scroller(qtbot, example_config) -> None:
    """The tab scrolls once; the selector group must not scroll again inside it."""
    from fpdb_3_legacy import ModernHudPreferences as M

    get_qapp()
    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    page = _dynamic_panels_page(dialog)

    assert isinstance(page, QScrollArea)
    selectors = dialog.panel_selector_grid.parentWidget()
    assert selectors is not None
    assert selectors.findChild(QScrollArea) is None, "the selectors are scrolled by the tab, not by a scroller of their own"


def test_the_dynamic_panels_behaviour_fields_and_enabled_flag_stay_reachable(qtbot, example_config) -> None:
    """The seven "Then show" fields and the Enabled box are all laid out.

    "Enabled" used to sit at cell (1, 6) of a full grid, a position the layout
    could drop; it is now in a row of its own, and every field keeps a caption.
    """
    from fpdb_3_legacy import ModernHudPreferences as M

    app = get_qapp()
    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    _open_dynamic_panels(dialog)
    dialog.resize(FITS_WIDTH, FITS_HEIGHT)
    process(app)

    fields = (
        dialog.panel_rule_panel_combo,
        dialog.panel_rule_profile_combo,
        dialog.panel_rule_fallback_combo,
        dialog.panel_rule_priority,
        dialog.panel_rule_min_sample,
        dialog.panel_rule_sample,
        dialog.panel_rule_id,
    )
    for field in fields:
        container = field.parentWidget()
        assert container is not None
        assert dialog.panel_behaviour_grid.indexOf(container) >= 0, f"{type(field).__name__} left the grid"
        assert field.isVisibleTo(dialog), f"{type(field).__name__} is not reachable"
    assert dialog.panel_rule_enabled.isVisibleTo(dialog)
    assert dialog.panel_rule_enabled.isChecked()


def test_the_analytics_stat_catalogue_folds_and_says_how_many_it_holds(qtbot, example_config) -> None:
    """The catalogue is the tallest optional block; it folds but still reports."""
    from fpdb_3_legacy import ModernHudPreferences as M

    get_qapp()
    dialog = M.ModernHudPreferences(example_config, None)
    qtbot.addWidget(dialog)
    _open_dynamic_panels(dialog)
    section = dialog.panel_stat_section

    assert not section.is_expanded(), "the catalogue is folded by default so the rules table stays above the fold"
    assert section.summary().endswith("available")
    assert int(section.summary().split()[0]) == len(dialog.panel_stat_choices) > 0
    assert not section.body().isVisible()

    section.set_expanded(True)
    assert section.body().isVisible()
    assert dialog.panel_stat_combo.count() == len(dialog.panel_stat_choices)
    assert dialog.panel_stat_add_button.text()
