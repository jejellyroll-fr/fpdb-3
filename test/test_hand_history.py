"""Unit tests for the legacy HandHistory XML parser.

``HandHistory`` parses the site-independent ``<Game>`` XML dump stored in the
``HandHistory.XMLDump`` column. The tests build representative XML documents
and assert on the parsed structure, attribute extraction and boolean
coercion for ``allin`` / ``sitting_out`` player flags.
"""

from __future__ import annotations

from xml.parsers.expat import ExpatError

import pytest

from fpdb_3_legacy.HandHistory import (
    Action,
    Award,
    Awards,
    Betting,
    Game,
    HandHistory,
    Post,
    Posts,
    Round,
)

GAME = "<GAME><GAME_NAME>Hold'em</GAME_NAME><MAX>6</MAX><HIGHLOW>None</HIGHLOW><STRUCTURE>NL</STRUCTURE><MIXED>0</MIXED></GAME>"


def player_xml(**attrs: str) -> str:
    attr_str = "".join(f' {k.upper()}="{v}"' for k, v in attrs.items())
    return f"<PLAYER{attr_str}/>"


def hand_history_xml(players: str = "", awards: str = "", posts: str = "") -> str:
    return (
        f"<Game>{GAME}"
        f"<PLAYERS>{players}</PLAYERS>"
        f"<AWARDS>{awards}</AWARDS>"
        f"<POSTS>{posts}</POSTS>"
        f"<BETTING><ROUND ROUND_NAME='preflop'>"
        f"<ACTION PLAYER='alice' ACT='raise' AMOUNT='2' ALLIN='0'/>"
        f"</ROUND></BETTING>"
        f"</Game>"
    )


def test_hand_history_builds_all_default_elements() -> None:
    xml = hand_history_xml()
    hh = HandHistory(xml)
    assert isinstance(hh.BETTING, Betting)
    assert isinstance(hh.AWARDS, Awards)
    assert isinstance(hh.POSTS, Posts)
    assert isinstance(hh.GAME, Game)
    assert hh.PLAYERS == {}


def test_hand_history_restricted_elements() -> None:
    xml = hand_history_xml()
    hh = HandHistory(xml, elements=("GAME",))
    assert isinstance(hh.GAME, Game)
    assert not hasattr(hh, "BETTING")
    assert not hasattr(hh, "AWARDS")
    assert not hasattr(hh, "POSTS")
    assert not hasattr(hh, "PLAYERS")


def test_hand_history_missing_optional_sections() -> None:
    xml = f"<Game>{GAME}</Game>"
    hh = HandHistory(xml, elements=("ALL",))
    assert not hasattr(hh, "BETTING")
    assert not hasattr(hh, "PLAYERS")


def test_hand_history_parses_players_by_name() -> None:
    xml = hand_history_xml(
        players=(
            player_xml(NAME="alice", SEAT="0", STACK="100", SHOWED_HAND="True", CARDS="AhKh", ALLIN="1", SITTING_OUT="0")
            + player_xml(NAME="bob", SEAT="1", STACK="50")
        )
    )
    hh = HandHistory(xml)
    assert list(hh.PLAYERS) == ["alice", "bob"]
    alice = hh.PLAYERS["alice"]
    assert alice.name == "alice"
    assert alice.seat == "0"
    assert alice.stack == "100"
    assert alice.showed_hand == "True"
    assert alice.cards == "AhKh"
    assert alice.allin is True
    assert alice.sitting_out is False


def test_player_coerces_boolean_flags() -> None:
    hh = HandHistory(hand_history_xml(players=player_xml(NAME="x", ALLIN="FALSE", SITTING_OUT="0")))
    player = hh.PLAYERS["x"]
    assert player.allin is False
    assert player.sitting_out is False

    hh = HandHistory(hand_history_xml(players=player_xml(NAME="x", ALLIN="", SITTING_OUT="True")))
    player = hh.PLAYERS["x"]
    assert player.allin is False
    assert player.sitting_out is True

    hh = HandHistory(hand_history_xml(players=player_xml(NAME="x", ALLIN="yes", SITTING_OUT="yes")))
    player = hh.PLAYERS["x"]
    assert player.allin is True
    assert player.sitting_out is True


def test_player_string_repr() -> None:
    hh = HandHistory(hand_history_xml(players=player_xml(NAME="alice", SEAT="0", STACK="100", CARDS="AhKh", SHOWED_HAND="True", ALLIN="0", HAND="full")))
    text = str(hh.PLAYERS["alice"])
    assert "alice" in text
    assert "seat = 0" in text
    assert "stack = 100" in text
    assert "cards = AhKh" in text
    assert "showed_hand = True" in text
    assert "allin = False" in text
    assert "hand = full" in text


def test_awards_parses_entries() -> None:
    awards_xml = "<AWARD PLAYER='alice' AMOUNT='10' POT='1'/><AWARD PLAYER='bob' AMOUNT='5' POT='1'/>"
    hh = HandHistory(hand_history_xml(awards=awards_xml))
    assert len(hh.AWARDS.awards) == 2
    assert hh.AWARDS.awards[0].player == "alice"
    assert hh.AWARDS.awards[0].amount == "10"
    assert hh.AWARDS.awards[0].pot == "1"
    assert "alice won 10 from 1" == str(hh.AWARDS.awards[0])
    assert "alice" in str(hh.AWARDS)


