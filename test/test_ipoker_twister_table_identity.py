#!/usr/bin/env python3
"""Regression tests for the identity of an iPoker (Bwin.fr) tournament table.

A Twister/Spins client reuses the SAME window for the next match of the series,
so a HUD that cannot tell one match's table from another's ends up on the wrong
one. Three defects combined to make that happen:

1. Only the first hand of a session file carries the header <tablename> that
   re_game_info needs, so every later hand -- all of live auto-import -- fell
   back to the XML parser, which named the table after <tournamentname> and
   dropped the ", <tableId>" suffix. The same table was then stored under two
   names and the HUD, which keys on the trailing token, rebuilt itself from
   scratch on the second hand of every tournament.
2. The window search regex for a Twister was the bare "(?:Twister|Spins)", which
   matches any Twister window, including the recycled one of the next match.
3. getTableNoRe was the inherited "<tournament>.+Table (\\d+)", which no iPoker
   title ever matches, so a window changing table was never detected.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpdb_3_legacy.iPoker.xml_format import IPokerXMLFormatMixin
from fpdb_3_legacy.iPokerToFpdb import iPoker

# Trimmed to the tags the parsers read; two <game> blocks so the second one
# exercises the header-less path that live auto-import always takes.
TWISTER_SESSION = """<?xml version="1.0" encoding="UTF-8"?>
<session sessioncode="5879605893">
<general>
<client_version>26.1.1.31</client_version>
<mode>real</mode>
<gametype>Holdem NL €0.05/€0.10</gametype>
<tablename>Twister 0.25€, 1200531183</tablename>
<duration>00:05:54</duration>
<gamecount>2</gamecount>
<startdate>2026-08-27 21:17:37</startdate>
<currency>EUR</currency>
<nickname>hero</nickname>
<bets>0,25€</bets>
<wins>0€</wins>
<tournamentcode>1200531182</tournamentcode>
<tournamentname>Twister 0.25€</tournamentname>
<place>3</place>
<buyin>0,24€+0,01€</buyin>
<totalbuyin>0,25€</totalbuyin>
<win>0€</win>
<tablesize>3</tablesize>
</general>
<games>
<game gamecode="9069037993">
<general>
<startdate>2026-08-27 21:17:37</startdate>
<players>
<player seat="1" name="villain_a" chips="500€" dealer="0" win="0€" bet="20€"/>
<player seat="2" name="villain_b" chips="500€" dealer="1" win="40€" bet="10€"/>
<player seat="3" name="hero" chips="500€" dealer="0" win="0€" bet="10€"/>
</players>
</general>
</game>
<game gamecode="9069038035">
<general>
<startdate>2026-08-27 21:17:48</startdate>
<players>
<player seat="1" name="villain_a" chips="480€" dealer="1" win="0€" bet="20€"/>
<player seat="2" name="villain_b" chips="530€" dealer="0" win="40€" bet="10€"/>
<player seat="3" name="hero" chips="490€" dealer="0" win="0€" bet="10€"/>
</players>
</game>
</games>
</session>
"""

# What the Bwin.fr client actually puts in the window title bar. The number is
# the physical table id (tournament code + 1), and it is the only id present.
TITLE_MATCH_1 = "Twister 0.25€ 1200531183 | NL Hold'em | Niveau 1 | 10/20     v.26.1.1.31"
TITLE_MATCH_2 = "Twister 0.25€ 1200530962 | NL Hold'em     v.26.1.1.31"


class _XMLParser(IPokerXMLFormatMixin):
    """The XML fallback path on its own, with no Config and no file on disk."""

    def __init__(self, whole_file: str) -> None:
        self.whole_file = whole_file
        self.info: dict = {}
        self.tinfo: dict = {}
        self.tablename = ""
        self.hero = ""

    def _filename_game_info_source(self) -> str:
        return "Twister.xml"


def _hand_chunks(session: str) -> list[str]:
    """Split a session the way HandHistoryConverter feeds hands to the parser."""
    return [chunk + "</game>" for chunk in session.split("</game>") if "<game " in chunk]


def test_second_hand_keeps_the_table_id() -> None:
    """Every hand of a file must name the table the same way.

    The second hand carries no <tablename> of its own; taking it from the
    session header is what keeps the HUD key stable across the whole match.
    """
    chunks = _hand_chunks(TWISTER_SESSION)
    assert len(chunks) == 2
    assert "<tablename>" not in chunks[1], "fixture no longer exercises the header-less path"

    names = []
    for chunk in chunks:
        parser = _XMLParser(TWISTER_SESSION)
        info = parser._parse_xml_format(chunk)
        assert info["type"] == "tour"
        names.append(info["table_name"])

    assert names[0] == "Twister 0.25€, 1200531183"
    assert names[1] == names[0]


def test_table_name_falls_back_to_the_tournament_name() -> None:
    """A session without <tablename> still has to produce a name."""
    session = TWISTER_SESSION.replace("<tablename>Twister 0.25€, 1200531183</tablename>\n", "")
    info = _XMLParser(session)._parse_xml_format(_hand_chunks(session)[1])
    assert info["table_name"] == "Twister 0.25€"


@pytest.mark.parametrize("title", [TITLE_MATCH_1, TITLE_MATCH_2])
def test_twister_regex_only_matches_its_own_window(title: str) -> None:
    """A Twister HUD must not attach to the next match's recycled window."""
    import re

    regex = iPoker.getTableTitleRe(
        "tour",
        tournament="1200531182",
        table_number=1200531183,
        tourney_name="Twister 0.25€",
    )
    assert (re.search(regex, title) is not None) == (title == TITLE_MATCH_1)


