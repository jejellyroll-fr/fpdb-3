"""XML that fpdb reads from disk must not be able to act on the machine.

Python's stock XML parsers honour entity declarations, which turns any file
they read into two attacks. An external entity makes the parser fetch a path of
the attacker's choosing and paste it into the document, so a hand history can
read ~/.ssh/id_rsa and hand it to whatever the document is used for. Nested
entities expand geometrically -- the "billion laughs" -- so a few hundred bytes
exhaust memory.

Neither is hypothetical here: hand histories arrive from poker rooms and
configuration packages are passed around between players, and both are parsed
without anyone looking at them first.

These tests pin the refusal at each entry point. They fail if a parser is ever
swapped back to the standard library, which is the whole point -- the change is
one import, and nothing else would notice.
"""

from __future__ import annotations

import shutil
import textwrap
from pathlib import Path
from typing import Any

import pytest
from defusedxml.common import DefusedXmlException

from fpdb_3_legacy.Configuration import Config

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "HUD_config.xml"

# Reads a file off the machine and pastes it into an attribute.
XXE = """<?xml version="1.0"?>
<!DOCTYPE FreePokerToolsConfig [ <!ENTITY stolen SYSTEM "file:///etc/passwd"> ]>
<FreePokerToolsConfig><general stolen="&stolen;"/></FreePokerToolsConfig>
"""

# Each entity multiplies the one below it; a real one nests deep enough to
# exhaust memory, and this is the same construct kept small.
BILLION_LAUGHS = textwrap.dedent("""\
    <?xml version="1.0"?>
    <!DOCTYPE FreePokerToolsConfig [
      <!ENTITY a "aaaaaaaaaa">
      <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
      <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
    ]>
    <FreePokerToolsConfig><general big="&c;"/></FreePokerToolsConfig>
""")

HOSTILE = {"an external entity": XXE, "a billion laughs": BILLION_LAUGHS}


@pytest.fixture(params=sorted(HOSTILE), ids=sorted(HOSTILE))
def hostile_file(request, tmp_path) -> Path:
    target = tmp_path / "hostile.xml"
    target.write_text(HOSTILE[request.param], encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# The parsers themselves
# --------------------------------------------------------------------------


def test_the_dom_parser_refuses_it(hostile_file) -> None:
    import defusedxml.minidom

    with pytest.raises(DefusedXmlException):
        defusedxml.minidom.parse(str(hostile_file))


def test_the_element_tree_parser_refuses_it(hostile_file) -> None:
    import defusedxml.ElementTree

    with pytest.raises(DefusedXmlException):
        defusedxml.ElementTree.parse(str(hostile_file))


# The modules that read XML fpdb did not write. HandHistoryConverter is the
# one that matters most: a hand history is whatever the poker room wrote.
PARSING_MODULES = (
    "Configuration.py",
    "HandHistoryConverter.py",
    "GuiReplayer.py",
    "HandHistory.py",
    "ModernHudPreferences.py",
    "L10n.py",
    "ThemeManager.py",
    "fix_ipoker_duplicate_session_hands.py",
)

# Creating a document is not parsing, so getDOMImplementation stays on the
# standard library and is not what this looks for.
STDLIB_PARSE_CALLS = (
    "xml.dom.minidom.parse",
    "xml.dom.minidom.parseString",
    "xml.etree.ElementTree",
)


@pytest.mark.parametrize("module", PARSING_MODULES)
def test_no_module_parses_with_the_standard_library(module) -> None:
    # The difference between a hardened parser and a vulnerable one is a single
    # import, and nothing at runtime would notice it being changed back.
    source = (ROOT / "fpdb_3_legacy" / module).read_text(encoding="utf-8")

    found = [call for call in STDLIB_PARSE_CALLS if call in source]

    assert found == [], f"{module} parses XML with {found}; use defusedxml"


# --------------------------------------------------------------------------
# What the application does with the refusal
# --------------------------------------------------------------------------


def test_a_hostile_configuration_is_reported_the_way_a_broken_one_is(hostile_file) -> None:
    # A refused file has to take the path a malformed file already took, or
    # hardening the parser would only move the crash somewhere else.
    with pytest.raises(ValueError, match="Unable to load configuration file"):
        Config(file=str(hostile_file))


def test_a_malformed_configuration_still_fails_the_same_way(tmp_path) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("<this is not closed", encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to load configuration file"):
        Config(file=str(broken))


@pytest.fixture
def config(tmp_path) -> Any:
    mine = tmp_path / "HUD_config.xml"
    shutil.copy(SHIPPED, mine)
    return Config(file=str(mine))


def test_a_configuration_that_turns_hostile_is_refused_on_reload(config, hostile_file) -> None:
    # Reloading is what the preferences dialog calls after writing, so this is
    # where a file swapped underneath fpdb would be read.
    before = len(config.supported_sites)
    Path(config.file).write_text(hostile_file.read_text(encoding="utf-8"), encoding="utf-8")

    assert config.reload() is False
    assert len(config.supported_sites) == before


def test_an_ordinary_configuration_is_still_read(config) -> None:
    # The guard must refuse the two constructs and nothing else.
    assert config.reload() is True
    assert config.supported_sites
