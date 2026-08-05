"""Registering an AoF variant must be one edit, not a hunt through modules.

Six modules used to carry their own ``{"aof_omaha", "aof_holdem"}`` literal, so
a third variant meant finding and changing every one of them -- and any that
was missed would parse the hand as a normal preflop game. These tests pin the
registry as the single answer, by adding a variant at runtime and checking the
consumers follow.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fpdb_3_legacy import DerivedStats
from fpdb_3_legacy.autonotes_aof import AOF_CATEGORIES, AofRuleset, is_aof_category, ruleset_for

VARIANT = "aof_shortdeck"


@pytest.fixture
def registered_variant(monkeypatch):
    """A new AoF game, registered the only way a new game should need to be."""
    import fpdb_3_legacy.autonotes_aof as module

    ruleset = AofRuleset(category=VARIANT, hole_cards=2, game_name="holdem", evaluator_game="holdem")
    monkeypatch.setitem(module._RULESETS, VARIANT, ruleset)
    return ruleset


def test_the_registry_answers_for_every_known_category() -> None:
    assert AOF_CATEGORIES == {"aof_omaha", "aof_holdem"}
    for category in AOF_CATEGORIES:
        assert ruleset_for(category) is not None
        assert is_aof_category(category)


def test_a_normal_game_is_not_all_in_or_fold() -> None:
    assert not is_aof_category("omahahi")
    assert not is_aof_category("holdem")
    assert not is_aof_category("")
    assert not is_aof_category(None)


def test_the_category_is_matched_regardless_of_case_or_padding() -> None:
    """Categories reach us from XML attributes and DB rows, not just literals."""
    assert is_aof_category("AoF_Omaha")
    assert is_aof_category("  aof_omaha ")


def test_a_newly_registered_variant_is_recognized_without_touching_callers(registered_variant) -> None:
    assert is_aof_category(VARIANT)

    hand = SimpleNamespace(gametype={"category": VARIANT})
    assert DerivedStats._is_all_in_or_fold(hand), "the stats path must follow the registry"


def test_a_parser_routes_a_new_variant_through_the_aof_street_model(registered_variant, monkeypatch) -> None:
    """AoF has no preflop round, so its parsers must take the AoF branch."""
    from fpdb_3_legacy.GGPokerToFpdb import GGPoker

    taken = []
    monkeypatch.setattr(GGPoker, "_mark_aof_streets", staticmethod(taken.append))
    parser = GGPoker.__new__(GGPoker)
    hand = SimpleNamespace(gametype={"category": VARIANT, "base": "hold"}, handText="")

    parser.markStreets(hand)

    assert taken == [hand], "an unregistered variant would be parsed as a preflop game"
