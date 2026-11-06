from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy import Card
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Hand import hand_factory
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker
from tests.helpers import analytics_golden as golden

ROOT = Path(__file__).resolve().parents[1]
PACIFIC_TOUR = ROOT / "regression-test-files" / "tour" / "PacificPoker" / "Flop"
PACIFIC_PLO5 = (
    ROOT
    / "regression-test-files"
    / "cash"
    / "PacificPoker"
    / "Flop"
    / "PLO5-6max-USD-0.50-1-202611.five.hole.cards.txt"
)


def test_supported_pacific_games_do_not_require_stud_bring_in() -> None:
    supported_games = PacificPoker.__new__(PacificPoker).readSupportedGames()

    assert supported_games
    assert {base for _, base, _ in supported_games} == {"hold"}
    assert {game_type for game_type, _, _ in supported_games} == {"ring", "tour"}


def _read_hand_info(hand_history: str) -> SimpleNamespace:
    # handid mirrors Hand's default: the buy-in is read before the hand number.
    hand = SimpleNamespace(handText=hand_history, gametype={}, tablename="", handid=0)
    PacificPoker.readHandInfo(PacificPoker.__new__(PacificPoker), hand)
    return hand


def _fixture(filename: str) -> str:
    path = PACIFIC_TOUR / filename
    for encoding in PacificPoker.codepage:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    msg = f"no codepage of the parser decodes {path}"
    raise AssertionError(msg)


@pytest.mark.parametrize(
    ("filename", "currency", "buyin", "fee"),
    [
        # Symbol written before the amount, and after it (888 localised headers).
        ("NLHE-USD-HUSNG-0.25-201201.Sample.txt", "USD", 250, 25),
        ("NLHE-6max-MTT-40-4-201901.ro.MM.fix.txt", "USD", 4000, 400),
        ("NLHE-6max-SNG-0.10-201206.hands.txt", "EUR", 9, 1),
        # Header states a buy-in but no separate rake.
        ("NLHE-MTT-EUR-0.01-201206.freeroll.buyin.hands.txt", "EUR", 1, 0),
    ],
)
def test_real_money_buyins_keep_their_currency(
    filename: str,
    currency: str,
    buyin: int,
    fee: int,
) -> None:
    hand = _read_hand_info(_fixture(filename))

    assert hand.buyinCurrency == currency
    assert hand.buyin == buyin
    assert hand.fee == fee


@pytest.mark.parametrize(
    "filename",
    [
        "NLHE-10max-FREE-201901.txt",
        # 888 localises the freeroll marker; it carries no amount either.
        "NLHE-10max-Free-202004.space.delimiter.txt",
    ],
)
def test_freerolls_have_no_buyin(filename: str) -> None:
    hand = _read_hand_info(_fixture(filename))

    assert hand.buyinCurrency == "FREE"
    assert hand.buyin == 0
    assert hand.fee == 0


def test_play_money_buyin_is_not_reported_as_a_freeroll() -> None:
    hand = _read_hand_info(_fixture("NLHE-PM-MTT-10-20120221.txt"))

    assert hand.buyinCurrency == "play"
    assert hand.buyin == 1000
    assert hand.fee == 100
    assert hand.gametype["currency"] == "play"


def test_unknown_buyin_currency_is_an_explicit_parse_error() -> None:
    # Same header as the play money fixture, without the marker that proves the
    # symbol-less amount is play chips.
    hand_history = _fixture("NLHE-PM-MTT-10-20120221.txt").replace(
        "(Practice Play)",
        "(Real Money)",
    )

    with pytest.raises(FpdbParseError):
        _read_hand_info(hand_history)


_OMAHA_HAND = """#Game No : 799338265
***** 888.de Hand History for Game 799338265 *****
$0.50/$1 Blinds {limit} {game} - *** 03 11 2026 14:20:00
Table Mariupol 6 Max (Real Money)
Seat 9 is the button
Total number of players : 2
Seat 1: alice ( $100 )
Seat 9: bob ( $100 )
bob posts small blind [$0.50]
alice posts big blind [$1]
** Dealing down cards **
{dealt}bob calls [$0.50]
alice checks
** Dealing flop ** [ 2c, 7d, Kh ]
alice checks
bob checks
** Dealing turn ** [ 3s ]
alice checks
bob checks
** Dealing river ** [ 9c ]
alice checks
bob checks
** Summary **
alice shows [ {alice} ]
bob mucks [ {bob} ]
alice collected [ $2 ]
"""
_ALICE_5 = "Qh, Tc, Th, Ts, 6s"
_BOB_5 = "As, Ad, 4h, 5h, 8c"
_ALICE_4 = "Qh, Tc, Th, Ts"
_BOB_4 = "As, Ad, 4h, 5h"


