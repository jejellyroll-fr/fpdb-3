import re
import pytest


re_GameInfo = re.compile(r"""SwCPoker\sHand\s*\#(?P<HID>\d+):\s((Tournament|Cashgame|sitngo)\s\((.*?)\)\#(?P<TOURNO>\d+),\s(?P<BUYIN>(?P<BIAMT>\d+)\+(?P<BIRAKE>\d+))\s|\s)(?P<GAME>(Hold\'em|Omaha|Omaha\s5\sCards))\s(?P<LIMIT>(NL|PL|Limit|Pot\sLimit|No\sLimit))\s((-\sLevel\s\w+\s)|)\((?P<SB>\d+(\.\d+)?)/(?P<BB>\d+(\.\d+)?)\)\s-\s(?P<DATETIME>.*)""",re.VERBOSE)


def test_re_GameInfo():
    text = 'SwCPoker Hand #183314831: Tournament (5 Card Omaha Freeroll [20 Chips])#183316169, 0+0 Omaha 5 Cards Pot Limit - Level I (10/20) - 2023/06/26 19:30:22 UTC'
    match = re_GameInfo.search(text)
    assert match is not None
    assert match.group('HID') == '183314831'
    assert match.group('TOURNO') == '183316169'
    assert match.group('BUYIN') == '0+0'
    assert match.group('BIAMT') == '0'
    assert match.group('BIRAKE') == '0'
    assert match.group('GAME') == 'Omaha 5 Cards'
    assert match.group('LIMIT') == 'Pot Limit'
    assert match.group('SB') == '10'
    assert match.group('BB') == '20'
    assert match.group('DATETIME') == '2023/06/26 19:30:22 UTC'


def test_re_GameInfo2():
    text = 'SwCPoker Hand #183387021: Tournament (NLH Freeroll [30 Chips])#183390848, 0+0 Hold\'em No Limit - Level I (10/20) - 2023/06/27 9:30:26 UTC'
    match = re_GameInfo.search(text)
    assert match is not None
    assert match.group('HID') == '183387021'

def test_re_GameInfo2():
    text = 'SwCPoker Hand #183411552:  Omaha Pot Limit (0.02/0.04) - 2023/06/27 14:43:04 UTC'
    match = re_GameInfo.search(text)
    assert match is not None
    assert match.group('HID') == '183411552'

def test_re_GameInfo2():
    text = 'SwCPoker Hand #183411639:  Hold\'em No Limit (0.02/0.04) - 2023/06/27 14:47:48 UTC'
    match = re_GameInfo.search(text)
    assert match is not None
    assert match.group('HID') == '183411639'


re_HandInfo = re.compile(r"""^Table\s(?P<TABLE>((\'No-Rake\sMicro\sStakes\s(\#\d+|\w+)\'\(\d+\))|)\s((?P<MAX>\d+)-(max|half|deep)|(?P<HU>HU))\s\(\w+\s\w+\))""",re.MULTILINE)

def test_re_HandInfo():
    text = """Table 'No-Rake Micro Stakes #1'(28248) 9-max (Real Money) Seat #7 is the button"""
    match = re_HandInfo.search(text)
    assert match is not None
    assert match.group('TABLE') == """'No-Rake Micro Stakes #1'(28248) 9-max (Real Money)"""
    assert match.group('MAX') == "9"
    assert match.group('HU') is None

def test_re_HandInfo2():
    text = """Table 'No-Rake Micro Stakes PLO'(24812) 9-max (Real Money) Seat #4 is the button"""
    match = re_HandInfo.search(text)
    assert match is not None
    assert match.group('TABLE') == """'No-Rake Micro Stakes PLO'(24812) 9-max (Real Money)"""
    assert match.group('MAX') == "9"
    assert match.group('HU') is None



re_PlayerInfo   = re.compile(r"""^Seat\s+(?P<SEAT>\d+):\s+(?P<PNAME>\w+)\s+\((?P<CASH>\d{1,3}(,\d{3})*(\.\d+)?)\sin\schips\)""" , re.MULTILINE|re.VERBOSE)

