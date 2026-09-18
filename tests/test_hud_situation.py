"""Context-aware dynamic HUD panels (#298).

The acceptance criteria are checked in order: the live hand state becomes a
stable situation context, a resolver separate from the table/profile resolver
selects panels, the preflop open / 3-bet / squeeze and postflop c-bet contexts
work, position- and stack-sensitive rules work, the static HUD is unchanged when
dynamic panels are off, and rule precedence and context transitions are
validated.

The last section runs the whole layer against the golden corpus: the contexts
come from the canonical situations of #294, so a rule's condition is checked on
real decisions rather than on hand-built dictionaries.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy import analytics_query
from fpdb_3_legacy import hud_situation as hs
from tests.helpers import analytics_golden as golden

# --------------------------------------------------------------------------- #
# The context.
# --------------------------------------------------------------------------- #


def test_context_from_stat_dict_uses_the_live_position() -> None:
    entry = {"player_id": 7, "screen_name": "Anna", "position": "1", "live_position": "0", "n": 120}
    context = hs.HudSituationContext.from_stat_dict(entry, {"street": "flop", "pot_type": "single_raised"})
    assert context.position == "BTN"
    assert context.street == "flop"
    assert context.pot_type == "single_raised"


def test_context_from_stat_dict_prefers_live_over_imported_position() -> None:
    """The imported position is last hand's; the panel must follow this hand's."""
    entry = {"position": "B", "live_position": "S"}
    assert hs.HudSituationContext.from_stat_dict(entry).position == "SB"
    assert hs.HudSituationContext.from_stat_dict({"position": "B"}).position == "BB"


def test_context_key_is_stable_across_equivalent_spellings() -> None:
    left = hs.HudSituationContext(street="Flop", position="bu", pot_type="SINGLE_RAISED")
    right = hs.HudSituationContext(street="flop", position="BTN", pot_type="single_raised")
    assert left.key() == right.key()
    assert left == right.normalized() or left.normalized() == right.normalized()


def test_context_key_moves_when_the_decision_moves() -> None:
    base = hs.HudSituationContext(street="flop", pot_type="single_raised", in_position=True)
    other = hs.HudSituationContext(street="turn", pot_type="single_raised", in_position=True)
    assert base.key() != other.key()


def test_unknown_live_state_is_absent_not_a_value() -> None:
    """A rule asking for a small bet must not match a sizing nobody saw."""
    context = hs.HudSituationContext(street="river").normalized()
    assert "facing_sizing_pct" not in context.filters()
    assert "role" not in context.filters()
    assert "stack_bucket" not in context.filters()


def test_left_alone_values_are_kept_including_false_and_zero() -> None:
    context = hs.HudSituationContext(street="flop", in_position=False, to_call=0)
    values = context.filters()
    assert values["in_position"] is False
    assert values["to_call"] == 0


def test_stack_bucket_falls_back_to_the_big_blind_bands() -> None:
    assert hs.HudSituationContext(effective_stack_bb=15).normalized().stack_bucket == "short"
    assert hs.HudSituationContext(effective_stack_bb=40).normalized().stack_bucket == "medium"
    assert hs.HudSituationContext(effective_stack_bb=120).normalized().stack_bucket == "deep"


# --------------------------------------------------------------------------- #
# The filter vocabulary is the query engine's.
# --------------------------------------------------------------------------- #


def test_every_panel_condition_exists_in_the_query_engine() -> None:
    """One vocabulary: a name that selects a panel selects a query."""
    resolver = hs.load_default_resolver()
    known = set(analytics_query.FILTERS)
    for rule in resolver.rules:
        assert set(rule.when) <= known, rule.panel


def test_an_unknown_condition_is_refused_with_the_list() -> None:
    with pytest.raises(ValueError) as caught:
        hs.PanelRule.from_mapping({"panel": "x", "when": {"nonexistent": 1}})
    assert "nonexistent" in str(caught.value)
    assert "street" in str(caught.value)


def test_unknown_rule_fields_are_refused() -> None:
    with pytest.raises(ValueError) as caught:
        hs.PanelRule.from_mapping({"panel": "x", "wenn": {"street": "flop"}})
    assert "wenn" in str(caught.value)


def test_a_rule_needs_a_panel_name() -> None:
    with pytest.raises(ValueError):
        hs.PanelRule.from_mapping({"when": {"street": "flop"}})


# --------------------------------------------------------------------------- #
# Condition semantics.
# --------------------------------------------------------------------------- #


def test_set_condition_matches_equality_and_membership() -> None:
    flop = hs.HudSituationContext(street="flop")
    turn = hs.HudSituationContext(street="turn")
    assert hs.condition_matches("street", "flop", flop)
    assert not hs.condition_matches("street", "flop", turn)
    assert hs.condition_matches("street", ["turn", "river"], turn)
    assert not hs.condition_matches("street", ["turn", "river"], flop)


def test_range_condition_is_inclusive_with_optional_ends() -> None:
    context = hs.HudSituationContext(effective_stack_bb=100)
    assert hs.condition_matches("effective_stack_bb", [100, 200], context)
    assert hs.condition_matches("effective_stack_bb", [50, 100], context)
    assert not hs.condition_matches("effective_stack_bb", [101, 200], context)
    assert hs.condition_matches("effective_stack_bb", [101, None], context) is False
    assert hs.condition_matches("effective_stack_bb", [None, 200], context)


def test_percentage_conditions_compare_against_basis_points() -> None:
    """``facing_sizing_pct`` is written in per cent and measured in bp."""
    context = hs.HudSituationContext(facing_sizing_bp=2500)
    assert hs.condition_matches("facing_sizing_pct", [20, 30], context)
    assert not hs.condition_matches("facing_sizing_pct", [26, None], context)
    assert hs.condition_matches("facing_sizing_pct", [None, 30], context)


def test_boolean_condition_matches_false() -> None:
    out = hs.HudSituationContext(in_position=False)
    assert hs.condition_matches("in_position", False, out)
    assert not hs.condition_matches("in_position", True, out)
    unknown = hs.HudSituationContext()
    assert not hs.condition_matches("in_position", False, unknown), "unknown is not false"


def test_label_condition_matches_a_situation_word() -> None:
    context = hs.HudSituationContext(labels=("squeeze", "multiway"))
    assert hs.condition_matches("situation", "squeeze", context)
    assert hs.condition_matches("situation", ["no_such_label", "squeeze"], context)
    assert not hs.condition_matches("situation", "probe", context)


def test_street_index_zero_still_reads_as_preflop() -> None:
    preflop = hs.HudSituationContext(street="preflop", street_index=0)
    assert hs.condition_matches("street_index", [0, 0], preflop)


# --------------------------------------------------------------------------- #
# Rules from data.
# --------------------------------------------------------------------------- #


def test_attributes_round_trip_through_xml_shape() -> None:
    rule = hs.panel_rule_from_attributes(
        {
            "panel": "srp_cbet_ip",
            "id": "srp-cbet-ip",
            "street": "flop",
            "pot_type": "single_raised",
            "in_position": "true",
            "to_call": "[null, 0]",
            "min_sample": "50",
            "priority": "30",
            "substitutions": '{"BB": "srp_bb_flop"}',
        },
        0,
    )
    reloaded = hs.panel_rule_from_attributes(rule.as_xml_attributes(), 0)
    assert reloaded == rule


def test_json_values_survive_the_attribute_encoding() -> None:
    rule = hs.panel_rule_from_attributes({"panel": "x", "street": '["turn", "river"]', "in_position": "false"}, 0)
    assert rule.when == {"street": ["turn", "river"], "in_position": False}
    assert hs.panel_rule_from_attributes(rule.as_xml_attributes(), 0).when == rule.when


def test_a_when_attribute_is_accepted_as_json() -> None:
    rule = hs.panel_rule_from_attributes({"panel": "x", "when": '{"street": "river"}'}, 0)
    assert rule.when == {"street": "river"}


def test_saving_rules_round_trips_through_a_load(tmp_path: Path) -> None:
    resolver = hs.load_default_resolver()
    target = tmp_path / "panels.json"
    hs.save_rules(resolver.rules, target, fallback=resolver.fallback)
    loaded, fallback = hs.load_rules(target)
    assert fallback == resolver.fallback
    assert [rule.panel for rule in loaded] == [rule.panel for rule in resolver.rules]
    assert [rule.when for rule in loaded] == [rule.when for rule in resolver.rules]


def test_a_newer_schema_is_refused() -> None:
    with pytest.raises(ValueError, match="newer"):
        hs.parse_rules({"schema_version": hs.PANEL_SCHEMA_VERSION + 1, "rules": []})


def test_a_non_object_document_is_refused() -> None:
    with pytest.raises(ValueError):
        hs.parse_rules(["not", "a", "document"])


def test_the_shipped_library_loads_and_is_warning_free() -> None:
    resolver = hs.load_default_resolver()
    assert len(resolver.rules) == 19
    assert resolver.fallback == "core"
    assert resolver.duplicate_selectors() == []
    assert hs.validate_rules(resolver) == ()


def test_shipped_rule_ids_are_unique() -> None:
    resolver = hs.load_default_resolver()
    ids = [rule.rule_id for rule in resolver.rules]
    assert len(ids) == len(set(ids))
    assert all(ids)


# --------------------------------------------------------------------------- #
# Precedence.
# --------------------------------------------------------------------------- #


def test_specificity_beats_priority() -> None:
    broad = hs.PanelRule.from_mapping({"panel": "broad", "priority": 99, "when": {"street": "flop"}})
    narrow = hs.PanelRule.from_mapping(
        {"panel": "narrow", "priority": 1, "when": {"street": "flop", "in_position": True}}
    )
    resolver = hs.HudSituationResolver([broad, narrow])
    assert resolver.resolving_rule(hs.HudSituationContext(street="flop", in_position=True)).panel == "narrow"


def test_priority_breaks_a_specificity_tie() -> None:
    low = hs.PanelRule.from_mapping({"panel": "low", "priority": 1, "when": {"street": "flop"}})
    high = hs.PanelRule.from_mapping({"panel": "high", "priority": 5, "when": {"street": "flop"}})
    resolver = hs.HudSituationResolver([low, high])
    assert resolver.resolving_rule(hs.HudSituationContext(street="flop")).panel == "high"


def test_file_order_breaks_a_full_tie() -> None:
    first = hs.PanelRule.from_mapping({"panel": "first", "when": {"street": "flop"}}, 0)
    second = hs.PanelRule.from_mapping({"panel": "second", "when": {"street": "flop"}}, 1)
    resolver = hs.HudSituationResolver([first, second])
    assert resolver.resolving_rule(hs.HudSituationContext(street="flop")).panel == "first"


def test_the_resolver_reports_every_rule_that_decided_a_panel() -> None:
    resolver = hs.HudSituationResolver(
        [
            hs.PanelRule.from_mapping({"panel": "a", "id": "rule-a", "when": {"street": "flop"}}),
            hs.PanelRule.from_mapping({"panel": "b", "id": "rule-b", "when": {"in_position": True}}),
        ]
    )
    selection = resolver.resolve(hs.HudSituationContext(street="flop", in_position=True))
    assert set(selection.panels) == {"a", "b"}
    assert selection.decided_by("a").rule_id == "rule-a"
    assert selection.decided_by("b").rule_id == "rule-b"
    assert selection.decided_by("c") is None


def test_a_disabled_rule_never_matches() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "x", "when": {}, "enabled": False})
    assert not rule.matches(hs.HudSituationContext())


def test_a_duplicate_selector_is_reported() -> None:
    rule = {"panel": "x", "when": {"street": "flop"}}
    resolver = hs.HudSituationResolver([hs.PanelRule.from_mapping(rule, 0), hs.PanelRule.from_mapping(rule, 1)])
    assert len(resolver.duplicate_selectors()) == 1


# --------------------------------------------------------------------------- #
# Fallback, samples, substitutions and profiles.
# --------------------------------------------------------------------------- #


def test_the_fallback_panel_shows_when_nothing_matches() -> None:
    """A profile that has rules keeps the core row up when none of them fits."""
    rule = hs.PanelRule.from_mapping({"panel": "river_threebet", "when": {"street": "river", "pot_type": "three_bet"}})
    resolver = hs.HudSituationResolver([rule], fallback="core")
    selection = resolver.resolve(hs.HudSituationContext(street="river", pot_type="single_raised"))
    assert selection.panels == ("core",)
    assert selection.fallback == "core"


def test_an_empty_resolver_is_the_static_hud() -> None:
    """No rule at all is not "no rule matched": there is nothing to fall back from."""
    selection = hs.HudSituationResolver([], fallback="core").resolve(hs.HudSituationContext())
    assert selection.enabled is False
    assert selection.panels == ()
    assert selection.fallback == ""


def test_no_fallback_and_no_match_leaves_no_panels() -> None:
    resolver = hs.HudSituationResolver([hs.PanelRule.from_mapping({"panel": "x", "when": {"street": "flop"}})])
    selection = resolver.resolve(hs.HudSituationContext(street="river"))
    assert selection.panels == ()
    assert selection.enabled


def test_min_sample_withholds_a_panel_and_says_why() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "deep", "min_sample": 200, "when": {"street": "preflop"}})
    resolver = hs.HudSituationResolver([rule])
    context = hs.HudSituationContext(street="preflop")
    assert resolver.resolve(context, samples={"n": 500}).panels == ("deep",)
    thin = resolver.resolve(context, samples={"n": 50})
    assert thin.panels == ()
    assert thin.suppressed == ("deep",)


def test_a_rule_without_a_sample_to_read_is_withheld() -> None:
    """No sample to consult is not a sample of zero."""
    rule = hs.PanelRule.from_mapping({"panel": "deep", "min_sample": 200, "sample": "chances", "when": {}})
    resolver = hs.HudSituationResolver([rule])
    assert resolver.resolve(hs.HudSituationContext()).suppressed == ("deep",)
    assert resolver.resolve(hs.HudSituationContext(), samples={"chances": 300}).panels == ("deep",)


def test_a_suppressed_rule_falls_back_to_its_named_panel() -> None:
    rule = hs.PanelRule.from_mapping(
        {
            "panel": "deep",
            "min_sample": 200,
            "fallback": "preflop_open",
            "when": {"street": "preflop"},
        }
    )
    resolver = hs.HudSituationResolver([rule])
    selection = resolver.resolve(hs.HudSituationContext(street="preflop"), samples={"n": 10})
    assert selection.panels == ("preflop_open",)
    assert selection.suppressed == ("deep",)
    assert selection.decided_by("preflop_open").rule_id == rule.rule_id


def test_position_substitution_renames_the_panel() -> None:
    rule = hs.PanelRule.from_mapping(
        {"panel": "srp_flop", "substitutions": {"BB": "srp_bb_flop"}, "when": {"street": "flop"}}
    )
    blind = hs.HudSituationContext(street="flop", position="B")
    button = hs.HudSituationContext(street="flop", position="0")
    assert rule.panel_for(blind) == "srp_bb_flop"
    assert rule.panel_for(button) == "srp_flop"


def test_rules_are_scoped_to_a_profile() -> None:
    aof = hs.PanelRule.from_mapping({"panel": "aof_only", "profile": "aof_default", "when": {"street": "preflop"}})
    generic = hs.PanelRule.from_mapping({"panel": "generic", "when": {"street": "preflop"}})
    resolver = hs.HudSituationResolver([aof, generic])
    context = hs.HudSituationContext(street="preflop")
    assert set(resolver.resolve(context, "holdring_modern").panels) == {"generic"}
    assert set(resolver.resolve(context, "aof_default").panels) == {"aof_only", "generic"}


def test_a_profile_without_rules_disables_dynamic_panels() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "x", "profile": "aof_default", "when": {}})
    resolver = hs.HudSituationResolver([rule])
    assert resolver.is_enabled("aof_default")
    assert not resolver.is_enabled("holdring_modern")
    selection = resolver.resolve(hs.HudSituationContext(), "holdring_modern")
    assert selection.enabled is False
    assert selection.panels == ()


def test_switching_the_resolver_off_is_the_static_hud() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "x", "when": {}})
    off = hs.HudSituationResolver([rule], enabled=False)
    selection = off.resolve(hs.HudSituationContext())
    assert selection.enabled is False
    assert selection.panels == ()
    assert selection.describe() == "dynamic panels disabled"


# --------------------------------------------------------------------------- #
# Context transitions and rendering.
# --------------------------------------------------------------------------- #


def test_a_seat_keeps_its_selection_until_the_context_moves() -> None:
    resolver = hs.load_default_resolver()
    state = hs.PanelState(resolver)
    preflop = hs.HudSituationContext(street="preflop", pot_type="unopened")
    _, change = state.update("seat-3", preflop)
    assert "preflop_open" in change.added
    _, again = state.update("seat-3", preflop)
    assert again.dirty is False
    assert state.active_panels("seat-3")


def test_a_street_change_reports_only_the_panels_that_moved() -> None:
    resolver = hs.load_default_resolver()
    state = hs.PanelState(resolver)
    state.update("seat-3", hs.HudSituationContext(street="preflop", pot_type="unopened"))
    _, change = state.update(
        "seat-3",
        hs.HudSituationContext(street="flop", pot_type="single_raised", is_preflop_aggressor=True, in_position=True),
    )
    assert change.added == ("srp_cbet_ip",)
    assert change.removed == ("preflop_open",)
    assert change.unchanged == ("core",)
    assert change.changed == ("srp_cbet_ip", "preflop_open")
    assert change.describe() == "+srp_cbet_ip -preflop_open"


def test_a_context_that_resolves_the_same_way_is_not_a_change() -> None:
    """A sizing move inside one panel band must not redraw anything."""
    resolver = hs.HudSituationResolver(
        [
            hs.PanelRule.from_mapping(
                {"panel": "small", "when": {"facing_sizing_pct": [None, 30]}}
            ),
            hs.PanelRule.from_mapping(
                {"panel": "big", "when": {"facing_sizing_pct": [31, None]}}
            ),
        ]
    )
    state = hs.PanelState(resolver)
    state.update("seat-3", hs.HudSituationContext(facing_sizing_bp=2000))
    selection, change = state.update("seat-3", hs.HudSituationContext(facing_sizing_bp=2500))
    assert selection.panels == ("small",)
    assert change.dirty is False


def test_forgetting_a_seat_replays_the_first_selection() -> None:
    resolver = hs.load_default_resolver()
    state = hs.PanelState(resolver)
    context = hs.HudSituationContext(street="preflop", pot_type="unopened")
    state.update("seat-3", context)
    state.forget("seat-3")
    assert state.active_panels("seat-3") == ()
    _, change = state.update("seat-3", context)
    assert "preflop_open" in change.added


def test_blocks_are_matched_by_label_id_or_position() -> None:
    assert hs.panel_matches_block("srp_cbet_ip", {"label": "SRP c-bet IP"}) is False
    assert hs.panel_matches_block("core", {"label": "Core"})
    assert hs.panel_matches_block("core", {"id": "CORE"})
    assert hs.panel_matches_block("btn", {"position": "BTN"})
    assert not hs.panel_matches_block("", {"label": "Core"})


def test_a_named_block_shows_and_an_unnamed_one_keeps_the_position_rule() -> None:
    resolver = hs.HudSituationResolver(
        [hs.PanelRule.from_mapping({"panel": "srp_cbet_ip", "when": {"street": "flop"}})],
        fallback="core",
    )
    selection = resolver.resolve(hs.HudSituationContext(street="flop"))
    # Named by the selection: shown even though its position binding does not
    # match, because the rule already describes the spot.
    assert hs.block_visible_for({"id": "srp_cbet_ip", "position": "BTN"}, selection, "SB")
    # Not named: the position rule decides, exactly as before.
    assert not hs.block_visible_for({"id": "other", "position": "BTN"}, selection, "SB")
    assert hs.block_visible_for({"id": "other", "position": "BTN"}, selection, "BTN")


def test_without_a_selection_the_position_rule_is_untouched() -> None:
    assert hs.block_visible_for({"position": "BTN"}, None, "BTN")
    assert not hs.block_visible_for({"position": "BTN"}, None, "SB")
    assert hs.block_visible_for({}, None, "SB")


def test_normalize_position_is_the_single_implementation() -> None:
    from fpdb_3_legacy import Aux_Hud

    for raw in ("0", "B", "S", "1", "4", "BTN", "", None, "zz"):
        assert Aux_Hud.normalize_position(raw) == hs.normalize_position(raw)


# --------------------------------------------------------------------------- #
# The shipped library, context by context.
# --------------------------------------------------------------------------- #


def test_preflop_open_context_supports_the_issue_examples() -> None:
    resolver = hs.load_default_resolver()
    opening = resolver.resolve(hs.HudSituationContext(street="preflop", pot_type="unopened", position="CO"))
    assert "preflop_open" in opening.panels
    facing = resolver.resolve(
        hs.HudSituationContext(
            street="preflop",
            pot_type="unopened",
            facing_action="raises",
            position="B",
        )
    )
    assert {"preflop_facing_open", "blinds_defence"} <= set(facing.panels)
    squeezed = resolver.resolve(
        hs.HudSituationContext(street="preflop", pot_type="single_raised", labels=("squeeze_defence",), to_call=600)
    )
    assert "preflop_squeeze" in squeezed.panels


def test_facing_a_three_bet_shows_the_defence_panel() -> None:
    resolver = hs.load_default_resolver()
    selection = resolver.resolve(
        hs.HudSituationContext(street="preflop", pot_type="single_raised", facing_action="raises", to_call=900)
    )
    assert "preflop_facing_three_bet" in selection.panels


def test_postflop_srp_panels_split_on_position() -> None:
    resolver = hs.load_default_resolver()
    in_position = resolver.resolve(
        hs.HudSituationContext(
            street="flop", pot_type="single_raised", is_preflop_aggressor=True, in_position=True
        )
    )
    out_of_position = resolver.resolve(
        hs.HudSituationContext(
            street="flop", pot_type="single_raised", is_preflop_aggressor=True, in_position=False
        )
    )
    assert "srp_cbet_ip" in in_position.panels
    assert "srp_cbet_oop" not in in_position.panels
    assert "srp_cbet_oop" in out_of_position.panels


def test_effective_stack_rules_are_honoured() -> None:
    resolver = hs.load_default_resolver()
    short = resolver.resolve(hs.HudSituationContext(street="preflop", effective_stack_bb=15))
    assert "ssh_stack" in short.panels
    deep = resolver.resolve(hs.HudSituationContext(street="preflop", effective_stack_bb=200))
    assert "ssh_stack" not in deep.panels


def test_the_static_core_is_always_present() -> None:
    resolver = hs.load_default_resolver()
    for context in (
        hs.HudSituationContext(),
        hs.HudSituationContext(street="river", pot_type="four_bet_plus"),
        hs.HudSituationContext(street="turn", pot_type="three_bet", in_position=False),
    ):
        assert "core" in resolver.resolve(context).panels


# --------------------------------------------------------------------------- #
# Against the golden corpus.
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def corpus_hands(tmp_path_factory) -> list:
    """Every corpus hand, parsed in process (no database, no importer)."""
    config = golden.build_config(tmp_path_factory.mktemp("hud_situation"))
    return [hand for path in golden.golden_files() for hand in golden.parse_golden_file(config, path)]


@pytest.fixture(scope="module")
def corpus(corpus_hands: list) -> list:
    """Every canonical situation of the golden corpus (#294).

    The situations come from the same ``DerivedStats`` pass the importer runs,
    so a rule is checked against real decisions rather than against a
    hand-built context.
    """
    situations: list = []
    for hand in corpus_hands:
        hand.stats.getStats(hand)
        situations.extend(hand.stats.getSituations())
    return situations


def test_corpus_contexts_resolve_to_a_panel_on_every_street(corpus: list) -> None:
    resolver = hs.load_default_resolver()
    assert corpus, "the golden corpus must yield situations"
    per_street: dict[str, set[str]] = {}
    for situation in corpus:
        context = hs.HudSituationContext.from_situation(situation)
        selection = resolver.resolve(context)
        assert selection.panels, f"no panel for {context.describe()}"
        per_street.setdefault(context.street, set()).update(selection.panels)
    assert set(per_street) == {"preflop", "flop", "turn", "river"}
    assert "preflop_open" in per_street["preflop"]
    # The corpus raises from the seats that act first postflop, so the single
    # raised pot c-bet it shows is the out-of-position one -- and the panel that
    # fires is the c-bet panel, not the probe or the defence one.
    assert "srp_cbet_oop" in per_street["flop"]
    assert "srp_face_cbet_ip" in per_street["flop"]


def test_corpus_contexts_are_stable_and_sized_from_the_model(corpus: list) -> None:
    for situation in corpus[:50]:
        context = hs.HudSituationContext.from_situation(situation)
        assert context == context.normalized()
        assert context.key() == context.normalized().key()
        assert context.filters()["street"] == situation.street_name


def test_corpus_street_and_pot_type_conditions_are_the_model_ones(corpus: list) -> None:
    """The contexts really carry the model's street and pot shape."""
    streets = {hs.HudSituationContext.from_situation(s).street for s in corpus}
    pots = {hs.HudSituationContext.from_situation(s).pot_type for s in corpus}
    assert streets <= set(hs.STREETS)
    assert pots <= set(hs.POT_TYPES)


def test_the_shipped_library_stays_valid_json_data() -> None:
    path = Path(hs.default_rules_dir()) / "core.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == hs.PANEL_SCHEMA_VERSION
    assert len(document["rules"]) == 19
    for rule in document["rules"]:
        assert set(rule) <= hs._RULE_FIELDS, rule


# --------------------------------------------------------------------------- #
# What the HUD publishes, and what each seat's aggregate row answers.
# --------------------------------------------------------------------------- #


def test_live_state_from_hand_reads_the_shape_of_the_hand(corpus_hands: list) -> None:
    for hand in corpus_hands:
        state = hs.live_state_from_hand(hand)
        assert state["street"] in hs.STREETS
        assert state["pot_type"] in hs.POT_TYPES
        assert state["street_index"] == hs.STREETS.index(state["street"])
        assert state["players_in_hand"] >= 1
        assert state["multiway"] == (state["players_in_hand"] >= 3)


def test_live_state_pot_type_is_the_one_the_model_gives_the_hand(corpus_hands: list) -> None:
    """The independent reading: the shape the preflop round ended in.

    The model's own pot type is written on every decision, so the last preflop
    decision of a hand is the shape that round ended in -- the same question
    ``live_state_from_hand`` answers from the action stream alone.
    """
    for hand in corpus_hands:
        hand.stats.getStats(hand)
        preflop = [situation for situation in hand.stats.getSituations() if situation.street_name == "preflop"]
        assert preflop, f"hand {hand.handid} must have a preflop decision"
        assert hs.live_state_from_hand(hand)["pot_type"] == preflop[-1].pot_type, hand.handid


def test_live_state_counts_the_players_who_started_the_deepest_street(corpus_hands: list) -> None:
    """Folds on the street reached are not counted out of it: the seat may face them."""
    for hand in corpus_hands:
        state = hs.live_state_from_hand(hand)
        before = sum(
            1
            for index in range(state["street_index"])
            for row in hand.actions.get(hs.STREETS[index].upper(), [])
            if row[1] == "folds"
        )
        assert state["players_in_hand"] == len(hand.players) - before, hand.handid


def test_live_state_of_something_that_is_not_a_hand_is_empty() -> None:
    """Nothing known is the honest answer for a hand that has not been read."""
    assert hs.live_state_from_hand(None) == {}
    assert hs.live_state_from_hand(object()) == {}


def test_entry_facts_read_the_seat_own_hand() -> None:
    row = {
        "street1Aggr": 1,
        "street1InPosition": 1,
        "foldToStreet1CBChance": 1,
        "val_f_bet_facing_bp": 6600,
        "street1FaceRaise": 0,
    }
    facts = hs.entry_facts(row, "flop")
    assert facts["street_index"] == 1
    assert facts["is_aggressor"] is True
    assert facts["in_position"] is True
    assert facts["facing_action"] == "bets"
    assert facts["facing_sizing_bp"] == 6600
    assert "is_preflop_aggressor" not in facts, "no street0Aggr column means no answer"


def test_entry_facts_answer_the_preflop_question_on_any_street() -> None:
    """The row is one hand: who raised preflop is readable on the flop too."""
    facts = hs.entry_facts({"street0Aggr": 1, "street1Aggr": 0, "street1InPosition": 1}, "flop")
    assert facts["is_preflop_aggressor"] is True
    assert facts["is_aggressor"] is False


def test_entry_facts_keep_a_false_and_prefer_a_raise_over_a_bet() -> None:
    facts = hs.entry_facts({"street2Aggr": 0, "street2InPosition": 0, "street2FaceRaise": 1, "foldToStreet2CBChance": 1}, "turn")
    assert facts["is_aggressor"] is False
    assert facts["in_position"] is False
    assert facts["facing_action"] == "raises"


def test_entry_facts_take_the_deepest_level_faced() -> None:
    facts = hs.entry_facts({"val_p_2bet_facing_bp": 400, "val_p_3bet_facing_bp": 1800}, "preflop")
    assert facts["facing_sizing_bp"] == 1800
    assert "facing_action" not in facts, "no raise faced, no bet faced"


def test_from_stat_dict_prefers_the_feed_over_the_aggregate_row() -> None:
    row = {"street1Aggr": 1, "street1InPosition": 1, "foldToStreet1CBChance": 1, "val_f_bet_facing_bp": 6600}
    from_row = hs.HudSituationContext.from_stat_dict(row, {"street": "flop", "pot_type": "single_raised"})
    assert from_row.is_aggressor
    assert from_row.in_position is True
    assert from_row.facing_action == "bets"
    from_feed = hs.HudSituationContext.from_stat_dict(
        row,
        {"street": "flop", "pot_type": "single_raised", "in_position": False, "facing_action": "raises"},
    )
    assert from_feed.in_position is False
    assert from_feed.facing_action == "raises"


def test_the_aggregate_row_makes_a_postflop_panel_reachable() -> None:
    """The point of reading the row: a live seat can match a postflop rule."""
    resolver = hs.load_default_resolver()
    live = {"street": "flop", "pot_type": "single_raised", "players_in_hand": 2}
    aggressor = {"live_position": "0", "street0Aggr": 1, "street1Aggr": 1, "street1InPosition": 1}
    defender = {
        "live_position": "B",
        "street0Aggr": 0,
        "street1Aggr": 0,
        "street1InPosition": 0,
        "foldToStreet1CBChance": 1,
    }
    in_position = resolver.resolve(hs.HudSituationContext.from_stat_dict(aggressor, live))
    facing = resolver.resolve(hs.HudSituationContext.from_stat_dict(defender, live))
    assert "srp_cbet_ip" in in_position.panels
    assert "srp_face_cbet_oop" in facing.panels


# --------------------------------------------------------------------------- #
# The wiring: the configuration section, and the HUD that reads it.
# --------------------------------------------------------------------------- #


EXAMPLE_CONFIG = Path(__file__).parents[1] / "HUD_config.xml.example"


def test_the_shipped_config_carries_a_disabled_documented_panel_section() -> None:
    """Present and inert: discoverable, but a no-op until a user turns it on."""
    from fpdb_3_legacy import Configuration

    config = Configuration.Config(file=str(EXAMPLE_CONFIG))
    assert config.get_hud_panel_rules() == []
    assert not config.hud_panel_rules_enabled
    assert config.doc.getElementsByTagName("hud_panel_rules"), "the section must exist to be found"
    assert "hud_panel_rule " in EXAMPLE_CONFIG.read_text(encoding="utf-8"), "an example must be documented"


def test_a_disabled_section_reads_as_no_rules_even_when_it_names_a_source(tmp_path: Path) -> None:
    """Off means off: the shipped library is not loaded and nothing shows."""
    from fpdb_3_legacy import Configuration

    path = _config_with_panel_section(tmp_path, 'enabled="false" source="builtin"')
    config = Configuration.Config(file=str(path))
    assert config.hud_panel_rules == []
    assert config.get_hud_panel_rules() == []


def test_source_builtin_is_the_shipped_library(tmp_path: Path) -> None:
    from fpdb_3_legacy import Configuration

    path = _config_with_panel_section(tmp_path, 'enabled="true" source="builtin" fallback="core"')
    config = Configuration.Config(file=str(path))
    rules = config.get_hud_panel_rules()
    assert len(rules) == 19
    assert [rule.panel for rule in rules][:2] == ["core", "preflop_open"]
    assert config.hud_panel_fallback == "core"


def test_an_inline_rule_is_a_condition_in_the_query_vocabulary(tmp_path: Path) -> None:
    from fpdb_3_legacy import Configuration

    path = _config_with_panel_section(
        tmp_path,
        'enabled="true"',
        '<hud_panel_rule panel="srp_cbet_ip" id="mine" street="flop" pot_type="single_raised" min_sample="50"/>',
    )
    config = Configuration.Config(file=str(path))
    rules = config.get_hud_panel_rules()
    assert [rule.panel for rule in rules] == ["srp_cbet_ip"]
    assert rules[0].min_sample == 50
    assert rules[0].when == {"street": "flop", "pot_type": "single_raised"}


def test_enabling_the_section_on_an_existing_config_installs_it_explained(tmp_path: Path) -> None:
    """Upgrading users get the section, with the comment that documents it."""
    import defusedxml.minidom as minidom

    from fpdb_3_legacy import Configuration

    source = minidom.parse(str(EXAMPLE_CONFIG))
    for node in list(source.getElementsByTagName("hud_panel_rules")):
        node.parentNode.removeChild(node)
    path = tmp_path / "HUD_config.xml"
    path.write_text(source.toxml(), encoding="utf-8")

    config = Configuration.Config(file=str(path))
    added = config.add_missing_elements(config.doc, str(EXAMPLE_CONFIG))

    saved = path.read_text(encoding="utf-8")
    assert added == 1
    assert "<hud_panel_rules" in saved
    assert "Dynamic HUD panels: show the panels that fit" in saved, "the section must arrive explained"
    assert Configuration.Config(file=str(path)).get_hud_panel_rules() == []


def test_saving_panel_rules_round_trips_through_the_config(tmp_path: Path) -> None:
    from fpdb_3_legacy import Configuration

    path = _config_with_panel_section(tmp_path, 'enabled="true" fallback="core"')
    config = Configuration.Config(file=str(path))
    config.set_hud_panel_rules(
        [hs.PanelRule.from_mapping({"panel": "srp_flop", "substitutions": {"B": "srp_bb"}, "when": {"street": "flop"}})],
        fallback="core",
    )
    config.save(file=str(path))

    reloaded = Configuration.Config(file=str(path))
    rules = reloaded.get_hud_panel_rules()
    assert [rule.panel for rule in rules] == ["srp_flop"]
    assert rules[0].substitutions == {"BB": "srp_bb"}
    assert rules[0].when == {"street": "flop"}
    assert reloaded.hud_panel_fallback == "core"
    assert path.read_text(encoding="utf-8").count("<hud_panel_rules") == 1, "the GUI reuses the section"


def test_setting_no_rules_turns_the_dynamic_panels_off(tmp_path: Path) -> None:
    from fpdb_3_legacy import Configuration

    path = _config_with_panel_section(tmp_path, 'enabled="true" source="builtin"')
    config = Configuration.Config(file=str(path))
    assert config.get_hud_panel_rules()
    config.set_hud_panel_rules([], enabled=False)
    assert config.get_hud_panel_rules() == []
    config.save(file=str(path))
    assert Configuration.Config(file=str(path)).get_hud_panel_rules() == []


def test_a_missing_source_is_reported_rather_than_silently_empty(tmp_path: Path) -> None:
    from fpdb_3_legacy import Configuration

    path = _config_with_panel_section(tmp_path, 'enabled="true" source="nowhere/panels.json"')
    with pytest.raises(OSError):
        Configuration.Config(file=str(path))


def _config_with_panel_section(tmp_path: Path, attributes: str, *rules: str) -> Path:
    """The shipped configuration with the panel section replaced, as a user's file."""
    import defusedxml.minidom as minidom

    document = minidom.parse(str(EXAMPLE_CONFIG))
    section = document.getElementsByTagName("hud_panel_rules")[0]
    body = "".join(rules)
    replacement = minidom.parseString(f'<hud_panel_rules {attributes}>{body}</hud_panel_rules>').documentElement
    section.parentNode.replaceChild(document.importNode(replacement, True), section)
    path = tmp_path / "HUD_config.xml"
    path.write_text(document.toxml(), encoding="utf-8")
    return path


def test_set_live_state_is_a_partial_update_that_wakes_every_aux_window() -> None:
    """A new hand clears what is no longer true and refreshes the panels."""
    from types import SimpleNamespace

    from fpdb_3_legacy import Hud as hud_module

    hud = hud_module.Hud.__new__(hud_module.Hud)
    hud.live_state = {}
    forgotten: list[str] = []
    hud.aux_windows = [
        SimpleNamespace(forget_dynamic_panels=lambda: forgotten.append("window")),
        SimpleNamespace(),  # a classic aux window has no panel memory
    ]
    hud.set_live_state(street="flop", pot_type="single_raised")
    assert hud.live_state == {"street": "flop", "pot_type": "single_raised"}
    hud.set_live_state(street=None)
    assert hud.live_state == {"pot_type": "single_raised"}, "None clears a key"
    assert forgotten == ["window", "window"]


def test_a_profile_without_panel_rules_keeps_the_static_grid() -> None:
    from types import SimpleNamespace

    from fpdb_3_legacy import Aux_Hud

    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aux.config = SimpleNamespace(get_hud_panel_rules=lambda: [])
    aux.game_params = SimpleNamespace(name="default")
    aux.hud = SimpleNamespace(stat_dict={7: {"live_position": "0"}}, live_state={})
    assert aux.dynamic_panel_selection(3, 7) is None, "the caller then applies the position rule"


def test_a_configured_profile_answers_with_the_seat_panels() -> None:
    from types import SimpleNamespace

    from fpdb_3_legacy import Aux_Hud

    rules = hs.load_default_resolver().rules
    aux = Aux_Hud.SimpleHUD.__new__(Aux_Hud.SimpleHUD)
    aux.config = SimpleNamespace(get_hud_panel_rules=lambda: rules, hud_panel_fallback="core")
    aux.game_params = SimpleNamespace(name="default")
    aux.hud = SimpleNamespace(
        stat_dict={7: {"live_position": "0", "street0Aggr": 1, "street1InPosition": 1}},
        live_state={"street": "flop", "pot_type": "single_raised"},
    )
    selection = aux.dynamic_panel_selection(3, 7)
    assert selection is not None
    assert "srp_cbet_ip" in selection.panels
    # A seat with no data at all is a seat with no live state, not a crash.
    aux.hud.stat_dict = {}
    assert aux.dynamic_panel_selection(3, 99) is not None
