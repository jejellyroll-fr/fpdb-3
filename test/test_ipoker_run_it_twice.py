"""iPoker marks a run-it-twice hand with per-board attributes on tags the
parser matched by whitelisting attribute names, so such hands never imported.

Two tags change when the remaining players run the board more than once:

    <player ... board1win="EUR0" board2win="EUR456,87" .../>
    <cards board="board1" type="River">S2</cards>

re_player_info and re_board both consume ``<tag ...>`` as one-or-more
repetitions of a closed set of attributes. An attribute outside that set makes
the whole tag fail to match, so re_player_info found zero players and the hand
was rejected as partial ("Less than 2 players"); with that fixed, re_board then
failed on the river and readCommunityCards rejected it instead.

Both boards are dealt from the same pot and each player's ``win`` attribute is
already their total across boards, so reading board 1 and ignoring the rest
imports a correct hand -- the second board is simply not modelled yet.

Structure below mirrors a real €1/€2 5-card PLO hand run twice from the river
(bwin, 2024-12-09), with the screen names replaced.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.base import iPoker

HEADER = """<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="4156657155">
 <general>
  <mode>real</mode>
  <gametype>PL €1/€2</gametype>
  <tablename>100BB Table 11, 488785596</tablename>
  <tablecurrency>EUR</tablecurrency>
  <smallblind>€1</smallblind>
  <bigblind>€2</bigblind>
  <gamecount>1</gamecount>
  <startdate>2024-12-09 21:57:22</startdate>
  <currency>EUR</currency>
  <nickname>hero_seat6</nickname>
  <tablesize>6</tablesize>
 </general>
"""

# All-in on the turn, river run twice: seat 3 takes board 1, seat 5 takes board 2.
RIT_GAME = """<game gamecode="3956819422">
  <general>
   <startdate>2024-12-09 22:41:03</startdate>
   <players>
    <player bet="€7" board2win="€0" seat="1" board1win="€0" dealer="0" chips="€121,08" name="opp_seat1" win="€0"/>
    <player bet="€453,62" board2win="€0" seat="3" board1win="€456,87" dealer="1" chips="€453,62" name="opp_seat3" win="€456,87"/>
    <player bet="€616,50" board2win="€456,87" seat="5" board1win="€0" dealer="0" chips="€659,25" name="opp_seat5" win="€456,87"/>
    <player bet="€2" board2win="€0" seat="6" board1win="€0" dealer="0" chips="€200" name="hero_seat6" win="€0"/>
   </players>
  </general>
  <round no="0">
   <action sum="€1" player="opp_seat5" no="1" type="1"/>
   <action sum="€2" player="hero_seat6" no="2" type="2"/>
  </round>
  <round no="1">
   <cards player="opp_seat3" type="Pocket">SJ H9 D10 D3 C8</cards>
   <cards player="opp_seat5" type="Pocket">S7 HA D8 CA H6</cards>
   <action sum="€7" player="opp_seat1" no="5" type="23"/>
   <action sum="€7" player="opp_seat3" no="6" type="3"/>
   <action sum="€30" player="opp_seat5" no="7" type="23"/>
   <action sum="€0" player="hero_seat6" no="8" type="0"/>
   <action sum="€0" player="opp_seat1" no="9" type="0"/>
   <action sum="€23" player="opp_seat3" no="10" type="3"/>
  </round>
  <round no="2">
   <cards type="Flop">S6 H3 C10</cards>
   <action sum="€34,50" player="opp_seat5" no="11" type="5"/>
   <action sum="€172,50" player="opp_seat3" no="12" type="23"/>
   <action sum="€138" player="opp_seat5" no="13" type="3"/>
  </round>
  <round no="3">
   <cards type="Turn">HJ</cards>
   <action sum="€414" player="opp_seat5" no="14" type="5"/>
   <action sum="€251,12" player="opp_seat3" no="15" type="7"/>
  </round>
  <round no="4">
   <cards board="board1" type="River">S2</cards>
   <cards board="board2" type="River">HK</cards>
  </round>
 </game>
</session>
"""

RIT_FILE = HEADER + RIT_GAME


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _hand(config: Config, tmp_path, whole_file: str):
    # allHandsAsList re-reads in_path, so the session has to exist on disk.
    path = tmp_path / "session.xml"
    path.write_text(whole_file, encoding="utf-8")

    parser = iPoker(config, in_path=str(path), autostart=False)
    assert parser.determineGameType(whole_file)
    hands = parser.allHandsAsList()
    assert len(hands) == 1
    return parser.processHand(hands[0])


def test_run_it_twice_hand_is_imported(config: Config, tmp_path) -> None:
    # Regression: this raised FpdbHandPartialError("Less than 2 players").
    hand = _hand(config, tmp_path, RIT_FILE)

    assert hand.handid == "3956819422"
    assert len(hand.players) == 4


def test_run_it_twice_players_keep_their_stacks(config: Config, tmp_path) -> None:
    # board1win/board2win sit between the attributes the regex does capture, so
    # a match that stops early would silently lose seats or chip counts.
    hand = _hand(config, tmp_path, RIT_FILE)

    stacks = {name: chips for _seat, name, chips, *_rest in hand.players}
    assert stacks == {
        "opp_seat1": "121.08",
        "opp_seat3": "453.62",
        "opp_seat5": "659.25",
        "hero_seat6": "200",
    }


def test_run_it_twice_reads_the_first_board(config: Config, tmp_path) -> None:
    hand = _hand(config, tmp_path, RIT_FILE)

    assert hand.board["FLOP"] == ["6s", "3h", "Tc"]
    assert hand.board["TURN"] == ["Jh"]
    assert hand.board["RIVER"] == ["2s"]  # board 1; board 2's Kh is not modelled


def test_single_board_hand_still_reads_its_river(config: Config, tmp_path) -> None:
    # The board attribute is optional -- ordinary hands must be unaffected.
    single = RIT_FILE.replace('<cards board="board1" type="River">S2</cards>\n   ', "").replace(
        '<cards board="board2" type="River">HK</cards>',
        '<cards type="River">S2</cards>',
    )
    hand = _hand(config, tmp_path, single)

    assert hand.board["RIVER"] == ["2s"]
