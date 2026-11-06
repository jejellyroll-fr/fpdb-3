"""The user-facing vocabulary of the research browser (issue #329).

The engine keeps its own names; this module is what the browser shows instead.
The tests below are the issue's acceptance criteria, stated as facts:

* every engine filter is described in poker language, and the description is
  *not* the engine's column name;
* the closed domains a selector offers come from the modules that define those
  vocabularies, so a choice cannot name a value the classifier never writes;
* the active question is restated in plain language, including ranges, boolean
  phrasing and the breakdown -- and an unknown filter is named rather than
  silently dropped from the sentence that claims to describe the query.

No Qt, no database: this layer is presentation, and it is tested as such.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import player_situations as situations
from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy import research_labels as labels
from fpdb_3_legacy.analytics_query import DIMENSIONS, FILTERS, KNOWN_METRICS, POSITION_CODES
from fpdb_3_legacy.board_features import CONNECTIVITIES, PAIRINGS, RANK_BUCKETS, SUIT_STRUCTURES
from fpdb_3_legacy.hand_state import DRAW_CATEGORIES, MADE_HANDS, NUTNESS_LEVELS, PAIR_DETAILS
from fpdb_3_legacy.hud_situation import POT_TYPES, STREETS
from fpdb_3_legacy.sizing_buckets import DEFAULT_BUCKETS

# ---------------------------------------------------------------------------
# Every filter is described, in its own words.
# ---------------------------------------------------------------------------


def test_every_filter_has_a_user_facing_label() -> None:
    missing = [spec.name for spec in rb.FILTER_SPECS if not spec.label]
    assert missing == []


def test_every_filter_has_a_user_facing_description() -> None:
    missing = [spec.name for spec in rb.FILTER_SPECS if not spec.user_description]
    assert missing == []


def test_the_user_description_is_not_the_engine_column() -> None:
    """The issue's rule: the SQL column is not the primary user-facing text."""
    same = [spec.name for spec in rb.FILTER_SPECS if spec.user_description == spec.description]
    assert same == []


def test_internal_names_are_kept_for_the_expert_view() -> None:
    """Simplifying the default surface must not delete the engine vocabulary."""
    hero = rb.filter_spec("hero")
    assert hero.name == "hero" and hero.description


def test_expert_only_filters_are_a_subset_and_still_exist() -> None:
    assert labels.EXPERT_ONLY_FILTERS <= set(FILTERS)
    # Nothing is removed from the engine by hiding it from Beginner mode.
    hidden = [spec for spec in rb.FILTER_SPECS if spec.expert_only]
    assert hidden and all(spec.name in FILTERS for spec in hidden)


def test_every_dimension_has_a_label() -> None:
    missing = [spec.name for spec in rb.DIMENSION_SPECS if not spec.label or spec.label == spec.name]
    assert missing == []


def test_dimension_specs_cover_the_engine_dimensions() -> None:
    assert {spec.name for spec in rb.DIMENSION_SPECS} == set(DIMENSIONS)


def test_unknown_dimension_spec_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="nope"):
        rb.dimension_spec("nope")


def test_beginner_dimensions_are_real_dimensions() -> None:
    assert set(labels.BEGINNER_DIMENSIONS) <= set(DIMENSIONS)
    beginner = {spec.name for spec in rb.DIMENSION_SPECS if spec.beginner}
    assert beginner == set(labels.BEGINNER_DIMENSIONS)


def test_every_metric_has_a_label() -> None:
    missing = [name for name in KNOWN_METRICS if labels.metric_label(name) == name]
    assert missing == []


def test_filter_groups_are_labelled() -> None:
    for group in (spec.group for spec in rb.FILTER_SPECS):
        assert group in labels.FILTER_GROUP_LABELS


# ---------------------------------------------------------------------------
# The closed domains a selector offers exist, and come from the classifiers.
# ---------------------------------------------------------------------------


def test_position_choices_are_the_seats_the_engine_accepts() -> None:
    values = [choice.value for choice in labels.filter_choices("position")]
    # Table order, early seat to the blinds: the order a player reads a list of
    # positions in, not the alias table's insertion order.
    assert values == ["utg", "mp2", "mp", "lj", "hj", "co", "btn", "sb", "bb"]
    assert all(value in POSITION_CODES for value in values)


def test_street_choices_are_the_street_vocabulary() -> None:
    assert [c.value for c in labels.filter_choices("street")] == list(STREETS)


def test_pot_type_choices_are_the_situation_model_pot_types() -> None:
    assert [c.value for c in labels.filter_choices("pot_type")] == list(POT_TYPES)


def test_situation_choices_are_rule_names_labelled_by_the_rule_table() -> None:
    choices = {choice.value: choice.label for choice in labels.filter_choices("primary_situation")}
    rules = {rule.name: rule.label for rule in situations.SITUATION_RULES}
    assert choices == rules


def test_board_choices_are_the_persisted_board_vocabulary() -> None:
    assert [c.value for c in labels.filter_choices("board_suit")] == list(SUIT_STRUCTURES)
    assert [c.value for c in labels.filter_choices("board_pairing")] == list(PAIRINGS)
    assert [c.value for c in labels.filter_choices("board_rank")] == list(RANK_BUCKETS)
    assert [c.value for c in labels.filter_choices("board_connectivity")] == list(CONNECTIVITIES)


