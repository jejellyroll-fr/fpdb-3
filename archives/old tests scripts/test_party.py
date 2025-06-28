import re

import pytest

substitutions = {
    "LEGAL_ISO": "USD|EUR",  # legal ISO currency codes
    "LS": r"\$|\u20ac|\xe2\x82\xac|",  # Currency symbols - Euro(cp1252, utf-8)
    "NUM": r".,'\dKMB",
}

re_GameInfo = re.compile(
    r"""\*{5}\sHand\sHistory\s(F|f)or\sGame\s(?P<HID>\w+)\s\*{5}(\s\((?P<SITE>Poker\sStars|PokerMaster|Party|IPoker|Pacific|WPN|PokerBros)\))?\s+(.+?\shas\sleft\sthe\stable\.\s+)*(.+?\sfinished\sin\s\d+\splace\.\s+)*((?P<CURRENCY>(\$|\u20ac|\xe2\x82\xac|)))?\s*(([%(LS)s]?(?P<SB>[%(NUM)s]+)[%(LS)s]?(?P<BB>[%(NUM)s]+)\s*(?:%(LEGAL_ISO)s)?\s+(?P<FAST3>fastforward\s)?((?P<LIMIT3>NL|PL|FL|)\s+)?)|((?P<CASHBI>[%(NUM)s]+)\s*(?:%(LEGAL_ISO)s)?\s*)(?P<FAST2>fastforward\s)?(?P<LIMIT2>(NL|PL|FL|))?\s*)(Tourney\s*)?(?P<GAME>(Texas\sHold\'?em|Hold\'?em|Omaha\sHi-Lo|Omaha\sHiLo|Omaha(\sHi)?|7\sCard\sStud\sHi-Lo|7\sCard\sStud\sHiLo|7\sCard\sStud|Double\sHold\'?em|Short\sDeck))\s*(Game\sTable\s*)?((\((?P<LIMIT>(NL|PL|FL|Limit|))\)\s*)?(\((?P<SNG>SNG|STT|MTT)(\sJackPot)?\sTournament\s\#(?P<TOURNO>\d+)\)\s*)?)?(?:\s\(Buyin\s(?P<BUYIN>[%(LS)s][%(NUM)s]+)\s\+\s(?P<FEE>[%(LS)s][%(NUM)s]+)\))?\s*-\s*(?P<DATETIME>.+)"""
    % substitutions,
    re.VERBOSE | re.UNICODE,
)


def test_re_GameInfo():
    text = """
                ***** Hand History for Game 23913549618 *****
                €2 EUR PL Omaha - Monday, September 25, 20:28:14 CEST 2023
                Table Besançon (Real Money)
                """
    match = re_GameInfo.search(text)
    assert match is not None
    assert match.group("HID") == "23913549618"
    assert match.group("CURRENCY") == "€"
    assert match.group("GAME") == "Omaha"
    assert match.group("LIMIT3") == "PL"