@pytest.mark.parametrize(
    "table_number",
    [
        1200531182,  # TableWindow's fallback: the tournament number itself
        1,  # a seat-style index, which no Twister title contains
        None,
    ],
)
def test_twister_regex_stays_loose_without_a_table_id(table_number: int | None) -> None:
    """Hand histories that never carried a table id keep the old behaviour.

    Pinning the search to a number the title cannot contain would find no window
    at all, which is worse than the loose match it replaces.
    """
    import re

    regex = iPoker.getTableTitleRe(
        "tour",
        tournament="1200531182",
        table_number=table_number,
        tourney_name="Twister 0.25€",
    )
    assert re.search(regex, TITLE_MATCH_1)
    assert re.search(regex, TITLE_MATCH_2)


def test_table_no_regex_reads_the_id_from_the_title() -> None:
    """get_table_no() must return the table id, not False, on an iPoker title."""
    import re

    regex = iPoker.getTableNoRe(tournament="1200531182")
    assert int(re.search(regex, TITLE_MATCH_1).group(1)) == 1200531183
    assert int(re.search(regex, TITLE_MATCH_2).group(1)) == 1200530962
    # Blinds and levels are not table ids.
    assert re.search(regex, "Twister 0.25€ | NL Hold'em | Niveau 1 | 10/20") is None


def test_the_table_id_is_read_from_the_end_of_the_name() -> None:
    """A table can be named after its tournament as well as its own id.

    Reading the first long number would return the tournament, which never
    matches the table the hand history names -- and has_table_title_changed()
    would then call every hand a reseat and kill the HUD on each one.
    """
    import re

    regex = iPoker.getTableNoRe(tournament="1193390834")
    title = "1193390834 Twister 5867402179 | NL Hold'em | Niveau 3"

    assert int(re.search(regex, title).group(1)) == 5867402179


def test_a_title_without_a_table_id_reads_as_no_table() -> None:
    """No number to anchor on must mean "no signal", never a wrong one."""
    import re

    regex = iPoker.getTableNoRe(tournament="1200531182")

    assert re.search(regex, "Twister 0.25€ | NL Hold'em | Niveau 1 | 10/20") is None
