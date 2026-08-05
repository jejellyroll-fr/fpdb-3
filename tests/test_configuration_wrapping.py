"""Keeping the saved configuration readable.

HUD_config.xml is written from a DOM, which puts each element on one line
however many attributes it has -- a site element runs past two hundred
characters. Since people do edit this file by hand, fpdb folds long lines at
the attribute boundaries before writing, lining the continuations up under the
first attribute.

It only does that when the file asks for it: config_wrap_len is what turns it
on, and without that setting nothing is folded at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

LONG = '    <site name="aaaa" second="bbbb" third="cccc" fourth="dddd"/>'


def config_xml(wrap: str | None) -> str:
    setting = "" if wrap is None else f' config_wrap_len="{wrap}"'
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"{setting}/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        "</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make(wrap: str | None = "40") -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(config_xml(wrap), encoding="utf-8")
        return Config(file=str(path))

    return make


@pytest.fixture
def config(build) -> Any:
    return build()


# --------------------------------------------------------------------------
# When nothing is folded
# --------------------------------------------------------------------------


def test_a_configuration_that_never_asked_is_left_on_one_line(build) -> None:
    # No config_wrap_len at all means no wrapping, which is what every
    # configuration written before the setting existed says.
    config = build(wrap=None)

    assert config.wrap_long_line(LONG) == LONG


@pytest.mark.parametrize("wrap", ["-1", "-100"])
def test_a_negative_width_means_no_folding(build, wrap) -> None:
    config = build(wrap=wrap)

    assert config.wrap_long_line(LONG) == LONG


def test_a_line_within_the_width_is_left_alone(config) -> None:
    short = '    <site name="a"/>'
    assert len(short) < 40

    assert config.wrap_long_line(short) == short


def test_a_line_with_no_indent_is_left_alone(config) -> None:
    # The fold is aligned under the first attribute, and where that is comes
    # from the leading whitespace; a line starting at column zero has none to
    # measure, so it is written out as it stands.
    flush = '<site name="aaaa" second="bbbb" third="cccc" fourth="dddd"/>'
    assert len(flush) > 40

    assert config.wrap_long_line(flush) == flush


def test_a_long_line_that_is_not_attributes_is_left_alone(config) -> None:
    # Folding happens between attributes; there is nowhere to break a line
    # that has none.
    prose = "    <!-- a comment long enough to go past the configured width -->"
    assert len(prose) > 40

    assert config.wrap_long_line(prose) == prose


def test_a_line_with_a_single_attribute_is_left_alone(config) -> None:
    # One attribute is one piece, and a piece cannot be folded against
    # itself.
    single = '    <site name="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/>'
    assert len(single) > 40

    assert config.wrap_long_line(single) == single


# --------------------------------------------------------------------------
# When it is
# --------------------------------------------------------------------------


def test_a_long_line_is_folded_at_the_attributes(config) -> None:
    folded = config.wrap_long_line(LONG)

    assert folded.splitlines() == [
        '    <site name="aaaa" ',
        '          second="bbbb" ',
        '          third="cccc" ',
        '          fourth="dddd"/>',
    ]


def test_the_continuations_line_up_under_the_first_attribute(config) -> None:
    # Which is the whole point: an element reads as one block rather than as
    # several unrelated lines.
    lines = config.wrap_long_line(LONG).splitlines()

    assert lines[0].index('name="') == len(lines[1]) - len(lines[1].lstrip())


def test_folding_keeps_every_attribute(config) -> None:
    # A fold that dropped one would quietly change the configuration.
    folded = config.wrap_long_line(LONG)

    for attribute in ("name", "second", "third", "fourth"):
        assert f'{attribute}="' in folded


def test_a_wider_setting_folds_less(build) -> None:
    assert build(wrap="200").wrap_long_line(LONG) == LONG
    assert build(wrap="40").wrap_long_line(LONG) != LONG


def test_a_width_of_zero_folds_everything_it_can(build) -> None:
    # Zero is not "off": it is a width every line exceeds.
    config = build(wrap="0")

    assert "\n" in config.wrap_long_line(LONG)


# --------------------------------------------------------------------------
# The whole document
# --------------------------------------------------------------------------


def test_every_line_of_the_document_goes_through_it(config) -> None:
    wrapped = config.wrap_long_lines(f"{LONG}\n{LONG}")

    assert wrapped.count('second="bbbb"') == 2


def test_the_document_ends_with_a_newline(config) -> None:
    # Files fpdb writes end properly, whether or not the DOM said so.
    assert config.wrap_long_lines("<a/>").endswith("\n")
    assert config.wrap_long_lines("<a/>\n").endswith("\n")


def test_an_empty_document_is_still_a_line(config) -> None:
    assert config.wrap_long_lines("") == "\n"


INDENTED = """<?xml version="1.0"?>
<FreePokerToolsConfig>
    <general version="{version}"{setting}/>
    <supported_databases>{database}</supported_databases>
    <supported_sites>
        <site site_name="PokerStars" enabled="True" screen_name="hero" HH_path="" TS_path="" converter="PokerStarsToFpdb"/>
    </supported_sites>
