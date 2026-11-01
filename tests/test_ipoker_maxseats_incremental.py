"""maxseats must come from the session <tablesize>, on every parse path.

Regression for the PMU/iPoker cash-game HUD misplacement: <tablesize> only
exists in the session header, so only the first hand of a file (whose split
text still contains the header) parsed it. Every later hand — i.e. every hand
delivered by live auto-import — went through _parse_xml_format, left "seats"
unset, and readHandInfo fell back to guessMaxSeats(). iPoker numbers 6-max
seats up to 10, so the guess returned 10: the Gametypes row flipped 6→10 and
the HUD laid out a 6-max table with the 10-max layout.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.base import iPoker

RING_GAME_1 = """ <game gamecode="9025178751">
  <general>
   <startdate>2026-07-21 14:45:39</startdate>
   <players>
    <player bet="0,04€" chips="2,63€" dealer="0" name="Player 1" seat="1" win="0€"/>
    <player bet="0€" chips="2,47€" dealer="1" name="Player 3" seat="3" win="0€"/>
    <player bet="0,06€" chips="3,42€" dealer="0" name="Hero" seat="6" win="0€"/>
    <player bet="0,06€" chips="1,67€" dealer="0" name="Player 10" rakeamount="0,01€" seat="10" win="0,15€"/>
   </players>
  </general>
  <round no="0">
   <action no="1" player="Hero" sum="0,01€" type="1"/>
   <action no="2" player="Player 10" sum="0,02€" type="2"/>
  </round>
 </game>"""

RING_GAME_2 = RING_GAME_1.replace('gamecode="9025178751"', 'gamecode="9025178752"').replace(
    "14:45:39",
    "14:46:41",
)

RING_HEADER = """<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="5869851690">
 <general>
  <client_version>26.1.1.23</client_version>
  <mode>real</mode>
  <gametype>Omaha PL 0,01€/0,02€</gametype>
  <tablename>Sea Lake, 560237915</tablename>
  <tablecurrency>EUR</tablecurrency>
  <smallblind>0,01€</smallblind>
  <bigblind>0,02€</bigblind>
  <duration>00:05:34</duration>
  <gamecount>5</gamecount>
  <startdate>2026-07-21 14:45:39</startdate>
  <currency>EUR</currency>
  <nickname>Hero</nickname>
  <tablesize>6</tablesize>
 </general>
"""

RING_FILE = RING_HEADER + RING_GAME_1 + "\n" + RING_GAME_2 + "\n</session>"

TOUR_FILE = """<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="1193390835">
 <general>
  <client_version>26.1.1.23</client_version>
  <mode>real</mode>
  <gametype>Holdem NL</gametype>
  <tablename>1193390834 Twister 0,25€, 1193390835</tablename>
  <duration>00:03:01</duration>
  <gamecount>8</gamecount>
  <startdate>2026-07-21 14:47:00</startdate>
  <currency>EUR</currency>
  <nickname>Hero</nickname>
  <tournamentcode>1193390834</tournamentcode>
  <tournamentname>Twister 0,25€</tournamentname>
  <place>2</place>
  <buyin>0€ + 0,02€ + 0,23€</buyin>
  <totalbuyin>0,25€</totalbuyin>
  <win>0€</win>
  <tablesize>3</tablesize>
 </general>
 <game gamecode="9025200001">
  <general>
   <startdate>2026-07-21 14:47:01</startdate>
   <players>
    <player bet="20" chips="500" dealer="1" name="Player 1" seat="1" win="0"/>
    <player bet="10" chips="500" dealer="0" name="Player 2" seat="2" win="30"/>
    <player bet="0" chips="500" dealer="0" name="Hero" seat="3" win="0"/>
   </players>
  </general>
 </game>
 <game gamecode="9025200002">
  <general>
   <startdate>2026-07-21 14:47:55</startdate>
   <players>
    <player bet="20" chips="480" dealer="0" name="Player 1" seat="1" win="0"/>
    <player bet="10" chips="530" dealer="1" name="Player 2" seat="2" win="30"/>
    <player bet="0" chips="490" dealer="0" name="Hero" seat="3" win="0"/>
   </players>
  </general>
 </game>
</session>"""


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _parser(config: Config, whole_file: str) -> iPoker:
    parser = iPoker(config, autostart=False)
    parser.whole_file = whole_file
    return parser


def test_first_hand_with_header_reads_tablesize(config: Config) -> None:
    """First split hand still contains the session header (standard regex path)."""
    parser = _parser(config, RING_FILE)
    gametype = parser.determineGameType(RING_HEADER + RING_GAME_1)

    assert gametype is not None
    assert parser.info["seats"] == "6"


def test_incremental_hand_without_header_reads_tablesize(config: Config) -> None:
    """A bare <game> block (live auto-import) goes through _parse_xml_format."""
    parser = _parser(config, RING_FILE)
    gametype = parser.determineGameType(RING_GAME_2)

    assert gametype is not None
    assert parser.info["seats"] == "6", "XML-format path must read <tablesize> from the session header"


def test_incremental_hand_sets_maxseats_without_guessing(config: Config) -> None:
    """readHandInfo must derive maxseats=6 for a bare <game> block, not guess 10."""
    parser = _parser(config, RING_FILE)
    assert parser.determineGameType(RING_GAME_2) is not None

    hand = SimpleNamespace(gametype={}, maxseats=None)
    match = parser.re_hand_info.search(RING_GAME_2)
    assert match is not None
    parser._set_basic_hand_info(hand, match)

    assert hand.maxseats == 6
    assert hand.gametype["maxSeats"] == 6


def test_twister_incremental_hand_reads_tablesize(config: Config) -> None:
    """Tournament (Twister) bare <game> blocks must get 3-max, not 10."""
    tour_game_2 = TOUR_FILE.split("</game>")[1] + "</game>"
    assert "<tablesize>" not in tour_game_2

    parser = _parser(config, TOUR_FILE)
    gametype = parser.determineGameType(tour_game_2)

    assert gametype is not None
    assert gametype["type"] == "tour"
    assert parser.info["seats"] == "3"


def test_missing_tablesize_keeps_previous_behaviour(config: Config) -> None:
    """Files without <tablesize> must not invent a seats value."""
    stripped = RING_FILE.replace("  <tablesize>6</tablesize>\n", "")
    parser = _parser(config, stripped)
    gametype = parser.determineGameType(RING_GAME_2.replace("</session>", ""))

    assert gametype is not None
    assert "seats" not in parser.info
