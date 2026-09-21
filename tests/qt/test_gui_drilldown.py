"""Offscreen UI checks for the two-sided source-hands pane (#366)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.analytics_query import Query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiDrillDown import SourceHandsPane
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_drilldown import (
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
