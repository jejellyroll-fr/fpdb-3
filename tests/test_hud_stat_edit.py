"""What an edit of a stat writes back, without a window (#763, B1 and B3)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.modern_hud_preferences import stat_edit


# --- Reading and writing a threshold -----------------------------------------
@pytest.mark.parametrize(
    ("text", "value"),
    [("12.5", 12.5), ("140", 140.0), (" -5 ", -5.0), ("0", 0.0), ("1e3", 1000.0)],
)
def test_parse_reads_any_number(text, value) -> None:
    assert stat_edit.parse(text) == value


@pytest.mark.parametrize("text", [None, "", "  ", "abc", "nan", "inf", "-inf"])
def test_parse_reads_no_number_from_anything_else(text) -> None:
    assert stat_edit.parse(text) is None


@pytest.mark.parametrize(
    ("value", "text"),
    [(12.5, "12.5"), (140.0, "140"), (0.0, "0"), (-0.0, "0"), (-5.25, "-5.25"), (33.333, "33.33"), (0.001, "0")],
)
def test_format_value_drops_trailing_zeros(value, text) -> None:
    assert stat_edit.format_value(value) == text


def test_shown_value_falls_back_and_clamps() -> None:
    assert stat_edit.shown_value("", 20.0) == 20.0
    assert stat_edit.shown_value("abc", 60.0) == 60.0
    assert stat_edit.shown_value("140", 60.0) == 140.0
    assert stat_edit.shown_value("1e12", 60.0) == stat_edit.MAXIMUM
    assert stat_edit.shown_value("-1e12", 20.0) == stat_edit.MINIMUM


def test_the_inputs_are_not_capped_at_100() -> None:
    assert stat_edit.MAXIMUM > 100
    assert stat_edit.MINIMUM < 0
    assert stat_edit.DECIMALS >= 1


@pytest.mark.parametrize(
    ("stat", "expected"),
    [
        ({}, False),
        ({"stat_loth": "", "stat_hith": ""}, False),
        ({"stat_loth": " ", "stat_hith": None}, False),
        ({"stat_locolor": "#ff0000"}, False),
        ({"stat_loth": "0"}, True),
        ({"stat_hith": "140"}, True),
    ],
)
def test_has_thresholds(stat, expected) -> None:
    assert stat_edit.has_thresholds(stat) is expected


# --- Keeping the stored string -----------------------------------------------
@pytest.mark.parametrize("stored", ["12.5", "140", "12.345", "1e3", "abc", " 7 "])
def test_an_untouched_threshold_keeps_its_string(stored) -> None:
    shown = stat_edit.shown_value(stored, 20.0)
    assert stat_edit.stored_text(stored, shown, shown) == stored


def test_a_changed_threshold_stores_the_number_shown() -> None:
    assert stat_edit.stored_text("12.5", 12.5, 150.5) == "150.5"
    assert stat_edit.stored_text("140", 140.0, 100.0) == "100"


def test_a_threshold_with_nothing_stored_stores_the_number_shown() -> None:
    assert stat_edit.stored_text("", 20.0, 20.0) == "20"
    assert stat_edit.stored_text(None, 60.0, 60.0) == "60"


def test_threshold_values_off_clears_both() -> None:
    stored = {"stat_loth": "12.5", "stat_hith": "140"}
    assert stat_edit.threshold_values(stored, False, (12.5, 140.0), (12.5, 140.0)) == {
        "stat_loth": "",
        "stat_hith": "",
    }


def test_threshold_values_on_keeps_what_was_not_touched() -> None:
    stored = {"stat_loth": "12.5", "stat_hith": "140"}
    assert stat_edit.threshold_values(stored, True, (12.5, 140.0), (12.5, 250.0)) == {
        "stat_loth": "12.5",
        "stat_hith": "250",
    }


# --- Writing only what changed -----------------------------------------------
def test_changes_lists_only_what_differs() -> None:
    before = {"row": 0, "stat": "vpip", "stat_loth": "12.5", "stat_midcolor": ""}
    after = {"row": 0, "stat": "pfr", "stat_loth": "12.5", "stat_midcolor": "#ffff00"}
    assert stat_edit.changes(before, after) == {"stat": "pfr", "stat_midcolor": "#ffff00"}
    assert stat_edit.changes(after, dict(after)) == {}


def test_apply_changes_does_not_add_empty_attributes() -> None:
    stat = {"stat": "vpip", "stat_loth": "10"}
    assert not stat_edit.apply_changes(stat, {"stat_midcolor": "", "stat_loth": "10"})
    assert stat == {"stat": "vpip", "stat_loth": "10"}


def test_apply_changes_writes_new_and_cleared_values() -> None:
    stat = {"stat": "vpip", "stat_loth": "10"}
    assert stat_edit.apply_changes(stat, {"stat_loth": "", "stat_hicolor": "#00ff00"})
    assert stat == {"stat": "vpip", "stat_loth": "", "stat_hicolor": "#00ff00"}


def test_edit_target_restores_what_the_form_shows_as_loaded() -> None:
    original = {"stat_loth": "12.5", "stat_hith": "140"}
    at_load = {"stat_loth": "12.5", "stat_hith": "140"}
    # The user moved the high threshold, then moved it back: the stat gets its
    # own string back, not the one of the intermediate edit.
    assert stat_edit.edit_target(original, at_load, {"stat_loth": "12.5", "stat_hith": "150"}) == {
        "stat_loth": "12.5",
        "stat_hith": "150",
    }
    assert stat_edit.edit_target(original, at_load, dict(at_load)) == original


def test_edit_target_of_an_attribute_the_stat_lacked_is_empty() -> None:
    assert stat_edit.edit_target({}, {"stat_hith": "60"}, {"stat_hith": "60"}) == {"stat_hith": ""}


# --- The colour preview ------------------------------------------------------
def test_preview_span_is_0_to_100_for_percentages() -> None:
    assert stat_edit.preview_span(20.0, 60.0) == (0.0, 100.0)
    assert stat_edit.preview_span(60.0, 20.0) == (0.0, 100.0)


def test_preview_span_widens_for_a_threshold_above_100() -> None:
    start, end = stat_edit.preview_span(12.5, 140.0)
    assert start == 0.0
    assert end > 140.0


def test_preview_span_widens_for_a_negative_threshold() -> None:
    start, end = stat_edit.preview_span(-5.0, 10.0)
    assert start < -5.0
    assert end == 100.0


# --- Popups to pick from (B15) ---------------------------------------------------
def test_popup_options_list_none_then_the_popups() -> None:
    assert stat_edit.popup_options(["Multicol", "default", "", "default"]) == [
        ("(no popup)", ""),
        ("default", "default"),
        ("Multicol", "Multicol"),
    ]


def test_a_popup_the_configuration_lacks_is_kept_and_marked() -> None:
    options = stat_edit.popup_options(["default"], "gone")
    assert options[-1] == ("gone (missing)", "gone")
    assert stat_edit.popup_options(["default"], "default") == [("(no popup)", ""), ("default", "default")]
