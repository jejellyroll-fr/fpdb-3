"""Card-reading contracts for the Winamax converter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.WinamaxToFpdb import Winamax

ROOT = Path(__file__).resolve().parents[1]
STUD = ROOT / "regression-test-files" / "cash" / "Winamax" / "Stud"
TOUR = ROOT / "regression-test-files" / "tour" / "Winamax" / "Flop"


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


def _compiled_parser(players: list[str]) -> Winamax:
    parser = Winamax.__new__(Winamax)
    parser.compiledPlayers = set()
    hand = SimpleNamespace(
        players=[(i + 1, name, "100") for i, name in enumerate(players)],
        gametype={"currency": "EUR"},
    )
    Winamax.compilePlayerRegexs(parser, hand)
    return parser


@pytest.mark.parametrize(
    ("filename", "currency", "buyin", "fee"),
    [
        # "buyIn: 0.93-0.07" -- the dash form, no symbol on the amounts.
        ("NLHE-10max-EUR-0.93-STT-201207.all.in.blind.txt", "EUR", 93, 7),
        # "buyIn: 0,90EUR + 0,10EUR" -- comma decimal and a symbol.
        ("NLHE-EUR-STT-FullHist.txt", "EUR", 90, 10),
        # "buyIn: 18EUR + 2EUR" -- whole euros must not lose their scale.
        ("NLHE-MTT-EUR-22.5-22.5-5-202208.bounty.ticket.txt", "EUR", 1800, 200),
    ],
)
def test_buyin_and_fee_are_recorded_in_cents(
    parser_config: Config,
    filename: str,
    currency: str,
    buyin: int,
    fee: int,
) -> None:
    hands = Winamax(config=parser_config, in_path=str(TOUR / filename), autostart=True).getProcessedHands()

    assert hands
    assert hands[0].buyinCurrency == currency
    assert hands[0].buyin == buyin
    assert hands[0].fee == fee


@pytest.mark.parametrize(
    "filename",
    [
        "NLHE-Ticket-MTT-201010.side.pot.txt",
        "NLHE-Free-MTT-201103.Full.History.txt",
    ],
)
def test_ticket_and_free_entries_have_no_buyin(parser_config: Config, filename: str) -> None:
    hands = Winamax(config=parser_config, in_path=str(TOUR / filename), autostart=True).getProcessedHands()

    assert hands
    assert hands[0].buyinCurrency == "FREE"
    assert hands[0].buyin == 0
    assert hands[0].fee == 0


def test_dealt_cards_regex_reads_every_player_not_only_the_hero() -> None:
    # 7-Card Stud states each player's board on every street with the same
    # "Dealt to" line, so this pattern is not hero-specific.
    parser = _compiled_parser(["Hero", "Player0", "Player1"])
    fifth_street = "Dealt to Player1 [X X Kc 6d] [7d]\nDealt to Player0 [X X 8h 5c] [Js]\n"

    matches = [(m.group("PNAME"), m.group("OLDCARDS"), m.group("NEWCARDS")) for m in parser.re_dealt_cards.finditer(fifth_street)]

    assert matches == [
        ("Player1", "X X Kc 6d", "7d"),
        ("Player0", "X X 8h 5c", "Js"),
    ]


def test_stud_hand_assigns_cards_to_each_player(tmp_path: Path) -> None:
    # Guards the rename end to end: the non-hero boards on 4th to 7th street are
    # read through the same pattern the hero's third street uses.
    source = next(STUD.glob("7-Stud-6max-EUR-25-50-201611._8games_.negative*"))
    parser = _compiled_parser(["Hero", "Player0", "Player1"])
    text = source.read_text(encoding="utf-8", errors="replace")

    dealt = {m.group("PNAME") for m in parser.re_dealt_cards.finditer(text)}

    assert dealt == {"Hero", "Player0", "Player1"}
