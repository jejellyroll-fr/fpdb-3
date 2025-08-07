#!/usr/bin/env python3

import re

# Substitutions from PokerStarsSummary.py
substitutions = {
    "LEGAL_ISO": "USD|EUR|GBP|CAD|FPP|SC|INR|CNY",
    "LS": "\\$|€|£|₹|¥|Rs\\.|Â£|â‚¬|â‚¹",
}

# Current regex from PokerStarsSummary.py
re_TourneyInfo = re.compile(
    """
                    \\#(?P<TOURNO>[0-9]+),\\s
                    (?P<DESC1>.+?\\sSNG\\s)?
                    ((?P<LIMIT>No\\sLimit|NO\\sLIMIT|Limit|LIMIT|Pot\\sLimit|POT\\sLIMIT|Pot\\sLimit\\sPre\\-Flop,\\sNo\\sLimit\\sPost\\-Flop)\\s)?
                    (?P<SPLIT>Split)?\\s?
                    (?P<GAME>Hold\'em|6\\+\\sHold\'em|Hold\\s\'Em|Razz|RAZZ|7\\sCard\\sStud|7\\sCard\\sStud\\sHi/Lo|Omaha|Omaha\\sHi/Lo|Badugi|Triple\\sDraw\\s2\\-7\\sLowball|Single\\sDraw\\s2\\-7\\sLowball|5\\sCard\\sDraw|(5|6)\\sCard\\sOmaha(\\sHi/Lo)?|Courchevel(\\sHi/Lo)?|HORSE|8\\-Game|HOSE|Mixed\\sOmaha\\sH/L|Mixed\\sHold\'em|Mixed\\sPLH/PLO|Mixed\\sNLH/PLO||Mixed\\sOmaha|Triple\\sStud).*?
                    (Buy-In:\\s(?P<CURRENCY>[{LS}]?)(?P<BUYIN>[,.0-9]+)(\\s(?P<CURRENCY1>(FPP|SC)))?(\\/[{LS}]?(?P<FEE>[,.0-9]+))?(\\/[{LS}]?(?P<BOUNTY>[,.0-9]+))?(?P<CUR>\\s({LEGAL_ISO}))?\\s+)?
                    (?P<ENTRIES>[0-9]+)\\splayers\\s+
                    ([{LS}]?(?P<ADDED>[,.\\d]+)(\\s({LEGAL_ISO}))?\\sadded\\sto\\sthe\\sprize\\spool\\sby\\s(PokerStars|Full\\sTilt)(\\.com)?\\s+)?
                    (Total\\sPrize\\sPool:\\s[{LS}]?(?P<PRIZEPOOL>[,.0-9]+|Sunday\\sMillion\\s(ticket|biļete))(\\s({LEGAL_ISO}))?\\s+)?
                    (?P<SATELLITE>Target\\sTournament\\s\\#(?P<TARGTOURNO>[0-9]+)\\s+
                     (Buy-In:\\s(?P<TARGCURRENCY>[{LS}]?)(?P<TARGBUYIN>[,.0-9]+)(\\/[{LS}]?(?P<TARGFEE>[,.0-9]+))?(\\/[{LS}]?(?P<TARGBOUNTY>[,.0-9]+))?(?P<TARGCUR>\\s({LEGAL_ISO}))?\\s+)?)?
                    ([0-9]+\\stickets?\\sto\\sthe\\starget\\stournament\\s+)?
                    Tournament\\sstarted\\s+(-\\s)?
                    (?P<DATETIME>.*$)
                    """.format(**substitutions),
    re.VERBOSE | re.MULTILINE | re.DOTALL,
)

# Test text
test_text = """#661361197, No Limit Hold'em
Super Satellite
Buy-In: Â£75.00/Â£7.00 GBP
43 players
Total Prize Pool: Â£3225.00 GBP
Target Tournament #637573140 Buy-In: Â£1850.00 GBP
Tournament started 2012/12/30 23:32:00 CET [2012/12/30 17:32:00 ET]"""


m = re_TourneyInfo.search(test_text)
if m:
    pass
else:

    # Let's test parts of the regex

    # Test tournament number part
    tourno_pattern = r"#(?P<TOURNO>[0-9]+),\s"
    m1 = re.search(tourno_pattern, test_text)

    # Test game part
    game_pattern = r"(?P<GAME>Hold\'em|6\\+\\sHold\'em|Hold\\s\'Em)"
    m2 = re.search(game_pattern, test_text)

    # Test buy-in part
    buyin_pattern = r"Buy-In:\s(?P<CURRENCY>[{LS}]*)(?P<BUYIN>[,.0-9]+)".format(**substitutions)
    m3 = re.search(buyin_pattern, test_text)

    # Test simpler buy-in
    simple_buyin = r"Buy-In:\s(.{0,3})([,.0-9]+)"
    m3b = re.search(simple_buyin, test_text)

    # Test currency pattern specifically
    currency_pattern = f"[{substitutions['LS']}]"
    m4 = re.search(currency_pattern, test_text)
