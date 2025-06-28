import re

substitutions = {
    "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP",  # legal ISO currency codes
    "LS": r"\$|\xe2\x82\xac|\u20ac|",
    # legal currency symbols - Euro(cp1252, utf-8)
}

re_Identify = re.compile(
    r"Winamax\sPoker\s\-\s(CashGame|Go\sFast|HOLD\-UP|Tournament\s\")",
)


def test_re_Identify():
    text = 'Winamax Poker - HOLD-UP "Colorado" - HandId: #18876587-492053-1695486636 - Holdem no limit (0.01€/0.02€) - 2023/09/23 16:30:36 UTC'
    match = re_Identify.search(text)
    assert match is not None


re_HandInfo = re.compile(
    r"""
\s*Winamax\sPoker\s-\s(?P<RING>(CashGame|Go\sFast\s\"[^\"]+\"|HOLD\-UP\s\"[^\"]+\"))?(?P<TOUR>Tournament\s(?P<TOURNAME>.+)?\sbuyIn:\s(?P<BUYIN>(?P<BIAMT>[%(LS)s\d\,.]+)?(\s\+?\s|-)(?P<BIRAKE>[%(LS)s\d\,.]+)?\+?(?P<BOUNTY>[%(LS)s\d\.]+)?\s?(?P<TOUR_ISO>%(LEGAL_ISO)s)?|(?P<FREETICKET>[\sa-zA-Z]+))?\s(level:\s(?P<LEVEL>\d+))?.*)?\s-\sHandId:\s\#(?P<HID1>\d+)-(?P<HID2>\d+)-(?P<HID3>\d+)\s-\s(?P<GAME>Holdem|Omaha|Omaha5|Omaha8|5\sCard\sOmaha|5\sCard\sOmaha\sHi/Lo|Omaha\sHi/Lo|7\-Card\sStud|7stud|7\-Card\sStud\sHi/Lo|7stud8|Razz|2\-7\sTriple\sDraw|Lowball27)\s(?P<LIMIT>fixed\slimit|no\slimit|pot\slimit)\s\((((%(LS)s)?(?P<ANTE>[.0-9]+)(%(LS)s)?)/)?((%(LS)s)?(?P<SB>[.0-9]+)(%(LS)s)?)/((%(LS)s)?(?P<BB>[.0-9]+)(%(LS)s)?)\)\s-\s(?P<DATETIME>.*)(Table:?\s\'(?P<TABLE>[^(]+)(.(?P<TOURNO>\d+).\#(?P<TABLENO>\d+))?.*\'\s(?P<MAXPLAYER>\d+)\-max\s(?P<MONEY>\(real\smoney\)))?
            """
    % substitutions,
    re.MULTILINE | re.DOTALL | re.VERBOSE,
)


def test_re_HandInfo():
    text = 'Winamax Poker - HOLD-UP "Colorado" - HandId: #18876587-492053-1695486636 - Holdem no limit (0.01€/0.02€) - 2023/09/23 16:30:36 UTC'
    match = re_HandInfo.search(text)
    assert match is not None


def test_re_HandInfoexp():
    text = 'Winamax Poker - Tournament "Expresso Nitro" buyIn: 0.23€ + 0.02€ level: 1 - HandId: #3011596205705658369-1-1695541274 - Holdem no limit (10/20) - 2023/09/24 07:41:14 UTC'
    match = re_HandInfo.search(text)
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


re_HUTP = re.compile(
    r"Hold\-up\sto\sPot:\stotal\s((%(LS)s)?(?P<AMOUNT>[.0-9]+)(%(LS)s)?)"
    % substitutions,
    re.MULTILINE | re.VERBOSE,
)


def test_re_HUTP():
    text = "Hold-up to Pot: total 0.20€"
    match = re_HUTP.search(text)
    assert match is not None
    assert match.group("AMOUNT") == "0.20"


re_PostSB = re.compile(
    r"(?P<PNAME>.*?)\sposts\ssmall\sblind\s(%(LS)s)?(?P<SB>[\.0-9]+)(%(LS)s)?(?!\sout\sof\sposition)"
    % substitutions,
    re.MULTILINE,
)


def test_re_PostSB():
    text = "LordShiva posts small blind 0.01€"
    match = re_PostSB.search(text)
    assert match is not None
    assert match.group("PNAME") == "LordShiva"
    assert match.group("SB") == "0.01"


re_PostBB = re.compile(
    r"(?P<PNAME>.*?)\sposts\sbig\sblind\s(%(LS)s)?(?P<BB>[\.0-9]+)(%(LS)s)?"
    % substitutions,
    re.MULTILINE,
)


def test_re_PostBB():
    text = "LordShiva posts big blind 0.01€"
    match = re_PostBB.search(text)
    assert match is not None
    assert match.group("PNAME") == "LordShiva"
    assert match.group("BB") == "0.01"


re_PlayerInfo = re.compile(
    r"Seat\s(?P<SEAT>[0-9]+):\s(?P<PNAME>.*)\s\((%(LS)s)?(?P<CASH>[.0-9]+)(%(LS)s)?(,\s(%(LS)s)?(?P<BOUNTY>[.0-9]+)(%(LS)s)?\sbounty)?\)"
    % substitutions,
)


def test_re_PlayerInfo():
    text = "Seat 1: 77boy77 (0.60€)"
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group("SEAT") == "1"
    assert match.group("PNAME") == "77boy77"
    assert match.group("CASH") == "0.60"
