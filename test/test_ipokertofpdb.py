import re


substitutions = {
    "LS": r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|",
    "PLYR": r"(?P<PNAME>[^\"]+)",
    "NUM": r"(?:\d+)|(\d+\s\d+)",
    "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
}

re_PlayerInfo = re.compile(
    r'<player( (seat="(?P<SEAT>[0-9]+)"|name="%(PLYR)s"|chips="(%(LS)s)?(?P<CASH>[%(NUM2)s]+)(%(LS)s)?"|dealer="(?P<BUTTONPOS>(0|1))"|win="(%(LS)s)?(?P<WIN>[%(NUM)s]+)(%(LS)s)?"|bet="(%(LS)s)?(?P<BET>[^"]+)(%(LS)s)?"|addon="\d*"|rebuy="\d*"|merge="\d*"|reg_code="[\d-]*"))+\s*/>'
    % substitutions,
    re.MULTILINE,
)


def test_re_PlayerInfo2():
    text = '<player bet="20" reg_code="5105918454" win="0" seat="10" dealer="1" rebuy="0" chips="20" name="clement10s" addon="0"/>'
    match = re_PlayerInfo.search(text)
    assert match is not None


def test_re_PlayerInfo7():
    text = (
        '<player bet="100" reg_code="" win="40" seat="3" dealer="0" rebuy="0" chips="1 480" name="pergerd" addon="0"/>'
    )
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group("SEAT") == "3"
    assert match.group("PNAME") == "pergerd"
    assert match.group("CASH") == "1 480"
    assert match.group("BUTTONPOS") == "0"
    assert match.group("WIN") == "40"
    assert match.group("BET") == "100"


def test_re_PlayerInfo3():
    text = '<player bet="100" reg_code="" win="40" seat="3" dealer="0" rebuy="0" chips="1 480" name="pergerd" addon="0"/><player bet="20" reg_code="5105918454" win="0" seat="10" dealer="1" rebuy="0" chips="20" name="clement10s" addon="0"/>'
    m = re_PlayerInfo.finditer(text)
    plist = {}
    for a in m:
        ag = a.groupdict()
        plist[a.group("PNAME")] = [int(a.group("SEAT")), (a.group("CASH")), (a.group("WIN")), False]
    assert len(plist) == 2


def test_re_PlayerInfo8():
    text = (
        '<player bet="740" reg_code="" win="1 480" seat="3" dealer="1" rebuy="0" chips="740" name="pergerd" addon="0"/>'
    )
    match = re_PlayerInfo.search(text)
    assert match is not None
    assert match.group("SEAT") == "3"
    assert match.group("PNAME") == "pergerd"
    assert match.group("CASH") == "740"
    assert match.group("BUTTONPOS") == "1"
    assert match.group("WIN") == "1 480"
    assert match.group("BET") == "740"


re_GameInfoTrny = re.compile(
    r"""
(?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
(?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
(?:(<rewarddrawn>(?P<REWARD>[%(NUM2)s%(LS)s]+)</rewarddrawn>))| 
(?:(<place>(?P<PLACE>.+?)</place>))|
(?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)\s\+\s(?P<BIRAKE2>[%(NUM2)s%(LS)s]+)</buyin>)|
(?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))|
(?:(<win>(%(LS)s)?(?P<WIN>[%(NUM2)s%(LS)s]+)</win>))
"""
    % substitutions,
    re.VERBOSE,
)


re_GameInfoTrny2 = re.compile(
    r"""
(?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
(?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
(?:(<place>(?P<PLACE>.+?)</place>))|
(?:(<buyin>(?P<BIAMT>[%(NUM2)s%(LS)s]+)\s\+\s)?(?P<BIRAKE>[%(NUM2)s%(LS)s]+)</buyin>)|
(?:(<totalbuyin>(?P<TOTBUYIN>[%(NUM2)s%(LS)s]+)</totalbuyin>))|
(?:(<win>(%(LS)s)?(?P<WIN>.+?|[%(NUM2)s%(LS)s]+)</win>))
"""
    % substitutions,
    re.VERBOSE,
)


