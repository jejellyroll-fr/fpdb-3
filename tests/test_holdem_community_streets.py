import pytest

from fpdb_3_legacy.Hand import HoldemOmahaHand


@pytest.mark.parametrize(
    "street",
    ["FLOP", "TURN", "RIVER", "FLOP1", "TURN2", "RIVER3"],
)
def test_board_streets_include_multi_run_variants(street: str) -> None:
    assert HoldemOmahaHand._is_community_street(street)


@pytest.mark.parametrize(
    "street",
    ["BLINDSANTES", "PREFLOP", "SHOWDOWN", "FLOPPED", "TURNOVER", "RIVERBOAT", "1"],
)
def test_non_board_streets_are_not_read_as_community_cards(street: str) -> None:
    assert not HoldemOmahaHand._is_community_street(street)