def test_hand_strength_choices_are_the_classifier_vocabulary() -> None:
    assert [c.value for c in labels.filter_choices("made_hand")] == list(MADE_HANDS)
    assert [c.value for c in labels.filter_choices("pair_detail")] == list(PAIR_DETAILS)
    assert [c.value for c in labels.filter_choices("draw")] == list(DRAW_CATEGORIES)
    assert [c.value for c in labels.filter_choices("nutness")] == list(NUTNESS_LEVELS)


def test_sizing_bucket_choices_come_from_the_sizing_module() -> None:
    assert [c.value for c in labels.filter_choices("facing_sizing_bucket")] == list(DEFAULT_BUCKETS.labels)


def test_choices_carry_a_label_distinct_from_the_token() -> None:
    """A selector shows poker words; the query still stores the engine token."""
    facing = next(c for c in labels.filter_choices("primary_situation") if c.value == "facing_cbet")
    assert facing.label == "facing a continuation bet"


def test_open_ended_filters_have_no_choices() -> None:
    """Free text is reserved for domains that really are open (player names)."""
    assert labels.filter_choices("player") == ()
    assert labels.filter_choices("site") == ()


# ---------------------------------------------------------------------------
# The active question, in plain language.
# ---------------------------------------------------------------------------


def test_scenario_a_reads_as_a_poker_question() -> None:
    """#337 Scenario A: fold versus a flop c-bet, broken down by bet size."""
    summary = rb.describe_preset(
        {
            "metric": "fold_frequency",
            "filters": {
                "game": "holdem",
                "max_seats": 6,
                "primary_situation": "facing_cbet",
                "street": "flop",
            },
            "group_by": ("facing_sizing_bucket",),
        },
    )
    assert "Hold'em" in summary
    assert "6-max" in summary
    assert "facing a continuation bet" in summary
    assert "on the flop" in summary
    assert "fold frequency" in summary
    assert "broken down by bet size faced" in summary
    # The engine vocabulary appears nowhere: that is the whole point.
    for token in ("primary_situation", "facing_cbet", "facing_sizing_bucket", "group_by"):
        assert token not in summary


def test_hero_state_is_the_population_not_a_clause() -> None:
    hero = rb.describe_preset({"metric": "frequency", "filters": {"hero": True}})
    opponent = rb.describe_preset({"metric": "frequency", "filters": {"hero": False}})
    everyone = rb.describe_preset({"metric": "frequency", "filters": {}})
    assert hero.startswith("Hero's decisions")
    assert opponent.startswith("All players except hero")
    assert everyone.startswith("All decisions")


def test_ranges_read_as_bounds_with_their_unit() -> None:
    summary = rb.describe_preset(
        {"metric": "frequency", "filters": {"effective_stack_bb": [80, 120]}},
    )
    assert "80-120 BB effective" in summary


def test_open_ended_ranges_read_as_upper_or_lower_bounds_only() -> None:
    below = rb.describe_preset({"metric": "frequency", "filters": {"effective_stack_bb": [None, 40]}})
    above = rb.describe_preset({"metric": "frequency", "filters": {"effective_stack_bb": [200, None]}})
    assert "up to 40 BB" in below
    assert "200 BB or more" in above


def test_boolean_filters_read_as_phrases() -> None:
    summary = rb.describe_preset(
        {"metric": "frequency", "filters": {"in_position": True, "multiway": False}},
    )
    assert "in position" in summary
    assert "heads-up pots" in summary


def test_a_filter_with_no_value_says_nothing() -> None:
    """An untouched control must not appear in the sentence either."""
    summary = rb.describe_preset(
        {"metric": "frequency", "filters": {"hero": None, "position": [], "primary_situation": None}},
    )
    assert summary == "All decisions. Measure how often the decision is taken (matching decisions ÷ opportunities)."


def test_an_unknown_filter_is_named_not_dropped() -> None:
    summary = rb.describe_preset({"metric": "frequency", "filters": {"not_a_filter": 1}})
    assert "not_a_filter" in summary


def test_a_missing_metric_describes_nothing() -> None:
    assert rb.describe_preset({}) == ""


def test_frequency_metrics_state_their_denominator() -> None:
    summary = rb.describe_preset({"metric": "fold_frequency"})
    assert "÷ opportunities" in summary


def test_a_per_hand_rate_says_its_denominator_is_hands() -> None:
    """VPIP counted in decisions is a different number from VPIP counted in
    hands, so the sentence has to say which one the question measured."""
    summary = rb.describe_preset({"metric": "hand_frequency"})
    assert "hands where it happened ÷ hands with the chance" in summary
    assert "per-hand frequency" in summary


def test_ev_metrics_are_labelled_apart_from_realized_profit() -> None:
    realized = rb.describe_preset({"metric": "total_profit"})
    adjusted = rb.describe_preset({"metric": "all_in_ev"})
    assert "realized profit" in realized
    assert "EV-adjusted" in adjusted and "realized profit" in adjusted


def test_breakdown_lists_every_dimension() -> None:
    summary = rb.describe_preset({"metric": "frequency", "group_by": ("position", "street")})
    assert "broken down by position and street" in summary


def test_no_breakdown_says_nothing_about_grouping() -> None:
    assert "broken down" not in rb.describe_preset({"metric": "frequency"})


def test_summary_is_stable_for_the_same_preset() -> None:
    preset = {"metric": "fold_frequency", "filters": {"hero": False}, "group_by": ("street",)}
    assert rb.describe_preset(preset) == rb.describe_preset(dict(preset))
