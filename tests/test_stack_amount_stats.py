"""The stack in its own unit next to the stack in big blinds (#402).

Every form reads the end-of-hand stack ``bbstack`` reconstructs from the last
imported hand; these tests pin the units, the missing-stack case and that the
forms agree with each other and with ``bbstack``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from fpdb_3_legacy.localized_formats import get_format_locale, set_format_locale
from fpdb_3_legacy.Stats import do_stat

STAT_DICT = {1: {"screen_name": "Hero"}, 2: {"screen_name": "Gone"}}


@pytest.fixture(autouse=True)
def english_numbers():
    previous = get_format_locale()
    set_format_locale("en_US")
    yield
    set_format_locale(previous)


def hand(*, start: str, bets: list[str], won: str = "0", bb: str, currency: str, kind: str = "ring") -> Any:
    return SimpleNamespace(
        players=[[1, "Hero", start, None, None], [2, "Villain", "100", None, None]],
        bets={"BLINDSANTES": {"Hero": []}, "PREFLOP": {"Hero": list(bets)}},
        pot=SimpleNamespace(returned={}),
        collectees={"Hero": won} if won != "0" else {},
        gametype={"bb": bb, "sb": str(float(bb) / 2), "currency": currency, "type": kind},
    )


def stat(name: str, table_hand: Any, player: int = 1) -> tuple:
    return do_stat(STAT_DICT, stat=name, player=player, hand_instance=table_hand)


def test_a_cash_stack_is_shown_in_its_currency() -> None:
    table = hand(start="45.00", bets=["2.25"], bb="1.00", currency="EUR")

    assert stat("stack_amount", table)[1] == "€42.75"
    assert stat("stack_bb", table)[1] == "42.8bb"
    assert stat("stack_native_bb", table)[1] == "€42.75 / 42.8bb"


def test_a_dollar_table_uses_the_dollar() -> None:
    table = hand(start="100", bets=["3"], won="10", bb="0.50", currency="USD")

    assert stat("stack_amount", table)[1] == "$107.00"
    assert stat("stack_bb", table)[1] == "214.0bb"


def test_tournament_chips_show_no_currency_symbol() -> None:
    table = hand(start="19000", bets=["580"], bb="800", currency="T$", kind="tour")

    assert stat("stack_amount", table)[1] == "18,420"
    assert stat("stack_bb", table)[1] == "23.0bb"
    # The combined form stays short enough for a HUD cell.
    assert stat("stack_native_bb", table)[1] == "18.4k / 23.0bb"


def test_play_money_is_chips_too() -> None:
    table = hand(start="1500", bets=["20"], bb="20", currency="play")

    assert stat("stack_amount", table)[1] == "1,480"


@pytest.mark.parametrize(("bb", "expected"), [("0.10", "425.0bb"), ("0.25", "170.0bb"), ("2.00", "21.3bb")])
def test_the_bb_form_follows_the_blind_size(bb: str, expected: str) -> None:
    table = hand(start="42.50", bets=[], bb=bb, currency="USD")

    assert stat("stack_amount", table)[1] == "$42.50"
    assert stat("stack_bb", table)[1] == expected


def test_every_form_reads_the_stack_bbstack_reads() -> None:
    table = hand(start="45.00", bets=["2.25"], bb="1.00", currency="EUR")

    bbstack = stat("bbstack", table)
    assert stat("stack_amount", table)[0] == pytest.approx(42.75)
    assert stat("stack_bb", table)[0] == pytest.approx(bbstack[0] * 100)
    assert int(stat("stack_bb", table)[0]) == int(bbstack[1])


def test_a_player_missing_from_the_hand_is_unavailable_not_zero() -> None:
    table = hand(start="45.00", bets=[], bb="1.00", currency="EUR")

    for name in ("stack_amount", "stack_bb", "stack_native_bb"):
        assert stat(name, table, player=2)[1] == "-"


def test_without_a_hand_every_form_is_unavailable() -> None:
    for name in ("stack_amount", "stack_bb", "stack_native_bb"):
        assert do_stat(STAT_DICT, stat=name, player=1, hand_instance=None)[1] == "-"


def test_without_a_big_blind_the_combined_form_keeps_the_amount() -> None:
    table = hand(start="45.00", bets=[], bb="0", currency="EUR")

    assert stat("stack_bb", table)[1] == "-"
    assert stat("stack_native_bb", table)[1] == "€45.00"
