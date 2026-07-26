"""Filling in the sections an older configuration never had.

fpdb ships an example configuration, and a file written by an earlier version
is missing whatever sections have been added since. Rather than refuse it,
fpdb copies those sections across from the example and saves, so a player who
upgrades keeps their settings and gains the new ones.

The comment on the function is the warning worth remembering: because a whole
missing section is put back, a section cannot be removed from a configuration
by deleting it. It has to be turned off instead.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

import fpdb_3_legacy.Configuration as config_module
from fpdb_3_legacy.Configuration import CONFIG_VERSION, Config

DATABASE = '<database db_name="fpdb" db_server="sqlite" db_ip="" db_user="" db_pass="" db_desc="test"/>'

EXAMPLE = """<?xml version="1.0"?>
<FreePokerToolsConfig>
  <raw_hands save="none" compression="none"/>
  <hud_ui label="From the example"/>
  <supported_sites>
    <site site_name="PokerStars" enabled="True" screen_name="from-example"
          HH_path="" TS_path="" converter="PokerStarsToFpdb"/>
  </supported_sites>
</FreePokerToolsConfig>
"""


def config_xml(sections: str = "") -> str:
    return (
        '<?xml version="1.0"?>\n<FreePokerToolsConfig>\n'
        f'<general version="{CONFIG_VERSION}"/>\n'
        f"<supported_databases>{DATABASE}</supported_databases>\n"
        f"{sections}\n</FreePokerToolsConfig>\n"
    )


@pytest.fixture
def build(tmp_path, monkeypatch) -> Any:
    monkeypatch.setattr(config_module, "CONFIG_PATH", str(tmp_path / "cfgdir"))

    def make(sections: str = "") -> Config:
        path = tmp_path / "HUD_config.xml"
        path.write_text(config_xml(sections), encoding="utf-8")
        return Config(file=str(path))

    return make


@pytest.fixture
def config(build) -> Any:
    return build()


@pytest.fixture
def example(tmp_path) -> Path:
    path = tmp_path / "HUD_config.xml.example"
    path.write_text(EXAMPLE, encoding="utf-8")
    return path


def sections_of(config: Any) -> list[str]:
    root = config.doc.getElementsByTagName("FreePokerToolsConfig")[0]
    return [node.localName for node in root.childNodes if node.nodeType == node.ELEMENT_NODE]


# --------------------------------------------------------------------------
# Copying what is missing
# --------------------------------------------------------------------------


def test_a_section_the_configuration_lacks_is_copied_in(config, example) -> None:
    assert "raw_hands" not in sections_of(config)

    config.add_missing_elements(config.doc, str(example))

    assert "raw_hands" in sections_of(config)


def test_the_number_of_sections_added_is_reported(config, example) -> None:
    # The caller re-reads the configuration when this is not zero, so it is
    # the answer that decides whether the new sections take effect at once.
    added = config.add_missing_elements(config.doc, str(example))

    assert added == 3


def test_the_whole_section_comes_across_not_just_its_name(config, example) -> None:
    # The copy is deep: a section is worth nothing without its children.
    config.add_missing_elements(config.doc, str(example))

    site = config.get_site_node("PokerStars")
    assert site is not None
    assert site.getAttribute("screen_name") == "from-example"


def test_a_section_already_there_is_left_as_it_is(build, example) -> None:
    # Someone's own settings must not be replaced by the example's.
    config = build('<hud_ui label="Mine"/>')

    added = config.add_missing_elements(config.doc, str(example))

    assert config.doc.getElementsByTagName("hud_ui")[0].getAttribute("label") == "Mine"
    assert added == 2


def test_a_configuration_missing_nothing_is_not_touched(build, example) -> None:
    config = build(
        '<hud_ui label="Mine"/><raw_hands save="none" compression="none"/>'
        '<supported_sites><site site_name="Winamax" enabled="True" screen_name="me"'
        ' HH_path="" TS_path="" converter="WinamaxToFpdb"/></supported_sites>'
    )
    before = Path(config.file).read_text(encoding="utf-8")

    assert config.add_missing_elements(config.doc, str(example)) == 0

    assert Path(config.file).read_text(encoding="utf-8") == before


def test_the_added_sections_are_written_out_at_once(config, example) -> None:
    # The configuration is saved as part of adding, so an upgrade survives
    # fpdb being closed before anything else is changed.
    config.add_missing_elements(config.doc, str(example))

    assert "raw_hands" in Path(config.file).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Examples it cannot read
# --------------------------------------------------------------------------


def test_an_example_that_is_not_there_adds_nothing(config, tmp_path) -> None:
    # Running from a source tree with no example beside the configuration, or
    # from a package that did not ship one.
    assert config.add_missing_elements(config.doc, str(tmp_path / "absent.example")) == 0

    assert "raw_hands" not in sections_of(config)


def test_an_example_that_is_not_valid_xml_adds_nothing(config, tmp_path) -> None:
    broken = tmp_path / "broken.example"
    broken.write_text("<this is not closed", encoding="utf-8")

    assert config.add_missing_elements(config.doc, str(broken)) == 0


def test_a_hostile_example_adds_nothing(config, tmp_path) -> None:
    # The example is parsed with the same guard as the configuration itself,
    # so a file carrying an external entity is refused rather than followed.
    hostile = tmp_path / "hostile.example"
    hostile.write_text(
        textwrap.dedent("""\
            <?xml version="1.0"?>
            <!DOCTYPE FreePokerToolsConfig [ <!ENTITY stolen SYSTEM "file:///etc/passwd"> ]>
            <FreePokerToolsConfig><raw_hands save="&stolen;"/></FreePokerToolsConfig>
        """),
        encoding="utf-8",
    )

    assert config.add_missing_elements(config.doc, str(hostile)) == 0

    assert "raw_hands" not in sections_of(config)


def test_an_example_with_a_different_root_adds_nothing(config, tmp_path) -> None:
    # Only a document rooted at FreePokerToolsConfig is looked through, so
    # some other XML file handed over by mistake is simply ignored.
    stranger = tmp_path / "stranger.example"
    stranger.write_text('<?xml version="1.0"?><SomethingElse><raw_hands/></SomethingElse>', encoding="utf-8")

    assert config.add_missing_elements(config.doc, str(stranger)) == 0

    assert "raw_hands" not in sections_of(config)


# --------------------------------------------------------------------------
# The consequence the function warns about
# --------------------------------------------------------------------------


def test_a_section_deleted_from_a_configuration_comes_back(build, example) -> None:
    # Which is what the comment on the function means by "can't just delete a
    # config section now": removing one is undone on the next start, and
    # turning it off is what actually works.
    config = build('<hud_ui label="Mine"/><raw_hands save="none" compression="none"/>')
    node = config.doc.getElementsByTagName("raw_hands")[0]
    node.parentNode.removeChild(node)

    config.add_missing_elements(config.doc, str(example))

    assert "raw_hands" in sections_of(config)
