"""Remembering where the player dragged the HUD windows.

A layout set holds, per table size, where each seat's stat window sits and how
big the table window was. Dragging a window and saving has to reach two places:
the document, so it is there next time, and the layout already loaded, so the
next table opened in this session uses the new positions rather than the ones
fpdb started with.

That second half is the one worth testing. A save that only reached the file
looks like it worked until a second table opens in the old places.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

LAYOUT = """<layout_sets><ls name="mine">
  <layout max="2" width="100" height="200">
    <location seat="1" x="1" y="2"/>
    <location seat="2" x="3" y="4"/>
    <location common="1" x="5" y="6"/>
  </layout>
  <layout max="6" width="300" height="400">
    <location seat="1" x="7" y="8"/>
  </layout>
</ls></layout_sets>"""


@pytest.fixture
def config(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"
    path.write_text(
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"{LAYOUT}\n</FreePokerToolsConfig>\n",
        encoding="utf-8",
    )
    return Config(file=str(path))


@pytest.fixture
def layout_set(config) -> Any:
    return config.layout_sets["mine"]


def in_use(config: Any, max_seats: int = 2) -> Any:
    """The layout the HUD reads when it opens its next table."""
    return config.layout_sets["mine"].layout[max_seats]


def in_file(config: Any, max_seats: int = 2) -> Any:
    return config.get_layout_node(config.get_layout_set_node("mine"), max_seats)


def seat_in_file(config: Any, seat: int, max_seats: int = 2) -> tuple[str, str]:
    node = config.get_location_node(in_file(config, max_seats), seat)
    return node.getAttribute("x"), node.getAttribute("y")


# --------------------------------------------------------------------------
# Where the seats are
# --------------------------------------------------------------------------


def test_a_moved_seat_reaches_the_file(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12)})

    assert seat_in_file(config, 1) == ("11", "12")


def test_a_moved_seat_reaches_the_layout_already_loaded(config, layout_set) -> None:
    # The point of the exercise: the next table opened in this session has to
    # use the new position without fpdb being restarted.
    config.save_layout_set(layout_set, 2, {1: (11, 12)})

    assert in_use(config).location[1] == (11, 12)


def test_the_seats_left_alone_stay_where_they_were(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12)})

    assert in_use(config).location[2] == (3, 4)
    assert seat_in_file(config, 2) == ("3", "4")


def test_several_seats_move_at_once(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12), 2: (13, 14)})

    assert in_use(config).location[1:] == [(11, 12), (13, 14)]


def test_only_the_table_size_being_saved_is_touched(config, layout_set) -> None:
    # One set holds a layout per table size, and saving a six-max arrangement
    # must not disturb the heads-up one.
    config.save_layout_set(layout_set, 6, {1: (99, 98)})

    assert in_use(config, 6).location[1] == (99, 98)
    assert in_use(config, 2).location[1] == (1, 2)


# --------------------------------------------------------------------------
# The shared window
# --------------------------------------------------------------------------


def test_the_common_window_is_kept_apart_from_the_seats(config, layout_set) -> None:
    # The mucked-cards display is not a seat; it is stored on its own and
    # would otherwise be indexed as one.
    config.save_layout_set(layout_set, 2, {"common": (55, 66)})

    assert in_use(config).common == (55, 66)
    assert in_use(config).location[1] == (1, 2)


def test_the_common_window_reaches_the_file_too(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {"common": (55, 66)})

    node = config.get_location_node(in_file(config), "common")
    assert (node.getAttribute("x"), node.getAttribute("y")) == ("55", "66")


def test_seats_and_the_common_window_can_move_together(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12), "common": (55, 66)})

    assert in_use(config).location[1] == (11, 12)
    assert in_use(config).common == (55, 66)


# --------------------------------------------------------------------------
# The size of the table window
# --------------------------------------------------------------------------


def test_a_resized_table_is_remembered(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12)}, width=800, height=600)

    assert (in_use(config).width, in_use(config).height) == (800, 600)
    assert in_file(config).getAttribute("width") == "800"
    assert in_file(config).getAttribute("height") == "600"


def test_saving_without_a_size_leaves_the_size_alone(config, layout_set) -> None:
    # Saving the mucked display's position comes through here with no size,
    # and it must not blank the one the table already had.
    config.save_layout_set(layout_set, 2, {"common": (55, 66)})

    assert (in_use(config).width, in_use(config).height) == (100, 200)
    assert in_file(config).getAttribute("width") == "100"


@pytest.mark.parametrize("dimension", ["width", "height"])
def test_one_dimension_can_be_saved_without_the_other(config, layout_set, dimension) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12)}, **{dimension: 640})

    assert getattr(in_use(config), dimension) == 640
    assert (in_use(config).width, in_use(config).height) != (640, 640)


def test_a_size_of_zero_is_treated_as_no_size(config, layout_set) -> None:
    # Observed: the width is written only when it is truthy, so a zero reads
    # as "not specified" rather than as a window with no width.
    config.save_layout_set(layout_set, 2, {1: (11, 12)}, width=0, height=0)

    assert (in_use(config).width, in_use(config).height) == (100, 200)


# --------------------------------------------------------------------------
# Round trip and the shapes it cannot save
# --------------------------------------------------------------------------


def test_a_saved_layout_is_read_back_from_the_file(config, layout_set) -> None:
    config.save_layout_set(layout_set, 2, {1: (11, 12), "common": (55, 66)}, width=800, height=600)
    config.save()

    assert config.reload() is True

    reloaded = in_use(config)
    assert reloaded.location[1] == (11, 12)
    assert reloaded.common == (55, 66)
    assert (reloaded.width, reloaded.height) == (800, 600)


def test_saving_nothing_at_all_changes_nothing(config, layout_set) -> None:
    before = Path(config.file).read_text(encoding="utf-8")

    config.save_layout_set(layout_set, 2, {})

    assert in_use(config).location[1] == (1, 2)
    assert Path(config.file).read_text(encoding="utf-8") == before


def test_a_seat_the_layout_does_not_have_cannot_be_saved(config, layout_set) -> None:
    # Observed, and not the failure it looks like. Searching for a seat reads
    # the seat number off every location it passes, including the common one,
    # which has no seat number -- so the search for a seat that is not there
    # runs into int("") before it can answer None.
    #
    # Every layout fpdb ships lists the common location last, so a real seat
    # is always found before that node is reached. It is only reachable by
    # asking for a seat the table does not have.
    with pytest.raises(ValueError, match="invalid literal for int"):
        config.save_layout_set(layout_set, 2, {9: (1, 1)})


def test_looking_up_a_seat_stops_at_the_common_location(config) -> None:
    # The same thing seen directly, so the reason the test above raises what
    # it raises does not have to be inferred from a traceback.
    layout = in_file(config)
    assert config.get_location_node(layout, 1) is not None

    with pytest.raises(ValueError, match="invalid literal for int"):
        config.get_location_node(layout, 9)


def test_a_table_size_the_set_does_not_have_cannot_be_saved(config, layout_set) -> None:
    assert config.get_layout_node(config.get_layout_set_node("mine"), 9) is None

    with pytest.raises(AttributeError):
        config.save_layout_set(layout_set, 9, {1: (1, 1)})


# --------------------------------------------------------------------------
# The two lookups answering "not there"
# --------------------------------------------------------------------------

BARE = """<layout_sets><ls name="bare">
  <layout max="2" width="100" height="200">
    <location seat="1" x="1" y="2"/>
  </layout>
