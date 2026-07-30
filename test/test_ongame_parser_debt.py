import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.OnGameToFpdb import OnGame

ROOT = Path(__file__).resolve().parents[1]
ONGAME = ROOT / "regression-test-files" / "cash" / "OnGame" / "Flop"


@pytest.mark.parametrize(
    ("filename", "currency"),
    [
        ("NLHE-6max-play-0.25-0.50-201204.txt", "play"),
        ("PLO8-USD-0.50-0.50-201111.txt", "USD"),
        ("PLO-6max-EUR-1-1-2011002.Sample.txt", "EUR"),
    ],
)
def test_determine_game_type_distinguishes_real_and_play_money(
    filename: str,
    currency: str,
) -> None:
    hand_history = (ONGAME / filename).read_text(encoding="utf-8")

    game_type = OnGame.determineGameType(OnGame.__new__(OnGame), hand_history)

    assert game_type["currency"] == currency


def test_dealt_cards_regex_identifies_each_player_and_draw_replacement() -> None:
    parser = OnGame.__new__(OnGame)
    parser.compiledPlayers = set()
    hand = SimpleNamespace(players=[(1, "Hero"), (2, "Villain")])
    parser.compilePlayerRegexs(hand)
    street = """
    Dealing to Hero: [Ah, Ad, 7c]
    Dealing to Villain: [-, -, Ks]
    New hand for Hero: [Ah, Ad, Qc]
    """

    matches = [match.groupdict() for match in parser.re_DealtCards.finditer(street)]

    assert [(match["PNAME"], match["CARDS"]) for match in matches] == [
        ("Hero", "Ah, Ad, 7c"),
        ("Villain", "-, -, Ks"),
        ("Hero", "Ah, Ad, Qc"),
    ]


@pytest.mark.parametrize(
    ("filename", "expected_utc"),
    [
        (
            "LHE-9max-USD-0.50-1.00-201008.All-in.with.showdown.txt",
            datetime.datetime(2010, 8, 18, 18, 32, 32, tzinfo=datetime.UTC),
        ),
        (
            "NLHE-6max-play-0.25-0.50-201204.txt",
            datetime.datetime(2012, 4, 13, 13, 12, 34, tzinfo=datetime.UTC),
        ),
        (
            "NLHE-5max-USD-0.05-0.10-201302.Strobe.txt",
            datetime.datetime(2013, 2, 28, 6, 30, 49, tzinfo=datetime.UTC),
        ),
        (
            "PLO8-USD-0.50-0.50-201111.txt",
            datetime.datetime(2011, 9, 11, 14, 58, 25, tzinfo=datetime.UTC),
        ),
    ],
)
def test_hand_start_time_honors_ongame_timezone(
    filename: str,
    expected_utc: datetime.datetime,
) -> None:
    parser = OnGame(Config(), str(ONGAME / filename), autostart=True)

    assert parser.getProcessedHands()[0].startTime == expected_utc
