"""Focused regressions for Entraction parser debt removal."""

import pytest

from fpdb_3_legacy.EntractionToFpdb import Entraction


@pytest.mark.parametrize(
    ("buyin", "header_currency", "expected"),
    [
        ("10+1", "EUR", "EUR"),
        ("100.5+10.5", "Fun", "play"),
        ("$10+$1", None, "USD"),
        ("£10+£1", None, "GBP"),
        ("10.50+1.50", None, "play"),
    ],
)
def test_entraction_tournament_currency_uses_header_symbol_or_play_money(buyin, header_currency, expected) -> None:
    info = {"BUYIN": buyin, "CURRENCY": header_currency}

    assert Entraction.tournamentCurrency(info) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("akilim                      Fold", ("akilim", "Fold", None)),
        ("Hero                        Check", ("Hero", "Check", None)),
        ("Makesdy                     Raise       (0.14)", ("Makesdy", "Raise", "0.14")),
        ("kos081                      Call        (0.14)", ("kos081", "Call", "0.14")),
        ("Vokha                       All-In      (0.42)", ("Vokha", "All-In", "0.42")),
    ],
)
def test_entraction_actions_without_an_amount_are_read(line, expected) -> None:
    """A fold or a check ends the line right after the verb.

    The pattern required whitespace between the verb and the (optional) amount,
    so folds and checks matched nothing: they were dropped from every hand, and
    a hand where everyone folded was stored with no betting action at all.
    """
    match = Entraction.re_Action.search(line)

    assert match is not None
    assert (match.group("PNAME"), match.group("ATYPE"), match.group("BET")) == expected
