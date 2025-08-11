"""Tests for Winamax regex patterns used in hand history parsing."""

import re

substitutions = {
    "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
    "LS": r"\$|\xe2\x82\xac|\u20ac|",
    # legal currency symbols - Euro(cp1252, utf-8)
}

re_identify = re.compile(
    r"Winamax\sPoker\s\-\s(CashGame|Go\sFast|HOLD\-UP|Tournament\s\")",
)


def test_re_identify() -> None:
    """Test regex pattern for identifying Winamax poker games."""
    text = (
        'Winamax Poker - HOLD-UP "Colorado" - HandId: #18876587-492053-1695486636 - '
        "Holdem no limit (0.01€/0.02€) - 2023/09/23 16:30:36 UTC"
    )
    match = re_identify.search(text)
    assert match is not None


re_hand_info = re.compile(
    r"""
\s*Winamax\sPoker\s-\s(?P<RING>(CashGame|Go\sFast\s\"[^\"]+\"|HOLD\-UP\s\"[^\"]+\"))?(?P<TOUR>Tournament\s(?P<TOURNAME>.+)?\sbuyIn:\s(?P<BUYIN>(?P<BIAMT>[{LS}\d\,.]+)?(\s\+?\s|-)(?P<BIRAKE>[{LS}\d\,.]+)?\+?(?P<BOUNTY>[{LS}\d\.]+)?\s?(?P<TOUR_ISO>{LEGAL_ISO})?|(?P<FREETICKET>[\sa-zA-Z]+))?\s(level:\s(?P<LEVEL>\d+))?.*)?\s-\sHandId:\s\#(?P<HID1>\d+)-(?P<HID2>\d+)-(?P<HID3>\d+)\s-\s(?P<GAME>Holdem|Omaha|Omaha5|Omaha8|5\sCard\sOmaha|5\sCard\sOmaha\sHi/Lo|Omaha\sHi/Lo|7\-Card\sStud|7stud|7\-Card\sStud\sHi/Lo|7stud8|Razz|2\-7\sTriple\sDraw|Lowball27)\s(?P<LIMIT>fixed\slimit|no\slimit|pot\slimit)\s\(((({LS})?(?P<ANTE>[.0-9]+)({LS})?)/)?(({LS})?(?P<SB>[.0-9]+)({LS})?)/(({LS})?(?P<BB>[.0-9]+)({LS})?)\)\s-\s(?P<DATETIME>.*)(Table:?\s\'(?P<TABLE>[^(]+)(.(?P<TOURNO>\d+).\#(?P<TABLENO>\d+))?.*\'\s(?P<MAXPLAYER>\d+)\-max\s(?P<MONEY>\(real\smoney\)))?
            """.format(**substitutions),
    re.MULTILINE | re.DOTALL | re.VERBOSE,
)


def test_re_hand_info() -> None:
    """Test regex pattern for parsing basic hand information."""
    text = (
        'Winamax Poker - HOLD-UP "Colorado" - HandId: #18876587-492053-1695486636 - '
        "Holdem no limit (0.01€/0.02€) - 2023/09/23 16:30:36 UTC"
    )
    match = re_hand_info.search(text)
    assert match is not None


def test_re_hand_info_exp() -> None:
    """Test regex pattern for parsing tournament hand information with detailed groups."""
    text = (
        'Winamax Poker - Tournament "Expresso Nitro" buyIn: 0.23€ + 0.02€ level: 1 - '
        "HandId: #3011596205705658369-1-1695541274 - Holdem no limit (10/20) - 2023/09/24 07:41:14 UTC"
    )
    match = re_hand_info.search(text)
    assert match is not None
    assert match.group("TOURNAME") == '"Expresso Nitro"'
    assert match.group("BUYIN") == "0.23€ + 0.02€"
    assert match.group("BIAMT") == "0.23€"
    assert match.group("BIRAKE") == "0.02€"
    assert match.group("LEVEL") == "1"
    assert match.group("HID1") == "3011596205705658369"
    assert match.group("HID2") == "1"
    assert match.group("HID3") == "1695541274"
    assert match.group("GAME") == "Holdem"
    assert match.group("LIMIT") == "no limit"
    assert match.group("SB") == "10"
    assert match.group("BB") == "20"
    assert match.group("DATETIME") == "2023/09/24 07:41:14 UTC"


re_hutp = re.compile(
    r"Hold\-up\sto\sPot:\stotal\s(({LS})?(?P<AMOUNT>[.0-9]+)({LS})?)".format(**substitutions),
    re.MULTILINE | re.VERBOSE,
)


def test_re_hutp() -> None:
    """Test regex pattern for parsing Hold-up to Pot amounts."""
    text = "Hold-up to Pot: total 0.20€"
    match = re_hutp.search(text)
    assert match is not None
    assert match.group("AMOUNT") == "0.20"


re_post_sb = re.compile(
    r"(?P<PNAME>.*?)\sposts\ssmall\sblind\s({LS})?(?P<SB>[\.0-9]+)({LS})?(?!\sout\sof\sposition)".format(
        **substitutions,
    ),
    re.MULTILINE,
)


def test_re_post_sb() -> None:
    """Test regex pattern for parsing small blind posts."""
    text = "LordShiva posts small blind 0.01€"
    match = re_post_sb.search(text)
    assert match is not None
    assert match.group("PNAME") == "LordShiva"
    assert match.group("SB") == "0.01"


re_post_bb = re.compile(
    r"(?P<PNAME>.*?)\sposts\sbig\sblind\s({LS})?(?P<BB>[\.0-9]+)({LS})?".format(**substitutions),
    re.MULTILINE,
)


def test_re_post_bb() -> None:
    """Test regex pattern for parsing big blind posts."""
    text = "LordShiva posts big blind 0.01€"
    match = re_post_bb.search(text)
    assert match is not None
    assert match.group("PNAME") == "LordShiva"
    assert match.group("BB") == "0.01"


re_player_info = re.compile(
    r"Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.*)\s\(({LS})?(?P<CASH>[.0-9]+)({LS})?(,\s({LS})?(?P<BOUNTY>[.0-9]+)({LS})?\sbounty)?\)".format(
        **substitutions,
    ),
)


def test_re_player_info() -> None:
    """Test regex pattern for parsing player seat information."""
    text = "Seat 1: 77boy77 (0.60€)"
    match = re_player_info.search(text)
    assert match is not None
    assert match.group("SEAT") == "1"
    assert match.group("PNAME") == "77boy77"
    assert match.group("CASH") == "0.60"
