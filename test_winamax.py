import re
import pytest

substitutions = {
                     'LEGAL_ISO' : "USD|EUR|GBP|CAD|FPP",     # legal ISO currency codes
                            'LS' : r"\$|\xe2\x82\xac|\u20ac|"
                              # legal currency symbols - Euro(cp1252, utf-8)
                    }

re_Identify = re.compile(r'Winamax\sPoker\s\-\s(CashGame|Go\sFast|HOLD\-UP|Tournament\s\")')

def test_re_Identify():
    text = 'Winamax Poker - HOLD-UP "Colorado" - HandId: #18876587-492053-1695486636 - Holdem no limit (0.01€/0.02€) - 2023/09/23 16:30:36 UTC'
    match = re_Identify.search(text)
    assert match is not None


re_HandInfo = re.compile(r"""
\s*Winamax\sPoker\s-\s(?P<RING>(CashGame|Go\sFast\s\"[^\"]+\"|HOLD\-UP\s\"[^\"]+\"))?(?P<TOUR>Tournament\s(?P<TOURNAME>.+)?\sbuyIn:\s(?P<BUYIN>(?P<BIAMT>[%(LS)s\d\,.]+)?(\s\+?\s|-)(?P<BIRAKE>[%(LS)s\d\,.]+)?\+?(?P<BOUNTY>[%(LS)s\d\.]+)?\s?(?P<TOUR_ISO>%(LEGAL_ISO)s)?|(?P<FREETICKET>[\sa-zA-Z]+))?\s(level:\s(?P<LEVEL>\d+))?.*)?\s-\sHandId:\s\#(?P<HID1>\d+)-(?P<HID2>\d+)-(?P<HID3>\d+)\s-\s(?P<GAME>Holdem|Omaha|Omaha5|Omaha8|5\sCard\sOmaha|5\sCard\sOmaha\sHi/Lo|Omaha\sHi/Lo|7\-Card\sStud|7stud|7\-Card\sStud\sHi/Lo|7stud8|Razz|2\-7\sTriple\sDraw|Lowball27)\s(?P<LIMIT>fixed\slimit|no\slimit|pot\slimit)\s\((((%(LS)s)?(?P<ANTE>[.0-9]+)(%(LS)s)?)/)?((%(LS)s)?(?P<SB>[.0-9]+)(%(LS)s)?)/((%(LS)s)?(?P<BB>[.0-9]+)(%(LS)s)?)\)\s-\s(?P<DATETIME>.*)(Table:?\s\'(?P<TABLE>[^(]+)(.(?P<TOURNO>\d+).\#(?P<TABLENO>\d+))?.*\'\s(?P<MAXPLAYER>\d+)\-max\s(?P<MONEY>\(real\smoney\)))?
            """ % substitutions, re.MULTILINE|re.DOTALL|re.VERBOSE)


def test_re_HandInfo():
    text = 'Winamax Poker - HOLD-UP "Colorado" - HandId: #18876587-492053-1695486636 - Holdem no limit (0.01€/0.02€) - 2023/09/23 16:30:36 UTC'
    match = re_HandInfo.search(text)
    assert match is not None