"""A range filter must read back the bounds it was given (#411).

The control holds two number fields, and ``value()`` reads a field sitting at
its minimum as "no bound" -- the state ``setSpecialValueText`` shows blank. Qt
starts a number field at 0 rather than at its minimum, so the two sides
disagreed: a preset's ``[null, 40]`` was written into a field left at 0 and
read back as ``[0, 40]``, narrowing "up to 40 BB" to "0 to 40 BB" the moment
the preset was chosen. The same 0 came back from a row nobody had touched, so
adding a range filter narrowed the question to a stack of exactly nothing.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy.GuiResearchBrowser import _FilterRow


@pytest.fixture
def row(qapp):
    return _FilterRow(rb.filter_spec("effective_stack_bb"))


def test_an_untouched_range_row_asks_for_no_bound(row) -> None:
    assert row.value() is None


def test_a_blank_bound_is_shown_blank(row) -> None:
    # The special value text, not a 0 the reader would take for a bound.
    assert (row.low_spin.text(), row.high_spin.text()) == (" ", " ")


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [([None, 40], [None, 40.0]), ([10, None], [10.0, None]), ([10, 40], [10.0, 40.0])],
)
def test_a_range_loads_back_as_it_was_written(row, bounds, expected) -> None:
    row.set_value(bounds)

    assert row.value() == expected


def test_a_preset_with_one_open_bound_keeps_it(row) -> None:
    preset = rb.validate_preset({"metric": "raise_frequency", "filters": {"effective_stack_bb": [None, 40]}})

    row.set_value(preset["filters"]["effective_stack_bb"])

    assert row.value() == [None, 40.0]
    assert row.high_spin.text().startswith("40")


def test_a_range_with_neither_bound_is_read_back_as_no_filter(row) -> None:
    # Which is why a pack cannot store one: the filter would vanish.
    row.set_value([None, None])

    assert row.value() is None
