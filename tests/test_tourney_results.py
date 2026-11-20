"""The per-tournament results behind the Tourney Stats tab."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.GuiTourneyPlayerStats import GuiTourneyPlayerStats
from fpdb_3_legacy.tourney_results import (
    BY_BUYIN,
    BY_DATE,
    BY_DESCRIPTION,
    BY_TOURNAMENT,
    TOURNEY_RESULTS_QUERY,
    TourneyResult,
    describe,
    filter_results,
    group_results,
    main_currency,
    result_from_row,
    running_curves,
    summarize,
)
from tests import test_knockout_filter

# The two imported sit-and-gos of the knockout tests, shared as a fixture.
two_sngs = test_knockout_filter.two_sngs


def result(tourney_id: int, *, prize: float | None = 0.0, bounties: float = 0.0, **fields) -> TourneyResult:
    values = {
        "tourney_id": tourney_id,
        "tourney_no": 1000 + tourney_id,
        "tourney_type_id": 1,
        "player_id": 7,
        "player_name": "alice",
        "site": "Winamax",
        "currency": "EUR",
        "buy_in": 0.23,
        "fee": 0.02,
        "prize": prize,
        "bounties": bounties,
        "max_seats": 3,
        "speed": "Hyper",
        "category": "holdem",
        "limit_type": "nl",
        "sng": True,
        "start": datetime(2026, 6, 21, 12, tourney_id),
    }
    values.update(fields)
    return TourneyResult(**values)


def test_a_result_reads_a_row_whatever_the_column_case() -> None:
    # PostgreSQL folds unquoted aliases to lower case.
    row = {
        "tourneyid": 3,
        "tourneyno": 1134150786,
        "tourneytypeid": 2,
        "playerid": 7,
        "playername": "alice",
        "sitename": "Winamax",
        "currency": "EUR",
        "buyin": 23,
        "fee": 2,
        "finish": 1,
        "winnings": 75,
        "bounties": 0,
        "starttime": "2026-06-21 21:05:00",
        "handcount": 12,
        "maxseats": 3,
        "sng": 1,
    }

    parsed = result_from_row(row)

    assert parsed.cost == pytest.approx(0.25)
    assert parsed.net == pytest.approx(0.50)
    assert parsed.finish == 1
    assert parsed.hands == 12
    assert parsed.start == datetime(2026, 6, 21, 21, 5)
    assert parsed.cashed


def test_play_money_keeps_its_buy_in_in_chips_as_the_stats_query_does() -> None:
    parsed = result_from_row(
        {"tourneyId": 1, "tourneyTypeId": 1, "playerId": 1, "currency": "play", "buyIn": 1500, "fee": 100}
    )

    assert parsed.buy_in == 1500
    assert parsed.fee == 0


def test_an_unknown_rank_is_no_finish() -> None:
    parsed = result_from_row({"tourneyId": 1, "tourneyTypeId": 1, "playerId": 1, "finish": 0})

    assert parsed.finish is None


def test_the_summary_counts_cashes_on_prizes_and_finishes_when_known() -> None:
    results = [
        result(1, prize=0.75),
        result(2, finish=2),
        result(3, bounties=0.10, finish=3),
        result(4, finish=1, prize=0.50),
    ]
    results[0] = result(1, prize=0.75, finish=1)

    (summary,) = summarize(results).values()

    assert summary.count == 4
    assert summary.cost == pytest.approx(1.00)
    assert summary.won == pytest.approx(1.35)
    assert summary.net == pytest.approx(0.35)
    assert summary.roi == pytest.approx(35.0)
    # A bounty alone is not a cash, as in tourneyPlayerDetailedStats.
    assert summary.cashes == 2
    assert summary.itm == pytest.approx(50.0)
    assert (summary.first, summary.second, summary.third) == (2, 1, 1)
    assert summary.avg_finish == pytest.approx(7 / 4)


def test_amounts_in_different_currencies_are_never_added() -> None:
    totals = summarize([result(1, prize=1.0), result(2, currency="USD"), result(3, currency="USD")])

    assert set(totals) == {"EUR", "USD"}
    assert totals["EUR"].net == pytest.approx(0.75)
    assert totals["USD"].net == pytest.approx(-0.50)
    assert main_currency([result(1), result(2, currency="USD"), result(3, currency="USD")]) == "USD"


def test_a_tournament_without_a_result_is_not_a_loss() -> None:
    """Imported from its hands alone, a tournament has no prize: it is unknown, not a lost buy-in."""
    results = [result(1, prize=0.75), result(2, prize=None), result(3)]

    (summary,) = summarize(results).values()

    assert summary.count == 3
    assert summary.unknown == 1
    assert summary.cost == pytest.approx(0.50)
    assert summary.net == pytest.approx(0.25)
    assert summary.itm == pytest.approx(50.0)
    assert running_curves(results).net == pytest.approx([0.50, 0.25])
    assert result_from_row({"tourneyId": 1, "tourneyTypeId": 1, "playerId": 1, "winnings": None}).known is False


def test_the_curves_run_after_each_tournament() -> None:
    curves = running_curves([result(1, prize=0.75), result(2), result(3)])

    assert curves.net == pytest.approx([0.50, 0.25, 0.0])
    assert curves.roi == pytest.approx([200.0, 50.0, 0.0])
    assert curves.itm == pytest.approx([100.0, 50.0, 100.0 / 3])


def test_each_view_groups_the_results_it_shows() -> None:
    results = [
        result(1, prize=0.75),
        result(2, tourney_type_id=2, buy_in=0.45, fee=0.05),
        result(3, start=datetime(2026, 6, 22, 12, 0)),
    ]

    assert [g.summary.count for g in group_results(BY_DESCRIPTION, results)] == [2, 1]
    assert [g.key for g in group_results(BY_BUYIN, results)] == [("EUR", 0.25), ("EUR", 0.5)]
    assert len(group_results(BY_DATE, results)) == 2
    assert len(group_results(BY_TOURNAMENT, results)) == 3
    (first,) = [g for g in group_results(BY_DESCRIPTION, results) if g.summary.count == 2]
    assert [r.tourney_id for r in filter_results(results, BY_DESCRIPTION, first.key)] == [1, 3]


def test_the_description_reads_like_a_tournament_list() -> None:
    assert describe(result(1)) == "SNG (3-max) Hyper NL Hold'em"
    assert describe(result(1, sng=False, entries=180, max_seats=9, knockout=True)) == "MTT (9-max) Hyper NL Hold'em KO"


def test_the_results_query_matches_the_detailed_stats(two_sngs) -> None:
    """Both queries take the same filters: the overview must add up to the old grid."""
    hero_ids = [row[0] for row in two_sngs.get_cursor().execute("SELECT id FROM Players WHERE name = 'Hero'")]
    site_ids = [row[0] for row in two_sngs.get_cursor().execute("SELECT DISTINCT siteId FROM TourneyTypes")]
    tab = SimpleNamespace(
        db=two_sngs,
        detailFilters=[],
        filters=SimpleNamespace(getDates=lambda: ("1970-01-01", "2100-01-01"), getTourneyFormat=lambda: "all"),
    )

    def rows(query: str) -> list[dict]:
        cursor = two_sngs.get_cursor()
        cursor.execute(GuiTourneyPlayerStats.refineQuery(tab, query, 0, [], hero_ids, site_ids, None))
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    unknown = [result_from_row(row) for row in rows(TOURNEY_RESULTS_QUERY)]
    assert len(unknown) == 2
    assert all(r.hands > 0 for r in unknown)
    assert not any(r.known for r in unknown)

    # With the results recorded, as a tournament summary records them.
    cursor = two_sngs.get_cursor()
    cursor.execute(
        "UPDATE TourneysPlayers SET rank = 1, winnings = 2000 WHERE playerId IN (SELECT id FROM Players WHERE name = 'Hero')"
    )
    two_sngs.commit()
    results = [result_from_row(row) for row in rows(TOURNEY_RESULTS_QUERY)]
    detailed = rows(two_sngs.sql.query["tourneyPlayerDetailedStats"])

    (summary,) = summarize(results).values()
    assert summary.count == sum(row["tourneyCount"] for row in detailed)
    assert summary.cost == pytest.approx(sum(row["spent"] for row in detailed))
    assert summary.net == pytest.approx(sum(row["net"] for row in detailed))
    assert summary.bounties == pytest.approx(sum(row["bounties"] for row in detailed))
