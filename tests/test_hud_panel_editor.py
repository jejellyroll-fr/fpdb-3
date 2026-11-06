"""The model behind the Dynamic Panels tab (#309), without a window.

The tab is thin on purpose: it reads selectors out of widgets and prints what
this module answers. Everything that decides something -- which selectors exist,
whether two rules conflict, which rule wins and why, what an exported file holds,
what a stat choice is -- is here, and is checked here.

The two commitments that matter are checked directly: a selector name is always
one the query engine knows, and a preview agrees with the production resolver.
"""

from __future__ import annotations

import json

import pytest

from fpdb_3_legacy import analytics_query, player_situations
from fpdb_3_legacy import hud_panel_editor as editor
from fpdb_3_legacy import hud_situation as hs


def resolver() -> hs.HudSituationResolver:
    return hs.load_default_resolver()


# --------------------------------------------------------------------------- #
# The selector vocabulary.
# --------------------------------------------------------------------------- #


def test_every_condition_the_editor_offers_is_one_the_engine_knows() -> None:
    """The tab cannot offer a condition the resolver would refuse to evaluate."""
    offered = {field.name for field in editor.selector_fields() if field.name != "profile"}
    assert offered <= set(analytics_query.FILTERS)


def test_the_profile_selector_is_the_rule_scope_not_a_condition() -> None:
    """`profile` scopes a rule to a stat set; it is not something a hand *is*."""
    assert "profile" not in analytics_query.FILTERS
    assert editor.selector_field("profile") is not None


def test_every_selector_has_a_label_a_kind_and_a_group() -> None:
    for field in editor.selector_fields():
        assert field.label
        assert field.kind in ("set", "bool", "range")
        assert field.group
        if field.kind == "set" and field.choices:
            assert all(str(choice) for choice in field.choices)


def test_the_issue_selectors_are_all_present() -> None:
    """The list the issue asks for, so a missing one is a failing test."""
    wanted = (
        "site",
        "game",
        "profile",
        "tournament",
        "seats",
        "street",
        "pot_type",
        "position",
        "opponent_position",
        "in_position",
        "action_faced",
        "role",
        "is_preflop_aggressor",
        "is_aggressor",
        "stack_bucket",
        "effective_stack_bb",
    )
    offered = {field.name for field in editor.selector_fields()}
    assert set(wanted) <= offered


def test_open_vocabularies_are_filled_from_the_application() -> None:
    """Sites and games are the configuration's, not a literal in the editor."""
    filled = editor.fill_choices(editor.selector_fields(), site=["PokerStars"], game=["holdem"], seats=["6"])
    by_name = {field.name: field for field in filled}
    assert by_name["site"].choices == ("PokerStars",)
    assert by_name["game"].choices == ("holdem",)
    assert by_name["seats"].choices == ("6",)
    assert by_name["street"].choices == hs.STREETS, "a closed vocabulary is untouched"


def test_the_situation_words_come_from_the_situation_model() -> None:
    """A label the model does not have is a rule that can never match."""
    labels = {rule.label for rule in player_situations.SITUATION_RULES}
    assert labels, "the model names its spots"
    filled = editor.fill_choices(editor.selector_fields(), situation=sorted(labels))
    assert set({field.name: field for field in filled}["situation"].choices) == labels


# --------------------------------------------------------------------------- #
# Drafts.
# --------------------------------------------------------------------------- #


def test_a_draft_round_trips_through_every_rule_of_the_shipped_library() -> None:
    for rule in resolver().rules:
        draft = editor.PanelRuleDraft.from_rule(rule)
        assert draft.to_rule(rule.order) == rule, rule.panel


def test_a_draft_of_a_condition_the_loader_refuses_raises_its_message() -> None:
    """A half-filled form fails with the message a hand-edited file would get."""
    draft = editor.PanelRuleDraft(panel="", conditions={"street": "flop"})
    with pytest.raises(ValueError, match="panel"):
        draft.to_rule()
    draft = editor.PanelRuleDraft(panel="x", conditions={"streets": "flop"})
    with pytest.raises(ValueError, match="unknown condition"):
        draft.to_rule()


