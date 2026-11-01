"""Integration test: ChipEV curves SQL wiring (no database required).

Validates that the bundled descriptors compile into the tourneyChipEVByPosition
query via GraphAdapter, that no placeholder is left dangling, and that the
filter-substitution shape used by GuiTourneyGraphViewer.getData produces
executable-looking SQL.
"""
from __future__ import annotations

from fpdb_3_legacy import SQL
from fpdb_3_legacy import stat_registry as sr
from fpdb_3_legacy.stat_adapters import GraphAdapter


def _registry():
    reg = sr.StatRegistry()
    reg.load_directory(sr.default_stats_dir())
    return reg


def test_chipev_columns_inject_five_case_expressions():
    reg = _registry()
    adapter = GraphAdapter(alias="hp")
    descriptors = reg.series_for_scope("tour")
    query = SQL.Sql(db_server="sqlite").query["tourneyChipEVByPosition"]
    query = query.replace("<chipev_columns>", adapter.select_clause(descriptors))

    assert "<chipev_columns>" not in query
    # seats lives on Hands (alias h), position on HandsPlayers (alias hp).
    assert query.count("CASE WHEN h.seats") == 5
    assert "hp.position" in query
    for alias in (
        "chipev_3h_btn__allInEV",
        "chipev_3h_sb__allInEV",
        "chipev_3h_bb__allInEV",
        "chipev_hu_sb__allInEV",
        "chipev_hu_bb__allInEV",
    ):
        assert f'"{alias}"' in query


def test_full_substitution_leaves_no_placeholders():
    reg = _registry()
    adapter = GraphAdapter(alias="hp")
    query = SQL.Sql(db_server="sqlite").query["tourneyChipEVByPosition"]
    query = query.replace("<chipev_columns>", adapter.select_clause(reg.series_for_scope("tour")))

    # Mirror GuiTourneyGraphViewer.getData.apply_filters substitutions.
    query = query.replace("<player_test>", "(42)")
    query = query.replace("<site_test>", "(2)")
    query = query.replace("<startdate_test>", "2024-01-01")
    query = query.replace("<enddate_test>", "2025-01-01")
    query = query.replace("<currency_test>", "AND tt.currency in ('EUR','USD')")
    # GuiTourneyGraphViewer.getData replaces the whole "AND ... <placeholder>" line.
    query = query.replace("AND tt.category in <tourney_cat>", "")
    query = query.replace("AND tt.limitType in <tourney_lim>", "")
    query = query.replace("AND tt.buyin in <tourney_buyin>", "")
    query = query.replace(",)", ")")

    # No <..._test> / <tourney_*> / <chipev_columns> placeholders remain. (Bare
    # '<' from the startTime date comparison is a legitimate SQL operator.)
    import re

    assert not re.search(r"<[a-z_]+>", query), query


def test_row_mapping_matches_select_aliases():
    """The aliases the SQL emits are exactly the keys GraphAdapter reads back."""
    reg = _registry()
    adapter = GraphAdapter(alias="hp")
    d = reg.get("chipev_hu_bb")
    # Emulate one fetched row keyed by the SQL alias.
    row = {"chipev_hu_bb__allInEV": 4000}
    assert adapter.series_values(d, [row]) == [40.0]
