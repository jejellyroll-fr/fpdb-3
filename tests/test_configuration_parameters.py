"""The settings fpdb hands to the HUD and to the importer.

Configuration turns HUD_config.xml into the dictionaries the rest of the
application reads. Almost every field is wrapped in its own try/except with its
own fallback, so a setting a user never wrote still has a value -- and a
fallback that is wrong is invisible until the HUD behaves oddly.

Nothing here touches the configuration of whoever runs the tests: every Config
is built from a copy of the shipped file, made in the test's own directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import Config

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "HUD_config.xml"


@pytest.fixture
def config(tmp_path) -> Any:
    """The shipped configuration, copied so nothing writes back to it."""
    mine = tmp_path / "HUD_config.xml"
    shutil.copy(SHIPPED, mine)
    return Config(file=str(mine))


# --------------------------------------------------------------------------
# What the HUD is told
# --------------------------------------------------------------------------


def test_the_shipped_configuration_answers_with_usable_settings(config) -> None:
    hui = config.get_hud_ui_parameters()

    assert hui["label"]
    assert isinstance(hui["card_ht"], int)
    assert isinstance(hui["hud_days"], int)


def test_a_setting_that_was_never_written_falls_back(config) -> None:
    # An older configuration, or one edited by hand, carries none of these.
    config.ui = SimpleNamespace()

    hui = config.get_hud_ui_parameters()

    assert hui["card_ht"] == 42
    assert hui["card_wd"] == 30
    assert hui["deck_type"] == "colour"
    assert hui["card_back"] == "back04"
    assert hui["hud_days"] == 90
    assert hui["agg_bb_mult"] == 1
    assert hui["seats_style"] == "A"
    assert hui["seats_cust_nums_low"] == 1
    assert hui["seats_cust_nums_high"] == 10


def test_the_hero_settings_have_their_own_fallbacks(config) -> None:
    # The hero is shown a shorter window than everyone else by default.
    config.ui = SimpleNamespace()

    hui = config.get_hud_ui_parameters()

    assert hui["h_stat_range"] == "S"
    assert hui["h_hud_days"] == 30
    assert hui["h_agg_bb_mult"] == 1
    assert hui["h_seats_style"] == "A"
    assert hui["h_seats_cust_nums_low"] == 1
    assert hui["h_seats_cust_nums_high"] == 10


def test_the_settings_that_were_written_are_the_ones_returned(config) -> None:
    config.ui = SimpleNamespace(
        label="My menu",
        card_ht="60",
        card_wd="45",
        deck_type="simple",
        card_back="back01",
        stat_range="T",
        hud_days="7",
        agg_bb_mult="3",
        seats_style="E",
        seats_cust_nums_low="4",
        seats_cust_nums_high="8",
    )

    hui = config.get_hud_ui_parameters()

    assert hui["label"] == "My menu"
    assert hui["card_ht"] == 60
    assert hui["deck_type"] == "simple"
    assert hui["stat_range"] == "T"
    assert hui["hud_days"] == 7
    assert hui["seats_cust_nums_high"] == 8


def test_an_empty_menu_label_is_replaced(config) -> None:
    # A blank label leaves the HUD menu with nothing to right-click.
    config.ui = SimpleNamespace(label="")

    assert config.get_hud_ui_parameters()["label"] == "FPDB Menu - Right click\nLeft-Drag to Move"


@pytest.mark.parametrize(
    ("field", "fallback"),
    [
        ("card_ht", 42),
        ("card_wd", 30),
        ("hud_days", 90),
        ("agg_bb_mult", 1),
        ("h_hud_days", 30),
        ("seats_cust_nums_low", 1),
        ("seats_cust_nums_high", 10),
        ("h_seats_cust_nums_low", 1),
        ("h_seats_cust_nums_high", 10),
        ("xshift", 0),
        ("yshift", 0),
        ("update_interval", 10),
        ("max_seats", 10),
        ("query_limit", 1000),
        ("profile_min_hands", 10),
    ],
)
def test_a_number_that_is_not_one_falls_back(config, field, fallback) -> None:
    # These reach the config as text and are converted here; a hand-edited
    # file can hold anything.
    config.ui = SimpleNamespace(**{field: "not a number"})

    assert config.get_hud_ui_parameters()[field] == fallback


def test_the_appearance_settings_have_fallbacks(config) -> None:
    config.ui = SimpleNamespace()

    hui = config.get_hud_ui_parameters()

    assert hui["bgcolor"] == "#000000"
    assert hui["fgcolor"] == "#FFFFFF"
    assert hui["font"] == "Sans"
    assert hui["opacity"] == "1.0"
    assert hui["tooltip_bgcolor"] == "#FFFFE0"


def test_the_behaviour_settings_have_fallbacks(config) -> None:
    config.ui = SimpleNamespace()

    hui = config.get_hud_ui_parameters()

    assert hui["update_interval"] == 10
    assert hui["max_seats"] == 10
    assert hui["query_limit"] == 1000
    assert hui["profile_min_hands"] == 10
    assert hui["disable_hud"] == "False"
    assert hui["on_click"] == "Nothing"


def test_a_written_appearance_setting_is_returned_as_written(config) -> None:
    config.ui = SimpleNamespace(bgcolor="#123456", font_size="14", max_seats="6")

    hui = config.get_hud_ui_parameters()

    assert hui["bgcolor"] == "#123456"
    assert hui["font_size"] == "14"
    assert hui["max_seats"] == 6


def test_an_unwritten_stat_range_comes_back_as_true_rather_than_all_time(config) -> None:
    # Observed, not intended: stat_range is assigned twice in the reader, and
    # the second assignment defaults to "True", which is not one of the three
    # values the setting takes (A/S/T). Nothing breaks -- the database maps any
    # unrecognised value onto the same key as "A" -- but the documented default
    # is unreachable when the attribute is missing.
    config.ui = SimpleNamespace()

    assert config.get_hud_ui_parameters()["stat_range"] == "True"


# --------------------------------------------------------------------------
# Writing settings back
# --------------------------------------------------------------------------


def hud_ui_node(config: Any) -> Any:
    return config.doc.getElementsByTagName("hud_ui")[0]


def test_a_setting_is_written_onto_the_document(config) -> None:
    config.set_hud_ui_parameters({"label": "Written", "card_ht": 55})

    node = hud_ui_node(config)
    assert node.getAttribute("label") == "Written"
    assert node.getAttribute("card_ht") == "55"


def test_the_stored_names_are_not_the_names_of_the_settings(config) -> None:
    # The dictionary the HUD uses and the attributes the file carries were
    # never named alike, and the two have to keep matching for a saved setting
    # to be read back.
    config.set_hud_ui_parameters({"hud_days": 7, "agg_bb_mult": 3, "h_stat_range": "T"})

    node = hud_ui_node(config)
    assert node.getAttribute("stat_days") == "7"
    assert node.getAttribute("aggregation_level_multiplier") == "3"
    assert node.getAttribute("hero_stat_range") == "T"


def test_a_setting_that_was_not_offered_is_left_alone(config) -> None:
    before = hud_ui_node(config).getAttribute("card_ht")

    config.set_hud_ui_parameters({"label": "Only the label"})

    assert hud_ui_node(config).getAttribute("card_ht") == before


def test_the_node_is_created_when_the_configuration_has_none(config) -> None:
    node = hud_ui_node(config)
    node.parentNode.removeChild(node)

    config.set_hud_ui_parameters({"label": "Fresh"})

    assert hud_ui_node(config).getAttribute("label") == "Fresh"


def test_a_written_setting_is_read_back_without_reloading(config) -> None:
    # The write reaches the parsed settings as well as the document, so the
    # running HUD picks the value up straight away.
    config.set_hud_ui_parameters({"label": "Written", "hud_days": 7})

    hui = config.get_hud_ui_parameters()
    assert hui["label"] == "Written"
    assert hui["hud_days"] == 7


MIRRORED = {
    "label": "Menu",
    "card_ht": 60,
    "card_wd": 45,
    "deck_type": "simple",
    "card_back": "back01",
    "stat_range": "T",
    "hud_days": 7,
    "agg_bb_mult": 3,
    "seats_style": "E",
    "seats_cust_nums_low": 4,
    "seats_cust_nums_high": 8,
    "h_stat_range": "A",
    "h_hud_days": 14,
    "h_agg_bb_mult": 2,
    "h_seats_style": "C",
    "h_seats_cust_nums_low": 2,
    "h_seats_cust_nums_high": 9,
    "player_profiling": "False",
    "profile_in_name": "False",
    "profile_min_hands": 25,
}


@pytest.mark.parametrize("field", sorted(MIRRORED))
def test_every_hud_setting_reaches_the_running_hud(config, field) -> None:
    # The numbers are stored as text, the way the file holds them, so the
    # comparison is on the text either way.
    config.set_hud_ui_parameters(MIRRORED)

    assert str(getattr(config.ui, field)) == str(MIRRORED[field])


def test_saving_settings_leaves_them_readable_as_a_whole(config) -> None:
    config.set_hud_ui_parameters(MIRRORED)

    hui = config.get_hud_ui_parameters()

    assert hui["card_ht"] == 60
    assert hui["h_seats_cust_nums_high"] == 9
    assert hui["profile_min_hands"] == 25


def test_settings_can_be_written_before_the_file_was_parsed(config) -> None:
    # A configuration built for a first run has no parsed settings to mirror
    # onto, and writing must still reach the document.
    del config.ui

    config.set_hud_ui_parameters({"label": "First run"})

    assert hud_ui_node(config).getAttribute("label") == "First run"


@pytest.mark.parametrize(
    ("field", "written", "stale"),
    [("bgcolor", "#123456", "#000000"), ("font", "Courier", "Sans"), ("opacity", "0.5", "1.0")],
)
def test_an_appearance_setting_only_reaches_the_file(config, field, written, stale) -> None:
    # Two dozen settings -- the colours, the font, the opacity, max_seats,
    # update_interval -- are written onto the document but not onto the parsed
    # settings beside it, so they hold their old value until fpdb loads the
    # configuration again.
    config.set_hud_ui_parameters({field: written})

    assert hud_ui_node(config).getAttribute(field) == written
    assert config.get_hud_ui_parameters()[field] == stale


# --------------------------------------------------------------------------
# What the importer is told
# --------------------------------------------------------------------------


def test_the_shipped_configuration_answers_with_import_settings(config) -> None:
    imp = config.get_import_parameters()

    assert "callFpdbHud" in imp
    assert imp["ResultsDirectory"]
    assert "timezone" in imp


def test_an_import_setting_that_was_never_written_falls_back(config) -> None:
    config.imp = SimpleNamespace(ResultsDirectory="")

    imp = config.get_import_parameters()

    assert imp["callFpdbHud"] is True
    assert imp["interval"] == 10
    assert imp["sessionTimeout"] == 30
    assert imp["importFilters"] == []
    assert imp["timezone"] == "America/New_York"
    assert imp["saveActions"] is False


def test_no_results_directory_falls_back_to_the_default_one(config) -> None:
    config.imp = SimpleNamespace(ResultsDirectory="")

    assert config.get_import_parameters()["ResultsDirectory"] == "~/.fpdb/Results/"


def test_a_results_directory_that_was_set_is_kept(config) -> None:
    config.imp = SimpleNamespace(ResultsDirectory="/tmp/results")

    assert config.get_import_parameters()["ResultsDirectory"] == "/tmp/results"


def test_a_missing_results_directory_is_the_one_setting_that_stops_the_read(config) -> None:
    # Every other field falls back when absent; this one is read outside the
    # try/except that protects the rest, so it takes the whole call down.
    config.imp = SimpleNamespace()

    with pytest.raises(AttributeError):
        config.get_import_parameters()


# --------------------------------------------------------------------------
# The dumps used when reporting a configuration problem
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("section", "prefix"),
    [
        ("supported_sites", "Site = "),
        ("supported_databases", "Database = "),
        ("aux_windows", "Aux = "),
        ("stat_sets", "Name = "),
        ("layout_sets", "Layout set = "),
        ("supported_games", "Supported_games = "),
    ],
)
def test_a_section_dumps_itself_by_name(config, section, prefix) -> None:
    entries = getattr(config, section)
    assert entries, f"the shipped configuration has no {section}"

    dumped = str(next(iter(entries.values())))

    assert dumped.startswith(prefix)


def test_a_site_dump_names_its_settings(config) -> None:
    site = config.supported_sites["PokerStars"]

    dumped = str(site)

    assert "site_name = PokerStars" in dumped
    assert "enabled = " in dumped


def test_a_stat_set_dump_lists_the_stats_it_holds(config) -> None:
    stat_set = next(entry for entry in config.stat_sets.values() if entry.stats)

    dumped = str(stat_set)

    assert "_stat_name = " in dumped


def test_a_layout_set_dump_describes_each_table_size(config) -> None:
    layout_set = next(entry for entry in config.layout_sets.values() if entry.layout)

    dumped = str(layout_set)

    assert "max" in dumped
    assert "width=" in dumped


# --------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------
#
# main() builds a Config of its own from whatever the machine has, so every
# test here stands one in -- otherwise the output depends on the configuration
# of whoever runs the suite.


@pytest.fixture
def stub_config() -> Any:
    stub = MagicMock()
    stub.supported_sites = {"PokerStars": SimpleNamespace(enabled=True)}
    stub.supported_games = {"holdem": SimpleNamespace()}
    stub.supported_databases = {
        "fpdb": SimpleNamespace(db_server="sqlite", db_desc="Default", db_selected=True),
    }
    stub.get_hud_ui_parameters.return_value = {"label": "menu"}
    for empty in ("aux_windows", "layout_sets", "stat_sets", "hhcs", "popup_windows"):
        setattr(stub, empty, {})
    with patch.object(config_module, "Config", return_value=stub), patch.object(config_module, "set_logfile"):
        yield stub


def test_no_argument_at_all_prints_the_help(capsys) -> None:
    assert config_module.main([]) == 0

    assert "usage:" in capsys.readouterr().out


def test_validating_reports_what_was_loaded(stub_config, capsys) -> None:
    assert config_module.main(["--validate"]) == 0

    printed = capsys.readouterr().out
    assert "loaded successfully" in printed
    assert "Sites: 1" in printed


def test_the_sites_are_listed_with_their_state(stub_config, capsys) -> None:
    assert config_module.main(["--show-sites"]) == 0

    assert "PokerStars: ✓ enabled" in capsys.readouterr().out


def test_a_disabled_site_is_shown_as_disabled(stub_config, capsys) -> None:
    stub_config.supported_sites = {"Winamax": SimpleNamespace(enabled=False)}

    config_module.main(["--show-sites"])

    assert "Winamax: ✗ disabled" in capsys.readouterr().out


def test_the_databases_are_listed(stub_config, capsys) -> None:
    assert config_module.main(["--show-databases"]) == 0

    assert "fpdb: sqlite (Default) ✓ default" in capsys.readouterr().out


def test_everything_is_shown_at_once(stub_config, capsys) -> None:
    assert config_module.main(["--show-all"]) == 0

    printed = capsys.readouterr().out
    assert "Configured Sites" in printed
    assert "Supported Games" in printed
    assert "Database Configurations" in printed


def test_a_configuration_that_will_not_load_is_reported_rather_than_raised(capsys) -> None:
    with (
        patch.object(config_module, "Config", side_effect=OSError("no such file")),
        patch.object(config_module, "set_logfile"),
    ):
        assert config_module.main(["--validate"]) == 1

    assert "Error loading configuration" in capsys.readouterr().out


def test_the_interactive_run_walks_every_section(stub_config, capsys) -> None:
    with patch.object(config_module.sys, "stdin", SimpleNamespace(readline=lambda: "\n")):
        assert config_module.main(["--interactive"]) == 0

    assert "Running original interactive test" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Re-reading the file into the object already in use
# --------------------------------------------------------------------------
#
# reload() is what the preferences dialog and the auto-import window call once
# they have written a change, so it is the step that decides whether a saved
# setting takes effect before fpdb is restarted.


def rewrite(config: Any, old: str, new: str) -> None:
    """Change the file under the object's feet, the way saving does."""
    path = Path(config.file)
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")