def test_a_draft_reads_a_rule_back_into_a_form() -> None:
    rule = hs.PanelRule.from_mapping(
        {
            "panel": "srp_cbet_ip",
            "id": "mine",
            "profile": "holdring_modern",
            "when": {"street": "flop", "to_call": [None, 0]},
            "min_sample": 50,
            "fallback": "core",
            "priority": 30,
        }
    )
    draft = editor.PanelRuleDraft.from_rule(rule)
    assert draft.panel == "srp_cbet_ip"
    assert draft.profile == "holdring_modern"
    assert draft.conditions == {"street": "flop", "to_call": [None, 0]}
    assert (draft.min_sample, draft.fallback, draft.priority) == (50, "core", 30)
    assert draft.describe().startswith("srp_cbet_ip (")


def test_editing_a_draft_does_not_touch_the_rule_it_came_from() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "x", "when": {"street": "flop", "to_call": [None, 0]}})
    draft = editor.PanelRuleDraft.from_rule(rule)
    draft.conditions["street"] = "turn"
    draft.conditions["to_call"] = [1, 2]
    assert rule.when["street"] == "flop"
    assert rule.when["to_call"] == [None, 0]


# --------------------------------------------------------------------------- #
# Conflicts.
# --------------------------------------------------------------------------- #


def test_a_duplicate_is_reported_on_both_rows_of_the_pair() -> None:
    """Which of the two wins is a matter of file order, so both are marked."""
    one = hs.PanelRule.from_mapping({"panel": "a", "when": {"street": "flop"}}, 0)
    two = hs.PanelRule.from_mapping({"panel": "a", "when": {"street": "flop"}}, 1)
    issues = editor.rule_issues([one, two])
    duplicates = [issue for issue in issues if issue.severity == "duplicate"]
    assert {issue.row for issue in duplicates} == {0, 1}
    assert all("selector" in issue.message or "duplicates" in issue.message for issue in duplicates)


def test_a_suspicious_rule_is_flagged_where_the_command_line_flags_it() -> None:
    """The tab and `tools/hud_panels.py --validate` report the same thing."""
    rule = hs.PanelRule.from_mapping({"panel": "x", "fallback": "core", "when": {"street": "flop"}})
    issues = editor.rule_issues([rule], panels=("core", "srp_cbet_ip"))
    assert any("min_sample" in issue.message for issue in issues)
    assert any("not a known block" in issue.message for issue in issues)


def test_a_rule_naming_a_known_block_has_no_warning_about_it() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "srp_cbet_ip", "when": {"street": "flop"}})
    assert not any("known block" in issue.message for issue in editor.rule_issues([rule], ["srp_cbet_ip"]))


# --------------------------------------------------------------------------- #
# The preview.
# --------------------------------------------------------------------------- #


def test_the_preview_agrees_with_the_resolver_on_a_spread_of_contexts() -> None:
    """Agreement is the point: a preview that differs is a second engine."""
    rules = resolver().rules
    contexts = (
        {"street": "preflop", "pot_type": "unopened", "position": "CO"},
        {"street": "preflop", "pot_type": "unopened", "action_faced": "raises", "position": "BB"},
        {"street": "preflop", "pot_type": "single_raised", "action_faced": "raises", "to_call": 900},
        {"street": "flop", "pot_type": "single_raised", "is_preflop_aggressor": True, "in_position": True},
        {"street": "flop", "pot_type": "single_raised", "is_preflop_aggressor": False, "in_position": False},
        {"street": "river", "pot_type": "four_bet_plus"},
        {"street": "preflop", "stack_bucket": "short"},
    )
    for conditions in contexts:
        preview = editor.preview(conditions, rules, fallback="core", samples={"n": 100})
        direct = hs.HudSituationResolver(rules, fallback="core").resolve(
            hs.HudSituationContext.from_filters(conditions),
            samples={"n": 100},
        )
        assert preview.selection.panels == direct.panels, conditions
        assert preview.winner is not None and preview.winner.panel == preview.selection.panels[0], conditions


def test_the_preview_names_the_winning_rule_and_what_it_beat() -> None:
    preview = editor.preview(
        {"street": "flop", "pot_type": "single_raised", "is_preflop_aggressor": True, "in_position": True},
        resolver().rules,
        fallback="core",
        samples={"n": 100},
    )
    assert preview.winner is not None and preview.winner.panel == "srp_cbet_ip"
    outcome = next(outcome for outcome in preview.outcomes if outcome.panel == "srp_cbet_ip")
    assert outcome.shown and "specificity" in outcome.reason
    core = next(outcome for outcome in preview.outcomes if outcome.panel == "core")
    assert core.shown and "outranked" in core.reason


