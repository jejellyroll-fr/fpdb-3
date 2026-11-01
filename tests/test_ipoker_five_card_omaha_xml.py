"""iPoker writes 5 card Omaha with no game name in <gametype> -- the limit and
blinds alone, "PL €1/€2", where every other variant is named ("Omaha PL €1/€2"
is the 4 card game).

Only the first hand of a session file carries the <general> header, so only that
hand is read by base.py's re_game_info, whose CATEGORY group is optional and
which maps an absent category to 5_omahahi. Every later hand is a bare <game>
block and goes through _parse_xml_format instead, which re-reads <gametype> from
whole_file but required a game name -- so the match failed and the filename
fallback labelled the hand NL Holdem 0.01/0.02.

The category alone splits one table across two gametype ids; the invented
0.01/0.02 blinds are worse, because the blind-posting logic sizes the posts
against them and every subsequent bet in the hand is then read wrong.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.base import iPoker

HEADER = """<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="4042104250">
 <general>
  <mode>real</mode>
  <gametype>{gametype}</gametype>
  <tablename>100BB Nokia 11, 488821530</tablename>
  <tablecurrency>EUR</tablecurrency>
  <currency>EUR</currency>
  <nickname>hero_seat8</nickname>
  <tablesize>6</tablesize>
 </general>
"""

# Two hands, so the second one exercises the header-less path.
GAME = """<game gamecode="{gamecode}">
  <general>
   <startdate>2021-02-09 20:54:03</startdate>
   <players>
    <player seat="5" name="opp_seat5" bet="€0" chips="€864,01" win="€0" dealer="1"/>
    <player seat="6" name="opp_seat6" bet="€45" chips="€596,60" win="€0" dealer="0"/>
    <player seat="8" name="hero_seat8" bet="€45" chips="€600" win="€87,28" dealer="0"/>
   </players>
  </general>
  <round no="0">
   <action sum="€3" player="opp_seat6" cards="" no="1" type="1"/>
   <action sum="€6" player="hero_seat8" cards="" no="2" type="2"/>
  </round>
  <round no="1">
   <cards player="opp_seat5" type="Pocket">X X X X X</cards>
   <action sum="€0" player="opp_seat5" cards="" no="3" type="0"/>
   <cards player="opp_seat6" type="Pocket">C2 D4 HQ HA C4</cards>
   <action sum="€18" player="opp_seat6" cards="" no="4" type="23"/>
   <cards player="hero_seat8" type="Pocket">C9 S10 SJ C8 S9</cards>
   <action sum="€12" player="hero_seat8" cards="" no="5" type="3"/>
  </round>
  <round no="2">
   <cards player="" type="Flop">H7 S8 H8</cards>
   <action sum="€0" player="opp_seat6" cards="" no="6" type="4"/>
   <action sum="€0" player="hero_seat8" cards="" no="7" type="4"/>
  </round>
  <round no="3">
   <cards player="" type="Turn">S7</cards>
   <action sum="€27" player="opp_seat6" cards="" no="8" type="5"/>
   <action sum="€27" player="hero_seat8" cards="" no="9" type="3"/>
  </round>
  <round no="4">
   <cards player="" type="River">SQ</cards>
   <action sum="€0" player="opp_seat6" cards="" no="10" type="4"/>
   <action sum="€0" player="hero_seat8" cards="" no="11" type="4"/>
  </round>
 </game>
"""

SESSION = HEADER.format(gametype="PL €3/€6") + GAME.format(gamecode="3570548920") + GAME.format(
    gamecode="3570548921",
) + "</session>\n"


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _parser(config: Config, tmp_path, whole_file: str) -> iPoker:
    # allHandsAsList re-reads in_path, so the session has to exist on disk. The
    # name matters: the fallback this bug landed in also guesses from filename.
    path = tmp_path / "4042104250.xml"
    path.write_text(whole_file, encoding="utf-8")
    return iPoker(config, in_path=str(path), autostart=False)


def test_every_hand_of_a_five_card_session_gets_the_same_gametype(config: Config, tmp_path) -> None:
    # Regression: hand 1 parsed as 5_omahahi/pl/3/6 and hands 2..N as
    # holdem/nl/0.01/0.02, splitting one table across two gametype ids.
    parser = _parser(config, tmp_path, SESSION)
    hands = parser.allHandsAsList()
    assert len(hands) == 2

    parsed = [parser.determineGameType(hand) for hand in hands]

    for info in parsed:
        assert (info["base"], info["category"]) == ("hold", "5_omahahi")
        assert info["limitType"] == "pl"
        assert (info["sb"], info["bb"]) == ("3", "6")


def test_five_card_blinds_are_read_from_the_gametype(config: Config, tmp_path) -> None:
    # The invented 0.01/0.02 defaults are what corrupted the money: posts sized
    # against them threw off every bet that followed.
    session = SESSION.replace("PL €3/€6", "PL €0,50/€1")
    parser = _parser(config, tmp_path, session)

    info = parser.determineGameType(parser.allHandsAsList()[1])

    assert (info["sb"], info["bb"]) == ("0.50", "1")


def test_headerless_hand_keeps_the_players_money(config: Config, tmp_path) -> None:
    parser = _parser(config, tmp_path, SESSION)
    hand = parser.processHand(parser.allHandsAsList()[1])

    collected = sum(Decimal(amount) for amount in hand.collectees.values())
    posted = sum(
        Decimal(amount)
        for street in hand.bets
        for amounts in hand.bets[street].values()
        for amount in amounts
    )
    # €45 + €45 in, €87.28 back out: the rest is rake, not a parsing artefact.
    assert posted == Decimal(90)
    assert collected == Decimal("87.28")


def test_a_named_omaha_session_is_still_the_four_card_game(config: Config, tmp_path) -> None:
    # iPoker is not consistent: "Omaha PL" is 4 card Omaha and has to keep
    # resolving to omahahi, so the nameless rule must not reach it.
    session = SESSION.replace("PL €3/€6", "Omaha PL €3/€6")
    parser = _parser(config, tmp_path, session)

    info = parser.determineGameType(parser.allHandsAsList()[1])

    assert info["category"] == "omahahi"
    assert info["limitType"] == "pl"


@pytest.mark.parametrize(
    ("gametype", "category", "limit_type"),
    [
        ("Holdem NL €3/€6", "holdem", "nl"),
        ("Holdem L €3/€6", "holdem", "fl"),
        ("Omaha PL €3/€6", "omahahi", "pl"),
        ("7 Card Stud L €3/€6", "studhi", "fl"),
    ],
)
def test_named_gametypes_are_untouched(
    config: Config,
    tmp_path,
    gametype: str,
    category: str,
    limit_type: str,
) -> None:
    parser = _parser(config, tmp_path, SESSION.replace("PL €3/€6", gametype))

    info = parser.determineGameType(parser.allHandsAsList()[1])

    assert info["category"] == category
    assert info["limitType"] == limit_type


def test_a_nameless_gametype_that_is_not_pot_limit_is_not_five_card_omaha(config: Config, tmp_path) -> None:
    # 5 card Omaha is pot limit only. A nameless "NL €3/€6" is not a game iPoker
    # deals, so it must not be invented as one -- it stays on the old fallback.
    parser = _parser(config, tmp_path, SESSION.replace("PL €3/€6", "NL €3/€6"))

    info = parser.determineGameType(parser.allHandsAsList()[1])

    assert info["category"] != "5_omahahi"