</ls></layout_sets>"""


@pytest.fixture
def bare(tmp_path, monkeypatch) -> Any:
    """A layout set with seats and no shared window."""
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))
    path = tmp_path / "HUD_config.xml"
    path.write_text(
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"{BARE}\n</FreePokerToolsConfig>\n",
        encoding="utf-8",
    )
    return Config(file=str(path))


def test_a_layout_with_no_shared_window_says_so(bare) -> None:
    layout = bare.get_layout_node(bare.get_layout_set_node("bare"), 2)

    assert bare.get_location_node(layout, "common") is None


def test_a_seat_that_is_not_there_says_so_when_nothing_gets_in_the_way(bare) -> None:
    # With no common location to read a seat number off, the search runs to
    # the end and answers None, which is what it means to do.
    layout = bare.get_layout_node(bare.get_layout_set_node("bare"), 2)

    assert bare.get_location_node(layout, 9) is None


def test_saving_a_shared_window_a_layout_does_not_have_is_refused(bare) -> None:
    with pytest.raises(AttributeError):
        bare.save_layout_set(bare.layout_sets["bare"], 2, {"common": (1, 1)})


def test_a_layout_set_that_does_not_exist_says_so(config) -> None:
    assert config.get_layout_set_node("no such set") is None


def test_saving_to_a_layout_set_that_does_not_exist_is_refused(config, layout_set) -> None:
    # save_layout_set names the set through the object it is handed, so this
    # is an object whose name no longer matches anything in the file.
    layout_set.name = "renamed away"

    with pytest.raises(AttributeError):
        config.save_layout_set(layout_set, 2, {1: (1, 1)})
