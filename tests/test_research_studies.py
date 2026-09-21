"""The declarative, spot-first study model (#359)."""

from __future__ import annotations

from typing import Any

import pytest

from fpdb_3_legacy import research_studies as studies
from fpdb_3_legacy.analytics_profit import ProfitReport
from fpdb_3_legacy.analytics_query import QueryResult
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.hand_state_composition import Composition
from fpdb_3_legacy.holdem_ranges import RangeMatrix
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_browser import DrillDown
from tests.helpers import analytics_golden as golden


@pytest.fixture(scope="module")
def browser_db(tmp_path_factory: pytest.TempPathFactory) -> Database:
    """The golden corpus imported once for the end-to-end study test."""
    tmp = tmp_path_factory.mktemp("research-studies")
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


def _srp_study() -> studies.StudySpec:
    """A complete SRP PFR-IP flop study, expressed only in engine vocabulary."""
    return studies.StudySpec(
        id="srp_pfr_ip_flop",
        title="Single-Raised Pot — PFR IP — Flop",
        path=("postflop", "single_raised", "pfr_ip", "flop"),
        base_filters={
            "game": "holdem",
            "street": "flop",
            "pot_type": "single_raised",
            "is_preflop_aggressor": True,
            "in_position": True,
        },
        variables=("hero", "date_from", "date_to", "effective_stack_bb"),
        panels=(
            studies.StudyPanelSpec("frequency", "C-bet frequency", "frequency", "bet_frequency"),
            studies.StudyPanelSpec(
                "responses",
                "Response distribution",
                "response_distribution",
                group_by=("response",),
            ),
            studies.StudyPanelSpec(
                "sizing",
                "C-bet sizing distribution",
                "sizing_distribution",
                group_by=("sizing_bucket",),
                filters={"response": "bet"},
            ),
            studies.StudyPanelSpec(
                "positions",
                "Position matrix",
                "position_matrix",
                group_by=("position", "opponent_position"),
            ),
            studies.StudyPanelSpec(
                "boards",
                "Board texture",
                "board_matrix",
                group_by=("board_suit", "board_pairing"),
            ),
            studies.StudyPanelSpec(
                "range",
                "Starting-hand range",
                "range_grid",
                metric="opportunities",
                holdem_only=True,
            ),
            studies.StudyPanelSpec("strength", "Hand strength", "hand_strength"),
            studies.StudyPanelSpec("profit", "Profit and EV", "profit", "total_profit"),
            studies.StudyPanelSpec("hands", "Source hands", "hands"),
        ),
        game="holdem",
    )


def test_srp_study_compiles_every_panel_over_one_population() -> None:
    study = _srp_study()
    compiled = study.panels_compiled()

    assert len(compiled) == 9
    assert all(panel.available for panel in compiled)
    assert all(panel.base_filters == study.base_filters for panel in compiled)
    for panel in compiled:
        for name, value in study.base_filters.items():
            assert panel.query.filters[name] == value
    assert {panel.adapter for panel in compiled} == {"query", "range", "composition", "profit", "hands"}


def test_mapping_round_trip_is_declarative() -> None:
    original = _srp_study()
    loaded = studies.StudySpec.from_mapping(original.as_dict())

    assert loaded.as_dict() == original.as_dict()
    serialized = str(original.as_dict()).lower()
    assert "select " not in serialized
    assert "exec(" not in serialized


def test_variables_bind_without_leaving_the_study() -> None:
    bound = _srp_study().bind({"hero": True, "date_from": "2026-01-01"})

    assert bound.base_filters["hero"] is True
    assert bound.base_filters["date_from"] == "2026-01-01"
    assert bound.panel("frequency").query.filters["hero"] is True
    with pytest.raises(studies.StudyValidationError, match="not declared"):
        _srp_study().bind({"site": "PokerStars"})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"base_filters": {"not_a_filter": True}}, "unknown filters"),
        ({"panels": ({"id": "bad", "title": "Bad", "kind": "frequency", "metric": "not_a_metric"},)}, "unknown metric"),
        ({"panels": ({"id": "bad", "title": "Bad", "kind": "frequency", "group_by": ["not_a_dimension"]},)}, "unknown dimensions"),
        ({"variables": ("not_a_filter",)}, "unknown study variables"),
    ],
)
def test_invalid_studies_fail_before_ui_load(change: dict[str, Any], message: str) -> None:
    payload = _srp_study().as_dict()
    payload.update(change)
    with pytest.raises(studies.StudyValidationError, match=message):
        studies.StudySpec.from_mapping(payload)


