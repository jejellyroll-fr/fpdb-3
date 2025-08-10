import re

substitutions = {
    "LS": r"\$|\xe2\x82\xac|\xe2\u201a\xac|\u20ac|\xc2\xa3|\£|RSD|",
    "PLYR": r"(?P<PNAME>[^\"]+)",
    "NUM": r"(?:\d+)|(\d+\s\d+)",
    "NUM2": r"\b((?:\d{1,3}(?:\s\d{3})*)|(?:\d+))\b",  # Regex pattern for matching numbers with spaces
}

re_PlayerInfo = re.compile(
    r'<player( (seat="(?P<SEAT>[0-9]+)"|name="{PLYR}"|chips="({LS})?(?P<CASH>[{NUM2}]+)({LS})?"|dealer="(?P<BUTTONPOS>(0|1))"|win="({LS})?(?P<WIN>[{NUM}]+)({LS})?"|bet="({LS})?(?P<BET>[^"]+)({LS})?"|addon="\d*"|rebuy="\d*"|merge="\d*"|reg_code="[\d-]*"))+\s*/>'.format(
        **substitutions,
    ),
    re.MULTILINE,
)


def test_re_PlayerInfo2() -> None:
    text = '<player bet="20" reg_code="5105918454" win="0" seat="10" dealer="1" rebuy="0" chips="20" name="clement10s" addon="0"/>'
    match = re_PlayerInfo.search(text)
    assert match is not None


def test_re_PlayerInfo7() -> None:
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


def test_re_PlayerInfo3() -> None:
    text = '<player bet="100" reg_code="" win="40" seat="3" dealer="0" rebuy="0" chips="1 480" name="pergerd" addon="0"/><player bet="20" reg_code="5105918454" win="0" seat="10" dealer="1" rebuy="0" chips="20" name="clement10s" addon="0"/>'
    m = re_PlayerInfo.finditer(text)
    plist = {}
    for a in m:
        a.groupdict()
        plist[a.group("PNAME")] = [
            int(a.group("SEAT")),
            (a.group("CASH")),
            (a.group("WIN")),
            False,
        ]
    assert len(plist) == 2


def test_re_PlayerInfo8() -> None:
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
(?:(<rewarddrawn>(?P<REWARD>[{NUM2}{LS}]+)</rewarddrawn>))|
(?:(<place>(?P<PLACE>.+?)</place>))|
(?:(<buyin>(?P<BIAMT>[{NUM2}{LS}]+)\s\+\s)?(?P<BIRAKE>[{NUM2}{LS}]+)\s\+\s(?P<BIRAKE2>[{NUM2}{LS}]+)</buyin>)|
(?:(<totalbuyin>(?P<TOTBUYIN>.*)</totalbuyin>))|
(?:(<win>({LS})?(?P<WIN>[{NUM2}{LS}]+)</win>))
""".format(**substitutions),
    re.VERBOSE,
)


re_GameInfoTrny2 = re.compile(
    r"""
(?:(<tour(?:nament)?code>(?P<TOURNO>\d+)</tour(?:nament)?code>))|
(?:(<tournamentname>(?P<NAME>[^<]*)</tournamentname>))|
(?:(<place>(?P<PLACE>.+?)</place>))|
(?:(<buyin>(?P<BIAMT>[{NUM2}{LS}]+)\s\+\s)?(?P<BIRAKE>[{NUM2}{LS}]+)</buyin>)|
(?:(<totalbuyin>(?P<TOTBUYIN>[{NUM2}{LS}]+)</totalbuyin>))|
(?:(<win>({LS})?(?P<WIN>.+?|[{NUM2}{LS}]+)</win>))
""".format(**substitutions),
    re.VERBOSE,
)


def test_re_GameInfoTrny() -> None:
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


def test_re_GameInfoTrnywin() -> None:
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


def test_re_GameInfoTrny_red() -> None:
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


def test_re_GameInfoTrny_red2() -> None:
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


def test_re_Tourno1() -> None:
    text = "Sit’n’Go Twister 0.20€, 829730819"
    match = re_TourNo.search(text)
    assert match.group("TOURNO") == "829730819"


re_client = re.compile(r"<client_version>(?P<CLIENT>.*?)</client_version>")


def test_re_cliento1() -> None:
    text = "<client_version>23.5.1.13</client_version>"
    match = re_client.search(text)
    assert match.group("CLIENT") == "23.5.1.13"


re_MaxSeats = re.compile(r"<tablesize>(?P<SEATS>[0-9]+)</tablesize>", re.MULTILINE)


def test_MaxSeats1() -> None:
    text = "<tablesize>6</tablesize>"
    match = re_MaxSeats.search(text)
    assert match.group("SEATS") == "6"


# Test for re_action regex
re_action = re.compile(
    r'<action(?=(?:[^>]*\bno="(?P<ACT>\d+)"))(?=(?:[^>]*\bplayer="(?P<PNAME>[^"]+)"))(?=(?:[^>]*\btype="(?P<ATYPE>\d+)"))(?=(?:[^>]*\bsum="[^"]*?(?P<BET>\d+(?:\.\d+)?)"))[^>]*>',
    re.MULTILINE,
)


def test_re_action_fold() -> None:
    """Test fold action parsing."""
    text = '<action no="1" player="Joueur1" type="0" sum="0" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "1"
    assert match.group("PNAME") == "Joueur1"
    assert match.group("ATYPE") == "0"
    assert match.group("BET") == "0"


def test_re_action_call() -> None:
    """Test call action parsing."""
    text = '<action no="2" player="Joueur2" type="3" sum="100" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "2"
    assert match.group("PNAME") == "Joueur2"
    assert match.group("ATYPE") == "3"
    assert match.group("BET") == "100"


def test_re_action_bet() -> None:
    """Test bet action parsing."""
    text = '<action no="3" player="Joueur3" type="5" sum="200" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "3"
    assert match.group("PNAME") == "Joueur3"
    assert match.group("ATYPE") == "5"
    assert match.group("BET") == "200"


def test_re_action_raise_to() -> None:
    """Test raise to action parsing."""
    text = '<action no="4" player="Joueur4" type="23" sum="500" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "4"
    assert match.group("PNAME") == "Joueur4"
    assert match.group("ATYPE") == "23"
    assert match.group("BET") == "500"


def test_re_action_check() -> None:
    """Test check action parsing."""
    text = '<action no="5" player="Joueur5" type="4" sum="0" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "5"
    assert match.group("PNAME") == "Joueur5"
    assert match.group("ATYPE") == "4"
    assert match.group("BET") == "0"


def test_re_action_all_in() -> None:
    """Test all-in action parsing."""
    text = '<action no="6" player="Joueur6" type="7" sum="1000" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "6"
    assert match.group("PNAME") == "Joueur6"
    assert match.group("ATYPE") == "7"
    assert match.group("BET") == "1000"


def test_re_action_multiple_actions() -> None:
    """Test parsing multiple actions in sequence."""
    text = """<action no="1" player="Joueur1" type="0" sum="0" timestamp="1234567890"/>
