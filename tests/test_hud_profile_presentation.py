"""A profile's presentation settings and its HUD window handler, without Qt (#764)."""

from __future__ import annotations

from types import SimpleNamespace

import defusedxml.minidom
import pytest

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.modern_hud_preferences import presentation, profile_io
from tests.helpers.hud_editor import EXAMPLE, config_copy

STANDARD = '<ss name="plain" rows="1" cols="2" xpad="1" ypad="0"><stat _rowcol="(1,1)" _stat_name="vpip"/></ss>'


def _write_back(xml: str, edit) -> tuple[Configuration.Stat_sets, object]:
    """Load ``xml`` as the editor does, apply ``edit``, write it in place, reparse."""
    doc = defusedxml.minidom.parseString(f"<stat_sets>{xml}</stat_sets>")
    node = doc.getElementsByTagName("ss")[0]
    profile = profile_io.profile_from_stat_set(Configuration.Stat_sets(node))
    edit(profile)
    profile_io.write_stat_set_attributes(node, profile)
    return Configuration.Stat_sets(node), node


# --- Mode --------------------------------------------------------------------
@pytest.mark.parametrize("value", ["True", "true", "YES", "1", " on "])
def test_every_spelling_the_hud_accepts_is_rich_text(value) -> None:
    assert presentation.mode_of({"rich_text": value}) == presentation.MODE_RICH


@pytest.mark.parametrize("value", ["", "false", "0", "no", "rich", None])
def test_anything_else_is_standard(value) -> None:
    assert presentation.mode_of({"rich_text": value}) == presentation.MODE_STANDARD


def test_a_list_profile_is_standard() -> None:
    assert presentation.mode_of([]) == presentation.MODE_STANDARD


def test_setting_the_current_mode_keeps_its_spelling() -> None:
    profile = {"rich_text": "yes"}
    presentation.set_mode(profile, presentation.MODE_RICH)
    assert profile["rich_text"] == "yes"
    off = {"rich_text": "false"}
    presentation.set_mode(off, presentation.MODE_STANDARD)
    assert off["rich_text"] == "false"


def test_switching_modes_writes_true_or_clears() -> None:
    profile = {"rich_text": ""}
    presentation.set_mode(profile, presentation.MODE_RICH)
    assert profile["rich_text"] == "True"
    presentation.set_mode(profile, presentation.MODE_STANDARD)
    assert profile["rich_text"] == ""


def test_the_rich_text_warning_is_only_a_field_of_rich_mode() -> None:
    assert "rich_text_support" in presentation.visible_fields(presentation.MODE_RICH)
    assert "rich_text_support" not in presentation.visible_fields(presentation.MODE_STANDARD)
    assert presentation.visible_fields("unknown") == presentation.visible_fields(presentation.MODE_STANDARD)


# --- Font size ---------------------------------------------------------------
@pytest.mark.parametrize(("value", "size"), [("10", 10), ("", 0), ("9.5", 0), ("big", 0), ("-3", 0), (None, 0)])
def test_the_font_size_is_what_the_hud_would_use(value, size) -> None:
    assert presentation.font_size_of({"font_size": value}) == size


def test_setting_the_font_size_clears_it_at_zero() -> None:
    profile = {"font_size": ""}
    presentation.set_font_size(profile, 12)
    assert profile["font_size"] == "12"
    presentation.set_font_size(profile, 0)
    assert profile["font_size"] == ""


def test_an_unchanged_font_size_is_left_as_written() -> None:
    profile = {"font_size": " 10"}
    presentation.set_font_size(profile, 10)
    assert profile["font_size"] == " 10"
    unreadable = {"font_size": "9.5"}
    presentation.set_font_size(unreadable, 0)
    assert unreadable["font_size"] == "9.5"


# --- Writing -----------------------------------------------------------------
def test_rich_text_and_font_size_survive_a_save_and_padding_is_kept() -> None:
    def edit(profile) -> None:
        presentation.set_mode(profile, presentation.MODE_RICH)
        presentation.set_font_size(profile, 11)

    stat_set, _node = _write_back(STANDARD, edit)
    reloaded = profile_io.profile_from_stat_set(stat_set)
    assert presentation.mode_of(reloaded) == presentation.MODE_RICH
    assert presentation.font_size_of(reloaded) == 11
    # No control edits the padding; it is written back as it was read.
    assert (stat_set.xpad, stat_set.ypad) == (1, 0)


