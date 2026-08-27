"""iPoker anonymises a hand ("Player N") only when the hero is not dealt in.

Confirmed on real bwin files (session 5870214435, 2026-07-22): hands the hero
did not play list only "Player 3/5/6/8/10" (== seat numbers), while the hands
the hero played carry real names (jejesat76 @ seat 1, CR7012 @ 3, Moula42 @ 5,
TheDarkRaise @ 8, confusius5 @ 10). No pocket cards are revealed in either.

So there is never an anonymous hero to recover: the anonymous hands are exactly
the hands the hero skipped. Their opponents are recovered instead from the
seat -> real name map learned from the session's named hands; unknown seats are
scoped to anon_<sessioncode>_<seat> so a global "Player 3" never merges
unrelated opponents.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.HandHistoryConverter import FpdbHandPartial
from fpdb_3_legacy.iPoker.base import iPoker

NICK = "jejesat76"
SESSION_CODE = "5870214435"

# Anonymous hand: hero not dealt -> every seat is "Player <seat>".
ANON_GAME = """ <game gamecode="9026868234">
  <general>
   <startdate>2026-07-22 23:27:00</startdate>
   <players>
    <player seat="3" name="Player 3" chips="2,63€" dealer="0" win="0€" bet="0,04€"/>
    <player seat="5" name="Player 5" chips="2,47€" dealer="1" win="0€" bet="0€"/>
    <player seat="6" name="Player 6" chips="3,42€" dealer="0" win="0€" bet="0,06€"/>
    <player seat="8" name="Player 8" chips="1,67€" dealer="0" win="0,15€" bet="0,06€"/>
    <player seat="10" name="Player 10" chips="1,90€" dealer="0" win="0€" bet="0,02€"/>
   </players>
  </general>
  <round no="0">
   <action no="1" player="Player 8" sum="0,01€" type="1"/>
   <action no="2" player="Player 10" sum="0,02€" type="2"/>
  </round>
  <round no="1">
   <action no="3" player="Player 3" sum="0€" type="0"/>
  </round>
 </game>"""

# Named hand: hero dealt in -> real names for everyone.
NAMED_GAME = """ <game gamecode="9026877611">
  <general>
   <startdate>2026-07-22 23:30:58</startdate>
   <players>
    <player seat="1" name="jejesat76" chips="1,90€" dealer="0" win="0€" bet="0,02€"/>
    <player seat="3" name="CR7012" chips="2,23€" dealer="0" win="0€" bet="0€"/>
    <player seat="5" name="Moula42" chips="2,00€" dealer="1" win="0€" bet="0€"/>
    <player seat="8" name="TheDarkRaise" chips="1,42€" dealer="0" win="0€" bet="0,04€"/>
    <player seat="10" name="confusius5" chips="1,79€" dealer="0" win="0€" bet="0€"/>
   </players>
  </general>
  <round no="0">
   <action no="1" player="jejesat76" sum="0,01€" type="1"/>
   <action no="2" player="CR7012" sum="0,02€" type="2"/>
  </round>
 </game>"""

HEADER = f"""<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="{SESSION_CODE}">
 <general>
  <client_version>26.1.1.31</client_version>
  <mode>real</mode>
  <gametype>Omaha PL 0,01€/0,02€</gametype>
  <tablename>Scone, 560235983</tablename>
  <tablecurrency>EUR</tablecurrency>
  <smallblind>0,01€</smallblind>
  <bigblind>0,02€</bigblind>
  <duration>00:05:34</duration>
  <gamecount>2</gamecount>
  <startdate>2026-07-22 23:27:00</startdate>
  <currency>EUR</currency>
  <nickname>{NICK}</nickname>
  <tablesize>6</tablesize>
 </general>