def _omaha_hand(
    *,
    alice: str = _ALICE_5,
    bob: str = _BOB_5,
    dealt: str = f"Dealt to alice [ {_ALICE_5} ]\n",
    limit: str = "Pot Limit",
    game: str = "Omaha",
) -> str:
    return _OMAHA_HAND.format(alice=alice, bob=bob, dealt=dealt, limit=limit, game=game)


@pytest.mark.parametrize(
    ("hand_history", "category"),
    [
        pytest.param(_omaha_hand(), "5_omahahi", id="hero-dealt-five"),
        pytest.param(_omaha_hand(dealt=""), "5_omahahi", id="observed-showdown-of-five"),
        pytest.param(_omaha_hand(game="Omaha Hi/Lo"), "5_omaha8", id="hi-lo-dealt-five"),
        pytest.param(
            _omaha_hand(alice=_ALICE_4, bob=_BOB_4, dealt=f"Dealt to alice [ {_ALICE_4} ]\n"),
            "omahahi",
            id="hero-dealt-four",
        ),
        pytest.param(
            _omaha_hand(alice=_ALICE_4, bob=_BOB_4, dealt=f"Dealt to alice [ {_ALICE_4} ]\n", game="Omaha Hi/Lo"),
            "omahahilo",
            id="hi-lo-dealt-four",
        ),
        pytest.param(_omaha_hand(alice=_ALICE_4, bob=_BOB_4, dealt=""), "omahahi", id="observed-showdown-of-four"),
    ],
)
def test_omaha_category_follows_the_number_of_hole_cards(hand_history: str, category: str) -> None:
    parser = PacificPoker.__new__(PacificPoker)

    assert parser.determineGameType(hand_history)["category"] == category


def test_observed_omaha_without_a_showdown_stays_four_card() -> None:
    # Nothing in the hand gives the variant away, and the header is the same.
    hand_history = _omaha_hand(dealt="").split("alice shows")[0] + "alice collected [ $2 ]\n"
    parser = PacificPoker.__new__(PacificPoker)

    assert parser.determineGameType(hand_history)["category"] == "omahahi"


def test_five_hole_cards_only_change_omaha_categories() -> None:
    hand_history = _omaha_hand(limit="No Limit", game="Holdem")
    parser = PacificPoker.__new__(PacificPoker)

    assert parser.determineGameType(hand_history)["category"] == "holdem"


def test_five_cards_shown_at_showdown_are_hole_cards_not_a_winning_hand(tmp_path: Path) -> None:
    # In a 4-card game five shown cards are read as the winning combination and
    # dropped, so the villain would lose all of them, not only the fifth.
    hand_file = tmp_path / "plo5_showdown.txt"
    hand_file.write_text(_omaha_hand(), encoding="utf-8")
    parser = PacificPoker(config=golden.build_config(tmp_path), in_path=str(hand_file), autostart=True)

    hand = parser.getProcessedHands()[0]

    assert hand.join_holecards("alice", asList=True) == _ALICE_5.split(", ")
    assert hand.join_holecards("bob", asList=True) == _BOB_5.split(", ")


@pytest.fixture
def five_card_hand(tmp_path: Path):
    """Import the hand of #682 into a throwaway database, then reload it."""
    config = golden.build_config(tmp_path)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    importer.addImportFile(str(PACIFIC_PLO5), "PacificPoker")
    importer.runImport()
    yield db, config
    db.disconnect()


def test_imported_five_card_omaha_keeps_every_hole_card(five_card_hand) -> None:
    db, _ = five_card_hand
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT hp.card1, hp.card2, hp.card3, hp.card4, hp.card5, hp.card6 "
        "FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId WHERE p.name = 'PlayerA'",
    )

    assert [Card.valueSuitFromCard(card) for card in cursor.fetchone()] == ["Qh", "Tc", "Th", "Ts", "6s", ""]


def test_reloaded_five_card_omaha_shows_every_hole_card(five_card_hand) -> None:
    # The Hand Viewer and the replayer read hands back through hand_factory.
    db, config = five_card_hand
    cursor = db.get_cursor()
    cursor.execute("SELECT id FROM Hands")

    hand = hand_factory(cursor.fetchone()[0], config, db)

    assert hand.gametype["category"] == "5_omahahi"
    assert hand.join_holecards("PlayerA", asList=True) == ["Qh", "Tc", "Th", "Ts", "6s"]