def test_re_PlayerInfo():
    text = """Seat 7: cheapsmack (4.75 in chips)"""
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == """7"""
    assert match.group('PNAME') == "cheapsmack"
    assert match.group('CASH') == "4.75"

def test_re_PlayerInfo2():
    text = """Seat 8: hero (4 in chips)"""
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == """8"""
    assert match.group('PNAME') == "hero"
    assert match.group('CASH') == "4"

def test_re_PlayerInfo3():
    text = """Seat 1: ab21ykd4gqnh (1,200 in chips)"""
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == """1"""
    assert match.group('PNAME') == "ab21ykd4gqnh"
    assert match.group('CASH') == "1,200"

def test_re_PlayerInfo3():
    text = """Seat 8: _all_in_ (958 in chips)"""
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == """8"""
    assert match.group('PNAME') == "_all_in_"
    assert match.group('CASH') == "958"

re_ButtonPos   = re.compile(r"""Seat\s+\#(?P<BUTTON>\d+)\sis\sthe\sbutton""",re.MULTILINE)



def test_re_ButtonPos():
    text = """\ufeffSwCPoker Hand #183411639:  Hold'em No Limit (0.02/0.04) - 2023/06/27 14:47:48 UTC\nTable 'No-Rake Micro Stakes #1'(28248) 9-max (Real Money) Seat #7 is the button\nSeat 7: cheapsmack (4.75 in chips)\nSeat 8: edinapoker (4 in chips)\ncheapsmack: posts small blind 0.02\nedinapoker: posts big blind 0.04\n*** HOLE CARDS ***\nDealt to edinapoker [3c 9d]\ncheapsmack: raises 0.06 to 0.08\nedinapoker: folds\nUncalled bet (0.04) returned to cheapsmack\n*** SHOW DOWN ***\ncheapsmack: doesn't show hand\ncheapsmack collected 0.08 from pot\n*** SUMMARY ***\nTotal pot 0.08 | Rake 0 \nSeat 7: cheapsmack (button) (small blind) collected (0.08)\nSeat 8: edinapoker (big blind) folded before Flop"""
    match = re_ButtonPos.search(text)
    assert match is not None
    assert match.group('BUTTON') == "7"

substitutions = {
                           'PLYR': r'(?P<PNAME>\w+)',
                          'BRKTS': r'(\(button\) |\(small blind\) |\(big blind\) |\(button\) \(small blind\) |\(button\) \(big blind\)| )?',
                    }

re_CollectPot       = re.compile(r"%(PLYR)s\s+%(BRKTS)s%(BRKTS)s(collected|wins|splits|won)\s+\((?P<POT>\d{1,3}(,\d{3})*(\.\d+)?)\)" %  substitutions, re.MULTILINE)
re_CollectPot2       = re.compile(r"^Seat (?P<SEAT>[0-9]+): %(PLYR)s ((%(BRKTS)s(((((?P<SHOWED>showed|mucked) \[(?P<CARDS>.*)\]( and (lost|(won|collected) \((?P<POT>[.\d]+)\)) with (?P<STRING>.+?)(\s\sand\s(won\s\([.\d]+\)|lost)\swith\s(?P<STRING2>.*))?)?$)|collected\s\((?P<POT2>[.\d]+)\)))|folded ((on the (Flop|Turn|River))|before Flop)))|folded before Flop \(didn't bet\))" %  substitutions, re.MULTILINE)



def test_re_CollectPot2():
    text = """Seat 7: cheapsmack (button) (small blind) collected (0.08)"""
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') == "0.08"
    assert match.group('SEAT') == "7"
    assert match.group('PNAME') == "cheapsmack"
    assert match.group('SHOWED') is None
    assert match.group('CARDS') is None

def test_re_CollectPot3():
    text = """Seat 4: cerami71 (button) mucked [2h 5c 3d 4h]"""
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') is None
    assert match.group('SEAT') == "4"
    assert match.group('PNAME') == "cerami71"
    assert match.group('SHOWED') == "mucked"
    assert match.group('CARDS') == "2h 5c 3d 4h"


