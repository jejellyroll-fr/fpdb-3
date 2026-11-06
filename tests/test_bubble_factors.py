"""Each preflop tournament decision's bubble factor, stored for the study pack (#446).

The sit-and-go bubble hand (three left of a 9-max, 50/30/20) is imported, then
its tournament's decisions are priced: only once the payouts are known and the
field fits at the table.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import bubble_factors, icm, tourney_payouts
from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.bubble_factor_buckets import (
    BUBBLE_FACTOR_BUCKETS,
    BUBBLE_FACTOR_CAP,
    bubble_factor_bucket_of,
)
from fpdb_3_legacy.bubble_factors import decision_bubble_factors
from tests.helpers.icm_hands import PAYOUTS, SNG_ALLIN, parse

STACKS = {"Hero": 4000.0, "Villain": 3000.0, "Short": 1000.0}


# --- one hand's decisions -------------------------------------------------------------


def test_a_decision_facing_an_action_is_priced_against_its_author() -> None:
    priced = decision_bubble_factors(STACKS, [(1, "Hero", None, "raise"), (2, "Villain", "Hero", "call")], PAYOUTS)

    action_no, opponent, stored = priced[1]
    assert (action_no, opponent) == (2, "Hero")
    assert stored == round(icm.bubble_factor(STACKS, PAYOUTS, "Villain", "Hero") * 100)


def test_first_in_is_priced_against_the_most_expensive_live_player() -> None:
    decisions = [(1, "Hero", None, "raise"), (2, "Villain", "Hero", "call"), (3, "Short", "Hero", "fold")]

    priced = decision_bubble_factors(STACKS, decisions, PAYOUTS)

    factors = {name: icm.bubble_factor(STACKS, PAYOUTS, "Hero", name) for name in ("Villain", "Short")}
    worst = max(factors, key=factors.__getitem__)
    assert priced[0] == (1, worst, round(factors[worst] * 100))


def test_a_shove_over_a_limp_is_priced_against_the_limper() -> None:
    # Codex (#631): the small blind limps, the big blind shoves; the limper can still call.
    stacks = {"SB": 3000.0, "BB": 4000.0, "Short": 1000.0}
    decisions = [(1, "Short", None, "fold"), (2, "SB", None, "call"), (3, "BB", None, "raise"), (4, "SB", "BB", "fold")]

    priced = {
        action_no: (opponent, stored)
        for action_no, opponent, stored in decision_bubble_factors(stacks, decisions, PAYOUTS)
    }

    assert priced[3] == ("SB", round(icm.bubble_factor(stacks, PAYOUTS, "BB", "SB") * 100))  # Short folded first
    assert priced[2] == ("BB", round(icm.bubble_factor(stacks, PAYOUTS, "SB", "BB") * 100))


def test_a_decision_with_nobody_left_or_no_chips_is_not_priced() -> None:
    priced = decision_bubble_factors(
        {"Hero": 4000.0, "Villain": 0.0}, [(1, "Hero", None, "raise"), (2, "Villain", "Hero", "fold")], PAYOUTS
    )

    assert priced == []  # Hero has no opponent with chips, Villain has none to put in


def test_an_all_in_that_gains_nothing_is_stored_at_the_cap() -> None:
    # Two left, both paid the same: winning gains nothing, the factor is infinite.
    priced = decision_bubble_factors(
        {"A": 1000.0, "B": 1000.0}, [(1, "A", None, "raise"), (2, "B", "A", "call")], [10.0, 10.0]
    )

    assert [stored for _no, _opponent, stored in priced] == [BUBBLE_FACTOR_CAP, BUBBLE_FACTOR_CAP]


# --- stored for a tournament ------------------------------------------------------------


@pytest.fixture
def stored(tmp_path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    _hand, path = parse(tmp_path)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT tourneyId FROM Hands")
    (tourney,) = cursor.fetchone()
    yield fresh_db, tourney, importer, tmp_path
    del importer  # kept alive until the test is done: dropping it closes the database


def sng(db, tourney, entries=9) -> None:
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])
    db.get_cursor().execute("UPDATE Tourneys SET entries = ? WHERE id = ?", (entries, tourney))
    db.commit()


def rows(db) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT pl.name, ib.opponent, ib.bubbleFactor FROM ActionBubbleFactors ib "
        "JOIN HandsActions a ON a.handId = ib.handId AND a.actionNo = ib.actionNo "
        "JOIN Players pl ON pl.id = a.playerId ORDER BY ib.actionNo"
    )
    return cursor.fetchall()


def test_a_sit_and_go_s_decisions_are_priced_from_the_stacks_at_the_start(stored) -> None:
    db, tourney, _importer, _path = stored
    sng(db, tourney)

    count = bubble_factors.refresh_tourney(db, tourney)

    priced = rows(db)
    assert count == len(priced) == 3  # Hero's shove, Villain's call, Short's fold
    for player, opponent, factor in priced:
        assert factor == round(icm.bubble_factor(STACKS, PAYOUTS, player, opponent) * 100)
    assert ("Villain", "Hero") in {(player, opponent) for player, opponent, _factor in priced}


def test_a_refresh_replaces_the_tournament_s_rows(stored) -> None:
    db, tourney, _importer, _path = stored
    sng(db, tourney)
    bubble_factors.refresh_tourney(db, tourney)
    bubble_factors.refresh_tourney(db, tourney)
    assert len(rows(db)) == 3

    tourney_payouts.clear_payouts(db, tourney)
    bubble_factors.refresh_tourney(db, tourney)
    assert rows(db) == []


@pytest.mark.parametrize("entries", [None, 180])
def test_a_field_that_does_not_fit_the_table_is_not_priced(stored, entries) -> None:
    db, tourney, _importer, _path = stored
    sng(db, tourney, entries)

    assert bubble_factors.refresh_tourney(db, tourney) == 0 and rows(db) == []


def test_a_tournament_without_payouts_is_not_priced(stored) -> None:
    db, tourney, _importer, _path = stored
    db.get_cursor().execute("UPDATE Tourneys SET entries = 9 WHERE id = ?", (tourney,))
    db.commit()

    assert bubble_factors.refresh_tourney(db, tourney) == 0


def test_an_import_refreshes_the_tournaments_it_touched(stored) -> None:
    db, tourney, importer, tmp_path = stored
    sng(db, tourney)
    later = tmp_path / "later.txt"
    later.write_text(
        SNG_ALLIN.replace("200000000001", "200000000009").replace("12:00:00", "12:10:00"), encoding="utf-8"
    )

    importer.addImportFile(str(later), "PokerStars")
    importer.runImport()

    cursor = db.get_cursor()
    cursor.execute("SELECT COUNT(DISTINCT handId) FROM ActionBubbleFactors WHERE tourneyId = ?", (tourney,))
    assert cursor.fetchone()[0] == 2  # the earlier hand too: the whole tournament is refreshed


def test_the_study_band_reads_the_stored_factor(stored) -> None:
    db, tourney, _importer, _path = stored
    sng(db, tourney)
    bubble_factors.refresh_tourney(db, tourney)

    result = run_query(
        db, Query(metric="opportunities", filters={"tournament": True}, group_by=["bubble_factor_bucket"])
    )

    bands = {row.group["bubble_factor_bucket"]: row.opportunities for row in result.rows}
    assert sum(count for band, count in bands.items() if band != "unknown") == 3
    assert set(bands) <= set(BUBBLE_FACTOR_BUCKETS)


# --- the bands ------------------------------------------------------------------------


def test_an_unknown_factor_is_its_own_band() -> None:
    assert bubble_factor_bucket_of(None) == bubble_factor_bucket_of(0) == "unknown"


@pytest.mark.parametrize(
    ("factor", "band"),
    [
        (0, "unknown"),
        (100, "up_to_1_2"),
        (120, "up_to_1_2"),
        (121, "1_2_to_1_5"),
        (150, "1_2_to_1_5"),
        (200, "1_5_to_2"),
        (300, "2_to_3"),
        (301, "3_plus"),
        (BUBBLE_FACTOR_CAP, "3_plus"),
    ],
)
def test_python_and_the_query_engine_put_a_factor_in_the_same_band(stored, factor, band) -> None:
    db, tourney, _importer, _path = stored
    sng(db, tourney)
    bubble_factors.refresh_tourney(db, tourney)
    db.get_cursor().execute("UPDATE ActionBubbleFactors SET bubbleFactor = ?", (factor,))
    db.commit()

    result = run_query(
        db, Query(metric="opportunities", filters={"tournament": True}, group_by=["bubble_factor_bucket"])
    )

    bands = {row.group["bubble_factor_bucket"]: row.opportunities for row in result.rows}
    assert bubble_factor_bucket_of(factor) == band
    assert bands.get(band, 0) >= 3  # the three stored decisions, whatever else is unknown
