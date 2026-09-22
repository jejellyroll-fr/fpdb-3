"""Offscreen UI checks for the synchronized Study dashboard (#361)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GuiResearchDistributions import DistributionChartWidget
from fpdb_3_legacy.GuiStudyDashboard import GuiStudyDashboard
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_studies import builtin_studies
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from tests.helpers import analytics_golden as golden

pytestmark = pytest.mark.qt


@pytest.fixture(scope="module")
def dashboard_db(tmp_path_factory) -> Database:
    tmp = tmp_path_factory.mktemp("study-dashboard-gui")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _STATE.append(importer)
    return db


_STATE: list[object] = []


def test_dashboard_has_one_study_context_and_lazy_panel_tabs(qtbot, dashboard_db: Database, tmp_path) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    assert dashboard.title_label.text() == "SRP · PFR IP · Flop"
    assert dashboard.tabs.count() == 7
    assert dashboard.comparison_combo.currentData() == "hero_vs_field"
    assert "position" in dashboard._variable_edits
    dashboard._variable_edits["position"].setText("btn")
    next(button for button in dashboard.findChildren(type(dashboard.refresh_button)) if button.text() == "Apply variables").click()
    assert dashboard.model.panel_query("hands").filters["position"] == "btn"
    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)
    assert dashboard._pages["overview"][1].rowCount() > 0


def test_stale_panel_result_cannot_render_into_a_different_active_panel(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    stale_fingerprint = dashboard.model.fingerprint("overview")
    dashboard.model.set_active_panel("hands")
    dashboard._serial = 1
    dashboard._panel_done((object(), None), 1, stale_fingerprint)

    assert stale_fingerprint not in dashboard._results


def test_effective_stack_variable_uses_stored_hundredths_of_bb() -> None:
    assert GuiStudyDashboard._parse_variable("effective_stack_bb", "80,120") == [8000.0, 12000.0]
    assert GuiStudyDashboard._parse_variable("stake_bb", "0.25,1") == [0.25, 1.0]
    assert GuiStudyDashboard._parse_variable("max_seats", "6") == [6, 6]
    assert GuiStudyDashboard._parse_variable("max_seats", "6,9") == [6, 9]


def test_cross_filter_is_visible_reversible_and_shared(qtbot, dashboard_db: Database, tmp_path) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)
    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)

    dashboard.add_cross_filter("board_pairing", "paired", "Paired boards")
    assert len(dashboard.model.state.cross_filters) == 1
    assert any("Paired boards" in button.text() for button in dashboard.findChildren(type(dashboard.refresh_button)))
    assert dashboard.model.panel_query("hands").filters["board_pairing"] == "paired"

    # Re-rendering with more than one filter must preserve both fixed controls:
    # the label remains first and the spacer remains last (#393).
    dashboard.add_cross_filter("response", "fold", "Response: fold")
    assert dashboard.filter_row.itemAt(0).widget().text() == "Active cross-filters:"
    assert {button.text() for button in dashboard.findChildren(type(dashboard.refresh_button))} >= {
        "Paired boards ×",
        "Response: fold ×",
    }

    dashboard.remove_cross_filter("board_pairing")
    assert tuple(item.name for item in dashboard.model.state.cross_filters) == ("response",)
    assert "board_pairing" not in dashboard.model.panel_query("hands").filters
    dashboard.remove_cross_filter("response")
    assert dashboard.model.state.cross_filters == ()


def test_distribution_chart_is_real_comparative_and_clickable(qtbot) -> None:
    from fpdb_3_legacy.research_distributions import build_distribution

    def fake_result(count: int, response: str = "fold"):
        row = type(
            "Row",
            (),
            {
                "as_dict": lambda self: {
                    "response": response,
                    "opportunities": count,
                    "actions": 0,
                    "value": count,
                    "unit": "count",
                    "frequency_bp": None,
                },
            },
        )()
        return type(
            "Result",
            (),
            {"rows": [row], "compiled": type("Compiled", (), {"metric": "opportunities"})()},
        )()

    chart = DistributionChartWidget()
    qtbot.addWidget(chart)
    hero = build_distribution(fake_result(3), "response")
    field = build_distribution(fake_result(1, "call"), "response")
    clicked: list[tuple[str, object, str]] = []
    chart.bin_clicked.connect(lambda name, value, label: clicked.append((name, value, label)))

    chart.set_comparison(hero, field)
    assert len(chart._bar_items) == 2
    assert [item.label for item in chart._bins] == ["fold", "call"]
    assert "Hero: 3 decisions" in chart.summary_label.text()
    assert "Field: 1 decisions" in chart.summary_label.text()

    chart.click_bin(0)
    assert clicked == [("response", "fold", "fold")]


def test_dashboard_renders_response_chart_and_turns_bar_click_into_shared_filter(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_defender_oop_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)
    chart = dashboard._distribution_widgets["overview"]
    assert len(chart._bar_items) == 2
    assert chart._bins

    expected_response = chart._bins[0].filter_value
    chart.click_bin(0)
    assert dashboard.model.state.cross_filters[0].name == "response"
    assert dashboard.model.state.cross_filters[0].value == expected_response


def test_dashboard_renders_position_matrix_and_click_filters_both_axes(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("preflop_facing_open", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    dashboard.model.set_active_panel("position")
    dashboard._load_active_panel()
    matrix = dashboard._matrix_widgets["position"]
    qtbot.waitUntil(lambda: matrix.table.rowCount() > 0 and matrix.table.columnCount() > 0, timeout=15000)
    populated = next(cell for cell in matrix._cells.values() if cell.opportunities > 0)
    row_index = matrix._row_values.index(populated.row_key)
    column_index = matrix._column_values.index(populated.column_key)

    matrix.click_cell(row_index, column_index)

    filters = {item.name: item.value for item in dashboard.model.state.cross_filters}
    assert filters[populated.filter_names[0]] == populated.row_key
    assert filters[populated.filter_names[1]] == populated.column_key


def test_dashboard_switches_hand_state_dimension_and_cross_filters_category(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_oop_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)
    dashboard.model.set_active_panel("strength")
    dashboard._load_active_panel()
    widget = dashboard._hand_strength_widgets["strength"]
    qtbot.waitUntil(lambda: "classified" in dashboard.sample_label.text(), timeout=15000)
    assert "coverage" in widget.coverage_label.text()

    widget.dimension_combo.setCurrentIndex(widget.dimension_combo.findData("draw"))
    qtbot.waitUntil(
        lambda: dashboard.model.panel("strength").dimension == "draw"
        and widget._hero is not None
        and widget._hero.dimension == "draw",
        timeout=15000,
    )
    category = next(category for category in widget._hero.categories if category.filter_name)
    expected_name = category.filter_name
    expected_value = category.filter_value
    widget.click_category(widget._categories.index(category))

    assert dashboard.model.state.cross_filters[0].name == expected_name
    assert dashboard.model.state.cross_filters[0].value == expected_value


def test_source_hands_open_both_sides_of_the_panel_population(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    """A study panel drills into hero and field without leaving comparison (#366)."""
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_pfr_ip_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    pane = dashboard.source_hands
    qtbot.waitUntil(lambda: pane.page is not None, timeout=15000)
    hero_query = dashboard.model.side_query("overview", True)
    field_query = dashboard.model.side_query("overview", False)
    context = dashboard.model.drill_context("overview")

    assert context.side_query("hero").filters == hero_query.filters
    assert context.side_query("field").filters == field_query.filters
    assert context.sides_agree()
    assert pane.current_target.side == "hero"

    pane.select_target("field")
    qtbot.waitUntil(lambda: pane.page is not None and pane.page.side == "field", timeout=15000)
    assert pane.page.side == "field"
    dashboard.close()


def test_a_visual_selection_reaches_both_sides_of_the_source_hands(
    qtbot,
    dashboard_db: Database,
    tmp_path,
) -> None:
    """Clicking a bar narrows hero and field identically, not only the chart (#366)."""
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_defender_oop_flop", remember=False)
    dashboard = GuiStudyDashboard(db=dashboard_db, selection=selection)
    qtbot.addWidget(dashboard)

    qtbot.waitUntil(lambda: "Hero:" in dashboard.sample_label.text(), timeout=15000)
    chart = dashboard._distribution_widgets["overview"]
    expected = chart._bins[0].filter_value
    chart.click_bin(0)

    qtbot.waitUntil(
        lambda: dashboard.source_hands._context is not None
        and dashboard.source_hands._context.side_query("hero").filters.get("response") == expected,
        timeout=15000,
    )
    context = dashboard.source_hands._context
    assert context.side_query("field").filters["response"] == expected
    assert context.sides_agree()

    dashboard.remove_cross_filter("response")
    assert "response" not in dashboard.source_hands._context.side_query("field").filters
    dashboard.close()
