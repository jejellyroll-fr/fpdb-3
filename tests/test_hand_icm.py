"""A tournament hand's all-in priced in prize equity, next to its chip EV (#446).

The hand is a sit-and-go bubble written in PokerStars format: three left of a
9-max, Hero shoves AsKs for 4000, Villain calls with QhQd for 3000, Short folds
the big blind. The equity comes from the engine when it is installed, and from
a fixed result otherwise, so the arithmetic is checked either way.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import equity, icm, tourney_payouts
from fpdb_3_legacy.hand_icm import hand_allin_icm, icm_for_replay

SNG_ALLIN = """PokerStars Hand #200000000001: Tournament #3000000001, $10+$1 USD Hold'em No Limit - Level V (100/200) - 2026/10/26 12:00:00 ET
Table '3000000001 1' 9-max Seat #1 is the button
Seat 1: Hero (4000 in chips)
Seat 3: Villain (3000 in chips)
Seat 5: Short (1000 in chips)
Villain: posts small blind 100
Short: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [As Ks]
Hero: raises 3800 to 4000 and is all-in
Villain: calls 2900 and is all-in
Short: folds
Uncalled bet (1000) returned to Hero
*** FLOP *** [2c 7d 9h]
*** TURN *** [2c 7d 9h] [Jc]
*** RIVER *** [2c 7d 9h Jc] [3s]
*** SHOW DOWN ***
Hero: shows [As Ks] (high card Ace)
Villain: shows [Qh Qd] (a pair of Queens)
Villain collected 6200 from pot
*** SUMMARY ***
Total pot 6200 | Rake 0
Board [2c 7d 9h Jc 3s]
Seat 1: Hero (button) showed [As Ks] and lost with high card Ace
Seat 3: Villain (small blind) showed [Qh Qd] and won (6200) with a pair of Queens
Seat 5: Short (big blind) folded before Flop