def test_re_GameInfoTrny():
    text = """
  <tournamentcode>826763510</tournamentcode>
  <tournamentname>Sit’n’Go Twister 0.20€</tournamentname>
  <rewarddrawn>0,80€</rewarddrawn>
  <place>2</place>
  <buyin>0€ + 0,01€ + 0,19€</buyin>
  <totalbuyin>0,20€</totalbuyin>
  <win>0</win>
"""
    matches = list(re_GameInfoTrny.finditer(text))

    assert matches[0].group("TOURNO") == "826763510"
    assert matches[1].group("NAME") == "Sit’n’Go Twister 0.20€"
    assert matches[2].group("REWARD") == "0,80€"
    assert matches[3].group("PLACE") == "2"
    assert matches[4].group("BIAMT") == "0€"
    assert matches[4].group("BIRAKE") == "0,01€"
    assert matches[4].group("BIRAKE2") == "0,19€"
    assert matches[5].group("TOTBUYIN") == "0,20€"
    assert matches[6].group("WIN") == "0"


def test_re_GameInfoTrnywin():
    text = """
  <tournamentcode>829730818</tournamentcode>
  <tournamentname>Sit’n’Go Twister 0.20€</tournamentname>
  <rewarddrawn>0,40€</rewarddrawn>
  <place>1</place>
  <buyin>0€ + 0,01€ + 0,19€</buyin>
  <totalbuyin>0,20€</totalbuyin>
  <win>0,40€</win>
"""
    matches = list(re_GameInfoTrny.finditer(text))

    assert matches[0].group("TOURNO") == "829730818"
    assert matches[1].group("NAME") == "Sit’n’Go Twister 0.20€"
    assert matches[2].group("REWARD") == "0,40€"
    assert matches[3].group("PLACE") == "1"
    assert matches[4].group("BIAMT") == "0€"
    assert matches[4].group("BIRAKE") == "0,01€"
    assert matches[4].group("BIRAKE2") == "0,19€"
    assert matches[5].group("TOTBUYIN") == "0,20€"
    assert matches[6].group("WIN") == "0,40€"


def test_re_GameInfoTrny_red():
    text = """
  <tournamentcode>1061132557</tournamentcode>
  <tournamentname>E10 Freebuy Sat 1x30€</tournamentname>
  <place>N/A</place>
  <buyin>€0 + €0</buyin>
  <totalbuyin>€0</totalbuyin>
  <win>N/A</win>
"""
    matches = list(re_GameInfoTrny2.finditer(text))

    assert matches[0].group("TOURNO") == "1061132557"
    assert matches[1].group("NAME") == "E10 Freebuy Sat 1x30€"

    assert matches[2].group("PLACE") == "N/A"
    assert matches[3].group("BIAMT") == "€0"
    assert matches[3].group("BIRAKE") == "€0"

    assert matches[4].group("TOTBUYIN") == "€0"
    assert matches[5].group("WIN") == "N/A"


def test_re_GameInfoTrny_red():
    text = """
  <tournamentcode>1067382320</tournamentcode>
  <tournamentname>Series Freebuy Sat 1x125€</tournamentname>
  <place>851</place>
  <buyin>€0 + €0</buyin>
  <totalbuyin>€0</totalbuyin>
  <win>0</win>
"""
    matches = list(re_GameInfoTrny2.finditer(text))

    assert matches[0].group("TOURNO") == "1067382320"
    assert matches[1].group("NAME") == "Series Freebuy Sat 1x125€"

    assert matches[2].group("PLACE") == "851"
    assert matches[3].group("BIAMT") == "€0"
    assert matches[3].group("BIRAKE") == "€0"

    assert matches[4].group("TOTBUYIN") == "€0"
    assert matches[5].group("WIN") == "0"


re_TourNo = re.compile(r"(?P<TOURNO>\d+)$")


def test_re_Tourno1():
    text = "Sit’n’Go Twister 0.20€, 829730819"
    match = re_TourNo.search(text)
    assert match.group("TOURNO") == "829730819"


re_client = re.compile(r"<client_version>(?P<CLIENT>.*?)</client_version>")


def test_re_cliento1():
    text = "<client_version>23.5.1.13</client_version>"
    match = re_client.search(text)
    assert match.group("CLIENT") == "23.5.1.13"


re_MaxSeats = re.compile(r"<tablesize>(?P<SEATS>[0-9]+)</tablesize>", re.MULTILINE)


def test_MaxSeats1():
    text = "<tablesize>6</tablesize>"
    match = re_MaxSeats.search(text)
    assert match.group("SEATS") == "6"
