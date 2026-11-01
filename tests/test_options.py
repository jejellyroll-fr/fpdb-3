"""Tests for command-line option helpers."""

from fpdb_3_legacy.Options import site_alias


def test_site_alias_resolves_known_room_alias() -> None:
    assert site_alias("Stars") == "PokerStars"


def test_site_alias_rejects_unknown_room_alias() -> None:
    assert site_alias("UnknownRoom") is False
