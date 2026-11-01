"""Unit tests for the GridAdapter (report-grid compilation of descriptors).

Pure tests: they check the generated SQL fragments, column specs, and the
derived-value computation from a fetched row, without touching a database.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import stat_registry as sr
from fpdb_3_legacy.stat_adapters import GridAdapter, dimension_predicate


@pytest.fixture()
def registry():
    reg = sr.StatRegistry()
    reg.load_directory(sr.default_stats_dir())
    return reg


class TestDimensionPredicate:
    def test_seats_and_position_char(self, registry):
        # 3-handed small blind -> position stored as 'S' in HandsPlayers.
        pred = dimension_predicate(registry.get("chipev_3h_sb"))
        assert pred == "h.seats = 3 AND hp.position = 'S'"

    def test_button_position_quoted_as_char(self, registry):
        # Logical button 0 must become the CHAR literal '0', not bare 0.
        pred = dimension_predicate(registry.get("chipev_3h_btn"))
        assert pred == "h.seats = 3 AND hp.position = '0'"

    def test_no_dimension_is_empty(self, registry):
        assert dimension_predicate(registry.get("chipev_tourney")) == ""


class TestSelectFragments:
    def test_dimensioned_sum_case(self, registry):
        adapter = GridAdapter()
        frags = adapter.select_fragments(registry.get("chipev_hu_bb"))
        assert frags == [
            "SUM(CASE WHEN h.seats = 2 AND hp.position = 'B' THEN hp.allInEV ELSE 0 END) AS \"chipev_hu_bb__allInEV\"",
        ]

    def test_context_input_not_aggregated(self, registry):
        # cnt_tourneys is context -> no SUM(CASE...) emitted for it.
        adapter = GridAdapter()
        frags = adapter.select_fragments(registry.get("chipev_tourney"))
        assert len(frags) == 1
        assert "allInEV" in frags[0]
        assert "cnt_tourneys" not in frags[0]

    def test_boolean_inputs_use_portable_true_count(self, registry):
        adapter = GridAdapter()
        frags = adapter.select_fragments(registry.get("cbet_flop"))
        assert frags == [
            'SUM(CASE WHEN hp.street1CBDone THEN 1 ELSE 0 END) AS "cbet_flop__street1CBDone"',
            'SUM(CASE WHEN hp.street1CBChance THEN 1 ELSE 0 END) AS "cbet_flop__street1CBChance"',
        ]
        assert all("SUM(hp." not in fragment for fragment in frags)

    def test_select_clause_has_leading_comma(self, registry):
        adapter = GridAdapter()
        clause = adapter.select_clause(registry.series_for_scope("tour"))
        assert clause.startswith(", ")
        assert clause.count("SUM(CASE WHEN") == 5


class TestComputeAndFormat:
    def test_dimensioned_value_scaled(self, registry):
        adapter = GridAdapter()
        d = registry.get("chipev_3h_sb")
        # Aggregated allInEV (x100) of 12345 -> 123.45 chips, formatted "%0.0f".
        row = {"chipev_3h_sb__allInEV": 12345}
        assert adapter.compute(d, row) == pytest.approx(123.45)
        assert adapter.augment_row([d], row) == {"chipev_3h_sb": "123"}

    def test_context_value_division(self, registry):
        adapter = GridAdapter()
        d = registry.get("chipev_tourney")
        row = {"chipev_tourney__allInEV": 200000, "cnt_tourneys": 40}
        # 200000/100/40 = 50
        assert adapter.compute(d, row) == pytest.approx(50.0)

    def test_zero_context_denominator_placeholder(self, registry):
        adapter = GridAdapter()
        d = registry.get("chipev_tourney")
        row = {"chipev_tourney__allInEV": 200000, "cnt_tourneys": 0}
        assert adapter.augment_row([d], row) == {"chipev_tourney": "-"}

    def test_column_spec_shape(self, registry):
        adapter = GridAdapter()
        spec = adapter.column_spec(registry.get("chipev_3h_sb"))
        assert spec == ["chipev_3h_sb", True, "ChipEV 3-handed SB", 1.0, "%s", "str"]
