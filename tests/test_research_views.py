"""The Research workbench's views (#331): the catalogue and its four shapes.

The analytics engine answers questions; this module is the layer that says which
questions the workbench knows how to *show*, and what each answer looks like.
The tests hold the two things a catalogue of views can get wrong:

* a view that names vocabulary the engine does not have -- caught at import by
  ``_check_catalogue``, and restated here so the failure mode is documented;
* a view whose presentation is a fiction -- a grid that invents cells, a
  composition that distributes cards nobody saw, a money view that reports one
  number where two exist.

Everything runs against the golden corpus in a throwaway SQLite database: no
Qt, no windows.
"""

from __future__ import annotations

from typing import Any

import pytest

from fpdb_3_legacy import player_situations as situations
from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy import research_views as rv
from fpdb_3_legacy.analytics_query import IMPLIED_NUMERATORS
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.holdem_ranges import NotHoldem
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden


def _names(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    return ()


@pytest.fixture(scope="module")
def browser_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("research-views")
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


# ---------------------------------------------------------------------------
# The catalogue.
# ---------------------------------------------------------------------------


def test_the_catalogue_covers_the_views_the_issue_names() -> None:
    """One entry per shape of answer, and nothing advertised that is missing."""
    assert set(rv.VIEW_IDS) == {
        "summary",
        "table",
        "frequencies",
        "sizing",
        "position",
        "board",
        "range",
        "hand_strength",
        "profit",
        "hands",
    }


def test_every_view_starts_from_a_query_the_engine_accepts() -> None:
    """A view is engine vocabulary, so a typo is a broken import, not a blank screen."""
    for spec in rv.VIEWS:
        clean = rv.preset(spec)
        assert clean["metric"] == spec.metric
        assert clean["filters"] == dict(spec.filters)
        # And every view says how to read its own answer.
        assert spec.how_to_read.strip()
        assert spec.question.strip()


def test_a_view_that_names_unknown_vocabulary_is_refused_at_import() -> None:
    """The check the module runs on itself, exercised on a broken catalogue."""
    bad = rv.ViewSpec(
        id="broken",
        label="Broken",
        question="?",
        metric="no_such_metric",
        group_by=(),
        kind=rv.TABLE,
        how_to_read="",
    )
    with pytest.raises(ValueError):
        rb.validate_preset(rv.preset(bad))


def test_an_unknown_kind_is_refused_when_the_view_is_built() -> None:
    with pytest.raises(ValueError, match="unknown view kind"):
        rv.ViewSpec(
            id="broken",
            label="Broken",
            question="?",
            metric="opportunities",
            group_by=(),
            kind="hologram",
            how_to_read="",
        )


def test_an_unknown_view_name_is_refused_with_the_ones_that_exist() -> None:
    with pytest.raises(KeyError) as raised:
        rv.view("no_such_view")
    assert "summary" in str(raised.value)


def test_a_view_is_a_starting_point_not_a_lock(browser_db: Database) -> None:
    """The view's filters are the question; a caller can narrow them further."""
    spec = rv.view("position")
    narrowed = rv.preset(spec, {"hero": True})
    assert narrowed["filters"]["hero"] is True
    assert narrowed["filters"]["primary_situation"] == "facing_open"
    assert narrowed["metric"] == spec.metric


def test_callers_can_replace_the_view_filters_rather_than_add_to_them() -> None:
    """The workbench runs its own controls, so a removed filter must be gone.

    Merging made a default impossible to delete: taking ``primary_situation``
    out of the builder still ran the view's own situation, while the visible
    summary -- built from those same controls -- said it had been removed.
    """
    spec = rv.view("position")
    replaced = rv.preset(spec, {"hero": True}, replace_filters=True)
    assert replaced["filters"] == {"hero": True}
    query = rv.query(spec, {"hero": True}, replace_filters=True)
    assert query.filters == {"hero": True}
    # The default is unchanged: every existing caller keeps the merge.
    assert rv.preset(spec, {"hero": True})["filters"]["primary_situation"] == "facing_open"


# ---------------------------------------------------------------------------
# The summary shape.
# ---------------------------------------------------------------------------


def _run(view_id: str, browser_db: Database, **extra) -> rb.ResearchResult:
    spec = rv.view(view_id)
    return rb.execute_preset(browser_db, rv.preset(spec, extra))


def test_the_summary_view_states_the_number_and_its_sample(browser_db: Database) -> None:
    spec = rv.view("summary")
    result = _run("summary", browser_db)
    summary = rv.summarize(result, spec)
    assert summary.sample_text == result.sample_text
    if result.rows:
        expected = result.rows[0].get("frequency_bp")
        if expected is not None:
            assert summary.value_text == f"{expected / 100:.1f}%"
        # The reading states the fraction, not only the percentage: a rate
        # without its denominator is exactly what the epic refuses to print.
        assert any("of" in note and "decisions" in note for note in summary.notes)
    assert spec.how_to_read in summary.notes


def test_a_grouped_answer_reports_its_shape_not_one_arbitrary_row(browser_db: Database) -> None:
    """A table has as many numbers as rows, so the headline is how many."""
    spec = rv.view("table")
    result = _run("table", browser_db)
    summary = rv.summarize(result, spec)
    if len(result.rows) > 1:
        assert summary.value_text == f"{len(result.rows)} groups"
    assert spec.how_to_read in summary.notes


def test_an_empty_answer_says_why_rather_than_showing_a_zero(browser_db: Database) -> None:
    spec = rv.view("summary")
    result = rb.execute_preset(
        browser_db,
        rv.preset(spec, {"primary_situation": "no_such_situation"}),
    )
    summary = rv.summarize(result, spec)
    assert summary.value_text == "no result"
    assert summary.notes[-1], "an empty answer must state a reason"


# ---------------------------------------------------------------------------
# The grid shape.
# ---------------------------------------------------------------------------


def test_the_grid_is_169_cells_and_reconciles_with_its_query(browser_db: Database) -> None:
    """Every decision the query selected is either in a cell or in the gap."""
    spec = rv.view("range")
    matrix = rv.range_matrix(browser_db, spec)
    cells = matrix.known_cells()
    assert len(cells) == 169
    assert len({cell.class_id for cell in cells}) == 169
    drawn = sum(cell.opportunities for cell in cells)
    assert drawn + matrix.unknown_opportunities() == matrix.total_opportunities
    # A cell says which class it is, in the vocabulary the engine names classes
    # in, so a drill-down from a cell asks the same question the cell answered.
    assert {cell.label for cell in cells} >= {"AA", "AKs", "22"}


def test_the_grid_reports_the_decisions_whose_cards_nobody_saw(browser_db: Database) -> None:
    spec = rv.view("range")
    matrix = rv.range_matrix(browser_db, spec)
    known = sum(cell.opportunities for cell in matrix.known_cells())
    # Unknown cards are reported, never spread over the grid: the two numbers
    # are the population, and one of them has a reason attached.
    assert matrix.unknown_opportunities() == matrix.total_opportunities - known


def test_a_population_that_is_not_holdem_makes_the_grid_unavailable(monkeypatch, browser_db: Database) -> None:
    """An unavailable answer is a reason, not an empty grid."""
    spec = rv.view("range")

    def refuse(*_args, **_kwargs):
        raise NotHoldem("the population contains a game whose two cards are not a Hold'em hand")

    monkeypatch.setattr(rv, "build_range", refuse)
    with pytest.raises(rv.Unavailable, match="not a Hold'em hand"):
        rv.range_matrix(browser_db, spec)


def test_a_table_view_refuses_to_build_a_grid(browser_db: Database) -> None:
    with pytest.raises(rv.Unavailable):
        rv.range_matrix(browser_db, rv.view("sizing"))


# ---------------------------------------------------------------------------
# The composition shape.
# ---------------------------------------------------------------------------


def test_the_composition_splits_the_population_and_counts_the_rest(browser_db: Database) -> None:
    """A composition that hides its unclassified decisions is a lie by omission."""
    spec = rv.view("hand_strength")
    composition = rv.hand_composition(browser_db, spec)
    assert composition.dimension == "made_hand"
    assert composition.total == composition.classified + composition.unclassified
    assert composition.rows, "the golden corpus should have classified decisions"
    if composition.partitions:
        assert sum(row.decisions for row in composition.rows) == composition.classified


def test_a_composition_can_be_asked_over_another_dimension(browser_db: Database) -> None:
    spec = rv.view("hand_strength")
    composition = rv.hand_composition(browser_db, spec, dimension="nutness")
    assert composition.dimension == "nutness"


def test_a_table_view_refuses_to_compose(browser_db: Database) -> None:
    with pytest.raises(rv.Unavailable):
        rv.hand_composition(browser_db, rv.view("table"))


# ---------------------------------------------------------------------------
# The money shape.
# ---------------------------------------------------------------------------


def test_the_money_view_reports_realized_and_ev_adjusted_together(browser_db: Database) -> None:
    spec = rv.view("profit")
    report = rv.money_report(browser_db, spec)
    assert report.group_by == ("position",)
    assert report.total.realized_cents is not None
    assert report.total.ev_adjusted_cents is not None
    # The rows and the total agree, so a reader cannot see two different sums.
    assert report.total.realized_cents == sum(row.realized_cents for row in report.rows)
    assert any("expected value" in note.lower() or "ev" in note.lower() for note in report.notes)


def test_a_table_view_refuses_to_report_money(browser_db: Database) -> None:
    with pytest.raises(rv.Unavailable):
        rv.money_report(browser_db, rv.view("table"))


def test_the_hands_view_is_the_drill_down_of_whatever_is_loaded(browser_db: Database) -> None:
    """It is a presentation, not a question: the query comes from the controls."""
    spec = rv.view("hands")
    assert spec.kind == rv.HANDS
    assert spec.group_by == ()


# ---------------------------------------------------------------------------
# A rate is measured over its opportunities, not over its outcome.
# ---------------------------------------------------------------------------


def test_a_view_never_measures_a_frequency_over_its_own_outcome() -> None:
    """``cbet`` and ``open_raise`` are only assigned when the response already
    was the bet or the raise, so a frequency over them reads 100% on every row
    with data. A view's population has to be the chance, not the result.
    """
    fixes_response = {
        rule.name: set(_names(rule.response))
        for rule in situations.SITUATION_RULES
        if rule.response
    }
    for spec in rv.VIEWS:
        implied = IMPLIED_NUMERATORS.get(spec.metric)
        if implied is None:
            continue
        wanted = set(_names(implied.get("response")))
        for name in _names(spec.filters.get("primary_situation")):
            already = fixes_response.get(name)
            assert not (already and already <= wanted), (
                f"{spec.id}: {spec.metric} over the {name!r} population would read 100%"
            )


def test_the_board_view_asks_over_c_bet_opportunities() -> None:
    spec = rv.view("board")
    assert spec.filters.get("primary_situation") == "cbet_spot"
    presets = situations.SITUATION_RULES
    assert "cbet_spot" in {rule.name for rule in presets}


def test_the_range_view_asks_over_unopened_pots() -> None:
    """Every populated cell of the grid used to read 100% of the hands it held."""
    spec = rv.view("range")
    assert spec.filters == {"pot_type": "unopened"}
    assert rv.preset(spec)["metric"] == "raise_frequency"
