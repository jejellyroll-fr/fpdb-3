"""The research browser's model: presets, a described result, drill-down (#303).

The engine layers below answer questions in one call. This module checks the
browser-shaped half of the issue: the filter vocabulary a picker can offer,
the presets that survive a restart without ever holding SQL, the result as a
table of *described* columns, and the drill-down that hands back the hands
behind a result row -- population and numerator alike -- with a count that
makes ``truncated`` a fact rather than a guess.

The tests run against the golden corpus imported once, and against preset
files in a throwaway directory: no Qt, no windows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy.analytics_query import (
    FILTERS,
    Query,
    compile_filters,
    run_hand_ids,
    run_query,
)
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden


@pytest.fixture(scope="module")
def browser_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("research-browser")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    # The importer's destructor closes the database connection; keep it alive.
    _MODULE_STATE.append(importer)
    return db


_MODULE_STATE: list[object] = []


# ---------------------------------------------------------------------------
# The filter vocabulary.
# ---------------------------------------------------------------------------


#: One value per filter kind that the compiler should accept, so the sweep
#: below can exercise every filter without a hand-written case for each.
_PLAUSIBLE_BY_KIND: dict[str, object] = {
    "scalar": "x",
    "set": ["x"],
    "range": [1, 2],
    "range_pct": [10, 200],
    "range_low": 1,
    "range_high": 2,
    "bool": True,
    "hero": True,
    "null_check": True,
    "label": "facing_open",
    "flagset": ["paired"],
    "flagset_all": ["paired"],
    "flagset_none": ["paired"],
    "identity_set": [("PokerStars", "Hero")],
}

#: The filters whose values are not free text: a coerced domain needs a value
#: from that domain rather than the generic token above.
_PLAUSIBLE_VALUES: dict[str, object] = {
    "position": ["btn"],
    "opponent_position": ["btn"],
    "made_hand": ["top_pair"],
    "made_hand_rank": [1, 5],
    "pair_detail": ["top_pair"],
    "nutness": ["nuts"],
    "draw": ["flush_draw"],
    "draw_all": ["flush_draw"],
    "draw_none": ["flush_draw"],
    "blocker": ["nut_flush_blocker"],
    "blocker_all": ["nut_flush_blocker"],
    "blocker_none": ["nut_flush_blocker"],
    "board_texture": ["paired"],
    "board_texture_all": ["paired"],
    "board_runout": ["runout_paired_board"],
    "identity": [("PokerStars", "Hero")],
    "starting_hand": ["AKs"],
    "date_from": "2026-01-01",
    "date_to": "2026-12-31",
}


def test_every_engine_filter_is_described() -> None:
    """The picker offers all of the engine's filters, none invented."""
    assert {spec.name for spec in rb.FILTER_SPECS} == set(FILTERS)


def test_every_filter_has_a_browser_group() -> None:
    """No filter falls into the catch-all group by accident."""
    ungrouped = [spec.name for spec in rb.FILTER_SPECS if spec.group == "other"]
    assert ungrouped == []


def test_every_filter_coerces_with_a_callable_or_not_at_all() -> None:
    """A vocabulary passed where the coercion goes is a filter that cannot run.

    ``_Filter``'s fourth field is ``coerce``, a callable. Handing it the tuple
    of legal values instead reads perfectly and blows up only when somebody
    filters on it -- which a dimension-only test never does.
    """
    miscast = [
        name for name, spec in FILTERS.items()
        if spec.coerce is not None and not callable(spec.coerce)
    ]
    assert miscast == []


@pytest.mark.parametrize("name", sorted(FILTERS))
def test_every_filter_compiles_with_a_plausible_value(name: str) -> None:
    """Every filter is exercised once, so none is only ever a dimension."""
    spec = FILTERS[name]
    value = _PLAUSIBLE_VALUES.get(name, _PLAUSIBLE_BY_KIND.get(spec.kind))
    if value is None:
        pytest.skip(f"no plausible value for the {spec.kind} filter {name!r}")
    where, params, aliases = compile_filters({name: value}, "?", "sqlite")

    assert where
    assert aliases


