"""Declarative stat and filter definitions (#306).

The query engine (#297) lets a new question be asked at call time; this layer
lets the question be *stored* -- as JSON (or YAML), validated before anything
runs, and compiled into the engine's query. The tests follow the acceptance
criteria in order:

* **Parsing and validation** -- every unsupported field, name or value is
  refused with a message that names it and lists what is allowed.
* **Schema versioning** -- a definition (or a whole file) from a newer schema
  is refused, not half-understood.
* **Fragments and aliases** -- reusable named filter bundles merge in the
  right order, cycles are caught, and the shorthand of a definition
  (``SRP``, ``PFR``, ``action_frequency``) resolves onto the engine's words.
* **Compilation** -- a definition becomes exactly the #297 query, with the
  same parameterization and no SQL text from the definition.
* **Display** -- labels localize, formats render, and the minimum-sample
  threshold is applied where it belongs.
* **Consumers** -- the bundled library drives a preflop and a postflop stat
  end to end on the golden corpus, and a new definition can be added at
  runtime without editing ``Stats.py``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from fpdb_3_legacy import analytics_definitions as dsl
from fpdb_3_legacy.analytics_query import Query, QueryRow, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden


@pytest.fixture(scope="module")
def query_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("definitions")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)
    return db


_MODULE_STATE: list[object] = []


def _definition(**overrides):
    """A minimal valid definition, with fields overridden per test."""
    data = {"name": "a_stat", "metric": "fold_frequency"}
    data.update(overrides)
    return dsl.parse_definition(data)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParsing:
    """Files and mappings become validated definitions."""

    def test_minimal_definition(self) -> None:
        definition = _definition()
        assert definition.name == "a_stat"
        assert definition.metric == "fold_frequency"
        assert definition.schema_version == dsl.DEFINITION_SCHEMA_VERSION

    def test_loads_a_single_object_and_a_stats_list(self, tmp_path: Path) -> None:
        single = tmp_path / "single.json"
        single.write_text(json.dumps({"name": "one", "metric": "opportunities"}))
        assert [d.name for d in dsl.load_definitions(single)] == ["one"]

        many = tmp_path / "many.json"
        many.write_text(json.dumps({"stats": [{"name": "one", "metric": "opportunities"}]}))
        assert [d.name for d in dsl.load_definitions(many)] == ["one"]

        bare = tmp_path / "bare.json"
        bare.write_text(json.dumps([{"name": "one", "metric": "opportunities"}]))
        assert [d.name for d in dsl.load_definitions(bare)] == ["one"]

    def test_load_directory_collects_only_definition_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.json").write_text(json.dumps({"name": "a", "metric": "opportunities"}))
        (tmp_path / "notes.txt").write_text("ignore me")
        assert [d.name for d in dsl.load_directory(tmp_path)] == ["a"]

    def test_unsupported_suffix_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "stat.toml"
        path.write_text("name = 'x'")
        with pytest.raises(ValueError, match="unsupported definition suffix"):
            dsl.load_definitions(path)

    def test_yaml_loads_when_available_and_explains_when_not(self, tmp_path: Path) -> None:
        path = tmp_path / "stat.yaml"
        path.write_text("name: x\nmetric: opportunities\n")
        if importlib.util.find_spec("yaml") is None:
            with pytest.raises(ValueError, match="requires PyYAML"):
                dsl.load_definitions(path)
        else:  # pragma: no cover - depends on the environment
            assert [d.name for d in dsl.load_definitions(path)] == ["x"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Unsupported fields and names fail loudly and actionably."""

    def test_unknown_top_level_field(self) -> None:
        with pytest.raises(ValueError, match="unsupported field.*sql"):
            _definition(sql="DROP TABLE Hands")

    def test_metric_is_required(self) -> None:
        with pytest.raises(ValueError, match="metric is required"):
            dsl.parse_definition({"name": "x"})

    def test_unknown_metric(self) -> None:
        with pytest.raises(ValueError, match="unknown metric"):
            _definition(metric="win_rate")

    def test_unknown_filter(self) -> None:
        with pytest.raises(ValueError, match="unknown filter"):
            _definition(filters={"made_up": 1})

    def test_unknown_dimension(self) -> None:
        with pytest.raises(ValueError, match="unknown dimension"):
            _definition(group_by=["made_up"])

    def test_filters_must_be_a_mapping(self) -> None:
        with pytest.raises(ValueError, match="filters must be a table"):
            _definition(filters=["street"])

    def test_name_must_be_a_string(self) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            dsl.parse_definition({"metric": "opportunities"})

    def test_bad_format_and_precision(self) -> None:
        with pytest.raises(ValueError, match="unknown format"):
            _definition(format="colour")
        with pytest.raises(ValueError, match="precision must be a non-negative integer"):
            _definition(precision=-1)
        with pytest.raises(ValueError, match="min_sample must be a non-negative integer"):
            _definition(min_sample="many")

    def test_bad_label_table(self) -> None:
        with pytest.raises(ValueError, match="label.en must be a string"):
            _definition(label={"en": 3})

    def test_error_names_the_source_file(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"name": "x", "metric": "nope"}))
        with pytest.raises(ValueError, match=r"bad\.json: unknown metric"):
            dsl.load_definitions(path)


