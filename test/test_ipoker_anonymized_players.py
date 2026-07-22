"""The recent iPoker client anonymises every seat as "Player N", hero included.

Regression for the PMU/bwin HUD blocker (log 2026-07-22, table "Sasolburg"):

    HUD not created for hand 599..602: hero 'tripsfountain99' (site_id=56)
    not among players ['Player 10', 'Player 3', 'Player 5', 'Player 6', 'Player 8']

The hero is only recoverable by cross-referencing the session <nickname> with
the one seat whose pocket cards are dealt (opponents show "X X X X"). The parser
must rename that seat to the nickname, and scope the remaining anonymous seats to
the session so a global "Player 3" no longer merges unrelated opponents.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.iPoker.base import iPoker

NICK = "tripsfountain99"
SESSION_CODE = "5869851690"

# Game 1: no showdown -> only the hero (seat 6) shows real pocket cards.
GAME_1 = """ <game gamecode="9025178751">
  <general>
   <startdate>2026-07-21 14:45:39</startdate>
   <players>
    <player seat="3" name="Player 3" chips="2,63€" dealer="0" win="0€" bet="0,04€"/>
    <player seat="5" name="Player 5" chips="2,47€" dealer="1" win="0€" bet="0€"/>
    <player seat="6" name="Player 6" chips="3,42€" dealer="0" win="0,15€" bet="0,06€"/>
    <player seat="10" name="Player 10" chips="1,67€" dealer="0" win="0€" bet="0,06€"/>
   </players>
  </general>
  <round no="0">
   <action no="1" player="Player 6" sum="0,01€" type="1"/>
   <action no="2" player="Player 10" sum="0,02€" type="2"/>
  </round>
  <round no="1">
   <cards type="Pocket" player="Player 3">X X X X</cards>
   <cards type="Pocket" player="Player 5">X X X X</cards>
   <cards type="Pocket" player="Player 6">CA HQ SD 2C</cards>
   <cards type="Pocket" player="Player 10">X X X X</cards>
   <action no="3" player="Player 3" sum="0€" type="0"/>
  </round>
 </game>"""

# Game 2: showdown -> hero (seat 6) AND an opponent (seat 3) both reveal.
GAME_2 = """ <game gamecode="9025178752">
  <general>
   <startdate>2026-07-21 14:46:41</startdate>
   <players>
    <player seat="3" name="Player 3" chips="2,63€" dealer="0" win="1,20€" bet="0,40€"/>
    <player seat="5" name="Player 5" chips="2,47€" dealer="1" win="0€" bet="0€"/>
    <player seat="6" name="Player 6" chips="3,42€" dealer="0" win="0€" bet="0,40€"/>
    <player seat="10" name="Player 10" chips="1,67€" dealer="0" win="0€" bet="0€"/>
   </players>
  </general>
  <round no="1">
   <cards type="Pocket" player="Player 3">CK DK HK SA</cards>
   <cards type="Pocket" player="Player 5">X X X X</cards>
   <cards type="Pocket" player="Player 6">CA HQ SD 2C</cards>
   <cards type="Pocket" player="Player 10">X X X X</cards>
  </round>
 </game>"""

HEADER = f"""<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="{SESSION_CODE}">
 <general>
  <client_version>26.1.1.23</client_version>
  <mode>real</mode>
  <gametype>Omaha PL 0,01€/0,02€</gametype>
  <tablename>Sasolburg, 560237915</tablename>
  <tablecurrency>EUR</tablecurrency>
  <smallblind>0,01€</smallblind>
  <bigblind>0,02€</bigblind>
  <duration>00:05:34</duration>
  <gamecount>2</gamecount>
  <startdate>2026-07-21 14:45:39</startdate>
  <currency>EUR</currency>
  <nickname>{NICK}</nickname>
  <tablesize>6</tablesize>
 </general>
