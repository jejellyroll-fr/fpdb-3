"""A filter selector must not show a value it is not applying (#353).

The choice selector is a multi-select: an item is ticked in place and the
chosen tokens go to the read-only field beside it, which is what the query
reads. Left as Qt builds it, the combo showed its *first* item, so a filter
just added read as "Situation = open raise" while the query carried no
situation at all. A question narrowed on screen ran against every decision in
the database and answered something else -- 559 decisions instead of 14 on the
database this was found on, with nothing on screen to say why.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy.GuiResearchBrowser import _ChoiceCombo
from fpdb_3_legacy.research_labels import Choice

CHOICES = (
    Choice("open_raise", "open raise (raise first in)"),
    Choice("over_limp", "over-limp behind limpers"),
    Choice("facing_cbet", "facing a continuation bet"),
)


@pytest.fixture
def combo(qapp):
    return _ChoiceCombo(CHOICES)


def test_a_new_selector_shows_nothing_because_it_holds_nothing(combo) -> None:
    assert combo.values() == []
    assert combo.currentIndex() == -1
    assert combo.currentText() == ""


def test_every_item_offers_itself_before_anything_is_chosen(combo) -> None:
    # The marker is what tells "not chosen" from "chosen" at a glance, so it
    # has to be there from the start, not only after the first click.
    assert [combo.itemText(index) for index in range(combo.count())] == [
        "＋ open raise (raise first in)",
        "＋ over-limp behind limpers",
        "＋ facing a continuation bet",
    ]


def test_choosing_an_item_ticks_it_and_yields_its_value(combo) -> None:
    combo._toggle(0)

    assert combo.values() == ["open_raise"]
    assert combo.itemText(0).startswith("✔")
    assert combo.itemText(1).startswith("＋")


def test_choosing_a_second_item_keeps_the_first(combo) -> None:
    combo._toggle(0)
    combo._toggle(2)

    assert combo.values() == ["open_raise", "facing_cbet"]


def test_choosing_a_ticked_item_again_removes_it(combo) -> None:
    combo._toggle(0)
    combo._toggle(0)

    assert combo.values() == []
    assert combo.itemText(0).startswith("＋")


def test_the_selector_never_displays_a_value_it_is_not_applying(combo) -> None:
    """The invariant the bug broke: what is shown is what is asked.

    The display stays blank whatever is ticked -- the ticks and the field
    beside it carry the answer -- so it can never disagree with the query.
    """
    for step in (lambda: None, lambda: combo._toggle(1), lambda: combo._toggle(0), lambda: combo._toggle(1)):
        step()
        assert combo.currentText() == "", combo.values()


def test_a_preset_loaded_into_the_selector_is_ticked(combo) -> None:
    combo.set_values(["facing_cbet"])

    assert combo.values() == ["facing_cbet"]
    assert combo.itemText(2).startswith("✔")
    assert combo.currentText() == ""