"""

# Whole session file: anonymous hands first (hero waiting), then named hands.
SESSION_FILE = HEADER + ANON_GAME + "\n" + NAMED_GAME + "\n</session>"


@pytest.fixture(scope="module")
def config() -> Config:
    return Config()


def _parser(config: Config, whole_file: str, hero: str = NICK) -> iPoker:
    parser = iPoker(config, autostart=False)
    parser.whole_file = whole_file
    parser.hero = hero
    return parser


def test_session_seat_names_learned_from_named_hands(config: Config) -> None:
    parser = _parser(config, SESSION_FILE)
    assert parser._session_seat_names() == {
        1: "jejesat76",
        3: "CR7012",
        5: "Moula42",
        8: "TheDarkRaise",
        10: "confusius5",
    }


def test_named_hand_is_left_untouched(config: Config) -> None:
    parser = _parser(config, SESSION_FILE)
    hand = SimpleNamespace(handText=NAMED_GAME, handid="9026877611")

    parser._deanonymize_players(hand)

    assert hand.handText == NAMED_GAME  # real names already, nothing rewritten


def test_anonymous_opponents_recovered_from_seat_map(config: Config) -> None:
    parser = _parser(config, SESSION_FILE)
    hand = SimpleNamespace(handText=ANON_GAME, handid="9026868234")

    parser._deanonymize_players(hand)

    # Seats known from the named hand -> real names, in players and actions.
    assert 'name="CR7012"' in hand.handText          # seat 3
    assert 'name="Moula42"' in hand.handText          # seat 5
    assert 'name="TheDarkRaise"' in hand.handText     # seat 8
    assert 'player="TheDarkRaise"' in hand.handText   # small-blind action rewritten
    assert 'name="confusius5"' in hand.handText       # seat 10
    # Seat 6 never carried a real name in the session -> scoped, not guessed.
    assert f'name="anon_{SESSION_CODE}_6"' in hand.handText
    assert "Player 3" not in hand.handText
    assert "Player 6" not in hand.handText


def test_hero_seat_never_resurrected_in_anonymous_hand(config: Config) -> None:
    # An anonymous hand that (defensively) has a Player 1 at the hero's seat must
    # be scoped, not renamed back to the hero -- the hero did not play this hand.
    anon_with_seat1 = ANON_GAME.replace(
        '<player seat="3" name="Player 3"',
        '<player seat="1" name="Player 1" chips="1,90€" dealer="0" win="0€" bet="0€"/>\n'
        '    <player seat="3" name="Player 3"',
    )
    parser = _parser(config, SESSION_FILE)
    hand = SimpleNamespace(handText=anon_with_seat1, handid="9026868234")

    parser._deanonymize_players(hand)

    assert f'name="{NICK}"' not in hand.handText
    assert f'name="anon_{SESSION_CODE}_1"' in hand.handText


def test_anonymous_hand_without_named_hand_scopes_all(config: Config) -> None:
    # Live import order: the anonymous hands arrive before the hero ever plays,
    # so no seat map exists yet -> everything is scoped (no pollution), and later
    # hands recover once the hero has played.
    only_anon = HEADER + ANON_GAME + "\n</session>"
    parser = _parser(config, only_anon)
    hand = SimpleNamespace(handText=ANON_GAME, handid="9026868234")

    parser._deanonymize_players(hand)

    for seat in (3, 5, 6, 8, 10):
        assert f'name="anon_{SESSION_CODE}_{seat}"' in hand.handText
    assert "Player" not in hand.handText.replace("PLAY", "")  # no bare "Player N"


def test_ambiguous_seat_occupant_is_scoped_not_guessed(config: Config) -> None:
    # If a seat shows two different real names across the session, it's dropped
    # from the map (occupant changed) and anonymous hands scope that seat.
    second_named = NAMED_GAME.replace('name="CR7012"', 'name="SomeoneElse"').replace(
        'gamecode="9026877611"',
        'gamecode="9026877999"',
    )
    session = HEADER + ANON_GAME + "\n" + NAMED_GAME + "\n" + second_named + "\n</session>"
    parser = _parser(config, session)

    assert 3 not in parser._session_seat_names()  # CR7012 vs SomeoneElse -> ambiguous

    hand = SimpleNamespace(handText=ANON_GAME, handid="9026868234")
    parser._deanonymize_players(hand)
    assert f'name="anon_{SESSION_CODE}_3"' in hand.handText


def test_a_fully_anonymous_hand_is_not_stored(config: Config) -> None:
    """Live import reaching an observed hand before the hero has played one.

    Nothing names a seat yet, so storing the hand would create a Players row per
    seat that no statistic is ever read back through -- the hero is not in the
    hand, so it builds no HUD, and the real names the file reveals minutes later
    never reach the rows already written. The hand is dropped instead; a later
    full import of the file stores it under the real opponents.
    """
    only_anon = HEADER + ANON_GAME + "\n</session>"
    parser = _parser(config, only_anon)
    parser.info = {"type": "ring"}
    hand = SimpleNamespace(handText=HEADER + ANON_GAME, handid="")

    with pytest.raises(FpdbHandPartial):
        parser.readHandInfo(hand)


def test_a_hand_with_one_recovered_seat_is_still_stored(config: Config) -> None:
    """Partial knowledge is real knowledge: only a nameless hand is dropped."""
    parser = _parser(config, SESSION_FILE)  # holds a named hand
    parser.info = {"type": "ring"}
    parser.tablename = "Scone, 560235983"
    hand = SimpleNamespace(handText=HEADER + ANON_GAME, handid="")

    parser.readHandInfo(hand)  # must not raise

    assert hand.handid == "9026868234"
    assert 'name="CR7012"' in hand.handText
