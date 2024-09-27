import re
import pytest


substitutions = {
                     'LEGAL_ISO' : "USD|EUR|GBP|CAD|FPP",      # legal ISO currency codes
                            'LS' : r"\$|€|", # legal currency symbols - Euro(cp1252, utf-8)
                           'PLYR': r'(?P<PNAME>.+?)',
                            'CUR': r"(\$|€|)",
                            'NUM' :r".(,|\s)\d\xa0",
                            'NUM2': r'\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b',  # Regex pattern for matching numbers with spaces
                    }

re_PlayerInfo   = re.compile(r"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.+?)\s
          \((%(LS)s)?(?P<CASH>[%(NUM)s]+)\sin\schips\)
          (\s\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?""" % substitutions, 
          re.MULTILINE|re.VERBOSE)

re_PlayerInfo2   = re.compile(r"""
          ^Seat\s(?P<SEAT>[0-9]+):\s
          (?P<PNAME>.+?)\s
          \((%(LS)s)?(?P<CASH>[%(NUM2)s]+)\sin\schips\)
          (\s\s\(EUR\s(%(CUR)s)?(?P<EUROVALUE>[%(NUM)s]+)\))?""" % substitutions, 
          re.MULTILINE|re.VERBOSE)


def test_re_PlayerInfo2():
    text = 'Seat 1: joker7 (1 200 in chips) '
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == '1'
    assert match.group('PNAME') == 'joker7'
    assert match.group('CASH') == '1 200'

def test_re_PlayerInfo3():
    text = 'Seat 1: joker7 (1 200 in chips) '
    match = re_PlayerInfo2.search(text)
    assert match is not None
    assert match.group('SEAT') == '1'
    assert match.group('PNAME') == 'joker7'
    assert match.group('CASH') == '1 200'

table_text = "Tournament: 17106061 Buy-In Freeroll : Table 10 - No Limit Holdem - 15/30"
hand_text = "Hand#710910543B500014 - Freeroll to GOLD CHIPS T17122229 -- FREEROLL -- $0 + $0 -- 9 Max -- Table 4 -- 0/10/20 NL Hold'em -- 2023/09/22 - 17:35:27"

re_GameInfo     = re.compile(r"""
          Hand\#(?P<HID>[A-Z0-9]+)\s+\-\s+(?P<TABLE>(?P<BUYIN1>(?P<BIAMT1>(%(LS)s)[%(NUM)s]+)\sNLH\s(?P<MAX1>\d+)\smax)?.+?)\s(\((Turbo,\s)?(?P<MAX>\d+)\-+[Mm]ax\)\s)?((?P<TOURNO>T\d+)|\d+)\s(\-\-\s(TICKET|CASH|TICKETCASH|FREEROLL)\s\-\-\s(?P<BUYIN>(?P<BIAMT>\$\d+)\s\+\s(?P<BIRAKE>\$\d+))\s\-\-\s(?P<TMAX>\d+)\sMax\s)?(\-\-\sTable\s(?P<TABLENO>\d+)\s)?\-\-\s(?P<CURRENCY>%(LS)s|)?(?P<ANTESB>(\-)?\d)/(%(LS)s)?(?P<SBBB>\d+)(/(%(LS)s)?(?P<BB>\d+))?\s(?P<LIMIT>NL|FL||PL)\s(?P<GAME>Hold\'em|Omaha|Omaha\sHi/Lo|OmahaHiLo)\s-\-\s(?P<DATETIME>.*$)
          """ % substitutions, re.MULTILINE|re.VERBOSE)

def test_re_GameInfo3():
    text = "Hand#710910543B500014 - Freeroll to GOLD CHIPS T17122229 -- FREEROLL -- $0 + $0 -- 9 Max -- Table 4 -- 0/10/20 NL Hold'em -- 2023/09/22 - 17:35:27"
    match = re_GameInfo.search(text)
    assert match is not None
    assert match.group('HID') == '710910543B500014'
    assert match.group('TABLE') == 'Freeroll to GOLD CHIPS'
    assert match.group('DATETIME') == '2023/09/22 - 17:35:27'
    assert match.group('TABLENO') == '4'
    assert match.group('BUYIN') == '$0 + $0'
    assert match.group('TMAX') == '9'
    assert match.group('BIAMT') == '$0'
    assert match.group('BIRAKE') == '$0'
    assert match.group('ANTESB') == '0'
    assert match.group('SBBB') == '10'
    assert match.group('BB') == '20'
    assert match.group('LIMIT') == 'NL'
    assert match.group('GAME') == 'Hold\'em'


