"""Which columns the cash-game report shows, and in what order.

The ring-game results table is described by a list of columns: the database
field, the heading, whether it shows in the plain and the positional views, the
format, and the alignment. The player rearranges that in the GUI and
save_gui_cash_stats puts it back into the configuration.

Reading it back is not symmetrical with writing it, which is the part worth
knowing: a column taken off the list comes back on the next start, because
loading appends any default the file does not mention. What survives is how
each column is shown, not whether it exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config, GUICashStats

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

# database field, heading, shown plainly, shown by position, format, type, alignment
MINE = [
    ["game", "Jeu", False, True, "%s", "str", 0.0],
    ["vpip", "VPIP", True, False, "%3.1f", "str", 1.0],
]


def config_xml(columns: str = "") -> str:
    section = f"<gui_cash_stats>{columns}</gui_cash_stats>" if columns else ""
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"{section}\n</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"

    def make(columns: str = "") -> Config:
        path.write_text(config_xml(columns), encoding="utf-8")
        return Config(file=str(path))

    return make


@pytest.fixture
def config(build) -> Any:
    return build()


def written(config: Any) -> list[dict[str, str]]:
    """The columns as the document now holds them."""
    return [
        {name: node.getAttribute(name) for name in node.attributes.keys()}
        for node in config.doc.getElementsByTagName("col")
    ]


def reopened(config: Any) -> Config:
    """Read the file again from scratch; reload() does not cover this section."""
    config.save()
    return Config(file=config.file)


# --------------------------------------------------------------------------
# Writing the list down
# --------------------------------------------------------------------------


def test_each_column_becomes_an_entry(config) -> None:
    config.gui_cash_stats[:] = MINE

    config.save_gui_cash_stats()

    assert [entry["col_name"] for entry in written(config)] == ["game", "vpip"]


def test_everything_about_a_column_is_written(config) -> None:
    # A missing attribute is not an error on the way back in, it is a silent
    # fallback to a default, so a half-written column shows up as the wrong
    # column rather than as a failure.
    config.gui_cash_stats[:] = MINE

    config.save_gui_cash_stats()

    assert written(config)[0] == {
        "col_name": "game",
        "col_title": "Jeu",
        "disp_all": "False",
        "disp_posn": "True",
        "field_format": "%s",
        "field_type": "str",
        "xalignment": "0.0",
    }


def test_the_order_chosen_is_the_order_written(config) -> None:
    # It is the order of the columns in the report, so it is the whole point
    # of rearranging them.
    config.gui_cash_stats[:] = [MINE[1], MINE[0]]

    config.save_gui_cash_stats()

    assert [entry["col_name"] for entry in written(config)] == ["vpip", "game"]


def test_a_configuration_with_no_such_section_gains_one(config) -> None:
    assert config.doc.getElementsByTagName("gui_cash_stats") == []

    config.save_gui_cash_stats()

    assert len(config.doc.getElementsByTagName("gui_cash_stats")) == 1


def test_saving_twice_replaces_rather_than_appends(config) -> None:
    # Every change in the GUI comes through here; keeping the old entries
    # would show each column once per save.
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()

    config.gui_cash_stats[:] = [MINE[0]]
    config.save_gui_cash_stats()

    assert [entry["col_name"] for entry in written(config)] == ["game"]


def test_the_columns_already_in_the_file_are_replaced_too(build) -> None:
    config = build(
        '<col col_name="hand" col_title="Main" disp_all="True" disp_posn="True"'
        ' field_format="%s" field_type="str" xalignment="0.0"/>'
    )
    config.gui_cash_stats[:] = MINE

    config.save_gui_cash_stats()

    assert [entry["col_name"] for entry in written(config)] == ["game", "vpip"]


def test_an_empty_list_leaves_no_columns_behind(config) -> None:
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()

    config.gui_cash_stats[:] = []
    config.save_gui_cash_stats()

    assert written(config) == []


# --------------------------------------------------------------------------
# Reading it back
# --------------------------------------------------------------------------


def test_how_a_column_is_shown_survives_the_file(config) -> None:
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()

    columns = {col[0]: col for col in reopened(config).gui_cash_stats}

    assert columns["game"] == ["game", "Jeu", False, True, "%s", "str", 0.0]
    assert columns["vpip"] == ["vpip", "VPIP", True, False, "%3.1f", "str", 1.0]


def test_the_chosen_columns_come_first(config) -> None:
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()

    back = reopened(config).gui_cash_stats

    assert [col[0] for col in back[:2]] == ["game", "vpip"]


def test_a_column_left_out_comes_back_on_the_next_start(config) -> None:
    # Loading appends every default the file does not mention, so the list can
    # be reordered and relabelled but not shortened. Someone wondering why a
    # column they removed is back is looking at this.
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()

    back = reopened(config).gui_cash_stats

    assert len(back) == len(GUICashStats.DEFAULTS)
    assert "hand" in {col[0] for col in back}


def test_a_column_hidden_rather_than_removed_stays_hidden(config) -> None:
    # Which is how the list is meant to be shortened: the column keeps its
    # place and stops being displayed.
    config.gui_cash_stats[:] = [["game", "Game", False, False, "%s", "str", 0.0]]
    config.save_gui_cash_stats()

    back = {col[0]: col for col in reopened(config).gui_cash_stats}

    assert back["game"][2:4] == [False, False]


def test_saving_nothing_at_all_restores_every_default(config) -> None:
    # The file then mentions no column, and loading treats that the same way
    # as a configuration that never had the section.
    config.gui_cash_stats[:] = []
    config.save_gui_cash_stats()

    assert len(reopened(config).gui_cash_stats) == len(GUICashStats.DEFAULTS)


def test_a_configuration_without_the_section_starts_from_the_defaults(config) -> None:
    assert config.doc.getElementsByTagName("gui_cash_stats") == []

    assert len(config.gui_cash_stats) == len(GUICashStats.DEFAULTS)


def test_rereading_the_configuration_does_not_touch_this_list(config) -> None:
    # Observed: reload() re-reads every other section but not this one, so the
    # report keeps the columns it had until fpdb is started again.
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()
    config.save()

    assert config.reload() is True

    assert len(config.gui_cash_stats) == len(MINE)


def test_the_written_file_holds_what_was_chosen(config) -> None:
    config.gui_cash_stats[:] = MINE
    config.save_gui_cash_stats()
    config.save()

    written_out = Path(config.file).read_text(encoding="utf-8")
    assert 'col_name="game"' in written_out
    assert 'col_title="Jeu"' in written_out


def test_the_report_is_handed_the_list_itself(config) -> None:
    # The GUI edits what it is given in place and then asks for it to be
    # saved, so this has to be the list and not a copy of it.
    config.gui_cash_stats[:] = MINE

    handed = config.get_gui_cash_stat_params()

    assert handed is config.gui_cash_stats
