"""A knockout tournament hand's all-in, priced with the bounty it can win (#447).

The sit-and-go bubble hand, made a PokerStars progressive knockout: Hero
($5 bounty, 4000 chips) shoves AsKs, Villain ($7.50 bounty, 3000 chips) calls
with queens. Hero covers Villain, so winning busts Villain and collects their
bounty; Villain cannot bust Hero, so collects nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fpdb_3_legacy import Hand
from fpdb_3_legacy.hand_bounty import BountyRules, bounty_for_replay, hand_allin_bounty
from tests.helpers.icm_hands import PKO, SNG_ALLIN, fixed_equity, parse

# A regular knockout: PokerStars prints no seat bounty, every head is worth the same $0.50.
KNOCKOUT = SNG_ALLIN.replace(
    "200000000001: Tournament #3000000001, $10+$1 USD", "200000000201: Tournament #3000000201, $4.40+$0.50+$0.60 USD"
).replace("Table '3000000001 1'", "Table '3000000201 1'")
EQUITY = fixed_equity(46, 54)


def test_a_progressive_bounty_is_half_cash_half_added_to_the_winner_s_own(tmp_path) -> None:
    hand, _ = parse(tmp_path, PKO)

    allin = hand_allin_bounty(hand, BountyRules(), equity_fn=EQUITY).allin

    assert allin.players == ("Hero", "Villain")
    assert allin.collects == {"Hero": Decimal("7.50"), "Villain": Decimal(0)}  # Villain cannot bust Hero
    assert allin.cash["Hero"] == Decimal("3.75")
    assert allin.bounty_ev["Hero"] == pytest.approx(Decimal("0.46") * Decimal("3.75"))
    assert allin.head_ev["Hero"] == pytest.approx(Decimal("0.46") * Decimal("3.75"))
    assert allin.bounty_ev["Villain"] == 0


# Codex (#633): Villain starts with 3000, posts a 200 ante, then puts the other 2800 in
# against Hero's 2800. Hero's stack is the smaller one, yet winning busts Villain.
ANTE = """PokerStars Hand #200000000301: Tournament #3000000301, $4.40+$5.00+$0.60 USD Hold'em No Limit - Level V (100/200) - 2026/10/26 12:00:00 ET
Table '3000000301 1' 9-max Seat #1 is the button
Seat 1: Hero (2800 in chips, $5 bounty)
Seat 3: Villain (3000 in chips, $7.50 bounty)
Seat 5: Short (1000 in chips, $5 bounty)
Villain: posts the ante 200
Villain: posts small blind 100
Short: posts big blind 200
*** HOLE CARDS ***
Dealt to Hero [As Ks]
Hero: raises 2600 to 2800 and is all-in
Villain: calls 2700 and is all-in
Short: folds
*** FLOP *** [2c 7d 9h]
*** TURN *** [2c 7d 9h] [Jc]
*** RIVER *** [2c 7d 9h Jc] [3s]
*** SHOW DOWN ***
Hero: shows [As Ks] (high card Ace)
Villain: shows [Qh Qd] (a pair of Queens)
Villain collected 6000 from pot
*** SUMMARY ***
Total pot 6000 | Rake 0
Board [2c 7d 9h Jc 3s]
Seat 1: Hero (button) showed [As Ks] and lost with high card Ace
Seat 3: Villain (small blind) showed [Qh Qd] and won (6000) with a pair of Queens
Seat 5: Short (big blind) folded before Flop



