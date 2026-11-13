"""tools/capture_wiki_screenshots.py: what the wiki pictures may and may not show."""

from __future__ import annotations

import pytest

from tools import capture_wiki_screenshots as capture


def test_rotate_gives_each_capture_the_next_theme_and_wraps() -> None:
    themes = capture.ROTATION_THEMES

    assert [capture.theme_for(index, "rotate") for index in range(len(themes))] == list(themes)
    assert capture.theme_for(len(themes), "rotate") == themes[0]


def test_a_named_theme_is_used_for_every_capture() -> None:
    assert {capture.theme_for(index, "dark_teal.xml") for index in range(5)} == {"dark_teal.xml"}


def test_the_rotation_holds_stock_dark_themes_only() -> None:
    # Light themes leave graphs and stats tables hard to read (#712).
    assert capture.ROTATION_THEMES
    assert all(theme.startswith("dark_") and theme.endswith(".xml") for theme in capture.ROTATION_THEMES)
    assert len(set(capture.ROTATION_THEMES)) == len(capture.ROTATION_THEMES)


@pytest.mark.parametrize("fragment", ["/Users/", "/home/", "\\Users\\", "~", "tmp"])
def test_the_folder_shown_in_the_wizard_names_nobody(fragment: str) -> None:
    assert fragment not in capture.PT4_ARCHIVE_EXAMPLE


def test_every_capture_has_a_distinct_png_name() -> None:
    names = [name for name, _view in capture.RESEARCH_SHOTS] + [name for name, *_rest in capture.STUDY_SHOTS]

    assert len(names) == len(set(names))
    assert all(name.endswith(".png") for name in names)


def test_the_editor_picture_shows_a_profile_made_of_panels_when_there_is_one() -> None:
    profiles = {"flat": {"stats": []}, "panels": {"blocks": [{}]}, "other": {"blocks": [{}]}}
    assert capture.editor_profile(profiles) == "panels"
    assert capture.editor_profile({"flat": {"stats": []}}) == "flat"
    assert capture.editor_profile({}) is None


def test_the_popup_picture_shows_a_classic_popup_with_several_stats() -> None:
    popups = {
        "a_grid": {"class": "BlockPopup", "stats": [{}] * 9},
        "b_short": {"class": "Submenu", "stats": [{}] * 2},
        "c_list": {"class": "Submenu", "stats": [{}] * 6},
    }
    assert capture.editor_popup(popups) == "c_list"
    assert capture.editor_popup({"a_grid": popups["a_grid"]}) is None
