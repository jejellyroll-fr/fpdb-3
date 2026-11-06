"""Knockout or freezeout: the filter of the study pack and of the tournament reports (#447).

Two sit-and-gos are imported: the bubble hand as a freezeout, and the same hand
as a PokerStars progressive knockout. The filter keeps one or the other.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.tourney_format import format_condition
from tests.helpers.icm_hands import PKO, SNG_ALLIN, parse


@pytest.mark.parametrize(
    ("tourney_format", "sqlite", "condition"),
    [
        ("all", True, ""),
        ("knockout", True, "AND tt.knockout = 1"),
        ("knockout", False, "AND tt.knockout = TRUE"),
        ("freezeout", False, "AND (tt.knockout IS NULL OR NOT tt.knockout = TRUE)"),
        ("unknown", True, ""),
    ],
)
def test_each_format_has_a_fixed_condition(tourney_format, sqlite, condition) -> None:
    assert format_condition(tourney_format, sqlite) == condition


@pytest.fixture
def two_sngs(tmp_path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    for name, text in (("freezeout", SNG_ALLIN), ("knockout", PKO)):
        folder = tmp_path / name
        folder.mkdir()
        _hand, path = parse(folder, text)
        importer.addImportFile(str(path), "PokerStars")
        importer.runImport()
    yield fresh_db
    del importer  # kept alive until the test is done: dropping it closes the database


def decisions(db, **filters) -> int:
    return sum(row.opportunities for row in run_query(db, Query(metric="opportunities", filters=filters)).rows)


def test_the_query_engine_keeps_knockout_hands_or_the_others(two_sngs) -> None:
    every = decisions(two_sngs, tournament=True)
    knockout = decisions(two_sngs, tournament=True, knockout=True)
    freezeout = decisions(two_sngs, tournament=True, knockout=False)

    assert knockout > 0 and freezeout > 0
    assert knockout + freezeout == every


def test_the_knockout_breakdown_splits_the_hands(two_sngs) -> None:
    result = run_query(two_sngs, Query(metric="opportunities", filters={"tournament": True}, group_by=["knockout"]))

    assert len(result.rows) == 2


def test_the_player_report_keeps_one_format(two_sngs) -> None:
    def report(tourney_format: str) -> list[tuple]:
        query = (
            two_sngs.sql.query["tourneyPlayerDetailedStats"]
            .replace("<nametest>", "(SELECT id FROM Players WHERE name = 'Hero')")
            .replace("<sitetest>", format_condition(tourney_format, sqlite=True))
            .replace("<seats_test>", "between 0 and 100")
            .replace("<startdate_test>", "1970-01-01")
            .replace("<enddate_test>", "2100-01-01")
        )
        cursor = two_sngs.get_cursor()
        cursor.execute(query)
        columns = [description[0].lower() for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    assert len(report("all")) == 2
    (knockout,) = report("knockout")
    (freezeout,) = report("freezeout")
    assert knockout["knockout"] and not freezeout["knockout"]


def test_the_research_browser_offers_a_yes_or_no_choice() -> None:
    # Codex (#635): a free-text field turned "No" into a truthy string, selecting knockouts.
    from fpdb_3_legacy.research_browser import FILTER_SPECS

    (spec,) = (spec for spec in FILTER_SPECS if spec.name == "knockout")
    assert spec.value_kind == "bool"


def test_each_breakdown_group_drills_into_the_hands_it_counts(two_sngs) -> None:
    # Codex (#635): a type whose knockout flag was never read is not a knockout, in the
    # breakdown as in the filter, so its hands sit in one group and come back with it.
    two_sngs.get_cursor().execute("UPDATE TourneyTypes SET knockout = NULL WHERE knockout = 0")
    two_sngs.commit()
    from fpdb_3_legacy.research_browser import drill_query

    grouped = Query(metric="opportunities", filters={"tournament": True}, group_by=["knockout"])
    rows = run_query(two_sngs, grouped).rows

    assert sorted(row.group["knockout"] for row in rows) == [0, 1]
    for row in rows:
        drilled = drill_query(grouped, row.group, numerator_only=False)
        assert decisions(two_sngs, **drilled.filters) == row.opportunities


def test_the_player_report_keeps_the_tables_within_the_number_of_players(two_sngs) -> None:
    """#651: a 6-max tournament stayed in the report with the maximum set to 3."""
    from types import SimpleNamespace

    from fpdb_3_legacy.GuiTourneyPlayerStats import GuiTourneyPlayerStats

    hero_ids = [row[0] for row in two_sngs.get_cursor().execute("SELECT id FROM Players WHERE name = 'Hero'")]
    type_ids = [row[0] for row in two_sngs.get_cursor().execute("SELECT id FROM TourneyTypes ORDER BY id")]
    site_ids = [row[0] for row in two_sngs.get_cursor().execute("SELECT DISTINCT siteId FROM TourneyTypes")]
    tab = SimpleNamespace(
        db=two_sngs,
        detailFilters=[],
        filters=SimpleNamespace(getDates=lambda: ("1970-01-01", "2100-01-01"), getTourneyFormat=lambda: "all"),
    )

    def seat_counts_shown(sizes, seats) -> list[int]:
        for type_id, size in zip(type_ids, sizes, strict=True):
            two_sngs.get_cursor().execute("UPDATE TourneyTypes SET maxSeats = ? WHERE id = ?", (size, type_id))
        query = GuiTourneyPlayerStats.refineQuery(
            tab, two_sngs.sql.query["tourneyPlayerDetailedStats"], 0, [], hero_ids, site_ids, seats
        )
        cursor = two_sngs.get_cursor()
        cursor.execute(query)
        columns = [description[0].lower() for description in cursor.description]
        return sorted(dict(zip(columns, row, strict=True))["maxseats"] for row in cursor.fetchall())

    assert seat_counts_shown((3, 6), {"from": 2, "to": 3}) == [3]
    assert seat_counts_shown((2, 8), {"from": 2, "to": 3}) == [2]
    assert seat_counts_shown((6, 8), {"from": 2, "to": 3}) == []
    assert seat_counts_shown((6, 8), {"from": 6, "to": 10}) == [6, 8]
    # A size the room did not give cannot be ruled out.
    assert seat_counts_shown((0, 8), {"from": 2, "to": 3}) == [0]
