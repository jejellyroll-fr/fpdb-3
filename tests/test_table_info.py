"""The table identity row must tolerate old and new column counts.

Adding ``limitType`` to ``get_table_name`` once broke table detection because
three HUD call sites unpacked a fixed number of values. These tests pin the
property that made that possible: any row shape the HUD can be handed -- a
short historical tuple, the current row, or a longer future one -- resolves to
the same named fields.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy.table_info import TableInfo

LEGACY_ROW = ("table-a", 6, "omahahi", "ring", False, 1, "coinpoker", 6, None, None, None)
CURRENT_ROW = (*LEGACY_ROW, "pl")


def test_current_row_exposes_every_field_by_name() -> None:
    info = TableInfo.coerce(CURRENT_ROW)

    assert info.table_name == "table-a"
    assert info.max_seats == 6
    assert info.poker_game == "omahahi"
    assert info.game_type == "ring"
    assert info.site_name == "coinpoker"
    assert info.num_seats == 6
    assert info.limit_type == "pl"


def test_a_row_written_before_limit_type_still_resolves() -> None:
    """Caches and tests still hold 11-field rows; they must not raise."""
    info = TableInfo.coerce(LEGACY_ROW)

    assert info.table_name == "table-a"
    assert info.game_type == "ring"
    assert info.limit_type == "all"  # the neutral value, matched by ANY rules


def test_a_future_extra_column_does_not_break_existing_fields() -> None:
    """The next column added to the SELECT must not shift any caller."""
    info = TableInfo.coerce((*CURRENT_ROW, "something-new"))

    assert info.table_name == "table-a"
    assert info.limit_type == "pl"


@pytest.mark.parametrize("row", [LEGACY_ROW, CURRENT_ROW])
def test_legacy_index_access_is_preserved(row: tuple) -> None:
    """Untouched call sites still read by index, so the order must not move."""
    info = TableInfo.coerce(row)

    assert info[0] == info.table_name
    assert info[3] == info.game_type
    assert info[5] == info.site_id
    assert info[7] == info.num_seats
    assert info[8] == info.tour_number
    assert info[9] == info.tab_number


def test_coercing_an_already_coerced_row_is_a_no_op() -> None:
    info = TableInfo.coerce(CURRENT_ROW)

    assert TableInfo.coerce(info) is info
