"""What a filtered population was holding (#302): the composition layer.

The rules the tests hold the layer to are the ones that make a composition
readable: the classified decisions partition or overlap exactly as the dimension
says, the decisions with no state are counted separately and never spread over
the categories, every row's count is the engine's own count for that category,
and a row drills down to the hands it counted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy import hand_state_composition as composition
from fpdb_3_legacy.analytics_query import FILTERS, Query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

_TOTAL_DECISIONS = 326
_CLASSIFIED_DECISIONS = 35

_MODULE_STATE: list[object] = []


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("composition")
    config = golden.build_config(tmp)
    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)
    return database


def compose(db: Database, dimension: str, **kwargs) -> composition.Composition:
    return composition.compose(db, Query(metric="opportunities"), dimension, **kwargs)


class TestDimensions:
    """Each dimension declares how its rows add up, and every one is usable."""

    def test_every_dimension_has_a_same_named_filter(self) -> None:
        """A row's category is a filter value, which is what makes it drillable."""
        for name in composition.DIMENSIONS:
            assert name in FILTERS, name

    def test_the_kinds_are_the_three_that_exist(self) -> None:
        assert {spec.kind for spec in composition.DIMENSIONS.values()} == {"partition", "subset", "multi"}

    def test_an_unknown_dimension_is_refused(self, db: Database) -> None:
        with pytest.raises(ValueError, match="Unknown composition dimension"):
            compose(db, "handedness")

    def test_the_categories_come_from_the_classifier(self) -> None:
        published = composition.categories()
        assert published["made_hand"] == composition.MADE_HANDS
        assert "flush_draw" in published["draw"]
        assert "overcard_blocker" in published["blocker"]


class TestPartitions:
    """Single-label dimensions partition the classified population."""

    @pytest.mark.parametrize("dimension", ["made_hand", "made_hand_rank", "nutness", "hand_state_street"])
    def test_the_rows_sum_to_the_classified_population(self, db: Database, dimension: str) -> None:
        report = compose(db, dimension)
        assert sum(row.decisions for row in report.rows) == report.classified == _CLASSIFIED_DECISIONS
        assert sum(row.share_bp or 0 for row in report.rows) == 10000
        assert report.partitions and report.kind == "partition"

    def test_the_unclassified_are_reported_and_counted_nowhere_else(self, db: Database) -> None:
        report = compose(db, "made_hand")
        assert report.total == _TOTAL_DECISIONS
        assert report.classified + report.unclassified == report.total
        assert report.coverage_bp == 1074  # 35 / 326, in basis points
        assert any("no hand state" in note for note in report.notes)
        assert all("not classified" not in row.label for row in report.rows)

    def test_the_made_hand_rows_are_the_corpus_shape(self, db: Database) -> None:
        rows = {row.label: row.decisions for row in compose(db, "made_hand").rows}
        assert rows == {"high_card": 19, "one_pair": 11, "two_pair": 3, "three_of_a_kind": 2}

    def test_a_rank_dimension_is_labelled_like_a_hand(self, db: Database) -> None:
        """The rank column is an int, so the label is the name it stands for."""
        rows = {row.label: row.decisions for row in compose(db, "made_hand_rank").rows}
        assert rows["high_card"] == 19 and None not in rows

    def test_a_subset_dimension_has_a_real_none_bucket(self, db: Database) -> None:
        report = compose(db, "pair_detail")
        rows = {row.label: row.decisions for row in report.rows}
        assert sum(rows.values()) == report.classified == _CLASSIFIED_DECISIONS
        assert rows["(no pair to detail)"] == 21
        assert rows["top_pair"] == 3 and rows["overpair"] == 1
        assert report.kind == "subset" and not report.partitions

    def test_the_counts_are_the_stored_rows(self, db: Database) -> None:
        """A composition figure is a GROUP BY over HandStates, not a recount."""
        c = db.get_cursor()
        c.execute("SELECT madeHand, COUNT(*) FROM HandStates GROUP BY madeHand")
        stored = {row[0]: row[1] for row in c.fetchall()}
        assert {row.label: row.decisions for row in compose(db, "made_hand").rows} == stored


class TestOverlappingDimensions:
    """A decision can have several draws, so those rows do not add up."""

    def test_the_rows_overlap_and_say_so(self, db: Database) -> None:
        report = compose(db, "draw")
        assert report.kind == "multi" and not report.partitions
        total = sum(row.decisions for row in report.rows)
        assert total > report.classified  # every counted decision is counted again
        assert sum(row.share_bp or 0 for row in report.rows) > 10000
        assert any("overlap" in note for note in report.notes)
        assert any("overlap" in note for note in compose(db, "blocker").notes)

    def test_the_flag_counts_are_the_engine_filters(self, db: Database) -> None:
        rows = {row.label: row.decisions for row in compose(db, "draw").rows}
        assert rows["backdoor_straight_draw"] == 18
        assert rows["backdoor_flush_draw"] == 3
        assert rows["gutshot"] == 2
        for name, count in rows.items():
            if name == "(no draw)":
                continue
            filtered = run_query(
                db,
                Query(metric="opportunities", filters={"hand_state_known": True, "draw": [name]}),
            )
            assert filtered.total_opportunities == count

    def test_the_none_row_is_the_complement_of_any_flag(self, db: Database) -> None:
        rows = {row.label: row.decisions for row in compose(db, "draw").rows}
        with_a_draw = run_query(
            db,
            Query(metric="opportunities", filters={"hand_state_known": True, "draw": list(composition.DRAW_BITS)}),
        )
        assert rows["(no draw)"] + with_a_draw.total_opportunities == _CLASSIFIED_DECISIONS

    def test_one_query_per_flag(self, db: Database) -> None:
        """Every flag is asked for as a filter of its own, plus the none case."""
        assert len(compose(db, "draw").compiled) == len(composition.DRAW_BITS) + 1
        assert len(compose(db, "made_hand").compiled) == 1

    def test_blockers_overlap_too(self, db: Database) -> None:
        rows = {row.label: row.decisions for row in compose(db, "blocker").rows}
        assert rows["overcard_blocker"] == 19
        assert rows["(no blocker)"] == 16
        assert sum(rows.values()) > _CLASSIFIED_DECISIONS


