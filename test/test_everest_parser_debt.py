"""Focused regressions for Everest parser debt removal."""

import datetime
from types import SimpleNamespace

from fpdb_3_legacy.EverestToFpdb import Everest

SESSION = (
    '<SESSION time="1" tableName="Mount Alpha" id="1" type="ring" money="$" '
    'screenName="Hero" game="hold-em" gametype="no-limit"/>'
)
HAND = '<HAND time="1291155932" id="42" index="1" blinds="$0.50/$1.00"'


def test_everest_hand_fragment_inherits_session_table_name() -> None:
    parser = Everest.__new__(Everest)

    game = parser.parseHeader(HAND, f"{SESSION}\n{HAND}")

    assert game["TABLENAME"] == "Mount Alpha"
    assert game["currency"] == "USD"


def test_everest_epoch_is_read_as_utc() -> None:
    parser = Everest.__new__(Everest)
    parser.info = {"TABLENAME": "Mount Alpha"}
    hand = SimpleNamespace(
        handText=HAND,
        gametype={"type": "ring", "sb": None, "bb": None},
        maxseats=6,
    )

    parser.readHandInfo(hand)

    assert hand.startTime == datetime.datetime(2010, 11, 30, 22, 25, 32, tzinfo=datetime.UTC)
    assert hand.tablename == "Mount Alpha"