"""


def test_a_shorter_stack_still_busts_an_opponent_whose_ante_left_them_all_in(tmp_path) -> None:
    hand, _ = parse(tmp_path, ANTE)

    allin = hand_allin_bounty(hand, BountyRules(), equity_fn=EQUITY).allin

    assert allin is not None
    assert allin.collects["Hero"] == Decimal("7.50")  # Villain's whole stack is in the pot
    assert allin.collects["Villain"] == Decimal("5")  # and so is Hero's


def test_a_regular_knockout_pays_its_fixed_bounty_in_cash(tmp_path) -> None:
    hand, _ = parse(tmp_path, KNOCKOUT)

    allin = hand_allin_bounty(hand, BountyRules(bounty=Decimal("0.50")), equity_fn=EQUITY).allin

    assert allin.cash["Hero"] == Decimal("0.50") and allin.head_ev["Hero"] == 0
    assert allin.bounty_ev["Hero"] == pytest.approx(Decimal("0.46") * Decimal("0.50"))


def test_the_bounty_is_added_to_the_chip_ev_when_a_chip_s_worth_is_known(tmp_path) -> None:
    hand, _ = parse(tmp_path, PKO)
    chip_value = Decimal("4.40") / 10000  # the prize part of the buy-in over a 10,000-chip starting stack

    allin = hand_allin_bounty(hand, BountyRules(chip_value=chip_value), equity_fn=EQUITY).allin

    assert allin.adjusted_chip_ev["Hero"] == pytest.approx(allin.chip_ev["Hero"] + allin.bounty_ev["Hero"] / chip_value)
    assert allin.adjusted_chip_ev["Villain"] == allin.chip_ev["Villain"]


def test_without_a_chip_value_there_is_no_adjusted_chip_ev(tmp_path) -> None:
    hand, _ = parse(tmp_path, PKO)

    assert hand_allin_bounty(hand, BountyRules(), equity_fn=EQUITY).allin.adjusted_chip_ev is None


def test_a_regular_knockout_without_its_bounty_says_so(tmp_path) -> None:
    hand, _ = parse(tmp_path, KNOCKOUT)

    priced = hand_allin_bounty(hand, BountyRules(), equity_fn=EQUITY)

    assert priced.allin is None and "bounty in play" in priced.reason


def test_what_the_all_in_cannot_price_is_said(tmp_path) -> None:
    hand, _ = parse(tmp_path, PKO.replace("Short: folds", "Short: calls 800 and is all-in"))

    assert "multiway" in hand_allin_bounty(hand, BountyRules(), equity_fn=EQUITY).reason


# --- what the replayer gets --------------------------------------------------------------


def test_a_parsed_hand_reads_its_own_knockout_rules(tmp_path) -> None:
    hand, _ = parse(tmp_path, KNOCKOUT)

    priced = bounty_for_replay(None, hand, None)

    assert priced.allin is not None and priced.allin.cash["Hero"] == Decimal("0.50")


def test_a_freezeout_is_not_a_knockout(tmp_path) -> None:
    hand, _ = parse(tmp_path)

    assert bounty_for_replay(None, hand, None).reason == "not a knockout tournament"


@pytest.fixture
def stored(tmp_path, fresh_db, legacy_config):
    from fpdb_3_legacy.Importer import Importer

    _hand, path = parse(tmp_path, PKO)
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=legacy_config, sql=None)
    importer.database = fresh_db
    importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    cursor = fresh_db.get_cursor()
    cursor.execute("SELECT id FROM Hands")
    (hand_id,) = cursor.fetchone()
    yield fresh_db, legacy_config, hand_id
    del importer  # kept alive until the test is done: dropping it closes the database


def test_a_stored_hand_is_priced_from_its_seat_bounties_and_tournament(stored, monkeypatch) -> None:
    db, config, hand_id = stored
    hand = Hand.hand_factory(hand_id, config, db)  # rebuilt from the database, as the replayer does
    monkeypatch.setattr("fpdb_3_legacy.hand_bounty.heads_up_allin", _fixed(EQUITY))

    allin = bounty_for_replay(db, hand, hand_id).allin

    assert allin.collects["Hero"] == Decimal("7.50") and allin.cash["Hero"] == Decimal("3.75")
    assert allin.adjusted_chip_ev is None  # the starting stack is not in the hand history


def test_a_stored_starting_stack_gives_the_adjusted_chip_ev(stored, monkeypatch) -> None:
    db, config, hand_id = stored
    db.get_cursor().execute("UPDATE TourneyTypes SET buyInChips = 10000")
    db.commit()
    hand = Hand.hand_factory(hand_id, config, db)
    monkeypatch.setattr("fpdb_3_legacy.hand_bounty.heads_up_allin", _fixed(EQUITY))

    allin = bounty_for_replay(db, hand, hand_id).allin

    chip_value = Decimal("4.40") / 10000
    assert allin.adjusted_chip_ev["Hero"] == pytest.approx(allin.chip_ev["Hero"] + allin.bounty_ev["Hero"] / chip_value)


def _fixed(equity_fn):
    from fpdb_3_legacy import hand_icm

    return lambda hand, _equity_fn=None: hand_icm.heads_up_allin(hand, equity_fn)
