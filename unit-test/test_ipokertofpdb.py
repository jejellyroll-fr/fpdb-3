import re
import pytest


substitutions = {
    'LS': r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|",
          
    'PLYR': r'(?P<PNAME>[^\"]+)',
    'NUM': r'(?:\d+)|(\d+\s\d+)',
    'NUM2': r'\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b',  # Regex pattern for matching numbers with spaces
}

re_PlayerInfo = re.compile(r'<player( (seat="(?P<SEAT>[0-9]+)"|name="%(PLYR)s"|chips="(%(LS)s)?(?P<CASH>[%(NUM2)s]+)(%(LS)s)?"|dealer="(?P<BUTTONPOS>(0|1))"|win="(%(LS)s)?(?P<WIN>[%(NUM)s]+)(%(LS)s)?"|bet="(%(LS)s)?(?P<BET>[^"]+)(%(LS)s)?"|addon="\d*"|rebuy="\d*"|merge="\d*"|reg_code="[\d-]*"))+\s*/>' % substitutions, re.MULTILINE)



def test_re_PlayerInfo2():
    text = '<player bet="20" reg_code="5105918454" win="0" seat="10" dealer="1" rebuy="0" chips="20" name="clement10s" addon="0"/>'
    match = re_PlayerInfo.search(text)
    assert match is not None

def test_re_PlayerInfo7():
    text = '<player bet="100" reg_code="" win="40" seat="3" dealer="0" rebuy="0" chips="1 480" name="pergerd" addon="0"/>'
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == '3'
    assert match.group('PNAME') == 'pergerd'
    assert match.group('CASH') == '1 480'
    assert match.group('BUTTONPOS') == '0'
    assert match.group('WIN') == '40'
    assert match.group('BET') == '100'

def test_re_PlayerInfo3():
    text='<player bet="100" reg_code="" win="40" seat="3" dealer="0" rebuy="0" chips="1 480" name="pergerd" addon="0"/><player bet="20" reg_code="5105918454" win="0" seat="10" dealer="1" rebuy="0" chips="20" name="clement10s" addon="0"/>'
    m = re_PlayerInfo.finditer(text)
    plist = {}
    for a in m:
        ag = a.groupdict()
        plist[a.group('PNAME')] = [int(a.group('SEAT')), (a.group('CASH')), 
                                        (a.group('WIN')), False]
    assert len(plist) == 2  
    

def test_re_PlayerInfo8():
    text = '<player bet="740" reg_code="" win="1 480" seat="3" dealer="1" rebuy="0" chips="740" name="pergerd" addon="0"/>'
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group('SEAT') == '3'
    assert match.group('PNAME') == 'pergerd'
    assert match.group('CASH') == '740'
    assert match.group('BUTTONPOS') == '1'
    assert match.group('WIN') == '1 480'
    assert match.group('BET') == '740'