class TestPopulation:
    """The composition is of the query's population, unchanged."""

    def test_a_filter_narrows_the_composition(self, db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        report = composition.compose(db, query, "made_hand")
        assert (report.total, report.classified, report.unclassified) == (56, 26, 30)
        assert {row.label for row in report.rows} == {"high_card", "one_pair", "two_pair", "three_of_a_kind"}

    def test_a_query_that_groups_is_refused(self, db: Database) -> None:
        """The dimension *is* the grouping; silently ignoring one would lie."""
        query = Query(metric="opportunities", group_by=("street",))
        with pytest.raises(ValueError, match="groups by its dimension"):
            composition.compose(db, query, "made_hand")

    def test_an_empty_population_is_an_empty_composition(self, db: Database) -> None:
        report = composition.compose(db, Query(metric="opportunities", filters={"player": ["Nobody"]}), "nutness")
        assert (report.total, report.classified, report.coverage_bp) == (0, 0, 0)
        assert report.rows == ()
        assert any("no decision" in note for note in report.notes)

    def test_min_sample_flags_rows_without_hiding_them(self, db: Database) -> None:
        report = compose(db, "made_hand", min_sample=4)
        flagged = {row.label for row in report.rows if row.flagged}
        assert flagged == {"two_pair", "three_of_a_kind"}
        assert sum(row.decisions for row in report.rows) == report.classified


class TestDrilldown:
    """A row's hands are the decisions the row counted."""

    @pytest.mark.parametrize("label", ["high_card", "one_pair", "two_pair"])
    def test_a_category_drills_down_to_its_hands(self, db: Database, label: str) -> None:
        report = compose(db, "made_hand")
        row = next(candidate for candidate in report.rows if candidate.label == label)
        hands = composition.compose_hands(db, "made_hand", label)
        assert len(hands) <= row.decisions
        assert len(set(hands)) == len(hands)
        names = run_query(
            db,
            Query(metric="opportunities", filters={"hand_state_known": True, "made_hand": [label]}),
        )
        assert names.total_opportunities == row.decisions

    def test_the_no_draw_row_drills_down_through_the_none_filter(self, db: Database) -> None:
        rows = {row.label: row.decisions for row in compose(db, "draw").rows}
        hands = composition.compose_hands(db, "draw", None)
        assert len(hands) <= rows["(no draw)"]

    def test_drilling_into_a_partition_dimension_with_no_key_is_refused(self, db: Database) -> None:
        with pytest.raises(ValueError, match="no flag"):
            composition.compose_hands(db, "nutness", None)

    def test_the_hands_are_the_filtered_population(self, db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        hands = composition.compose_hands(db, "made_hand", "one_pair", query)
        assert hands and all(isinstance(hand, int) for hand in hands)


class TestReporting:
    """What a caller (and the CLI) reads out of a composition."""

    def test_as_dict_carries_the_population_and_the_notes(self, db: Database) -> None:
        payload = compose(db, "nutness").as_dict()
        assert payload["dimension"] == "nutness"
        assert payload["total"] == _TOTAL_DECISIONS
        assert payload["classified"] + payload["unclassified"] == payload["total"]
        assert payload["partitions"] is True and payload["kind"] == "partition"
        assert payload["notes"]

    def test_render_names_the_population_it_describes(self, db: Database) -> None:
        text = compose(db, "made_hand").render()
        assert "35 classified decisions of 326" in text
        assert "291 not classified" in text
        assert "high_card" in text

    def test_render_marks_overlapping_rows(self, db: Database) -> None:
        assert "rows overlap" in compose(db, "draw").render()
        assert "rows overlap" not in compose(db, "made_hand").render()

    def test_render_says_when_a_missing_value_is_a_category(self, db: Database) -> None:
        text = compose(db, "pair_detail").render()
        assert "the first row is a category too" in text

    def test_render_can_limit_the_rows_without_changing_the_population(self, db: Database) -> None:
        report = compose(db, "draw")
        text = report.render(limit=3)
        assert report.classified == _CLASSIFIED_DECISIONS
        rows = [
            line
            for line in text.splitlines()
            if line.startswith("  ") and "%" in line and not line.lstrip().startswith("note:")
        ]
        assert len(rows) == 3


def test_a_rank_that_is_not_a_number_still_labels_itself() -> None:
    """The rank column is an int; a caller that hands in something else is told so."""
    assert composition._rank_label(None) == "None"
    assert composition._rank_label("9") == "straight_flush"
    assert composition._rank_label(0) == "rank 0"


def test_the_basis_point_unit_is_the_projects() -> None:
    """Shares are basis points, like every other frequency in the analytics."""
    assert composition.BP == 10000
    assert Path(composition.__file__ or "").name == "hand_state_composition.py"
