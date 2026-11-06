"""The synchronized Study dashboard contract (#361)."""

from __future__ import annotations

from fpdb_3_legacy.research_studies import builtin_studies
from fpdb_3_legacy.research_study_dashboard import (
    COMPARISON_HERO_VS_FIELD,
    StudyDashboardModel,
)
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel


def _dashboard(tmp_path) -> StudyDashboardModel:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study(
        "srp_pfr_ip_flop",
        context_filters={"game": "holdem", "max_seats": [6, 6], "hero": True},
        remember=False,
    )
    return StudyDashboardModel(selection)


def test_overview_sizing_board_and_hands_share_one_population(tmp_path) -> None:
    dashboard = _dashboard(tmp_path)
    population = dashboard.population_fingerprint()

    assert dashboard.panel_ids() == ("overview", "sizing", "board", "range", "strength", "profit", "hands")
    assert all(dashboard.panel(panel_id).base_filters == dashboard.base_filters for panel_id in ("overview", "sizing", "board", "hands"))
    assert all(dashboard.population_fingerprint() == population for _ in ("overview", "sizing", "board", "hands"))


def test_variables_and_cross_filters_update_every_panel_explicitly(tmp_path) -> None:
    dashboard = _dashboard(tmp_path)
    dashboard.set_variable("position", "btn")
    dashboard.add_cross_filter("board_pairing", "paired", "Paired boards")

    for panel_id in dashboard.panel_ids():
        query = dashboard.panel_query(panel_id)
        assert query.filters["position"] == "btn"
        assert query.filters["board_pairing"] == "paired"

    dashboard.remove_cross_filter("board_pairing")
    assert all("board_pairing" not in dashboard.panel_query(panel_id).filters for panel_id in dashboard.panel_ids())


def test_unknown_cross_filter_becomes_an_explicit_null_predicate(tmp_path) -> None:
    dashboard = _dashboard(tmp_path)

    dashboard.add_cross_filter("board_pairing", None, "Unknown boards")

    assert dashboard.panel_query("overview").filters["board_pairing"] == {"is_null": True}


def test_focus_filter_narrows_hands_without_changing_panel_population(tmp_path) -> None:
    dashboard = _dashboard(tmp_path)
    dashboard.set_focus_filters({"response": "fold"})

    assert dashboard.panel_query("overview").filters.get("response") != "fold"
    assert dashboard.drill_context("overview").query.filters["response"] == "fold"


def test_comparison_is_study_wide_and_uses_the_same_panel_population(tmp_path) -> None:
    dashboard = _dashboard(tmp_path)
    dashboard.set_comparison(COMPARISON_HERO_VS_FIELD)

    hero = dashboard.side_query("overview", True)
    field = dashboard.side_query("overview", False)
    assert hero.filters["hero"] is True
    assert field.filters["hero"] is False
    for name, value in dashboard.base_filters.items():
        if name != "hero":
            assert hero.filters[name] == value
            assert field.filters[name] == value