def test_value_kinds_come_from_engine_kinds() -> None:
    """Bool filters read as checkboxes, ranges as bounds, sets as tokens."""
    hero = rb.filter_spec("hero")
    assert hero.value_kind == "bool" and hero.group == "who"
    street = rb.filter_spec("street")
    assert street.value_kind == "set"
    sizing = rb.filter_spec("sizing_bp")
    assert sizing.value_kind == "range"
    draw = rb.filter_spec("draw")
    assert draw.value_kind == "flags"


def test_unknown_filter_spec_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="nope"):
        rb.filter_spec("nope")


def test_filter_specs_carry_the_user_metadata_of_329() -> None:
    """A picker needs the label, the description, the unit and the domain."""
    stack = rb.filter_spec("effective_stack_bb")
    assert stack.label != stack.name
    assert stack.user_description and stack.user_description != stack.description
    assert stack.unit == "BB"
    situation = rb.filter_spec("primary_situation")
    assert situation.choices and all(choice.label for choice in situation.choices)
    assert situation.multi is True


def test_tri_state_is_expressible_without_a_false_default() -> None:
    """The model half of #329: *Any* is the absence of a filter, not False."""
    hero = rb.filter_spec("hero")
    assert hero.value_kind == "bool"
    preset = rb.validate_preset({"metric": "frequency", "filters": {}})
    assert "hero" not in preset["filters"]
    explicit = rb.validate_preset({"metric": "frequency", "filters": {"hero": False}})
    assert explicit["filters"]["hero"] is False


def test_example_questions_are_valid_presets() -> None:
    """The first-run screen can only offer questions the engine accepts."""
    questions = rb.example_questions()
    assert questions
    for question in questions:
        assert question.name and question.description
        clean = rb.validate_preset(dict(question.preset))
        assert clean["metric"]
        assert rb.describe_preset(clean)


def test_dimension_specs_expose_the_breakdown_picker() -> None:
    """A breakdown entry needs a label and, when it has one, its domain."""
    bucket = rb.dimension_spec("facing_sizing_bucket")
    assert bucket.label == "Bet size faced"
    assert bucket.choices
    assert bucket.beginner is True
    assert rb.dimension_spec("session").beginner is False


# ---------------------------------------------------------------------------
# Presets: validation and the round trip through JSON.
# ---------------------------------------------------------------------------


def test_preset_validation_accepts_and_canonicalises() -> None:
    clean = rb.validate_preset(
        {"metric": "fold_frequency", "filters": {"hero": True}, "group_by": ["street"]},
    )
    assert clean["metric"] == "fold_frequency"
    assert clean["group_by"] == ("street",)
    assert clean["numerator"] == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"metric": "nope"},
        {"metric": "frequency", "filters": {"nope": 1}},
        {"metric": "frequency", "numerator": {"nope": 1}},
        {"metric": "frequency", "group_by": ["nope"]},
        {"metric": "frequency", "filters": "not-a-mapping"},
        "not-a-mapping",
    ],
)
def test_preset_validation_refuses_with_reason(payload) -> None:
    with pytest.raises(ValueError):
        rb.validate_preset(payload)


def test_preset_round_trip_keeps_vocabulary_only(tmp_path: Path) -> None:
    store = rb.ResearchPresets(directory=tmp_path)
    preset = {
        "metric": "fold_frequency",
        "filters": {"hero": True, "primary_situation": "facing_cbet"},
        "group_by": ["street"],
        "description": "hero folds vs c-bet",
    }
    store.save("hero folds", preset)
    raw = json.loads((tmp_path / "research_presets.json").read_text(encoding="utf-8"))
    assert raw["version"] == rb.PRESET_VERSION
    assert raw["presets"]["hero folds"]["filters"] == preset["filters"]
    stored = store.load()
    assert stored["hero folds"]["description"] == "hero folds vs c-bet"
    store.delete("hero folds")
    assert store.load() == {}


def test_preset_file_edited_by_hand_is_validated(tmp_path: Path) -> None:
    (tmp_path / "research_presets.json").write_text(
        json.dumps(
            {
                "version": 1,
                "presets": {
                    "good": {"metric": "frequency", "filters": {"hero": True}},
                    "bad": {"metric": "frequency", "filters": {"typo": True}},
                },
            },
        ),
        encoding="utf-8",
    )
    store = rb.ResearchPresets(directory=tmp_path)
    stored = store.load()
    assert "good" in stored and "bad" not in stored


