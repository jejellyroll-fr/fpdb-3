"""Guards for the custom Auto Notes engine: identity, durability, and templates.

Each test here pins a defect found while reviewing the custom-rules editor:
duplicate rule ids that make a note impossible to attribute, an in-place write
that could truncate the user's whole rule collection, a rule file that could
reach into objects through its note template, and a per-hand disk reload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy.AutoNotes import RULE_SET_REGISTRY
from fpdb_3_legacy.user_autonotes_parser import (
    MAX_CONDITION_DEPTH,
    compile_custom_rule_set,
    compile_custom_rule_sets,
    evaluate_condition_tree,
    invalidate_custom_rule_cache,
    load_custom_rule_sets,
    load_user_autonotes_data,
    render_note_template,
    save_user_autonotes_data,
)


@pytest.fixture(autouse=True)
def _clean_cache():
    invalidate_custom_rule_cache()
    yield
    invalidate_custom_rule_cache()


def _rule(rule_id: str, **overrides) -> dict:
    rule = {
        "rule_id": rule_id,
        "version": 1,
        "name": f"Rule {rule_id}",
        "note_template": "{player} did something",
        "conditions": {},
        "evidence": {},
    }
    rule.update(overrides)
    return rule


def _document(*rules: dict, rule_set_id: str = "custom_user_rules", **extra) -> dict:
    return {"version": 1, "custom_rule_sets": [{"rule_set_id": rule_set_id, "rules": list(rules), **extra}]}


class TestRuleIdentity:
    def test_a_repeated_rule_id_is_dropped(self) -> None:
        """Notes are keyed by rule id; two rules sharing one cannot be told apart."""
        rule_set = compile_custom_rule_set({"rule_set_id": "s", "rules": [_rule("dup"), _rule("dup"), _rule("other")]})

        assert [r.rule_id for r in rule_set.rules] == ["dup", "other"]

    def test_the_first_rule_of_a_duplicated_id_is_the_one_kept(self) -> None:
        rule_set = compile_custom_rule_set(
            {"rule_set_id": "s", "rules": [_rule("dup", name="first"), _rule("dup", name="second")]},
        )

        assert [r.name for r in rule_set.rules] == ["first"]

    def test_a_custom_set_cannot_shadow_a_builtin_id(self) -> None:
        builtin_id = next(iter(RULE_SET_REGISTRY)).rule_set_id
        document = _document(_rule("r1"), rule_set_id=builtin_id)

        assert compile_custom_rule_sets(document) == ()

    def test_a_repeated_rule_set_id_is_dropped(self) -> None:
        document = {
            "custom_rule_sets": [
                {"rule_set_id": "same", "rules": [_rule("a")]},
                {"rule_set_id": "same", "rules": [_rule("b")]},
            ],
        }

        compiled = compile_custom_rule_sets(document)

        assert len(compiled) == 1
        assert [r.rule_id for r in compiled[0].rules] == ["a"]


class TestDurableSave:
    def test_a_saved_file_round_trips(self, tmp_path: Path) -> None:
        target = tmp_path / "user_autonotes.json"
        document = _document(_rule("r1"))

        save_user_autonotes_data(document, target)

        assert load_user_autonotes_data(target) == document

    def test_a_failed_save_leaves_the_previous_file_intact(self, tmp_path: Path, monkeypatch) -> None:
        """An in-place write would truncate the user's whole rule collection."""
        target = tmp_path / "user_autonotes.json"
        save_user_autonotes_data(_document(_rule("original")), target)

        def explode(*_args, **_kwargs):
            message = "disk full"
            raise OSError(message)

        monkeypatch.setattr(json, "dump", explode)

        with pytest.raises(OSError, match="disk full"):
            save_user_autonotes_data(_document(_rule("replacement")), target)

        surviving = load_user_autonotes_data(target)
        assert surviving["custom_rule_sets"][0]["rules"][0]["rule_id"] == "original"

    def test_a_failed_save_leaves_no_temporary_file_behind(self, tmp_path: Path, monkeypatch) -> None:
        target = tmp_path / "user_autonotes.json"

        def explode(*_args, **_kwargs):
            message = "disk full"
            raise OSError(message)

        monkeypatch.setattr(json, "dump", explode)
        with pytest.raises(OSError, match="disk full"):
            save_user_autonotes_data(_document(_rule("r1")), target)

        assert list(tmp_path.iterdir()) == []

    def test_a_malformed_file_yields_an_empty_document(self, tmp_path: Path) -> None:
        target = tmp_path / "user_autonotes.json"
        target.write_text("{ not json", encoding="utf-8")

        assert load_user_autonotes_data(target) == {"version": 1, "custom_rule_sets": []}


