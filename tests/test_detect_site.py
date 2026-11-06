"""Unit tests for the legacy site-detection utility.

``detect_site`` maps the first line of a hand to the parser class and site
name it was built for. The detector table is static, so the tests exercise
the match logic against representative first lines.
"""

from __future__ import annotations

from fpdb_3_legacy.detect_site import SITE_DETECTORS, detect_site
from fpdb_3_legacy.GGPokerToFpdb import GGPoker
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs


def test_detector_table_is_ordered_and_static() -> None:
    patterns = [pattern for pattern, _, _ in SITE_DETECTORS]
    assert patterns == [r"SwCPoker Hand #", r"PokerStars Game #", r"Poker Hand #"]


def test_detects_seals_with_clubs() -> None:
    hand = "SwCPoker Hand #1-12345-6789: Table X"
    parser_cls, site = detect_site(hand)
    assert parser_cls is SealsWithClubs
    assert site == "SealsWithClubs"


def test_detects_pokerstars() -> None:
    hand = "PokerStars Game #2780605304:  Hold'em No Limit ($0.01/$0.02)"
    parser_cls, site = detect_site(hand)
    assert parser_cls is PokerStars
    assert site == "PokerStars"


def test_detects_ggpoker() -> None:
    hand = "Poker Hand #DR123456789: Hold'em No Limit"
    parser_cls, site = detect_site(hand)
    assert parser_cls is GGPoker
    assert site == "GGPoker"


def test_detection_uses_only_first_line() -> None:
    # A PokerStars marker buried in a later line must not be matched.
    hand = "Poker Hand #GG9999\nPokerStars Game #1"
    parser_cls, site = detect_site(hand)
    assert parser_cls is GGPoker
    assert site == "GGPoker"


def test_detection_matches_mid_line() -> None:
    # The pattern is searched, not anchored: surrounding text is fine.
    hand = "Log: PokerStars Game #42 started"
    parser_cls, site = detect_site(hand)
    assert parser_cls is PokerStars
    assert site == "PokerStars"


def test_unknown_site_returns_none() -> None:
    assert detect_site("PartyPoker Hand-123: something else") == (None, None)


def test_empty_and_none_inputs_return_none() -> None:
    assert detect_site("") == (None, None)
    assert detect_site(None) == (None, None)
    assert detect_site("")[0] is None