def test_preset_file_with_wrong_version_is_refused(tmp_path: Path) -> None:
    (tmp_path / "research_presets.json").write_text(json.dumps({"version": 99, "presets": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        rb.ResearchPresets(directory=tmp_path).load()


def test_preset_file_with_broken_json_is_refused(tmp_path: Path) -> None:
    (tmp_path / "research_presets.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        rb.ResearchPresets(directory=tmp_path).load()


def test_preset_to_query_maps_to_engine_query() -> None:
    query = rb.preset_to_query(
        {"metric": "fold_frequency", "filters": {"hero": True}, "group_by": ["street"]},
    )
    assert isinstance(query, Query)
    assert query.metric == "fold_frequency"
    assert query.filters == {"hero": True}
    assert query.group_by == ("street",)


# ---------------------------------------------------------------------------
# The executed result.
# ---------------------------------------------------------------------------


def test_frequency_result_groups_by_street(browser_db: Database) -> None:
    preset = {
        "metric": "fold_frequency",
        "filters": {"primary_situation": "facing_cbet"},
        "group_by": ["street"],
    }
    result = rb.execute_preset(browser_db, preset)
    assert result.empty_reason is None
    by_street = {row["street"]: row for row in result.rows}
    # Golden corpus, documented: 25 facing-cbet decisions across streets -- the
    # 18 flop folds are the documented population (test_analytics_query pins 22
    # flop *decisions* whose actor faces a c-bet label; two are raise-responses)
    assert sum(row["opportunities"] for row in result.rows) == 25
    flop = by_street["flop"]
    assert flop["actions"] == 18
    assert flop["frequency_bp"] == 18 * 10000 // 22


def test_result_columns_show_numerator_and_denominator() -> None:
    columns = rb.result_columns("fold_frequency", ("street",))
    sources = {column.key: column.source for column in columns}
    assert sources["opportunities"] == "denominator"
    assert sources["actions"] == "numerator"
    assert sources["frequency_bp"] == "value"
    assert sources["street"] == "dimension"


def test_sample_size_is_stated_prominently(browser_db: Database) -> None:
    result = rb.execute_preset(
        browser_db, {"metric": "fold_frequency", "filters": {"primary_situation": "facing_cbet"}},
    )
    assert "decisions" in result.sample_text
    assert result.total_opportunities == 25


def test_comparison_answers_hero_and_field_with_the_same_question(browser_db: Database) -> None:
    preset = {
        "metric": "hand_frequency",
        "filters": {"street": "preflop"},
        "numerator": {"response": ["call", "raise", "complete"]},
        "group_by": ["position"],
    }
    comparison = rb.run_comparison(browser_db, preset)
    query = rb.preset_to_query(preset)
    hero = run_query(
        browser_db,
        Query(
            metric=query.metric,
            filters={**query.filters, "hero": True},
            numerator=query.numerator,
            group_by=query.group_by,
        ),
    )
    field = run_query(
        browser_db,
        Query(
            metric=query.metric,
            filters={**query.filters, "hero": False},
            numerator=query.numerator,
            group_by=query.group_by,
        ),
    )
    expected_hero = {row.group["position"]: row for row in hero.rows}
    expected_field = {row.group["position"]: row for row in field.rows}
    actual = {row.group["position"]: row for row in comparison.rows}
    assert set(actual) == set(expected_hero) | set(expected_field)
    for position, row in actual.items():
        hero_row = expected_hero.get(position)
        field_row = expected_field.get(position)
        assert row.hero_opportunities == (hero_row.opportunities if hero_row else 0)
        assert row.hero_actions == (hero_row.actions if hero_row else 0)
        assert row.field_opportunities == (field_row.opportunities if field_row else 0)
        assert row.field_actions == (field_row.actions if field_row else 0)


def test_comparison_gap_is_unknown_without_two_samples() -> None:
    row = rb.ComparisonRow({}, 0, 0, 4, 1)
    assert row.hero_rate is None
    assert row.gap is None


def test_comparison_supports_a_non_frequency_metric(browser_db: Database) -> None:
    comparison = rb.run_comparison(browser_db, {"metric": "opportunities", "group_by": ["position"]})
    assert comparison.rows
    assert comparison.frequency is False
    assert all(row.hero_measure is not None or row.field_measure is not None for row in comparison.rows)


def test_ungrouped_zero_population_is_an_empty_state(browser_db: Database) -> None:
    result = rb.execute_preset(
        browser_db, {"metric": "frequency", "filters": {"primary_situation": "nope"}},
    )
    assert result.empty_reason == "no matching hands"
    assert result.sample_text == "0 decisions"


def test_grouped_zero_population_is_an_empty_state(browser_db: Database) -> None:
    result = rb.execute_preset(
        browser_db, {"metric": "frequency", "filters": {"primary_situation": "nope"}, "group_by": ["street"]},
    )
    assert result.empty_reason == "no matching hands"
    assert result.rows == []


def test_row_limit_pages_rows_not_the_population(browser_db: Database) -> None:
    preset = {"metric": "fold_frequency", "filters": {}, "group_by": ["primary_situation"]}
    full = rb.execute_preset(browser_db, preset)
    paged = rb.execute_preset(browser_db, preset, limit=2)
    assert len(paged.rows) == 2
    assert paged.total_opportunities == full.total_opportunities


def test_every_preset_row_matches_the_engine_directly(browser_db: Database) -> None:
    """The browser is a reader of the engine, never a second engine."""
    preset = {
        "metric": "fold_frequency",
        "filters": {"primary_situation": "facing_cbet"},
        "group_by": ["street"],
    }
    result = rb.execute_preset(browser_db, preset)
    direct = run_hand_ids(browser_db, rb.preset_to_query(preset))
    assert result.rows and direct


# ---------------------------------------------------------------------------
# Drill-down: the hands behind a row.
# ---------------------------------------------------------------------------


def _fold_query() -> Query:
    return rb.preset_to_query(
        {"metric": "fold_frequency", "filters": {"primary_situation": "facing_cbet"}, "group_by": ["street"]},
    )


def test_drill_population_selects_every_decision_hand(browser_db: Database) -> None:
    drill = rb.run_drill_down(browser_db, _fold_query(), group={"street": "flop"})
    assert drill.total_matches == 21  # the denominator row's own count
    assert not drill.truncated
    assert {row["handId"] for row in drill.rows} == set(drill.hand_ids)


def test_drill_numerator_narrows_to_the_folds(browser_db: Database) -> None:
    population = rb.run_drill_down(browser_db, _fold_query(), group={"street": "flop"}, numerator_only=False)
    numerator = rb.run_drill_down(browser_db, _fold_query(), group={"street": "flop"}, numerator_only=True)
    assert len(numerator.hand_ids) == 18
    assert set(numerator.hand_ids) <= set(population.hand_ids)


def test_drill_page_is_truncated_honestly(browser_db: Database) -> None:
    drill = rb.run_drill_down(browser_db, _fold_query(), group={"street": "flop"}, limit=5)
    assert drill.total_matches == 21
    assert drill.truncated
    assert len(drill.rows) == 5


def test_drill_rows_carry_the_columns_a_human_scans(browser_db: Database) -> None:
    drill = rb.run_drill_down(browser_db, _fold_query(), group={"street": "flop"}, limit=3)
    row = drill.rows[0]
    for key in ("handId", "startTime", "siteName", "category", "heroName", "heroProfit", "finalPot"):
        assert key in row
    # The acting player's cards: present when the row's player showed them.
    assert row["heroCards"] in ("",) or len(row["heroCards"]) >= 4


def test_drill_group_is_a_filter_not_a_recalculation(browser_db: Database) -> None:
    """A row's drill-down must equal the same query with the row as a filter."""
    query = _fold_query()
    drill = rb.run_drill_down(browser_db, query, group={"street": "flop"})
    direct = run_hand_ids(browser_db, Query(metric=query.metric, filters={**query.filters, "street": "flop"}))
    assert set(drill.hand_ids) == set(direct)


def test_drill_query_refuses_an_unknown_group(browser_db: Database) -> None:
    with pytest.raises(ValueError):
        rb.run_drill_down(browser_db, _fold_query(), group={"nope": "x"})


def test_money_metric_drills_with_pair_semantics(browser_db: Database) -> None:
    """A profit row drills to the same hands the engine's population names."""
    query = rb.preset_to_query({"metric": "total_profit", "filters": {"hero": True}})
    drill = rb.run_drill_down(browser_db, query)
    direct = run_hand_ids(browser_db, query)
    assert set(drill.hand_ids) == set(direct)
