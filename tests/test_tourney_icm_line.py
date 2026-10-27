"""The tournament graph's ICM line: results with the all-in luck taken out (#446).

The sit-and-go bubble hand is imported, then rebuilt from the database as the
graph does it. Hero shoves AsKs into Villain's queens and loses: the luck is
the prize equity the hand moved less its ICM $EV, and the line gives it back.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import Hand, tourney_payouts
from fpdb_3_legacy.hand_icm import hand_allin_icm
from fpdb_3_legacy.tourney_icm_line import allin_hands, icm_line
from tests.helpers.icm_hands import PAYOUTS, fixed_equity, parse

OTHER_TOURNEY = 999  # a tournament of the graph with no all-in hand


@pytest.fixture
def stored(tmp_path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    hand, path = parse(tmp_path)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT tourneyId FROM Hands")
    (tourney,) = cursor.fetchone()
    cursor.execute("SELECT name, id FROM Players")
    players = dict(cursor.fetchall())
    yield fresh_db, legacy_config, hand, tourney, players
    del importer  # kept alive until the test is done: dropping it closes the database


def loader(db, config):
    return lambda hand_id: Hand.hand_factory(hand_id, config, db)


def hero_luck(hand) -> float:
    allin = hand_allin_icm(hand, PAYOUTS, table_only=True, equity_fn=fixed_equity(46, 54)).allin
    return allin.icm_result["Hero"] - allin.icm_ev["Hero"]


def test_the_hands_are_those_the_player_saw_to_showdown_after_an_all_in(stored) -> None:
    db, _config, _hand, tourney, players = stored

    found = allin_hands(db, [players["Hero"], players["Villain"], players["Short"]])

    assert [name for _hand_id, name in found[tourney]] == ["Hero", "Villain"]  # Short folded


def test_without_a_payout_structure_the_line_is_the_profit(stored) -> None:
    db, config, _hand, tourney, players = stored

    line = icm_line(
        db,
        [(tourney, -11.0), (OTHER_TOURNEY, 5.0)],
        allin_hands(db, [players["Hero"]]),
        loader(db, config),
        equity_fn=fixed_equity(46, 54),
    )

    assert line.values == (-11.0, -6.0)
    assert (line.priced, line.allins) == (0, 1)


def test_a_priced_all_in_gives_its_luck_back(stored) -> None:
    db, config, hand, tourney, players = stored
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])

    line = icm_line(
        db,
        [(tourney, -11.0), (OTHER_TOURNEY, 5.0)],
        allin_hands(db, [players["Hero"]]),
        loader(db, config),
        equity_fn=fixed_equity(46, 54),
    )

    luck = hero_luck(hand)
    assert luck < 0  # the hand cost Hero more prize equity than a 46% shot was worth
    assert line.values == pytest.approx((-11.0 - luck, -6.0 - luck))
    assert (line.priced, line.allins) == (1, 1)


def test_a_hand_is_priced_once_per_structure(stored) -> None:
    db, config, _hand, tourney, players = stored
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])
    hands = allin_hands(db, [players["Hero"]])
    cache: dict = {}
    first = icm_line(db, [(tourney, 0.0)], hands, loader(db, config), cache=cache, equity_fn=fixed_equity(46, 54))

    def not_again(_hand_id):
        raise AssertionError("the hand was rebuilt again")

    again = icm_line(db, [(tourney, 0.0)], hands, not_again, cache=cache, equity_fn=fixed_equity(46, 54))
    assert again == first

    tourney_payouts.store_payouts(db, tourney, [10000])  # winner takes all: priced again
    changed = icm_line(db, [(tourney, 0.0)], hands, loader(db, config), cache=cache, equity_fn=fixed_equity(46, 54))
    assert changed.values != first.values and changed.priced == 1


def test_a_hand_that_cannot_be_rebuilt_keeps_its_result(stored) -> None:
    db, _config, _hand, tourney, players = stored
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])

    line = icm_line(db, [(tourney, -11.0)], allin_hands(db, [players["Hero"]]), lambda _hand_id: None)

    assert line.values == (-11.0,) and (line.priced, line.allins) == (0, 1)


def test_a_multi_table_field_keeps_its_result(stored) -> None:
    db, config, _hand, tourney, players = stored
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])
    db.get_cursor().execute("UPDATE Tourneys SET entries = 180 WHERE id = ?", (tourney,))
    db.commit()

    line = icm_line(
        db,
        [(tourney, -11.0)],
        allin_hands(db, [players["Hero"]]),
        loader(db, config),
        equity_fn=fixed_equity(46, 54),
    )

    assert line.values == (-11.0,) and line.priced == 0


def test_a_tournament_that_fails_keeps_its_result(stored) -> None:
    db, _config, _hand, tourney, players = stored
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])

    def broken(_hand_id):
        raise RuntimeError("the hand's rows are damaged")

    line = icm_line(db, [(tourney, -11.0), (OTHER_TOURNEY, 5.0)], allin_hands(db, [players["Hero"]]), broken)

    assert line.values == (-11.0, -6.0) and line.priced == 0
