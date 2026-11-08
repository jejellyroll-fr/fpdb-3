"""Find the 2026 Unibet client's table windows by the id in their title (#729).

A table window is titled e.g. "Omaha - PL5 (99465067)" (observed on the live
client, UnibetPoker v3.58.0): the id in parentheses is the hand's
``Table "99465067"`` id, i.e. the cash ``table_name`` or the tournament
``table_number``. The lobby window is "Unibet Poker v3.58.0" and carries no id.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.HandHistoryConverter import getTableNoRe, getTableTitleRe
from fpdb_3_legacy.UnibetToFpdb import Unibet

TABLE_TITLE = "Omaha - PL5 (99465067)"
# Tournament windows carry the tournament id, not the table id (observed live:
# the hand says Tournament #99007080 / Table "99503253", the window title
# carries (99007080), and the export file is named "H... T99007080 ...").
TOUR_TITLE = "0,25€ Power Spin Flash - 10/20  - Prize pool 5€ (99007080)"
OTHER_TOUR_TITLE = "0,25€ Power Spin Flash - 15/30  - Prize pool 0,50€ (99006969)"
LOBBY_TITLE = "Unibet Poker v3.58.0"
OTHER_TABLE_TITLE = "Omaha - PL5 (99433705)"


def test_cash_search_matches_the_table_id_in_parentheses() -> None:
    pattern = Unibet.getTableTitleRe("cash", table_name="99465067")

    assert re.search(pattern, TABLE_TITLE)
    # Windows titles may carry the app name as a suffix.
    assert re.search(pattern, f"{TABLE_TITLE}, Unibet Poker v3.58.0")
    assert not re.search(pattern, LOBBY_TITLE)
    assert not re.search(pattern, OTHER_TABLE_TITLE)


def test_tournament_search_uses_the_tournament_id() -> None:
    pattern = Unibet.getTableTitleRe("tour", tournament=99007080, table_number=99503253)

    assert re.search(pattern, TOUR_TITLE)
    # The table id is not in the title; another spin's window must not match.
    assert not re.search(pattern, OTHER_TOUR_TITLE)
    assert not re.search(pattern, "0,25€ Power Spin Flash (99503253)")
    assert not re.search(pattern, LOBBY_TITLE)


def _group1(pattern: str, title: str) -> str:
    match = re.search(pattern, title)
    assert match is not None
    return match.group(1)


def test_table_no_re_only_flags_an_id_different_from_the_tournament() -> None:
    pattern = Unibet.getTableNoRe(99007080)

    # The window's own id is the tournament's: not a table move.
    assert re.search(pattern, TOUR_TITLE) is None
    # A different id in parentheses (a real table move) is caught.
    assert _group1(pattern, "0,25€ Power Spin Flash - 10/20 (99503253)") == "99503253"
    assert re.search(pattern, LOBBY_TITLE) is None


def test_the_hhc_config_entry_dispatches_to_the_unibet_converter() -> None:
    # HUD_config.xml: <hhc site="Unibet" converter="UnibetToFpdb" .../>
    config = SimpleNamespace(hhcs={"Unibet": SimpleNamespace(converter="UnibetToFpdb")})

    assert re.search(getTableTitleRe(config, "Unibet", "cash", table_name="99465067"), TABLE_TITLE)
    assert re.search(getTableTitleRe(config, "Unibet", "tour", tournament=99007080, table_number=99503253), TOUR_TITLE)
    assert getTableNoRe(config, "Unibet", tournament=99007080) is not None
    assert re.search(getTableNoRe(config, "Unibet", tournament=99007080), TOUR_TITLE) is None


def test_unibet_is_a_target_process_for_the_macos_applescript_fallback() -> None:
    macos = pytest.importorskip("fpdb.infrastructure.platform.macos")
    detector = object.__new__(macos.MacOSTableDetector)

    assert detector._is_target_process("UnibetPoker")
    assert detector._is_target_process("Unibet Poker")
    assert not detector._is_target_process("SomeOtherApp")
