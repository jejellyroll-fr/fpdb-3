"""Rearranging the statistics a HUD block shows.

A stat set is the grid of statistics one HUD window displays, and editStats
replaces that grid wholesale. What makes it more than a list swap is that each
cell carries the player's own settings alongside the statistic -- the colour
thresholds, the popup it opens, the tooltip -- and those have to survive a
rearrangement that leaves the cell where it was.

Configs are built here rather than copied from the shipped file, so the grid
under test is small enough to state in full.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

# A two-by-two grid whose first cell is the one the player has customised.
DECORATED = """<stat _rowcol="(1,1)" _stat_name="vpip" click="tog_decorate" popup="my_popup"
      tip="how often" hudprefix="[" hudsuffix="]" hudcolor="#111111"
      stat_locolor="#222222" stat_loth="20" stat_midcolor="#333333"
      stat_hicolor="#444444" stat_hith="40"/>"""

CUSTOMISED = {
    "click": "tog_decorate",
    "popup": "my_popup",
    "tip": "how often",
    "hudprefix": "[",
    "hudsuffix": "]",
    "hudcolor": "#111111",
    "stat_locolor": "#222222",
    "stat_loth": "20",
    "stat_midcolor": "#333333",
    "stat_hicolor": "#444444",
    "stat_hith": "40",
}


def config_xml(stats: str = "") -> str:
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f'<ss name="mine" rows="2" cols="2">{stats}</ss>\n'
        "</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def config(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"
    path.write_text(config_xml(DECORATED), encoding="utf-8")
    return Config(file=str(path))


def grid(config: Any) -> dict[str, str]:
    """Position -> statistic, as the file now holds it."""
    node = config.getStatSetNode("mine")
    return {stat.getAttribute("_rowcol"): stat.getAttribute("_stat_name") for stat in node.getElementsByTagName("stat")}


def cell(config: Any, rowcol: str) -> Any:
    return next(
        stat
        for stat in config.getStatSetNode("mine").getElementsByTagName("stat")
        if stat.getAttribute("_rowcol") == rowcol
    )


# --------------------------------------------------------------------------
# Replacing the grid
# --------------------------------------------------------------------------


def test_the_statistics_are_the_ones_given(config) -> None:
    config.editStats("mine", [["vpip", "pfr"], ["three_B", "cbet"]])

    assert grid(config) == {"(1,1)": "vpip", "(1,2)": "pfr", "(2,1)": "three_B", "(2,2)": "cbet"}


def test_the_shape_is_recorded_on_the_set(config) -> None:
    # The HUD lays the window out from these two, so a grid that disagrees
    # with them is drawn wrong or not at all.
    config.editStats("mine", [["vpip", "pfr", "cbet"]])

    node = config.getStatSetNode("mine")
    assert (node.getAttribute("rows"), node.getAttribute("cols")) == ("1", "3")


def test_a_smaller_grid_drops_what_no_longer_fits(config) -> None:
    config.editStats("mine", [["vpip", "pfr"], ["three_B", "cbet"]])

    config.editStats("mine", [["vpip"]])

    assert grid(config) == {"(1,1)": "vpip"}


def test_a_bigger_grid_gains_the_new_cells(config) -> None:
    config.editStats("mine", [["vpip"]])

    config.editStats("mine", [["vpip", "pfr"]])

    assert grid(config) == {"(1,1)": "vpip", "(1,2)": "pfr"}


def test_editing_twice_does_not_leave_the_first_grid_behind(config) -> None:
    # Everything under the set is removed before the new stats go in; leaving
    # the old nodes would show each statistic twice.
    config.editStats("mine", [["vpip", "pfr"]])

    config.editStats("mine", [["cbet", "steal"]])

    assert grid(config) == {"(1,1)": "cbet", "(1,2)": "steal"}


# --------------------------------------------------------------------------
# What the player set on each cell
# --------------------------------------------------------------------------


@pytest.mark.parametrize("attribute", sorted(CUSTOMISED))
def test_a_cell_that_stays_put_keeps_its_settings(config, attribute) -> None:
    # Rearranging the grid must not cost the colours and thresholds someone
    # chose; the cell is rebuilt, so they are carried across by hand.
    config.editStats("mine", [["vpip", "pfr"], ["three_B", "cbet"]])

    assert cell(config, "(1,1)").getAttribute(attribute) == CUSTOMISED[attribute]


def test_the_settings_follow_the_position_rather_than_the_statistic(config) -> None:
    # They belong to the cell: putting a different statistic in that place
    # leaves the decoration where it was.
    config.editStats("mine", [["pfr"]])

    assert cell(config, "(1,1)").getAttribute("hudcolor") == "#111111"
    assert cell(config, "(1,1)").getAttribute("_stat_name") == "pfr"


def test_a_cell_that_had_nothing_gets_the_plain_defaults(config) -> None:
    config.editStats("mine", [["vpip", "pfr"]])

    new = cell(config, "(1,2)")
    assert new.getAttribute("popup") == "default"
    assert new.getAttribute("hudcolor") == ""
    assert new.getAttribute("tip") == ""


def test_every_cell_carries_the_whole_set_of_attributes(config) -> None:
    # The preferences window reads them all, and a missing one reads as empty
    # only because getAttribute is forgiving.
    config.editStats("mine", [["vpip"]])

    written = {*CUSTOMISED, "_stat_name", "_rowcol"}
    assert written <= set(cell(config, "(1,1)").attributes.keys())


def test_a_setting_left_empty_does_not_override_the_default(tmp_path, monkeypatch) -> None:
    # Only non-empty values are carried across. A cell whose popup is the
    # empty string -- which is what the preferences window writes when nothing
    # is chosen -- must come back as "default", not as the empty string.
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"
    path.write_text(config_xml('<stat _rowcol="(1,1)" _stat_name="vpip" popup="" hudcolor="#999999"/>'), "utf-8")
    config = Config(file=str(path))

    config.editStats("mine", [["vpip"]])

    assert cell(config, "(1,1)").getAttribute("popup") == "default"
    assert cell(config, "(1,1)").getAttribute("hudcolor") == "#999999"


def test_the_settings_are_kept_across_repeated_edits(config) -> None:
    config.editStats("mine", [["vpip"]])
    config.editStats("mine", [["vpip"]])

    assert cell(config, "(1,1)").getAttribute("popup") == "my_popup"
    assert cell(config, "(1,1)").getAttribute("click") == "tog_decorate"


def test_the_new_grid_survives_being_saved_and_read_again(config) -> None:
    config.editStats("mine", [["vpip", "pfr"]])
    config.save()

    assert config.reload() is True

    assert grid(config) == {"(1,1)": "vpip", "(1,2)": "pfr"}
    assert config.stat_sets["mine"].rows == 1
    assert config.stat_sets["mine"].cols == 2


# --------------------------------------------------------------------------
# Grids and names it cannot work with
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("empty", "shape"), [([], ("0", "0")), ([[]], ("1", "0"))], ids=["no row", "one empty row"])
def test_an_empty_grid_empties_the_set(config, empty, shape) -> None:
    # Both shapes clear it. [] used to raise IndexError instead, the width
    # being read off a first row nobody had checked was there.
    config.editStats("mine", empty)

    node = config.getStatSetNode("mine")
    assert node.getElementsByTagName("stat") == []
    assert (node.getAttribute("rows"), node.getAttribute("cols")) == shape


def test_an_emptied_set_can_be_filled_again(config) -> None:
    config.editStats("mine", [])

    config.editStats("mine", [["vpip", "pfr"]])

    assert grid(config) == {"(1,1)": "vpip", "(1,2)": "pfr"}


def test_a_stat_set_that_does_not_exist_is_named_in_the_error(config) -> None:
    # It used to be an AttributeError on None, which reads like a bug in the
    # caller rather than a name that is not there.
    assert config.getStatSetNode("no-such-set") is None

    with pytest.raises(ValueError, match="No stat set named 'no-such-set'"):
        config.editStats("no-such-set", [["vpip"]])


def test_the_file_is_untouched_when_the_set_is_not_found(config) -> None:
    before = Path(config.file).read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="No stat set"):
        config.editStats("no-such-set", [["vpip"]])

    assert Path(config.file).read_text(encoding="utf-8") == before


def test_the_other_stat_sets_are_untouched_when_the_set_is_not_found(config) -> None:
    with pytest.raises(ValueError, match="No stat set"):
        config.editStats("no-such-set", [["vpip"]])

    assert grid(config) == {"(1,1)": "vpip"}