def test_panel_cannot_silently_redefine_the_population() -> None:
    with pytest.raises(studies.StudyValidationError, match="conflicts"):
        studies.StudySpec(
            id="conflict",
            title="Conflict",
            path=("test",),
            base_filters={"street": "flop"},
            variables=(),
            panels=(
                studies.StudyPanelSpec(
                    "panel",
                    "Panel",
                    "headline",
                    filters={"street": "turn"},
                ),
            ),
        )


def test_opportunity_outcome_mistakes_are_refused() -> None:
    with pytest.raises(studies.StudyValidationError, match="opportunity variant"):
        studies.StudySpec(
            id="self-selecting",
            title="Self selecting",
            path=("test",),
            base_filters={"primary_situation": "cbet"},
            variables=(),
            panels=(studies.StudyPanelSpec("rate", "Rate", "frequency", "bet_frequency"),),
        )
    with pytest.raises(studies.StudyValidationError, match="must declare a response"):
        studies.StudySpec(
            id="unanswered",
            title="Unanswered",
            path=("test",),
            base_filters={},
            variables=(),
            panels=(studies.StudyPanelSpec("rate", "Rate", "frequency", "frequency"),),
        )


def test_holdem_only_panel_has_an_explicit_unavailable_state() -> None:
    study = studies.StudySpec(
        id="omaha-study",
        title="Omaha study",
        path=("postflop",),
        base_filters={"game": "omaha"},
        variables=(),
        panels=(studies.StudyPanelSpec("range", "Range", "range_grid", holdem_only=True),),
        game="omaha",
    )

    panel = study.panel("range")
    assert not panel.available
    assert panel.unavailable_reason and "Hold'em-only" in panel.unavailable_reason


def test_every_panel_adapter_uses_existing_analytics_owners(browser_db: Database) -> None:
    study = _srp_study()
    results = {panel.panel_id: studies.execute_panel(browser_db, panel) for panel in study.panels_compiled()}

    assert isinstance(results["frequency"], QueryResult)
    assert isinstance(results["responses"], QueryResult)
    assert isinstance(results["sizing"], QueryResult)
    assert isinstance(results["positions"], QueryResult)
    assert isinstance(results["boards"], QueryResult)
    assert isinstance(results["range"], RangeMatrix)
    assert isinstance(results["strength"], Composition)
    assert isinstance(results["profit"], ProfitReport)
    assert isinstance(results["hands"], DrillDown)


def test_registry_rejects_duplicate_study_ids() -> None:
    study = _srp_study()
    with pytest.raises(studies.StudyValidationError, match="study ids must be unique"):
        studies.StudyRegistry((study, study))


def test_registry_loads_mapping_definitions() -> None:
    registry = studies.StudyRegistry.from_mappings([_srp_study().as_dict()])

    assert registry.get("srp_pfr_ip_flop").title == "Single-Raised Pot — PFR IP — Flop"


def test_builtin_nlhe_pack_has_a_searchable_hierarchy_and_guidance() -> None:
    (pack,) = studies.load_study_packs()
    registry = pack.registry()
    expected = {
        "preflop_rfi",
        "preflop_facing_open",
        "preflop_facing_3bet",
        "preflop_squeeze",
        "preflop_blind_vs_blind",
        "srp_pfr_ip_flop",
        "srp_pfr_oop_flop",
        "srp_defender_oop_flop",
        "three_bet_pot_aggressor_flop",
        "three_bet_pot_defender_flop",
        "four_bet_pot_flop",
    }

    assert {study.id for study in registry.studies} == expected
    assert all(study.table_size == 6 and study.min_sample for study in registry.studies)
    assert all(study.default_panel in {panel.id for panel in study.panels} for study in registry.studies)
    assert all(study.search_terms for study in registry.studies)
    assert any(any("c-bet" in term for term in study.search_terms) for study in registry.studies)


def test_builtin_nlhe_pack_executes_every_shipped_panel_on_the_golden_corpus(browser_db: Database) -> None:
    registry = studies.builtin_studies()
    executed = 0

    for study in registry.studies:
        for panel in study.panels_compiled():
            result = studies.execute_panel(browser_db, panel)
            assert result is not None, f"{study.id}/{panel.panel_id} did not return a result"
            executed += 1

    assert executed == 68


def test_existing_advanced_presets_remain_available() -> None:
    from fpdb_3_legacy.research_presets import builtin_presets

    assert builtin_presets()
