"""Offscreen UI checks for the two-sided source-hands pane (#366)."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QTableWidgetItem

from fpdb_3_legacy.analytics_query import Query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiDrillDown import (
    SourceHandsPane,
    _card_description,
    _card_pixmap,
    _CardImagesDelegate,
    style_signed_measure,
)
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_drilldown import (
    SIDE_DRILL_COLUMNS,
    SIDE_FIELD,
    SIDE_HERO,
    DrillContext,
    DrillCounts,
)
from tests.helpers import analytics_golden as golden

pytestmark = pytest.mark.qt

_STATE: list[object] = []


@pytest.fixture(scope="module")
def drill_db(tmp_path_factory) -> Database:
    tmp = tmp_path_factory.mktemp("drilldown-gui")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _STATE.append(importer)
    return db


def _context() -> DrillContext:
    return DrillContext(
        query=Query(metric="fold_frequency", filters={"game": "holdem"}),
        group={"street": "flop"},
        label="Flop · fold",
    )


def _counts() -> DrillCounts:
    return DrillCounts(
        hero_population=296, hero_numerator=42, field_population=11880, field_numerator=1283,
    )


def test_a_comparison_row_offers_four_named_hand_sets(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)

    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.table.rowCount() > 0, timeout=15000)

    labels = [button.text() for button in pane._target_buttons.values()]
    assert labels == [
        "Your population (296)",
        "Your actions (42)",
        "Field population (11,880)",
        "Field actions (1,283)",
    ]
    assert pane.current_target.side == SIDE_HERO
    assert not pane.current_target.numerator_only


def test_each_side_loads_its_own_hands_without_rerunning_the_question(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.table.rowCount() > 0, timeout=15000)
    hero_players = {pane.table.item(row, 6).text() for row in range(pane.table.rowCount())}

    pane.select_target(SIDE_FIELD)
    qtbot.waitUntil(
        lambda: pane.page is not None and pane.page.side == SIDE_FIELD and pane.table.rowCount() > 0,
        timeout=15000,
    )
    field_players = {pane.table.item(row, 6).text() for row in range(pane.table.rowCount())}

    assert len(hero_players) == 1
    assert not hero_players & field_players


def test_the_numerator_side_is_a_separate_selectable_set(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.page is not None, timeout=15000)
    population = pane.page.total_matches

    pane.select_target(SIDE_HERO, numerator_only=True)
    qtbot.waitUntil(lambda: pane.page is not None and pane.page.numerator_only, timeout=15000)

    assert pane.page.total_matches <= population
    assert pane.current_target.numerator_only


def test_a_large_side_pages_rather_than_loading_everything(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db, page_size=5)
    qtbot.addWidget(pane)

    pane.set_context(_context(), _counts(), default_side=SIDE_FIELD)
    qtbot.waitUntil(lambda: pane.page is not None and pane.table.rowCount() > 0, timeout=15000)

    assert pane.table.rowCount() <= 5
    assert pane.next_button.isEnabled()
    assert not pane.previous_button.isEnabled()
    first = list(pane.page.hand_ids)

    pane.next_button.click()
    qtbot.waitUntil(lambda: pane.page is not None and pane.page.offset == 5, timeout=15000)

    assert not set(pane.page.hand_ids) & set(first)
    assert pane.previous_button.isEnabled()
    assert "of " in pane.note_label.text()


def test_unknown_cards_are_left_blank_and_the_coverage_is_stated(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)

    pane.set_context(_context(), _counts(), default_side=SIDE_FIELD)
    qtbot.waitUntil(lambda: pane.page is not None and pane.table.rowCount() > 0, timeout=15000)

    cards = [pane.table.item(row, 8).text() for row in range(pane.table.rowCount())]
    assert all(text == "" or len(text) == 4 for text in cards)
    assert "Cards known for" in pane.coverage_label.text()


def test_source_hand_card_cells_use_card_faces_and_remain_accessible(qtbot) -> None:
    pane = SourceHandsPane(object())
    qtbot.addWidget(pane)

    player_cards_column = next(index for index, col in enumerate(SIDE_DRILL_COLUMNS) if col.key == "playerCards")
    board_column = next(index for index, col in enumerate(SIDE_DRILL_COLUMNS) if col.key == "board")
    assert isinstance(pane.table.itemDelegateForColumn(player_cards_column), _CardImagesDelegate)
    assert isinstance(pane.table.itemDelegateForColumn(board_column), _CardImagesDelegate)
    assert _card_pixmap("A", "s", 24, 33) is not None
    assert _card_pixmap("T", "h", 24, 33) is not None
    assert _card_description("As9h") == "Cards: A of spades, 9 of hearts"


def test_signed_financial_values_use_semantic_colors() -> None:
    loss = QTableWidgetItem("-7 ¢")
    gain = QTableWidgetItem("70 ¢")
    style_signed_measure(loss, "playerProfit", -7)
    style_signed_measure(gain, "hero_profit", 70)

    assert loss.foreground().color().name() == "#fc8181"
    assert gain.foreground().color().name() == "#68d391"


def test_a_double_click_hands_the_hand_id_to_the_replayer(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.table.rowCount() > 0, timeout=15000)

    opened: list[int] = []
    pane.hand_activated.connect(opened.append)
    pane._emit_hand(pane.table.item(0, 0))

    assert opened == [int(pane.table.item(0, 0).text())]


def test_counts_are_measured_when_the_caller_has_none(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)

    pane.set_context(_context())
    qtbot.waitUntil(
        lambda: all("(" in button.text() for button in pane._target_buttons.values()),
        timeout=15000,
    )

    assert pane._counts is not None
    assert pane._counts.hero_population > 0
    assert pane._counts.field_population > 0


def test_clearing_the_row_drops_the_pending_page(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.table.rowCount() > 0, timeout=15000)

    pane.clear("Pick a row.")

    assert pane.table.rowCount() == 0
    assert pane.note_label.text() == "Pick a row."
    assert pane.current_target is None
    pane.stop()


def _loads(pane: SourceHandsPane) -> list[tuple[str, bool]]:
    """Record every page load the pane starts, as (side, numerator_only)."""
    started: list[tuple[str, bool]] = []
    load = pane._load

    def recording_load() -> None:
        if pane.current_target is not None:
            started.append((pane.current_target.side, pane.current_target.numerator_only))
        load()

    pane._load = recording_load  # type: ignore[method-assign]
    return started


@pytest.mark.parametrize("press", ["click", "toggle"])
def test_pressing_a_hand_set_button_loads_that_set(qtbot, drill_db: Database, press: str) -> None:
    """#654: a press that toggles the button without a click left the hands unchanged.

    ``toggle`` is what macOS's accessibility press does to a checkable button
    (VoiceOver, an automated audit): the button changed, the page did not.
    """
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.page is not None, timeout=15000)
    started = _loads(pane)

    getattr(pane._target_buttons["field_numerator"], press)()
    qtbot.waitUntil(
        lambda: pane.page is not None and pane.page.side == SIDE_FIELD and pane.page.numerator_only,
        timeout=15000,
    )

    assert started == [(SIDE_FIELD, True)]
    assert [target_id for target_id, button in pane._target_buttons.items() if button.isChecked()] == [
        "field_numerator",
    ]


def test_the_open_hand_set_cannot_be_unchecked_into_none(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.page is not None, timeout=15000)
    started = _loads(pane)

    pane._target_buttons["hero_population"].toggle()

    assert pane._target_buttons["hero_population"].isChecked()
    assert started == []


def test_choosing_a_set_in_code_loads_it_once(qtbot, drill_db: Database) -> None:
    pane = SourceHandsPane(drill_db)
    qtbot.addWidget(pane)
    pane.set_context(_context(), _counts())
    qtbot.waitUntil(lambda: pane.page is not None, timeout=15000)
    started = _loads(pane)

    pane.select_target(SIDE_FIELD)

    assert started == [(SIDE_FIELD, False)]
    assert pane._target_buttons["field_population"].isChecked()
    assert not pane._target_buttons["hero_population"].isChecked()
    pane.stop()  # the page it started is still loading


def test_a_pane_deleted_mid_query_does_not_take_the_process_down(qtbot, drill_db: Database, monkeypatch) -> None:
    """The workers were children of the pane: deleting it deleted a running QThread.

    Qt aborts the whole process then ("QThread: Destroyed while thread is still
    running"). It struck the CI when the garbage collector freed a pane whose
    page was still loading.
    """
    import threading

    import shiboken6

    from fpdb_3_legacy import GuiDrillDown

    release = threading.Event()
    entered = threading.Event()
    real_drill = GuiDrillDown.run_side_drill

    def blocking_drill(*args, **kwargs):
        entered.set()
        release.wait(10)
        return real_drill(*args, **kwargs)

    monkeypatch.setattr(GuiDrillDown, "run_side_drill", blocking_drill)
    pane = SourceHandsPane(drill_db)
    pane.set_context(_context(), _counts())
    assert entered.wait(10)
    worker = pane._workers[-1]

    shiboken6.delete(pane)  # what Qt does to a closed tab's widgets, or the collector to a dropped pane
    release.set()

    qtbot.waitUntil(lambda: not shiboken6.isValid(worker) or worker.isFinished(), timeout=15000)
