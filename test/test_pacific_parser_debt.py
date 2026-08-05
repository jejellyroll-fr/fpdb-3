from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.HandHistoryConverter import FpdbParseError
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker

ROOT = Path(__file__).resolve().parents[1]
PACIFIC_TOUR = ROOT / "regression-test-files" / "tour" / "PacificPoker" / "Flop"


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