def test_awards_empty() -> None:
    hh = HandHistory(hand_history_xml(awards=""))
    assert hh.AWARDS.awards == []
    assert str(hh.AWARDS) == ""


def test_posts_parses_entries() -> None:
    posts_xml = "<POST PLAYER='alice' AMOUNT='1' POSTED='sb' LIVE='True'/><POST PLAYER='bob' AMOUNT='2' POSTED='bb' LIVE='True'/>"
    hh = HandHistory(hand_history_xml(posts=posts_xml))
    assert len(hh.POSTS.posts) == 2
    assert hh.POSTS.posts[0].player == "alice"
    assert hh.POSTS.posts[0].amount == "1"
    assert hh.POSTS.posts[0].posted == "sb"
    assert hh.POSTS.posts[0].live == "True"
    assert "alice posted 1 sb True" == str(hh.POSTS.posts[0])
    assert "alice posted" in str(hh.POSTS)


def test_posts_empty() -> None:
    hh = HandHistory(hand_history_xml(posts=""))
    assert hh.POSTS.posts == []
    assert str(hh.POSTS) == ""


def test_game_parses_tags() -> None:
    hh = HandHistory(hand_history_xml())
    assert hh.GAME.tags["game_name"] == "Hold'em"
    assert hh.GAME.tags["max"] == "6"
    assert hh.GAME.tags["high_low"] == "None"
    assert hh.GAME.tags["structure"] == "NL"
    assert hh.GAME.tags["mixed"] == "0"


def test_game_skips_missing_tags() -> None:
    xml = "<Game><GAME><GAME_NAME>Omaha</GAME_NAME></GAME></Game>"
    hh = HandHistory(xml, elements=("GAME",))
    assert hh.GAME.tags == {"game_name": "Omaha"}


def test_game_ignores_non_text_child_nodes() -> None:
    # A tag whose only children are elements yields an empty title instead of crashing.
    xml = "<Game><GAME><GAME_NAME><nested>Hold'em</nested></GAME_NAME></GAME></Game>"
    hh = HandHistory(xml, elements=("GAME",))
    assert hh.GAME.tags == {"game_name": ""}


def test_game_string_repr() -> None:
    hh = HandHistory(hand_history_xml())
    assert "NL" in str(hh.GAME)


def test_betting_parses_rounds_and_actions() -> None:
    xml = (
        "<Game><BETTING>"
        "<ROUND ROUND_NAME='preflop'><ACTION PLAYER='alice' ACT='raise' AMOUNT='2' ALLIN='0'/></ROUND>"
        "<ROUND ROUND_NAME='flop'><ACTION PLAYER='bob' ACT='call' AMOUNT='2' ALLIN='1'/><ACTION PLAYER='alice' ACT='fold' AMOUNT='0' ALLIN='0'/></ROUND>"
        "</BETTING></Game>"
    )
    hh = HandHistory(xml, elements=("BETTING",))
    assert [r.name for r in hh.BETTING.rounds] == ["preflop", "flop"]
    first = hh.BETTING.rounds[0].action[0]
    assert first.player == "alice"
    assert first.action == "raise"
    assert first.amount == "2"
    assert first.allin == "0"
    assert "alice raise 2 0" == str(first)
    flop = hh.BETTING.rounds[1].action
    assert [a.action for a in flop] == ["call", "fold"]
    assert "preflop" in str(hh.BETTING.rounds[0])
    assert "preflop" in str(hh.BETTING)


def test_betting_round_without_actions() -> None:
    xml = "<Game><BETTING><ROUND ROUND_NAME='preflop'/></BETTING></Game>"
    hh = HandHistory(xml, elements=("BETTING",))
    assert hh.BETTING.rounds[0].action == []


def test_malformed_xml_raises() -> None:
    with pytest.raises(ExpatError):
        HandHistory("<Game><GAME><unclosed></Game>")


def test_leaf_classes_read_attributes_directly() -> None:
    from xml.dom.minidom import parseString

    award_node = parseString("<AWARD PLAYER='a' AMOUNT='1' POT='2'/>").documentElement
    award = Award(award_node)
    assert (award.player, award.amount, award.pot) == ("a", "1", "2")

    post_node = parseString("<POST PLAYER='b' AMOUNT='1' POSTED='sb' LIVE='True'/>").documentElement
    post = Post(post_node)
    assert (post.player, post.amount, post.posted, post.live) == ("b", "1", "sb", "True")

    action_node = parseString("<ACTION PLAYER='c' ACT='call' AMOUNT='5' ALLIN='0'/>").documentElement
    action = Action(action_node)
    assert (action.player, action.action, action.amount, action.allin) == ("c", "call", "5", "0")

    round_node = parseString("<ROUND ROUND_NAME='river'/>").documentElement
    round_ = Round(round_node)
    assert round_.name == "river"
    assert round_.action == []


def test_main_returns_codes(tmp_path, monkeypatch) -> None:
    from fpdb_3_legacy import HandHistory as hh_module

    assert hh_module.main(argv=[]) == 1  # test.xml absent -> graceful exit

    (tmp_path / "test.xml").write_text(
        hand_history_xml(players=player_xml(NAME="alice", SEAT="0"))
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hh_module, "sys", __import__("sys"), raising=False)
    assert hh_module.main(argv=None) == 0  # uses sys.argv default, parses test.xml
    assert hh_module.main(argv=["ignored"]) == 0

    (tmp_path / "test.xml").write_text("<Game><broken>")
    assert hh_module.main(argv=[]) == 1  # malformed XML -> graceful exit
