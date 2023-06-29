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