def test_a_change_made_to_the_file_is_picked_up(config) -> None:
    rewrite(config, "<hud_ui ", '<hud_ui bgcolor="#ABCDEF" ')

    assert config.reload() is True
    assert config.ui.bgcolor == "#ABCDEF"


def test_every_section_is_read_again(config) -> None:
    sections = ("supported_sites", "supported_games", "supported_databases", "aux_windows", "layout_sets", "stat_sets")
    before = {name: len(getattr(config, name)) for name in sections}

    config.reload()

    assert {name: len(getattr(config, name)) for name in sections} == before
    assert all(before.values())


def test_an_entry_that_is_no_longer_in_the_file_is_dropped(config) -> None:
    # Without the clearing step a removed site would linger for the rest of
    # the session.
    config.supported_sites["A Room That Was Removed"] = object()

    config.reload()

    assert "A Room That Was Removed" not in config.supported_sites


def test_a_file_that_is_no_longer_valid_xml_is_refused(config) -> None:
    Path(config.file).write_text("<this is not closed", encoding="utf-8")

    assert config.reload() is False


def test_the_settings_in_use_survive_a_refused_reload(config) -> None:
    before = len(config.supported_sites)
    Path(config.file).write_text("<this is not closed", encoding="utf-8")

    config.reload()

    assert len(config.supported_sites) == before


def test_a_file_that_is_gone_is_refused(config) -> None:
    Path(config.file).unlink()

    assert config.reload() is False


def test_a_failure_partway_through_leaves_the_settings_half_loaded(config) -> None:
    # The sections are emptied first and refilled one by one, so a section
    # that will not parse leaves the ones after it empty. reload() reports the
    # failure, but none of its four callers look at the return value, so what
    # they carry on with is a configuration with no popup windows.
    assert config.popup_windows

    with patch.object(config_module, "Popup", side_effect=ValueError("unreadable node")):
        assert config.reload() is False

    assert config.supported_sites
    assert config.popup_windows == {}


def test_a_configuration_without_a_general_section_falls_back_to_defaults(config) -> None:
    rewrite(config, "<general", "<general_disabled")
    rewrite(config, "</general", "</general_disabled")

    assert config.reload() is True
    assert config.general


def test_an_appearance_setting_takes_effect_once_it_is_saved_and_read_back(config) -> None:
    # The colours are written onto the document alone, so this is the whole
    # round trip a user makes: change it, save it, reload it.
    config.set_hud_ui_parameters({"bgcolor": "#654321"})
    config.save()

    assert config.reload() is True
    assert config.get_hud_ui_parameters()["bgcolor"] == "#654321"