def test_re_CollectPot4():
    text = """Seat 5: GER4SOUL (small blind) showed [5h 5s 6h 3s] and lost with a pair of Fives"""
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') is None
    assert match.group('SEAT') == "5"
    assert match.group('PNAME') == "GER4SOUL"
    assert match.group('SHOWED') == "showed"
    assert match.group('CARDS') == "5h 5s 6h 3s"
    assert match.group('STRING') == "a pair of Fives"

def test_re_CollectPot5():
    text = """Seat 6: edinapoker (big blind) showed [9h 5d 7c 4d] and won (0.42) with a flush, Ace high"""
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') == "0.42"
    assert match.group('POT2') is None
    assert match.group('SEAT') == "6"
    assert match.group('PNAME') == "edinapoker"
    assert match.group('SHOWED') == "showed"
    assert match.group('CARDS') == "9h 5d 7c 4d"
    assert match.group('STRING') == "a flush, Ace high"

def test_re_CollectPot6():
    text = """Seat 4: cerami71 (big blind) folded on the Turn"""
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') is None
    assert match.group('SEAT') == "4"
    assert match.group('PNAME') == "cerami71"
    assert match.group('SHOWED') is None
    assert match.group('CARDS') is None
    assert match.group('STRING') is None

def test_re_CollectPot7():
    text = """Seat 6: edinapoker (small blind) folded before Flop """
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') is None
    assert match.group('SEAT') == "6"
    assert match.group('PNAME') == "edinapoker"
    assert match.group('SHOWED') is None
    assert match.group('CARDS') is None
    assert match.group('STRING') is None

def test_re_CollectPot8():
    text = """Seat 4: cerami71 folded before Flop (didn't bet) """
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') is None
    assert match.group('SEAT') == "4"
    assert match.group('PNAME') == "cerami71"
    assert match.group('SHOWED') is None
    assert match.group('CARDS') is None
    assert match.group('STRING') is None


def test_re_CollectPot9():
    text = """Seat 5: GER4SOUL folded on the Turn """
    match = re_CollectPot2.search(text)
    assert match is not None
    assert match.group('POT') is None
    assert match.group('POT2') is None
    assert match.group('SEAT') == "5"
    assert match.group('PNAME') == "GER4SOUL"
    assert match.group('SHOWED') is None
    assert match.group('CARDS') is None
    assert match.group('STRING') is None

re_ShowdownAction   = re.compile(r"^(?P<PNAME>\w+): (shows \[(?P<CARDS>.*)\]\s\((?P<FHAND>.*?)\)|doesn't show hand|mucks hand)", re.MULTILINE)

def test_re_ShowdownAction():
    text = """GER4SOUL: shows [5h 5s 6h 3s] (a pair of Fives)"""
    match = re_ShowdownAction.search(text)
    assert match is not None
    assert match.group('CARDS') == "5h 5s 6h 3s"


re_Action           = re.compile(r"""^%(PLYR)s:(?P<ATYPE>\sbets|\schecks|\sraises|\scalls|\sfolds|\sdiscards|\sstands pat)(?:\s(?P<POT>\d{1,3}(?:,\d{3})*(\.\d+)?)(?:\sto\s(?P<BET>\d{1,3}(?:,\d{3})*(\.\d+)?))?)?"""
                         %  substitutions, re.MULTILINE|re.VERBOSE)



def test_re_Action():
    text = """cheapsmack: raises 0.06 to 0.08"""
    match = re_Action.search(text)
    assert match is not None
    assert match.group('POT') == "0.06"
    assert match.group('BET') == "0.08"
    assert match.group('ATYPE') == " raises"
    assert match.group('PNAME') == "cheapsmack"

def test_re_Action_checks():
    text = """GER4SOUL: checks"""
    match = re_Action.search(text)
    assert match is not None
    assert match.group('ATYPE') == " checks"
    assert match.group('PNAME') == "GER4SOUL"
    assert match.group('POT') is None  # Updated assertion to handle 'POT' being None
    assert match.group('BET') is None  # Updated assertion to handle 'BET' being None
