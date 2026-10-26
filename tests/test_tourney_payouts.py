"""Tournament payout structures (#446): what each place pays, so ICM has its input.

The pure part -- splitting a prize pool, presets, settling a structure from
results -- is checked directly; the database part on a throwaway SQLite
schema, with tournaments written as the importer would.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from fpdb_3_legacy import tourney_payouts as payouts
from fpdb_3_legacy.tourney_payouts import PRESETS, from_results, split_prize_pool

# --- splitting a prize pool ---------------------------------------------------------


def test_the_split_adds_up_to_the_prize_pool_to_the_hundredth() -> None:
    assert split_prize_pool(1000, [Fraction(1, 3)] * 3) == (334, 333, 333)
    assert sum(split_prize_pool(8136, PRESETS["sng_9max"](9))) == 8136


def test_the_leftover_hundredths_go_to_the_places_rounding_cut_most() -> None:
    assert split_prize_pool(101, [Fraction(1, 2), Fraction(3, 10), Fraction(1, 5)]) == (51, 30, 20)


@pytest.mark.parametrize(
    "shares",
    [[], [Fraction(1, 2)], [Fraction(3, 2), Fraction(-1, 2)]],
    ids=["none", "not-all-of-it", "negative"],
)
def test_shares_that_do_not_split_a_pool_are_refused(shares) -> None:
    with pytest.raises(ValueError):
        split_prize_pool(1000, shares)


@pytest.mark.parametrize(("preset", "entries"), [(name, 10) for name in PRESETS])
def test_every_preset_shares_out_the_whole_pool(preset, entries) -> None:
    shares = PRESETS[preset](entries)

    assert sum(shares) == 1
    assert list(shares) == sorted(shares, reverse=True)


def test_double_or_nothing_pays_half_the_field_equally() -> None:
    assert split_prize_pool(10000, PRESETS["double_or_nothing"](10)) == (2000,) * 5


# --- settling a structure from results -----------------------------------------------


def test_a_full_sng_result_settles_its_paid_places() -> None:
    results = [(1, 4068), (2, 2441), (3, 1627), *((place, 0) for place in range(4, 10))]

    assert from_results(results, entries=9) == (4068, 2441, 1627)


def test_a_winner_take_all_result_settles_one_place() -> None:
    assert from_results([(1, 300), (2, 0), (3, 0)], entries=3) == (300,)


def test_a_field_paid_down_to_the_last_place_is_settled_by_its_size() -> None:
    assert from_results([(1, 600), (2, 400)], entries=2) == (600, 400)


@pytest.mark.parametrize(
    "results",
    [
        [(8, 0)],  # a summary of the hero alone, out of the money
        [(1, 2000)],  # the winner alone: does second pay?
        [(1, 4068), (3, 1627), (4, 0)],  # a paid place missing
        [(5, 0), (6, 0)],  # nobody known to be paid
    ],
    ids=["hero-only", "winner-only", "gap", "no-winnings"],
)
def test_results_that_do_not_settle_every_paid_place_settle_nothing(results) -> None:
    assert from_results(results, entries=9) is None


@pytest.mark.parametrize(
    "results",
    [
        [(1, 600), (2, None)],  # Codex (#626): an unknown second prize is no proof of an unpaid place
        [(1, 600), (2, -1)],  # -1: a prize the importer could not read
        [(1, None), (2, 0)],
        [(1, 600), (2, None), (3, 0)],  # an unknown place inside what might be paid
    ],
    ids=["null-next", "sentinel-next", "null-winner", "null-inside"],
)
def test_unknown_winnings_neither_pay_nor_prove_a_place_unpaid(results) -> None:
    assert from_results(results, entries=9) is None


# --- the database ------------------------------------------------------------------
#
# Tournaments are written directly rather than imported: what the summary
# parsers store is their own matter (and #624, #625 track two of their bugs);
# here the question is what fpdb makes of a tournament's rows.

INSERT_TYPE = (
    "INSERT INTO TourneyTypes (siteId, currency, buyIn, fee, category, limitType, knockout, koBounty)"
    " VALUES (?, ?, ?, ?, 'holdem', 'nl', ?, ?)"
)
INSERT_TOURNEY = "INSERT INTO Tourneys (tourneyTypeId, siteTourneyNo, entries, prizepool) VALUES (?, ?, ?, ?)"
INSERT_PLAYER = "INSERT INTO Players (name, siteId) VALUES (?, ?)"
INSERT_RESULT = (
    "INSERT INTO TourneysPlayers (tourneyId, playerId, rank, winnings, winningsCurrency) VALUES (?, ?, ?, ?, ?)"
)


def add_tourney(
    db, number, results, *, entries, prize_pool, buy_in=1000, currency="USD", knockout=False, bounty=None
) -> int:
    """A tournament with ``results`` as (place, winnings in hundredths); returns its id."""
    cursor = db.get_cursor()
    cursor.execute(INSERT_TYPE, (2, currency, buy_in, buy_in // 10, knockout, bounty))
    cursor.execute(INSERT_TOURNEY, (cursor.lastrowid, number, entries, prize_pool))
    tourney = cursor.lastrowid
    for place, won in results:
        cursor.execute(INSERT_PLAYER, (f"player{number}_{place}", 2))
        cursor.execute(INSERT_RESULT, (tourney, cursor.lastrowid, place, won, currency))
    db.commit()
    return tourney


SNG_9 = [(1, 4500), (2, 2700), (3, 1800), *((place, 0) for place in range(4, 10))]


def test_results_that_settle_the_structure_are_its_source(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1001, SNG_9, entries=9, prize_pool=9000)

    found = payouts.payouts_for_tourney(fresh_db, tourney)

    assert found.payouts is not None
    assert found.payouts.amounts == (4500, 2700, 1800)
    assert found.payouts.source == "summary"
    assert found.payouts.currency == "USD"
    assert found.payouts.as_money() == [45.0, 27.0, 18.0]


def test_results_of_the_hero_alone_settle_nothing_and_say_why(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1002, [(8, 0)], entries=9, prize_pool=8136)

    found = payouts.payouts_for_tourney(fresh_db, tourney)

    assert found.payouts is None
    assert "no payout structure known" in found.reason


def test_knockout_winnings_are_never_read_as_a_structure(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1003, SNG_9, entries=9, prize_pool=9000, knockout=True)

    found = payouts.payouts_for_tourney(fresh_db, tourney)

    assert found.payouts is None
    assert "bounties" in found.reason


def test_an_entered_structure_overrides_the_results_until_it_is_cleared(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1004, SNG_9, entries=9, prize_pool=9000)

    payouts.store_payouts(fresh_db, tourney, [6000, 3000])
    entered = payouts.payouts_for_tourney(fresh_db, tourney).payouts
    assert entered is not None and (entered.amounts, entered.source) == ((6000, 3000), "manual")

    payouts.clear_payouts(fresh_db, tourney)
    assert payouts.payouts_for_tourney(fresh_db, tourney).payouts.source == "summary"


def test_a_preset_is_applied_to_the_prize_pool(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1005, [(8, 0)], entries=9, prize_pool=8136, currency="EUR")

    applied = payouts.apply_preset(fresh_db, tourney, "sng_9max")

    assert applied.amounts == (4068, 2441, 1627)
    assert sum(applied.amounts) == 8136
    assert applied.source == "preset:sng_9max"
    assert payouts.payouts_for_tourney(fresh_db, tourney).payouts == applied


def test_a_preset_falls_back_on_buy_in_times_entries(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1006, [], entries=10, prize_pool=None, buy_in=500)

    assert payouts.apply_preset(fresh_db, tourney, "double_or_nothing").amounts == (1000,) * 5


def test_a_knockout_fallback_pool_leaves_the_bounties_out(fresh_db) -> None:
    # Codex (#626): a $5+$5 knockout stores a $10 buy-in; only $5 of each feeds the places.
    tourney = add_tourney(fresh_db, 1009, [], entries=9, prize_pool=None, buy_in=1000, knockout=True, bounty=500)

    assert payouts.apply_preset(fresh_db, tourney, "winner_take_all").amounts == (4500,)


def test_a_knockout_with_no_prize_pool_nor_bounty_size_is_refused(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1010, [], entries=9, prize_pool=None, buy_in=1000, knockout=True)

    with pytest.raises(ValueError, match="bounty"):
        payouts.apply_preset(fresh_db, tourney, "sng_9max")
    assert payouts.stored_payouts(fresh_db, tourney) is None


def test_double_or_nothing_needs_the_field_size(fresh_db) -> None:
    # Codex (#626): without entries it used to store a winner-take-all structure.
    tourney = add_tourney(fresh_db, 1011, [], entries=None, prize_pool=10000)

    with pytest.raises(ValueError, match="field size"):
        payouts.apply_preset(fresh_db, tourney, "double_or_nothing")
    assert payouts.stored_payouts(fresh_db, tourney) is None


def test_an_unknown_preset_or_a_bad_structure_is_refused(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1007, SNG_9, entries=9, prize_pool=9000)

    with pytest.raises(ValueError):
        payouts.apply_preset(fresh_db, tourney, "sng_1000max")
    with pytest.raises(ValueError):
        payouts.store_payouts(fresh_db, tourney, [])
    with pytest.raises(ValueError):
        payouts.store_payouts(fresh_db, tourney, [100, -5])


def test_a_hand_is_given_its_tournament_s_structure(fresh_db) -> None:
    tourney = add_tourney(fresh_db, 1008, SNG_9, entries=9, prize_pool=9000)
    cursor = fresh_db.get_cursor()
    cursor.execute(
        "INSERT INTO Gametypes (siteId, currency, type, base, category, limitType, hiLo, mix, smallBlind,"
        " bigBlind, smallBet, bigBet, maxSeats, ante, buyinType)"
        " VALUES (2, 'T$', 'tour', 'hold', 'holdem', 'nl', 'h', 'none', 10, 20, 20, 0, 9, 0, 'regular')"
    )
    gametype = cursor.lastrowid
    cursor.execute(
        "INSERT INTO Hands (tableName, siteHandNo, tourneyId, gametypeId, fileId, startTime, importTime, seats,"
        " heroSeat, maxPosition, playersVpi, playersAtStreet1, playersAtStreet2, playersAtStreet3,"
        " playersAtStreet4, playersAtShowdown, street0Raises, street1Raises, street2Raises, street3Raises,"
        " street4Raises)"
        " VALUES ('t', 1, ?, ?, 0, '2026-01-01', '2026-01-01', 9, 0, 9, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
        (tourney, gametype),
    )
    fresh_db.commit()

    assert payouts.payouts_for_hand(fresh_db, cursor.lastrowid).payouts.amounts == (4500, 2700, 1800)


def test_a_hand_outside_a_tournament_has_no_structure(fresh_db) -> None:
    found = payouts.payouts_for_hand(fresh_db, 123456)

    assert found.payouts is None
    assert found.reason == "not a tournament hand"


def test_a_database_from_before_the_table_gets_it_on_connection(fresh_db) -> None:
    cursor = fresh_db.get_cursor()
    cursor.execute("DROP TABLE TourneyPayouts")
    fresh_db.commit()

    fresh_db.ensure_feature_tables()

    cursor.execute("SELECT COUNT(*) FROM TourneyPayouts")
    assert cursor.fetchone()[0] == 0