"""

ANON_FILE = HEADER + GAME_1 + "\n" + GAME_2 + "\n</session>"


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _parser(config: Config, whole_file: str, hero: str = NICK) -> iPoker:
    parser = iPoker(config, autostart=False)
    parser.whole_file = whole_file
    parser.hero = hero
    return parser


def test_resolve_hero_prefers_the_seat_dealt_in_every_hand(config: Config) -> None:
    """Seat 6 shows cards in both hands; seat 3 only at its lone showdown."""
    parser = _parser(config, ANON_FILE)
    assert parser._resolve_anonymized_hero() == "Player 6"


def test_hero_renamed_to_nickname_in_players_actions_and_cards(config: Config) -> None:
    parser = _parser(config, ANON_FILE)
    hand = SimpleNamespace(handText=GAME_1, handid="9025178751")

    parser._deanonymize_players(hand)

    # Hero recovered everywhere the anonymous name appeared.
    assert 'name="Player 6"' not in hand.handText
    assert 'player="Player 6"' not in hand.handText
    assert f'name="{NICK}"' in hand.handText
    assert f'player="{NICK}"' in hand.handText  # blind action + pocket cards


def test_opponents_scoped_to_the_session(config: Config) -> None:
    parser = _parser(config, ANON_FILE)
    hand = SimpleNamespace(handText=GAME_1, handid="9025178751")

    parser._deanonymize_players(hand)

    assert f'name="anon_{SESSION_CODE}_3"' in hand.handText
    assert f'name="anon_{SESSION_CODE}_5"' in hand.handText
    assert f'name="anon_{SESSION_CODE}_10"' in hand.handText
    # A fold by the seat-3 opponent must follow the rename.
    assert f'player="anon_{SESSION_CODE}_3"' in hand.handText
    # No bare "Player N" survives.
    assert "Player 3" not in hand.handText
    assert "Player 10" not in hand.handText


def test_real_hero_kept_while_anon_opponents_are_scoped(config: Config) -> None:
    """A seated real hero name is preserved; anonymous opponents are still scoped."""
    real = ANON_FILE.replace('name="Player 6"', 'name="tripsfountain99"').replace(
        'player="Player 6"',
        'player="tripsfountain99"',
    )
    game_1_real = GAME_1.replace('name="Player 6"', 'name="tripsfountain99"').replace(
        'player="Player 6"',
        'player="tripsfountain99"',
    )
    parser = _parser(config, real)
    hand = SimpleNamespace(handText=game_1_real, handid="9025178751")

    parser._deanonymize_players(hand)

    # Real opponents ("Player N" no longer, they keep their own names here) —
    # but the seat-3/5/10 opponents are still anonymous, so they get scoped;
    # the hero name is preserved as-is.
    assert 'name="tripsfountain99"' in hand.handText
    assert f'name="anon_{SESSION_CODE}_3"' in hand.handText


def test_unresolvable_hero_leaves_hand_anonymous(config: Config) -> None:
    """A single showdown hand (tie) must not guess or strip the hero."""
    single = HEADER + GAME_2 + "\n</session>"
    parser = _parser(config, single)
    hand = SimpleNamespace(handText=GAME_2, handid="9025178752")

    parser._deanonymize_players(hand)

    # Seat 3 and seat 6 both reveal once -> tie -> untouched.
    assert 'name="Player 6"' in hand.handText
    assert 'name="Player 3"' in hand.handText
    assert f"anon_{SESSION_CODE}" not in hand.handText


def test_incremental_hand_still_deanonymizes(config: Config) -> None:
    """A bare <game> block (live auto-import) resolves via the session whole_file."""
    parser = _parser(config, ANON_FILE)
    hand = SimpleNamespace(handText=GAME_2, handid="9025178752")

    parser._deanonymize_players(hand)

    assert f'name="{NICK}"' in hand.handText  # seat 6 -> hero
    assert f'name="anon_{SESSION_CODE}_3"' in hand.handText  # showdown opponent scoped
