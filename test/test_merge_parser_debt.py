from types import SimpleNamespace
from unittest.mock import Mock

from fpdb_3_legacy.MergeToFpdb import Merge


def _hand(sb: str | None, bb: str | None, game_type: str = "tour") -> SimpleNamespace:
    return SimpleNamespace(
        gametype={"type": game_type, "secondGame": False, "sb": sb, "bb": bb},
        addBlind=Mock(),
    )


def test_fix_tour_blinds_preserves_complete_non_two_to_one_level() -> None:
    hand = _hand("10", "25")

    Merge.__new__(Merge).fixTourBlinds(hand, {})

    assert (hand.sb, hand.bb) == ("10", "25")
    assert (hand.gametype["sb"], hand.gametype["bb"]) == ("10", "25")


def test_fix_tour_blinds_derives_only_the_missing_blind() -> None:
    hand = _hand(None, "25")

    Merge.__new__(Merge).fixTourBlinds(hand, {})

    assert (hand.sb, hand.bb) == ("12", "25")


def test_fix_tour_blinds_reconstructs_all_in_from_authoritative_level() -> None:
    parser = Merge.__new__(Merge)
    parser.adjustMergeTourneyStack = Mock()
    hand = _hand("10", "25")

    parser.fixTourBlinds(hand, {"Alice": "small blind", "Bob": "big blind"})

    parser.adjustMergeTourneyStack.assert_any_call(hand, "Alice", "10")
    parser.adjustMergeTourneyStack.assert_any_call(hand, "Bob", "25")
    hand.addBlind.assert_any_call("Alice", "small blind", "10")
    hand.addBlind.assert_any_call("Bob", "big blind", "25")


def test_fix_tour_blinds_ignores_ring_games() -> None:
    hand = _hand("10", "25", game_type="ring")

    Merge.__new__(Merge).fixTourBlinds(hand, {})

    assert not hasattr(hand, "sb")
    hand.addBlind.assert_not_called()


def test_merge_metadata_accepts_play_money_seconds_and_explicit_seats() -> None:
    hand_text = """
    <description type="Holdem" stakes="No Limit ($10/$20)"/>
    <game id="46154255-645" starttime="20111230232051" numholecards="2" gametype="1" seats="9" realmoney="false" data="20111230|Play Money|46154255|46154255-645|false">
    """
    parser = Merge.__new__(Merge)

    game_type = parser.determineGameType(hand_text)
    hand_info = parser.re_HandInfo.search(hand_text)

    assert game_type is not None
    assert game_type["currency"] == "play"
    assert hand_info is not None
    assert hand_info.group("REALMONEY") == "false"
    assert hand_info.group("DATETIME") == "20111230232051"
    assert hand_info.group("SEATS") == "9"