"""
PAYOUTS = [50.0, 30.0, 20.0]


def parse(tmp_path, text: str = SNG_ALLIN):
    from fpdb_3_legacy.Configuration import Config
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    path = tmp_path / "hand.txt"
    path.write_text(text, encoding="utf-8")
    parser = PokerStars(config=Config(file="HUD_config.xml"), in_path=str(path), autostart=True)
    (hand,) = parser.getProcessedHands()
    return hand, path


def fixed_equity(wins_a: int, wins_b: int, ties: int = 0):
    """An equity engine answer: A wins, B wins and ties out of their total."""

    def engine(_game, _pockets, _board, **_kwargs):
        samples = wins_a + wins_b + ties
        return SimpleNamespace(
            samples=samples,
            players=(
                SimpleNamespace(wins=wins_a, ties=ties, losses=wins_b),
                SimpleNamespace(wins=wins_b, ties=ties, losses=wins_a),
            ),
        )

    return engine


# --- the arithmetic, with a fixed equity -------------------------------------------------


def test_chip_ev_is_the_pot_share_less_what_was_put_in(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    priced = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(46, 54))

    allin = priced.allin
    assert allin is not None and allin.players == ("Hero", "Villain") and allin.street == "PREFLOP"
    assert allin.equity == pytest.approx({"Hero": 0.46, "Villain": 0.54})
    assert allin.chip_ev["Hero"] == pytest.approx(Decimal("0.46") * 6200 - 3000)
    assert allin.chip_ev["Villain"] == pytest.approx(Decimal("0.54") * 6200 - 3000)


def test_icm_ev_is_expected_prize_equity_after_less_before(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    allin = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(46, 54)).allin

    before = {"Hero": 4000.0, "Villain": 3000.0, "Short": 1000.0}
    hero_wins = icm.AllInOutcome(0.46, {"Hero": 7200.0, "Villain": 0.0, "Short": 800.0})
    villain_wins = icm.AllInOutcome(0.54, {"Hero": 1000.0, "Villain": 6200.0, "Short": 800.0})
    expected = icm.allin_icm_ev(before, [hero_wins, villain_wins], PAYOUTS, "Hero")
    assert allin.icm_ev["Hero"] == pytest.approx(expected)


def test_a_bubble_all_in_costs_both_players_prize_equity(tmp_path) -> None:
    # Near a coinflip with the short stack watching: the money goes to the short stack.
    hand, _ = parse(tmp_path)

    allin = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(46, 54)).allin

    assert allin.icm_ev["Hero"] < 0 and allin.icm_ev["Villain"] < 0


def test_the_result_is_what_the_hand_actually_moved(tmp_path) -> None:
    # Villain won: Hero is left 1000, Villain 6200, Short 800 after the big blind.
    hand, _ = parse(tmp_path)

    allin = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(46, 54)).allin

    now = icm.icm_equities([4000, 3000, 1000], PAYOUTS)
    after = icm.icm_equities([1000, 6200, 800], PAYOUTS)
    assert allin.icm_result["Hero"] == pytest.approx(after[0] - now[0])
    assert allin.icm_result["Villain"] == pytest.approx(after[1] - now[1])


def test_a_split_pot_is_priced_as_its_own_outcome(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    allin = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(0, 0, ties=10)).allin

    assert allin.equity == pytest.approx({"Hero": 0.5, "Villain": 0.5})
    # A certain split gives each half of the 6200 pot, Short's big blind included: 4100 / 3100 / 800.
    expected = icm.icm_equities([4100, 3100, 800], PAYOUTS)[0] - icm.icm_equities([4000, 3000, 1000], PAYOUTS)[0]
    assert allin.icm_ev["Hero"] == pytest.approx(expected)


def test_the_table_only_flag_is_carried_and_noted(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    priced = hand_allin_icm(hand, PAYOUTS, table_only=True, equity_fn=fixed_equity(46, 54))

    assert priced.allin.table_only
    assert priced.notes == ("priced as if this table were the whole field",)


@pytest.mark.skipif(equity.load_poker_eval() is None, reason="the equity engine is not installed")
def test_the_equity_engine_gives_aks_against_queens_its_known_share(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    allin = hand_allin_icm(hand, PAYOUTS).allin

    assert allin.equity["Hero"] == pytest.approx(0.46, abs=0.01)


# --- what is not priced, and why -------------------------------------------------------


def test_a_multiway_all_in_is_not_priced(tmp_path) -> None:
    hand, _ = parse(tmp_path, SNG_ALLIN.replace("Short: folds", "Short: calls 800 and is all-in"))

    priced = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(1, 1))

    assert priced.allin is None and "multiway" in priced.reason


def test_an_unshown_hand_is_not_priced(tmp_path) -> None:
    hand, _ = parse(tmp_path, SNG_ALLIN.replace("Villain: shows [Qh Qd] (a pair of Queens)\n", ""))
    hand.holecards["PREFLOP"].pop("Villain", None)

    priced = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(1, 1))

    assert priced.allin is None and "shown" in priced.reason


def test_a_hand_without_an_all_in_has_nothing_to_price(tmp_path) -> None:
    text = (
        SNG_ALLIN.replace("Hero: raises 3800 to 4000 and is all-in", "Hero: raises 200 to 400")
        .replace("Villain: calls 2900 and is all-in", "Villain: folds")
        .replace("Uncalled bet (1000) returned to Hero", "Uncalled bet (200) returned to Hero")
    )
    text = text.split("*** FLOP ***")[0] + (
        "Hero collected 500 from pot\n*** SUMMARY ***\nTotal pot 500 | Rake 0\n"
        "Seat 1: Hero (button) collected (500)\nSeat 3: Villain (small blind) folded before Flop\n"
        "Seat 5: Short (big blind) folded before Flop\n\n\n\n"
    )
    hand, _ = parse(tmp_path, text)

    priced = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(1, 1))

    assert priced.allin is None and priced.reason == "no all-in in this hand"


def test_payouts_the_model_cannot_take_are_refused(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    priced = hand_allin_icm(hand, [50.0, -1.0], equity_fn=fixed_equity(1, 1))

    assert priced.allin is None and "ICM not computed" in priced.reason


# --- what the replayer gets for a stored hand --------------------------------------------


@pytest.fixture
def stored_hand(tmp_path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    hand, path = parse(tmp_path)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id, tourneyId FROM Hands")
    hand_id, tourney_id = cursor.fetchone()
    yield fresh_db, hand, hand_id, tourney_id, importer


def test_a_stored_hand_without_a_payout_structure_says_so(stored_hand) -> None:
    db, hand, hand_id, _tourney, _importer = stored_hand

    priced = icm_for_replay(db, hand, hand_id)

    assert priced.allin is None and "no payout structure known" in priced.reason


def test_a_stored_hand_is_priced_with_its_tournament_s_structure(stored_hand) -> None:
    db, hand, hand_id, tourney, _importer = stored_hand
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])

    priced = icm_for_replay(db, hand, hand_id)

    assert priced.allin is not None
    assert priced.allin.table_only  # no summary: the field size is unknown


def test_a_single_table_field_is_priced_without_the_flag(stored_hand) -> None:
    db, hand, hand_id, tourney, _importer = stored_hand
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])
    db.get_cursor().execute("UPDATE Tourneys SET entries = 9 WHERE id = ?", (tourney,))
    db.commit()

    assert not icm_for_replay(db, hand, hand_id).allin.table_only


def test_a_multi_table_field_is_refused(stored_hand) -> None:
    db, hand, hand_id, tourney, _importer = stored_hand
    tourney_payouts.store_payouts(db, tourney, [5000, 3000, 2000])
    db.get_cursor().execute("UPDATE Tourneys SET entries = 180 WHERE id = ?", (tourney,))
    db.commit()

    priced = icm_for_replay(db, hand, hand_id)

    assert priced.allin is None and "multi-table" in priced.reason


def test_a_hand_that_is_not_stored_cannot_find_its_payouts(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    assert "not stored" in icm_for_replay(None, hand, None).reason


# Codex (#628): Short all-in for 1000 preflop, Villain folds the flop after putting in 2000.
# Two contenders remain, but 2000 of the pot is a side pot Short cannot win.
SIDE_POT = """PokerStars Hand #200000000002: Tournament #3000000001, $10+$1 USD Hold'em No Limit - Level V (100/200) - 2026/10/26 12:05:00 ET
Table '3000000001 1' 9-max Seat #1 is the button
Seat 1: Hero (4000 in chips)
Seat 3: Villain (3000 in chips)
Seat 5: Short (1000 in chips)
Villain: posts small blind 100
Short: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [As Ks]
Hero: raises 1800 to 2000
Villain: calls 1900
Short: calls 800 and is all-in
*** FLOP *** [2c 7d 9h]
Villain: checks
Hero: bets 1000
Villain: folds
Uncalled bet (1000) returned to Hero
*** TURN *** [2c 7d 9h] [Jc]
*** RIVER *** [2c 7d 9h Jc] [3s]
*** SHOW DOWN ***
Hero: shows [As Ks] (high card Ace)
Short: shows [Qh Qd] (a pair of Queens)
Hero collected 2000 from side pot
Short collected 3000 from main pot
*** SUMMARY ***
Total pot 5000 Main pot 3000. Side pot 2000. | Rake 0
Board [2c 7d 9h Jc 3s]
Seat 1: Hero (button) showed [As Ks] and won (2000) with high card Ace
Seat 3: Villain (small blind) folded on the Flop
Seat 5: Short (big blind) showed [Qh Qd] and won (3000) with a pair of Queens



"""


def test_a_side_pot_one_contender_cannot_win_is_not_priced(tmp_path) -> None:
    hand, _ = parse(tmp_path, SIDE_POT)

    priced = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(46, 54))

    assert priced.allin is None and "side pot" in priced.reason


@pytest.mark.parametrize(
    ("category", "why"),
    [("omahahilo", "hi/lo"), ("studhi", "flop games"), ("5_studhi", "flop games"), ("27_3draw", "flop games")],
)
def test_games_the_pricing_cannot_take_are_refused(tmp_path, category, why) -> None:
    # Codex (#628): hi/lo wins overlap, and stud pockets are not a flop game's.
    hand, _ = parse(tmp_path)
    hand.gametype["category"] = category

    priced = hand_allin_icm(hand, PAYOUTS, equity_fn=fixed_equity(46, 54))

    assert priced.allin is None and why in priced.reason