class TestTemplateRendering:
    def test_known_tags_are_substituted(self) -> None:
        assert render_note_template("{player} raised {hole}", {"player": "Alice", "hole": "Ah Kd"}) == "Alice raised Ah Kd"

    def test_an_unknown_tag_stays_visible(self) -> None:
        assert render_note_template("{player} {nope}", {"player": "Alice"}) == "Alice {nope}"

    def test_attribute_access_is_not_evaluated(self) -> None:
        """A shared rule file must not reach into objects through its template."""
        rendered = render_note_template("{player.__class__.__mro__}", {"player": "Alice"})

        assert rendered == "{player.__class__.__mro__}"
        assert "class" not in rendered.replace("__class__", "")

    def test_a_brace_that_is_not_a_tag_is_left_alone(self) -> None:
        assert render_note_template("100% {0} {}", {"player": "Alice"}) == "100% {0} {}"


class TestConditionTree:
    def test_an_empty_tree_matches(self) -> None:
        assert evaluate_condition_tree({}, None, "Alice", None) is True

    def test_a_tree_nested_past_the_limit_stops_matching(self) -> None:
        tree: dict = {"operator": "AND", "rules": []}
        cursor = tree
        for _ in range(MAX_CONDITION_DEPTH + 2):
            child: dict = {"operator": "AND", "rules": []}
            cursor["rules"].append(child)
            cursor = child

        assert evaluate_condition_tree(tree, None, "Alice", None) is False


class TestRuleSetCache:
    def test_a_second_load_does_not_reread_the_file(self, tmp_path: Path, monkeypatch) -> None:
        """available_rule_sets() runs once per imported hand."""
        target = tmp_path / "user_autonotes.json"
        save_user_autonotes_data(_document(_rule("r1")), target)
        load_custom_rule_sets(target)

        import fpdb_3_legacy.user_autonotes_parser as parser

        def explode(*_args, **_kwargs):
            message = "the cached compile must be reused"
            raise AssertionError(message)

        monkeypatch.setattr(parser, "load_user_autonotes_data", explode)

        assert [rs.rule_set_id for rs in load_custom_rule_sets(target)] == ["custom_user_rules"]

    def test_an_edit_is_picked_up(self, tmp_path: Path) -> None:
        target = tmp_path / "user_autonotes.json"
        save_user_autonotes_data(_document(_rule("before")), target)
        assert [r.rule_id for r in load_custom_rule_sets(target)[0].rules] == ["before"]

        save_user_autonotes_data(_document(_rule("after")), target)

        assert [r.rule_id for r in load_custom_rule_sets(target)[0].rules] == ["after"]

    def test_a_missing_file_yields_no_rule_sets(self, tmp_path: Path) -> None:
        assert load_custom_rule_sets(tmp_path / "absent.json") == ()


class TestGameFilter:
    class _Hand:
        def __init__(self, base: str) -> None:
            self.gametype = {"base": base}

    def test_an_undeclared_game_list_keeps_matching_every_hand(self) -> None:
        rule_set = compile_custom_rule_set({"rule_set_id": "s", "rules": [_rule("r1")]})

        assert rule_set.supports_hand(self._Hand("stud")) is True

    def test_a_declared_game_list_restricts_the_rule_set(self) -> None:
        rule_set = compile_custom_rule_set({"rule_set_id": "s", "games": ["holdem"], "rules": [_rule("r1")]})

        assert rule_set.supports_hand(self._Hand("hold")) is True
        assert rule_set.supports_hand(self._Hand("stud")) is False