# ---------------------------------------------------------------------------
# Schema versioning
# ---------------------------------------------------------------------------


class TestSchemaVersioning:
    """The schema carries a version and refuses the future."""

    def test_current_version_is_accepted(self) -> None:
        assert _definition(schema_version=dsl.DEFINITION_SCHEMA_VERSION).schema_version == 1

    def test_newer_definition_version_is_refused(self) -> None:
        with pytest.raises(ValueError, match="newer than supported"):
            _definition(schema_version=dsl.DEFINITION_SCHEMA_VERSION + 1)

    def test_newer_file_version_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "future.json"
        path.write_text(json.dumps({"schema_version": 99, "stats": [{"name": "x", "metric": "opportunities"}]}))
        with pytest.raises(ValueError, match="newer than supported"):
            dsl.load_definitions(path)

    @pytest.mark.parametrize("version", [0, -1, True, "2"])
    def test_malformed_file_version_is_refused(self, tmp_path: Path, version) -> None:
        path = tmp_path / "malformed.json"
        path.write_text(json.dumps({"schema_version": version, "stats": []}))
        with pytest.raises(ValueError, match="schema_version must be a positive integer"):
            dsl.load_definitions(path)

    def test_non_integer_version_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be a positive integer"):
            _definition(schema_version="one")

    def test_round_trip_keeps_the_version(self) -> None:
        definition = _definition(label="Label", format="percentage")
        assert dsl.parse_definition(definition.as_dict()).metric == definition.metric


# ---------------------------------------------------------------------------
# Fragments and aliases
# ---------------------------------------------------------------------------