def test_switching_back_to_standard_removes_the_attribute() -> None:
    rich = STANDARD.replace('ypad="0"', 'ypad="0" rich_text="True" font_size="10"')

    def edit(profile) -> None:
        presentation.set_mode(profile, presentation.MODE_STANDARD)
        presentation.set_font_size(profile, 0)

    _stat_set, node = _write_back(rich, edit)
    assert not node.hasAttribute("rich_text")
    assert not node.hasAttribute("font_size")


def test_an_untouched_profile_writes_back_identical_attributes() -> None:
    rich = STANDARD.replace('ypad="0"', 'ypad="0" rich_text="true" font_size="10"')

    def edit(profile) -> None:
        presentation.set_mode(profile, presentation.mode_of(profile))
        presentation.set_font_size(profile, presentation.font_size_of(profile))

    _stat_set, node = _write_back(rich, edit)
    assert node.getAttribute("rich_text") == "true"
    assert node.getAttribute("font_size") == "10"
    assert node.getAttribute("xpad") == "1"


# --- Window handlers ---------------------------------------------------------
@pytest.fixture
def example_config(tmp_path):
    if not EXAMPLE.exists():
        pytest.skip("example config missing")
    return Configuration.Config(file=str(config_copy(tmp_path)))


def test_the_handlers_of_a_profile_come_from_its_games(example_config) -> None:
    uses = presentation.hud_handlers_for(example_config, "holdem_ring")
    assert [use.name for use in uses] == ["ClassicHud"]
    assert uses[0].games[:3] == ["holdem", "2_holdem", "irish"]
    assert uses[0].draws_rich_text
    assert uses[0].font_size == 8


def test_a_mucked_cards_window_is_not_a_hud_handler(example_config) -> None:
    names = {use.name for use in presentation.hud_handlers_for(example_config, "stud_default")}
    assert names == {"ClassicHud"}


def test_a_profile_mapped_to_a_dedicated_window_gets_its_font(example_config) -> None:
    uses = presentation.hud_handlers_for(example_config, "plo_pro_html")
    assert [(use.name, use.games, use.font_size) for use in uses] == [("PLO4Hud", ["fusion"], 9)]
    assert presentation.handler_font_size(uses, 8) == 9


def test_a_profile_no_game_uses_has_no_handler(example_config) -> None:
    assert not presentation.hud_handlers_for(example_config, "no-such-profile")


def _fake_config(**aux_windows):
    games = {
        "razz": SimpleNamespace(
            aux="Simple_HUD, mucked, Missing", game_stat_set={"all": SimpleNamespace(stat_set="p")}
        ),
        "studhi": SimpleNamespace(aux="ClassicHud", game_stat_set={"all": SimpleNamespace(stat_set="p")}),
        "holdem": SimpleNamespace(aux=" , ClassicHud", game_stat_set={"ring": SimpleNamespace(stat_set="other")}),
    }
    return SimpleNamespace(supported_games=games, aux_windows={k: SimpleNamespace(**v) for k, v in aux_windows.items()})


def test_handlers_are_read_from_aux_windows_without_a_lookup_method() -> None:
    config = _fake_config(
        Simple_HUD={"module": "Aux_Hud", "class": "Simple_HUD", "font_size": "8"},
        ClassicHud={"module": "Aux_Classic_Hud", "class": "ClassicHud", "font_size": "10"},
        mucked={"module": "Mucked", "class": "Flop_Mucked"},
    )
    uses = presentation.hud_handlers_for(config, "p")
    assert [(use.name, use.games) for use in uses] == [("Simple_HUD", ["razz"]), ("ClassicHud", ["studhi"])]
    assert presentation.handlers_without_rich_text(uses) == ["Simple_HUD"]
    # The two windows disagree, so an unset size cannot be named.
    assert presentation.handler_font_size(uses, 7) == 7


def test_no_configuration_means_no_handler() -> None:
    assert not presentation.hud_handlers_for(None, "p")