def test_the_preview_says_which_condition_failed_and_what_the_context_had() -> None:
    preview = editor.preview({"street": "turn"}, resolver().rules, fallback="core")
    outcome = next(outcome for outcome in preview.outcomes if outcome.panel == "preflop_open")
    assert not outcome.matched
    assert "street=preflop" in outcome.reason and "turn" in outcome.reason


def test_the_preview_reports_a_withheld_panel_and_by_how_much() -> None:
    rules = resolver().rules
    preview = editor.preview(
        {"street": "preflop", "pot_type": "unopened", "effective_stack_bb": 200, "stack_bucket": "deep"},
        rules,
        fallback="core",
        samples={"n": 12},
    )
    assert "preflop_deep" in preview.selection.suppressed
    outcome = next(outcome for outcome in preview.outcomes if outcome.panel == "preflop_deep")
    assert outcome.suppressed and "12" in outcome.reason and "200" in outcome.reason


def test_the_preview_reports_a_panel_no_block_carries() -> None:
    preview = editor.preview(
        {"street": "preflop", "pot_type": "unopened"},
        resolver().rules,
        fallback="core",
        panels=("core",),
        samples={"n": 100},
    )
    assert any("no block carries" in note for note in preview.notes)


def test_the_preview_of_a_disabled_resolver_says_so() -> None:
    preview = editor.preview({"street": "flop"}, resolver().rules, fallback="core", enabled=False)
    assert preview.enabled is False
    assert all(not outcome.shown for outcome in preview.outcomes)
    assert any("disabled" in outcome.reason for outcome in preview.outcomes)
    assert "off" in preview.describe() or "disabled" in preview.describe()


def test_the_preview_says_when_no_rule_matches_and_there_is_no_fallback() -> None:
    rule = hs.PanelRule.from_mapping({"panel": "river_only", "when": {"street": "river"}})
    preview = editor.preview({"street": "flop"}, [rule])
    assert preview.selection.panels == ()
    assert any("no fallback" in note for note in preview.notes)


def test_the_preview_scopes_rules_to_the_profile() -> None:
    rules = [
        hs.PanelRule.from_mapping({"panel": "only_aof", "profile": "aof_default", "when": {"street": "preflop"}})
    ]
    other = editor.preview({"street": "preflop"}, rules, profile="holdring_modern", fallback="core")
    assert "only_aof" not in other.selection.panels
    assert any("scoped to profile" in outcome.reason for outcome in other.outcomes)
    mine = editor.preview({"street": "preflop"}, rules, profile="aof_default", fallback="core")
    assert "only_aof" in mine.selection.panels


# --------------------------------------------------------------------------- #
# Import and export.
# --------------------------------------------------------------------------- #


def test_an_exported_document_reads_back_into_the_same_rules(tmp_path) -> None:
    rules = resolver().rules
    document = editor.export_document(rules, fallback="core", description="a setup")
    path = editor.save_document(document, tmp_path / "panels.json")
    loaded = editor.load_document(path)
    imported = editor.import_document(loaded)
    assert [rule.panel for rule in imported.rules] == [rule.panel for rule in rules]
    assert [dict(rule.when) for rule in imported.rules] == [dict(rule.when) for rule in rules]
    assert imported.fallback == "core"
    assert imported.warnings == ()


def test_a_bare_rule_file_is_accepted_as_a_document() -> None:
    """The export of the command line and the export of the tab are one format."""
    document = {"schema_version": hs.PANEL_SCHEMA_VERSION, "fallback": "core", "rules": [{"panel": "x", "when": {}}]}
    rules, fallback, stats = editor.parse_document(document)
    assert [rule.panel for rule in rules] == ["x"] and fallback == "core" and stats == []


def test_a_document_of_another_kind_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="fpdb-hud-panels"):
        editor.parse_document({"kind": "something-else", "rules": []})