class TestFragmentsAndAliases:
    """Reusable filter bundles and the shorthand vocabulary."""

    def test_fragments_expand_in_order(self) -> None:
        assert dsl.expand_fragments(["preflop", "facing_3bet"]) == {
            "street": "preflop",
            "situation": "facing_3bet",
        }

    def test_definition_filters_win_over_fragments(self) -> None:
        merged = dsl.merge_fragments(["flop"], {"street": "turn"})
        assert merged == {"street": "turn"}

    def test_nested_fragments_expand(self) -> None:
        library = {"outer": {"fragments": ["inner"], "a": 1}, "inner": {"b": 2}}
        assert dsl.expand_fragments(["outer"], library) == {"b": 2, "a": 1}

    def test_fragment_cycle_is_refused(self) -> None:
        library = {"a": {"fragments": ["b"]}, "b": {"fragments": ["a"]}}
        with pytest.raises(ValueError, match="fragment cycle"):
            dsl.expand_fragments(["a"], library)

    def test_unknown_fragment_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown fragment"):
            dsl.expand_fragments(["made_up"])

    def test_metric_alias_resolves(self) -> None:
        assert dsl.resolve_metric("action_frequency") == "frequency"
        assert dsl.resolve_metric("sample_size") == "opportunities"

    def test_pot_type_and_role_shorthand_resolve(self) -> None:
        definition = _definition(filters={"pot_type": "SRP", "role": "PFR"})
        assert definition.filters["pot_type"] == "single_raised"
        assert definition.filters["role"] == "aggressor"

    def test_shorthand_maps_lists_element_by_element(self) -> None:
        definition = _definition(filters={"pot_type": ["SRP", "3BP"]})
        assert definition.filters["pot_type"] == ["single_raised", "three_bet"]

    def test_position_names_pass_through_to_the_engine(self) -> None:
        definition = _definition(filters={"position": "BTN", "opponent_position": "BB"})
        assert definition.filters == {"position": "BTN", "opponent_position": "BB"}

    def test_dimension_alias_resolves(self) -> None:
        definition = _definition(group_by=["bet_size_bucket"])
        assert definition.group_by == ("sizing_bucket",)

    def test_registry_can_add_a_fragment(self) -> None:
        registry = dsl.DefinitionRegistry()
        registry.add_fragment("my_spot", {"street": "turn"})
        assert dsl.expand_fragments(["my_spot"], registry.fragments) == {"street": "turn"}


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


class TestCompilation:
    """A definition becomes exactly the engine's query."""

    def test_compiles_to_a_query(self) -> None:
        definition = _definition(filters={"street": "flop"}, group_by=["response"])
        query = definition.to_query()
        assert isinstance(query, Query)
        assert query.metric == "fold_frequency"
        assert query.filters == {"street": "flop"}
        assert query.group_by == ("response",)

    def test_fragments_are_merged_into_the_compiled_sql(self) -> None:
        definition = _definition(fragments=["flop", "facing_cbet"])
        compiled = dsl.compile_definition(definition, placeholder="?", backend="sqlite")
        assert "SI.streetName" in compiled.sql
        assert "SI.labels LIKE ?" in compiled.sql

    def test_context_narrows_without_editing(self) -> None:
        definition = _definition(filters={"street": "flop"})
        narrowed = definition.to_query({"player": "Cara"})
        assert narrowed.filters == {"street": "flop", "player": "Cara"}

    def test_description_names_the_resolved_vocabulary(self) -> None:
        definition = _definition(filters={"pot_type": "SRP", "role": "PFR"}, group_by=["bet_size_bucket"])
        compiled = dsl.compile_definition(definition)
        assert "pot_type='single_raised'" in compiled.description
        assert "role='aggressor'" in compiled.description
        assert "group_by: sizing_bucket" in compiled.description

    def test_compiled_query_is_parameterized(self) -> None:
        definition = _definition(filters={"player": "x' OR 1=1 --"})
        compiled = dsl.compile_definition(definition, placeholder="?", backend="sqlite")
        assert "OR 1=1" not in compiled.sql
        assert "x' OR 1=1 --" in compiled.params


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class TestSecurity:
    """A definition can only name things the module already knows."""

    def test_no_expression_field_is_accepted(self) -> None:
        # The registry's StatDescriptor accepts an arithmetic ``value``; a
        # *filter* definition does not, because it has no business computing.
        with pytest.raises(ValueError, match="unsupported field.*value"):
            _definition(value="x / y")

    def test_sql_like_names_are_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown filter"):
            _definition(filters={"street; DROP TABLE Hands": "flop"})

    def test_filter_values_never_reach_the_sql_text(self) -> None:
        definition = _definition(filters={"player": "Robert'); DROP TABLE Hands;--"})
        compiled = dsl.compile_definition(definition, placeholder="%s", backend="postgresql")
        assert "DROP TABLE" not in compiled.sql
        assert any("DROP TABLE" in str(param) for param in compiled.params)


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------