</FreePokerToolsConfig>
"""


@pytest.fixture
def indented(tmp_path, monkeypatch) -> Any:
    """A configuration laid out the way the shipped one is."""
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make(wrap: str | None = "40") -> Config:
        path = tmp_path / "HUD_config.xml"
        setting = "" if wrap is None else f' config_wrap_len="{wrap}"'
        path.write_text(
            INDENTED.format(version=CONFIG_VERSION, setting=setting, database=DATABASE),
            encoding="utf-8",
        )
        return Config(file=str(path))

    return make


def site_lines(config: Any) -> list[str]:
    return [
        line
        for line in Path(config.file).read_text(encoding="utf-8").splitlines()
        if "site_name" in line or "enabled=" in line
    ]


def test_the_saved_file_is_folded(indented) -> None:
    # The path that matters: this runs over everything fpdb writes out, and a
    # site element is the longest line in a real configuration.
    config = indented(wrap="40")

    config.save()

    lines = site_lines(config)
    assert len(lines) > 1
    assert lines[1].startswith(" " * 14)


def test_the_saved_file_is_left_on_one_line_when_folding_was_not_asked_for(indented) -> None:
    config = indented(wrap=None)

    config.save()

    assert len(site_lines(config)) == 1


def test_folding_the_file_does_not_change_what_it_says(indented) -> None:
    # The point of a whitespace-only rewrite: it must survive being read back.
    config = indented(wrap="40")
    config.save()

    assert config.reload() is True
    assert config.supported_sites["PokerStars"].screen_name == "hero"
    assert config.supported_databases["fpdb"].db_server == "sqlite"


# --------------------------------------------------------------------------
# Saving, which is what folds
# --------------------------------------------------------------------------


def test_the_previous_file_is_kept_as_a_backup(indented) -> None:
    # Saving moves the old file aside first, so a write that goes wrong does
    # not take the configuration with it.
    config = indented()
    before = Path(config.file).read_text(encoding="utf-8")

    config.save()

    assert Path(f"{config.file}.backup").read_text(encoding="utf-8") == before


def test_saving_elsewhere_leaves_the_configuration_where_it_is(indented, tmp_path) -> None:
    # An explicit destination is a copy, not a move: no backup is taken and
    # the file fpdb is using stays put.
    config = indented()
    elsewhere = tmp_path / "exported.xml"

    config.save(file=str(elsewhere))

    assert elsewhere.exists()
    assert Path(config.file).exists()
    assert not Path(f"{config.file}.backup").exists()


def test_a_backup_that_cannot_be_taken_does_not_stop_the_save(indented, monkeypatch) -> None:
    # Losing the previous copy is worse than not having one, but refusing to
    # save at all would be worse still: the settings just changed.
    config = indented()

    def refuse(*_args, **_kwargs):
        msg = "read-only directory"
        raise OSError(msg)

    monkeypatch.setattr(config_module.shutil, "move", refuse)

    config.save()

    assert "PokerStars" in Path(config.file).read_text(encoding="utf-8")
