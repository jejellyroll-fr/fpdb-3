"""Where the items of a HUD panel sit: the editor's grid rules, without Qt."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.modern_hud_preferences import layout_model as lm


def _stat(name: str, row: int, col: int, colspan: int = 1) -> dict:
    d = {"stat": name, "row": row, "col": col}
    if colspan != 1:
        d["colspan"] = colspan
    return d


def _panel(*stats: dict, rows: int = 2, cols: int = 3, texts=(), hlines=()) -> dict:
    return {"rows": rows, "cols": cols, "stats": list(stats), "texts": list(texts), "hlines": list(hlines)}


# --- Positions and spans -----------------------------------------------------
def test_each_kind_reads_its_own_position_field() -> None:
    assert lm.position("stat", {"row": 2, "col": 1}) == (2, 1)
    assert lm.position("text", {"rowcol": (3, 0)}) == (3, 0)
    assert lm.position("stat", {}) == (0, 0)


@pytest.mark.parametrize(
    ("kind", "ref", "width"),
    [
        ("stat", {}, 1),
        ("stat", {"colspan": 2}, 2),
        ("text", {"colspan": 0}, 1),
        ("hline", {"colspan": 0}, 4),
        ("hline", {}, 4),
        ("hline", {"colspan": 2}, 2),
    ],
)
def test_a_line_without_a_span_covers_the_whole_row(kind, ref, width) -> None:
    assert lm.span(kind, ref, cols=4) == width


def test_occupancy_covers_every_cell_of_a_wide_item() -> None:
    wide = _stat("vpip", 0, 0, colspan=2)
    line = {"rowcol": (1, 0), "colspan": 0}
    taken = lm.occupancy(_panel(wide, hlines=[line]))
    assert taken[(0, 0)] == ("stat", wide)
    assert taken[(0, 1)] == ("stat", wide)
    assert (0, 2) not in taken
    assert {cell for cell, item in taken.items() if item[1] is line} == {(1, 0), (1, 1), (1, 2)}


def test_two_equal_stats_are_still_two_items() -> None:
    a, b = _stat("vpip", 0, 0), _stat("vpip", 0, 0)
    panel = _panel(a, b)
    assert lm.collisions(panel) == [((0, 0), ("stat", a), ("stat", b))]
    assert lm.occupancy(panel, ignore=a)[(0, 0)] == ("stat", b)


def test_occupant_names_the_item_on_a_cell() -> None:
    text = {"rowcol": (1, 2), "label": "PRE"}
    panel = _panel(texts=[text])
    assert lm.occupant(panel, 1, 2) == ("text", text)
    assert lm.occupant(panel, 0, 0) is None


# --- Placing -----------------------------------------------------------------
def test_a_taken_cell_cannot_hold_another_item() -> None:
    vpip = _stat("vpip", 0, 1)
    panel = _panel(vpip)
    assert not lm.can_place(panel, 0, 1)
    assert lm.can_place(panel, 0, 1, ignore=vpip)
    assert lm.can_place(panel, 0, 2)
    assert not lm.can_place(panel, 0, 0, width=2)
    assert not lm.can_place(panel, -1, 0)
    assert not lm.can_place(panel, 0, 0, width=0)


def test_the_first_free_cell_fills_a_hole_before_adding_a_row() -> None:
    panel = _panel(_stat("a", 0, 0), _stat("b", 0, 1), _stat("c", 1, 0), rows=2, cols=2)
    assert lm.first_free_cell(panel) == (1, 1)


def test_a_full_panel_offers_the_row_below() -> None:
    panel = _panel(_stat("a", 0, 0), _stat("b", 0, 1), rows=1, cols=2)
    assert lm.first_free_cell(panel) == (1, 0)


def test_a_wide_item_needs_a_run_of_free_cells() -> None:
    panel = _panel(_stat("a", 0, 1), rows=1, cols=3)
    assert lm.first_free_cell(panel, width=2) == (1, 0)
    assert lm.first_free_cell(panel, width=9) == (1, 0)


def test_items_past_the_declared_rows_are_seen() -> None:
    panel = _panel(_stat("a", 0, 0), _stat("b", 3, 0), rows=1, cols=1)
    assert lm.first_free_cell(panel) == (1, 0)
    assert lm.first_free_row(panel) == 1


def test_adding_grows_the_panel_and_refuses_a_taken_cell() -> None:
    panel = _panel(_stat("a", 0, 0), rows=1, cols=1)
    new = {"stat": "pfr"}
    assert lm.add(panel, "stat", new, 2, 1)
    assert panel["stats"][-1] is new and (new["row"], new["col"]) == (2, 1)
    assert (panel["rows"], panel["cols"]) == (3, 2)
    assert not lm.add(panel, "stat", {"stat": "x"}, 0, 0)
    assert len(panel["stats"]) == 2


def test_a_line_grows_rows_but_not_columns() -> None:
    panel = _panel(rows=1, cols=2)
    assert lm.add(panel, "hline", {"colspan": 0}, 1, 0)
    assert panel["hlines"][0]["rowcol"] == (1, 0)
    assert (panel["rows"], panel["cols"]) == (2, 2)


def test_remove_takes_out_that_item_and_no_equal_one() -> None:
    a, b = _stat("vpip", 0, 0), _stat("vpip", 0, 0)
    panel = _panel(a, b)
    assert lm.remove(panel, b)
    assert panel["stats"] == [a] and panel["stats"][0] is a
    assert not lm.remove(panel, b)


# --- Moving ------------------------------------------------------------------
def test_moving_onto_a_free_cell() -> None:
    a = _stat("a", 0, 0)
    panel = _panel(a, rows=1, cols=2)
    assert lm.move(panel, a, 1, 1) == "moved"
    assert (a["row"], a["col"]) == (1, 1)
    assert panel["rows"] == 2


def test_moving_onto_another_item_swaps_them() -> None:
    a, b = _stat("a", 0, 0), _stat("b", 1, 2)
    panel = _panel(a, b)
    assert lm.move(panel, a, 1, 2) == "swapped"
    assert (a["row"], a["col"], b["row"], b["col"]) == (1, 2, 0, 0)


def test_a_text_and_a_stat_swap() -> None:
    a = _stat("a", 0, 0)
    t = {"rowcol": (1, 1), "label": "PRE"}
    panel = _panel(a, texts=[t])
    assert lm.move(panel, t, 0, 0) == "swapped"
    assert t["rowcol"] == (0, 0) and (a["row"], a["col"]) == (1, 1)


def test_a_wide_item_does_not_swap_into_a_narrow_hole() -> None:
    wide = _stat("wide", 0, 0, colspan=2)
    a, b = _stat("a", 1, 0), _stat("b", 1, 1)
    panel = _panel(wide, a, b, rows=2, cols=2)
    assert lm.move(panel, wide, 1, 0) == "refused"
    assert (wide["row"], a["row"], a["col"], b["col"]) == (0, 1, 0, 1)


def test_a_swap_that_would_overlap_a_third_item_is_refused() -> None:
    a = _stat("a", 0, 0)
    wide = _stat("wide", 1, 0, colspan=2)
    c = _stat("c", 0, 1)
    panel = _panel(a, wide, c, rows=2, cols=2)
    assert lm.move(panel, wide, 0, 0) == "refused"
    assert (a["row"], a["col"], wide["row"], wide["col"]) == (0, 0, 1, 0)


def test_a_narrow_item_does_not_swap_with_a_wide_one_that_would_cover_a_third() -> None:
    wide = _stat("wide", 0, 0, colspan=2)
    b, c = _stat("b", 1, 0), _stat("c", 1, 1)
    panel = _panel(wide, b, c, rows=2, cols=2)
    assert lm.move(panel, b, 0, 0) == "refused"
    assert (wide["row"], wide["col"], b["row"], b["col"]) == (0, 0, 1, 0)


def test_a_legacy_clash_elsewhere_does_not_block_a_swap() -> None:
    a, b = _stat("a", 0, 0), _stat("b", 0, 1)
    twin1, twin2 = _stat("t", 1, 1), _stat("t", 1, 1)
    panel = _panel(a, b, twin1, twin2)
    assert lm.move(panel, a, 0, 1) == "swapped"


@pytest.mark.parametrize("target", [(-1, 0), (0, -1)])
def test_moving_off_the_grid_is_refused(target) -> None:
    a = _stat("a", 0, 0)
    assert lm.move(_panel(a), a, *target) == "refused"


def test_moving_an_item_of_another_panel_is_refused() -> None:
    assert lm.move(_panel(_stat("a", 0, 0)), _stat("a", 0, 0), 1, 1) == "refused"


def test_find_answers_by_identity() -> None:
    a = _stat("a", 0, 0)
    panel = _panel(a)
    assert lm.find(panel, a) == ("stat", a)
    assert lm.find(panel, dict(a)) is None
