"""Tests for PokerStars tournament table window title matching."""

import re

from fpdb_3_legacy.HandHistoryConverter import HandHistoryConverter
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

TITLE_EN = "WCOOP 2nd Chance 02: $1,050 NLHE - Tournament 307521826 Table 1 - Blinds $30/$60"
TITLE_IT = (
    " [ID ADM: M00AA00000A00AAA][ID di partecipazione: N00AA0000AAAAAAA]€0.50 NL Hold'em "
    "[6 Giocatori - Turbo] - 10/20 - Torneo 4039582670 Tavolo 1 - Accesso effettuato player1"
)


def test_title_re_matches_english_table() -> None:
    regex = PokerStars.getTableTitleRe("tour", tournament="307521826", table_number="1")
    assert re.search(regex, TITLE_EN)


def test_title_re_matches_italian_table() -> None:
    regex = PokerStars.getTableTitleRe("tour", tournament="4039582670", table_number="1")
    assert re.search(regex, TITLE_IT)


def test_title_re_does_not_match_other_table() -> None:
    regex = PokerStars.getTableTitleRe("tour", tournament="4039582670", table_number="2")
    assert not re.search(regex, TITLE_IT)


def test_table_no_re_english() -> None:
    match = re.search(HandHistoryConverter.getTableNoRe("307521826"), TITLE_EN)
    assert match
    assert match.group(1) == "1"


def test_table_no_re_italian() -> None:
    match = re.search(HandHistoryConverter.getTableNoRe("4039582670"), TITLE_IT)
    assert match
    assert match.group(1) == "1"