class TestDisplay:
    """Presentation is separate from semantics and renders per format."""

    def test_label_localizes_with_english_fallback(self) -> None:
        definition = _definition(label={"en": "Fold", "fr": "Fold FR"})
        assert definition.display.label_for("fr") == "Fold FR"
        assert definition.display.label_for("de") == "Fold"
        assert _definition(label="Plain").display.label_for("fr") == "Plain"

    def test_precision_defaults_per_format(self) -> None:
        assert dsl.DisplaySpec(fmt="percentage").precision_for() == 0
        assert dsl.DisplaySpec(fmt="currency").precision_for() == 2
        assert dsl.DisplaySpec(fmt="count", precision=1).precision_for() == 1

    def test_renders_each_format(self) -> None:
        assert dsl.DisplaySpec(fmt="percentage").render(33.333) == "33%"
        assert dsl.DisplaySpec(fmt="count").render(7.9) == "7"
        assert dsl.DisplaySpec(fmt="currency").render(1500) == "15.00"
        assert dsl.DisplaySpec(fmt="bb").render(500, big_blind_cents=200) == "2.50"
        assert dsl.DisplaySpec(fmt="decimal", precision=3).render(1.23456) == "1.235"
        assert dsl.DisplaySpec(fmt="percentage").render(None) == dsl.NO_DATA

    def test_minimum_sample_gates_the_display(self) -> None:
        definition = _definition(format="percentage", min_sample=10)
        small = QueryRow(group={}, opportunities=4, actions=2, value=2, unit="bp", frequency_bp=5000)
        big = QueryRow(group={}, opportunities=40, actions=20, value=20, unit="bp", frequency_bp=5000)
        assert dsl.format_row(definition, small) == dsl.NO_DATA
        assert dsl.format_row(definition, big) == "50%"

    def test_percentage_uses_the_frequency_not_the_raw_value(self) -> None:
        definition = _definition(format="percentage")
        row = QueryRow(group={}, opportunities=8, actions=2, value=2, unit="bp", frequency_bp=2500)
        assert dsl.format_row(definition, row) == "25%"


# ---------------------------------------------------------------------------
# The bundled library, end to end
# ---------------------------------------------------------------------------


class TestBundledLibrary:
    """Definitions shipped with fpdb drive real stats on the corpus."""

    def test_library_loads_and_is_versioned(self) -> None:
        registry = dsl.load_default_registry()
        assert len(registry) >= 4
        assert "fold_to_3bet_preflop" in registry
        assert "fold_to_cbet_flop" in registry

    def test_has_a_preflop_and_a_postflop_definition(self) -> None:
        registry = dsl.load_default_registry()
        categories = {d.display.category for d in registry.all()}
        assert any("Preflop" in category for category in categories)
        assert any("Postflop" in category for category in categories)

    def test_preflop_definition_runs(self, query_db: Database) -> None:
        definition = dsl.load_default_registry().resolve("fold_to_3bet_preflop")
        result = dsl.run_definition(query_db, definition)
        assert result.rows[0].opportunities > 0
        assert 0 <= result.rows[0].frequency_bp <= 10000

    def test_postflop_definition_runs(self, query_db: Database) -> None:
        definition = dsl.load_default_registry().resolve("fold_to_cbet_flop")
        result = dsl.run_definition(query_db, definition)
        assert result.rows[0].opportunities > 0
        assert dsl.format_row(definition, result.rows[0]).endswith("%")

    def test_a_definition_agrees_with_the_engine_it_compiles_to(self, query_db: Database) -> None:
        definition = dsl.load_default_registry().resolve("fold_to_cbet_flop")
        from_definition = dsl.run_definition(query_db, definition).rows[0]
        from_engine = run_query(
            query_db,
            Query(
                metric="fold_frequency",
                filters={"street": "flop", "situation": "facing_cbet"},
                numerator={"response": "fold"},
            ),
        ).rows[0]
        assert (from_definition.opportunities, from_definition.actions) == (
            from_engine.opportunities,
            from_engine.actions,
        )

    def test_grouped_definition_produces_one_row_per_group(self, query_db: Database) -> None:
        definition = dsl.load_default_registry().resolve("fold_to_cbet_flop_by_size")
        result = dsl.run_definition(query_db, definition)
        groups = [row.group["facing_sizing_bucket"] for row in result.rows]
        assert groups == sorted(set(groups)) or len(groups) == len(set(groups))