def test_an_unknown_stat_is_kept_and_reported_rather_than_dropped() -> None:
    """A file from a later build imports: the rules are the user's work."""
    document = {
        "kind": editor.PANEL_DOCUMENT_KIND,
        "schema_version": hs.PANEL_SCHEMA_VERSION,
        "fallback": "core",
        "rules": [{"panel": "x", "when": {}}],
        "stats": [{"name": "from_the_future", "source": "analytics"}],
    }
    imported = editor.import_document(document, known_stats=("vpip", "pfr"))
    assert imported.stats == ({"name": "from_the_future", "source": "analytics"},)
    assert any("from_the_future" in warning for warning in imported.warnings)


def test_an_older_schema_is_read_and_said_out_loud() -> None:
    document = {"kind": editor.PANEL_DOCUMENT_KIND, "schema_version": 0, "rules": [{"panel": "x", "when": {}}]}
    imported = editor.import_document(document)
    assert imported.rules and any("older" in warning for warning in imported.warnings)


def test_a_stat_entry_without_a_name_is_a_refusal() -> None:
    with pytest.raises(ValueError, match="name"):
        editor.parse_document({"kind": editor.PANEL_DOCUMENT_KIND, "rules": [], "stats": [{"source": "analytics"}]})


def test_export_refuses_a_rule_set_that_cannot_be_read_back() -> None:
    """Validation at export is what makes the format trustworthy at import."""
    bad = hs.PanelRule.from_mapping({"panel": "x", "when": {"street": "flop"}})
    object.__setattr__(bad, "when", {"nothing": "like this"})
    with pytest.raises(ValueError, match="unknown condition"):
        editor.export_document([bad])


# --------------------------------------------------------------------------- #
# The stat picker.
# --------------------------------------------------------------------------- #


def test_the_picker_lists_the_column_stats_and_the_analytics_ones() -> None:
    choices = editor.stat_choices()
    sources = {choice.source for choice in choices}
    assert sources == {"registry", "analytics"}
    assert all(choice.name and choice.label for choice in choices)


def test_an_analytics_choice_shows_the_query_it_applies() -> None:
    """A picker that cannot say what a stat measures cannot say whether it fits."""
    choice = next(choice for choice in editor.analytics_choices() if choice.name == "fold_to_cbet_flop")
    assert choice.filters, "the fragments' filters are the half a user cannot see"
    assert choice.min_sample >= 0
    assert "filters:" in choice.describe()
    assert choice.fmt in ("percentage", "count", "bb", "currency", "decimal", "ratio")


def test_a_registry_choice_shows_its_sample_column() -> None:
    choice = next(choice for choice in editor.registry_choices() if choice.name == "cbet_flop")
    assert choice.sample == "street1CBChance"
    assert "sample: street1CBChance" in choice.describe()


def test_an_analytics_stat_is_written_with_where_it_comes_from() -> None:
    choice = next(choice for choice in editor.analytics_choices() if choice.name == "fold_to_cbet_flop")
    attributes = editor.stat_entry_attributes(choice, grid=(1, 0))
    assert attributes["name"] == "fold_to_cbet_flop"
    assert attributes["data_source"] == "analytics"
    assert attributes["data_definition"] == "fold_to_cbet_flop"
    assert attributes["data_format"] == choice.fmt
    assert (attributes["row"], attributes["col"]) == (1, 0), "the cell is a number, not a string"


def test_a_column_stat_is_written_as_its_name_alone() -> None:
    """No new attributes on the stats that already work: the XML stays quiet."""
    choice = next(choice for choice in editor.registry_choices() if choice.name == "vpip")
    attributes = editor.stat_entry_attributes(choice)
    assert attributes == {"name": "vpip"}


def test_the_picker_uses_the_engine_vocabulary_for_a_condition_value() -> None:
    assert editor.readable(True) == "true"
    assert editor.readable([None, 0]) == "[null, 0]"
    assert editor.readable("flop") == "flop"


def test_a_document_keeps_its_stats_through_an_export_import_cycle(tmp_path) -> None:
    document = editor.export_document(
        [hs.PanelRule.from_mapping({"panel": "core", "when": {}})],
        fallback="core",
        stats=[{"name": "fold_to_cbet_flop", "source": "analytics", "fmt": "percentage", "min_sample": 5}],
    )
    path = editor.save_document(document, tmp_path / "setup.json")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    imported = editor.import_document(reloaded, known_stats=("fold_to_cbet_flop",))
    assert imported.stats[0]["min_sample"] == 5
    assert imported.warnings == ()
