"""The ``<gametype>`` value of an iPoker session header, read one way.

The value is read twice per file: by the session header regex for the first
hand (``iPoker.re_game_info``), and by the XML path for every later hand,
which arrives as a bare ``<game>`` block (``_parse_xml_format``). The two used
separate patterns, and the XML one only knew the currency written before the
amount (``€0.01/€0.02``). PMU writes it after (``0,01€/0,02€``), so every hand
but the first of a file fell to the filename fallback and was imported as
no-limit with 0.01/0.02 blinds, whatever the game (#715). Both paths now build
on this pattern and these tables.
"""

from __future__ import annotations

import re
from typing import Final

SUBSTITUTIONS: Final[dict[str, str]] = {
    "LS": r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|kr|",  # Currency symbols
    "PLYR": r"(?P<PNAME>[^\"]+)",  # Regex pattern for matching player names
    "NUM": r"(.,\d+)|(\d+)",  # Regex pattern for matching numbers
    "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
}

LIMITS: Final[dict[str, str]] = {
    "No limit": "nl",
    "Pot limit": "pl",
    "Limit": "fl",
    "NL": "nl",
    "SL": "nl",
    "БЛ": "nl",
    "PL": "pl",
    "LP": "pl",
    "L": "fl",
    "LZ": "nl",
}

GAMES: Final[dict[str, tuple[str, str]]] = {  # base, category
    "7 Card Stud": ("stud", "studhi"),
    "7 Card Stud Hi-Lo": ("stud", "studhilo"),
    "7 Card Stud HiLow": ("stud", "studhilo"),
    "5 Card Stud": ("stud", "5_studhi"),
    "Holdem": ("hold", "holdem"),
    "Six Plus Holdem": ("hold", "6_holdem"),
    "Omaha": ("hold", "omahahi"),
    "Omaha Hi-Lo": ("hold", "omahahilo"),
    "Omaha HiLow": ("hold", "omahahilo"),
}

#: The text between ``<gametype>`` and ``</gametype>``, in ``re.VERBOSE``
#: syntax. A currency symbol may stand on either side of each amount.
GAMETYPE_VALUE: Final[str] = r"""
    (?P<GAME>((?P<CATEGORY>(5|7)\sCard\sStud(\sHi\-Lo|\sHiLow)?|(Six\sPlus\s)?Holdem|Omaha(\sHi\-Lo|\sHiLow)?)?\s?(?P<LIMIT>NL|SL|L|LZ|PL|БЛ|LP|No\slimit|Pot\slimit|Limit))|LH\s(?P<LSB>[{NUM}]+)({LS})?/(?P<LBB>[{NUM}]+)({LS})?.+?)
    (\s({LS})?(?P<SB>[{NUM}]+)({LS})?/({LS})?(?P<BB>[{NUM}]+))?({LS})?(\sAnte\s({LS})?(?P<ANTE>[{NUM}]+)({LS})?)?
""".format(**SUBSTITUTIONS)

_RE_GAMETYPE_VALUE: Final = re.compile(rf"\s*{GAMETYPE_VALUE}\s*$", re.VERBOSE)

#: 5 card Omaha is the only game iPoker leaves unnamed, and it is pot limit only.
_NAMELESS_LIMITS: Final = frozenset({"PL", "LP", "Pot limit"})


def read_gametype(text: str) -> dict[str, str | None] | None:
    """Read a ``<gametype>`` value into ``base``, ``category``, ``limitType``, ``SB`` and ``BB``.

    The blinds are returned as written (``0,01``), ``None`` when the value
    carries none (tournaments). ``None`` when the value is not a game this
    pattern knows: the caller keeps its own fallback then.
    """
    match = _RE_GAMETYPE_VALUE.match(text)
    if not match:
        return None
    category, limit = match.group("CATEGORY"), match.group("LIMIT")
    sb, bb = match.group("SB"), match.group("BB")
    if match.group("GAME").startswith("LH"):
        category, limit, bb = "Holdem", "L", match.group("LBB") or bb
    if category is None:
        if limit not in _NAMELESS_LIMITS:
            return None
        base, game = "hold", "5_omahahi"
    elif category in GAMES:
        base, game = GAMES[category]
    else:
        return None
    if limit not in LIMITS:
        return None
    return {"base": base, "category": game, "limitType": LIMITS[limit], "SB": sb, "BB": bb}
