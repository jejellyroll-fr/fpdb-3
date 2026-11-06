"""Every hand of an iPoker session must get the gametype of the first (#715).

The first hand of a file still carries the session header and is read by
``re_game_info``; every later one is a bare ``<game>`` block, read by
``_parse_xml_format``. The XML path only knew the currency written before the
amount (``€0.01/€0.02``): on PMU, which writes it after (``0,01€/0,02€``), a
PLO table imported its first hand as ``omahahi/pl`` and the rest as
``omahahi/nl`` with 0.01/0.02 blinds, and the solver review refused them. The
same path also read Omaha Hi-Lo as plain Omaha and Six Plus Hold'em as
Hold'em, whichever side the currency stood on.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.iPoker.gametype_text import read_gametype

HEADER = """<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="5898779713">
 <general>
  <client_version>26.1.1.23</client_version>
  <mode>real</mode>
  <gametype>{gametype}</gametype>
  <tablename>Sample Table, 560234179</tablename>
  <tablecurrency>EUR</tablecurrency>
  <duration>00:05:34</duration>
  <gamecount>2</gamecount>
  <startdate>2026-11-06 12:01:36</startdate>
  <currency>EUR</currency>
  <nickname>Hero</nickname>
  <tablesize>6</tablesize>
 </general>
"""

GAME = """ <game gamecode="{code}">
  <general>
   <startdate>2026-11-06 12:01:36</startdate>
   <players>
    <player bet="0,01€" chips="2€" dealer="0" name="alice" seat="1" win="0€"/>
    <player bet="0,02€" chips="2€" dealer="0" name="Hero" seat="3" win="0,03€"/>
    <player bet="0€" chips="2€" dealer="1" name="bob" seat="6" win="0€"/>
   </players>
  </general>
 </game>"""

#: (gametype text, category, limitType, sb, bb)
CASES = [
    ("Omaha PL 0,01€/0,02€", "omahahi", "pl", "0.01", "0.02"),
    ("Omaha PL 0,05€/0,10€", "omahahi", "pl", "0.05", "0.10"),
    ("Omaha PL €0.50/€1", "omahahi", "pl", "0.50", "1"),
    ("Omaha Hi-Lo PL 0,05€/0,10€", "omahahilo", "pl", "0.05", "0.10"),
    ("Omaha Hi-Lo PL €0.05/€0.10", "omahahilo", "pl", "0.05", "0.10"),
    ("Holdem NL 0,02€/0,05€", "holdem", "nl", "0.02", "0.05"),
    ("Holdem NL €0.05/€0.10", "holdem", "nl", "0.05", "0.10"),
    ("Holdem L 0,10€/0,20€", "holdem", "fl", "0.05", "0.10"),
    ("Six Plus Holdem NL €0.25/€0.50", "6_holdem", "nl", "0.25", "0.50"),
    ("PL 0,50€/1€", "5_omahahi", "pl", "0.50", "1"),
    ("PL €2/€4", "5_omahahi", "pl", "2", "4"),
]


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _gametype(config: Config, gametype: str, *, first: bool) -> dict:
    header = HEADER.format(gametype=gametype)
    games = [GAME.format(code="9155492626"), GAME.format(code="9155492696")]
    parser = iPoker(config, autostart=False)
    parser.whole_file = header + "\n".join(games) + "\n</session>"
    parser.in_path = "5898779713"  # PMU names its files by session code: no game in the name
    hand_text = header + games[0] if first else games[1]
    info = parser.determineGameType(hand_text)
    assert info is not None
    return info


@pytest.mark.parametrize(("gametype", "category", "limit_type", "sb", "bb"), CASES)
def test_the_hands_after_the_first_keep_its_gametype(
    config: Config,
    gametype: str,
    category: str,
    limit_type: str,
    sb: str,
    bb: str,
) -> None:
    expected = (category, limit_type, sb, bb)
    for first in (True, False):
        info = _gametype(config, gametype, first=first)
        assert (info["category"], info["limitType"], info["sb"], info["bb"]) == expected, (
            f"{'first' if first else 'next'} hand of {gametype!r}"
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Omaha PL 0,01€/0,02€", ("hold", "omahahi", "pl", "0,01", "0,02")),
        ("Omaha PL $0.01/$0.02", ("hold", "omahahi", "pl", "0.01", "0.02")),
        ("Holdem NL", ("hold", "holdem", "nl", None, None)),
        ("7 Card Stud Hi-Lo L 0,10€/0,20€", ("stud", "studhilo", "fl", "0,10", "0,20")),
        ("PL €1/€2", ("hold", "5_omahahi", "pl", "1", "2")),
    ],
)
def test_read_gametype(text: str, expected: tuple) -> None:
    gametype = read_gametype(text)
    assert gametype is not None
    assert (gametype["base"], gametype["category"], gametype["limitType"], gametype["SB"], gametype["BB"]) == expected


@pytest.mark.parametrize("text", ["NL €3/€6", "Badugi PL €1/€2", ""])
def test_read_gametype_refuses_what_it_does_not_know(text: str) -> None:
    # A nameless game is 5 card Omaha only when pot limit (#685).
    assert read_gametype(text) is None