# ---------------------------------------------------------------------------
# Consumers
# ---------------------------------------------------------------------------


class TestConsumers:
    """The same definition feeds a report, a popup and a new stat."""

    def test_report_renders_localized_rows(self, query_db: Database) -> None:
        registry = dsl.load_default_registry()
        report = dsl.build_report(query_db, registry.all(), locale="fr")
        assert report
        labels = {entry["label"] for entry in report}
        assert any("préflop" in label for label in labels)
        assert all("value" in entry and "opportunities" in entry for entry in report)

    def test_report_includes_group_keys(self, query_db: Database) -> None:
        registry = dsl.load_default_registry()
        grouped = registry.resolve("fold_to_cbet_flop_by_size")
        report = dsl.build_report(query_db, [grouped], locale="en")
        assert len(report) > 1
        assert all("facing_sizing_bucket" in entry["group"] for entry in report)

    def test_report_uses_fragments_from_the_originating_registry(self, query_db: Database) -> None:
        registry = dsl.DefinitionRegistry()
        registry.add_fragment("custom_turn", {"street": "turn"})
        definition = dsl.parse_definition(
            {
                "name": "custom_turn_checks",
                "metric": "check_frequency",
                "fragments": ["custom_turn"],
            },
        )
        report = dsl.build_report(query_db, [definition], fragments=registry.fragments)
        assert report[0]["opportunities"] > 0

    def test_popup_context_filters_to_one_player(self, query_db: Database) -> None:
        definition = dsl.load_default_registry().resolve("fold_to_cbet_flop")
        all_players = dsl.run_definition(query_db, definition).rows[0].opportunities
        one_player = dsl.run_definition(query_db, definition, {"player": "Cara"}).rows[0].opportunities
        assert 0 < one_player < all_players

    def test_new_stat_needs_no_python_change(self, query_db: Database) -> None:
        """A stat added purely as a definition runs like any other."""
        fresh = dsl.parse_definition(
            {
                "name": "turn_check_frequency",
                "metric": "check_frequency",
                "fragments": ["turn"],
                "label": "Turn check frequency",
                "format": "percentage",
                "min_sample": 1,
            },
        )
        registry = dsl.DefinitionRegistry()
        registry.add(fresh)
        assert registry.names() == ["turn_check_frequency"]
        result = dsl.run_definition(query_db, registry.resolve("turn_check_frequency"))
        assert result.rows
        assert dsl.format_row(fresh, result.rows[0]).endswith("%")

    def test_registry_resolves_or_explains(self) -> None:
        registry = dsl.DefinitionRegistry()
        with pytest.raises(ValueError, match="unknown stat definition"):
            registry.resolve("nope")

    def test_report_of_an_empty_population_uses_no_data(self, tmp_path_factory) -> None:
        tmp = tmp_path_factory.mktemp("empty")
        config = golden.build_config(tmp)
        db = Database(config)
        db.recreate_tables()
        definition = dsl.load_default_registry().resolve("fold_to_cbet_flop")
        report = dsl.build_report(db, [definition])
        assert report[0]["value"] == dsl.NO_DATA
        db.disconnect()
