"""Card-reading contracts for the Winamax converter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fpdb_3_legacy.WinamaxToFpdb import Winamax

ROOT = Path(__file__).resolve().parents[1]
STUD = ROOT / "regression-test-files" / "cash" / "Winamax" / "Stud"


def _compiled_parser(players: list[str]) -> Winamax:
    parser = Winamax.__new__(Winamax)
    parser.compiledPlayers = set()
    hand = SimpleNamespace(
        players=[(i + 1, name, "100") for i, name in enumerate(players)],
        gametype={"currency": "EUR"},
    )
    Winamax.compilePlayerRegexs(parser, hand)
    return parser


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
