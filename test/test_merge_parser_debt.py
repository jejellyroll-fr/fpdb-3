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