<action no="2" player="Joueur2" type="3" sum="100" timestamp="1234567891"/>
<action no="3" player="Joueur3" type="5" sum="200" timestamp="1234567892"/>"""

    actions = {int(match.group("ACT")): match.groupdict() for match in re_action.finditer(text)}

    assert len(actions) == 3
    assert actions[1]["PNAME"] == "Joueur1"
    assert actions[1]["ATYPE"] == "0"
    assert actions[1]["BET"] == "0"
    assert actions[2]["PNAME"] == "Joueur2"
    assert actions[2]["ATYPE"] == "3"
    assert actions[2]["BET"] == "100"
    assert actions[3]["PNAME"] == "Joueur3"
    assert actions[3]["ATYPE"] == "5"
    assert actions[3]["BET"] == "200"


def test_re_action_with_spaces_in_name() -> None:
    """Test action parsing with spaces in player name."""
    text = '<action no="7" player="Joueur Avec Espaces" type="3" sum="50" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "7"
    assert match.group("PNAME") == "Joueur Avec Espaces"
    assert match.group("ATYPE") == "3"
    assert match.group("BET") == "50"


def test_re_action_decimal_bet() -> None:
    """Test action parsing with decimal bet amount."""
    text = '<action no="8" player="Joueur8" type="23" sum="15.50" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "8"
    assert match.group("PNAME") == "Joueur8"
    assert match.group("ATYPE") == "23"
    assert match.group("BET") == "15.50"


def test_re_action_currency_prefix() -> None:
    """Test action parsing with currency prefix in sum."""
    text = '<action no="9" player="Joueur9" type="5" sum="€25.00" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "9"
    assert match.group("PNAME") == "Joueur9"
    assert match.group("ATYPE") == "5"
    assert match.group("BET") == "25.00"


def test_re_action_real_ipoker_format() -> None:
    """Test with real iPoker format."""
    text = """<action no="1" player="Hero" type="1" sum="€0.05" timestamp="1234567890"/>
<action no="2" player="Villain" type="2" sum="€0.10" timestamp="1234567891"/>
<action no="3" player="Hero" type="3" sum="€0.10" timestamp="1234567892"/>
<action no="4" player="Villain" type="23" sum="€0.30" timestamp="1234567893"/>
<action no="5" player="Hero" type="0" sum="€0.00" timestamp="1234567894"/>"""

    actions = {int(match.group("ACT")): match.groupdict() for match in re_action.finditer(text)}

    assert len(actions) == 5
    assert actions[1]["PNAME"] == "Hero"
    assert actions[1]["ATYPE"] == "1"
    assert actions[1]["BET"] == "0.05"
    assert actions[2]["PNAME"] == "Villain"
    assert actions[2]["ATYPE"] == "2"
    assert actions[2]["BET"] == "0.10"
    assert actions[3]["PNAME"] == "Hero"
    assert actions[3]["ATYPE"] == "3"
    assert actions[3]["BET"] == "0.10"
    assert actions[4]["PNAME"] == "Villain"
    assert actions[4]["ATYPE"] == "23"
    assert actions[4]["BET"] == "0.30"
    assert actions[5]["PNAME"] == "Hero"
    assert actions[5]["ATYPE"] == "0"
    assert actions[5]["BET"] == "0.00"


def test_re_action_with_attributes_order() -> None:
    """Test action parsing with different attribute order."""
    text = '<action type="5" sum="€50.00" no="10" player="Player10" timestamp="1234567890"/>'
    match = re_action.search(text)
    assert match is not None
    assert match.group("ACT") == "10"
    assert match.group("PNAME") == "Player10"
    assert match.group("ATYPE") == "5"
    assert match.group("BET") == "50.00"
