from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PartyPokerSummary import PartyPokerSummary
from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker


def _hand():
    now = datetime.datetime(2026, 7, 13, 20, 0, tzinfo=datetime.UTC)
    return SimpleNamespace(
        handText="Player Alice finished in 1 place and received €12.50 EUR",
        in_path="party-tourney.txt",
        tourNo="12345",
        tourneyName="Sunday Party",
        tablename="Sunday Party",
        buyin=1000,
        fee=100,
        buyinCurrency="EUR",
        startTime=now,
        endTime=now,
        gametype={"base": "hold", "category": "holdem", "limitType": "nl", "mix": "none"},
        maxseats=9,
        entries=2,
        prizepool=Decimal("12.50"),
        isSng=False,
        isRebuy=False,
        isAddOn=False,
        isKO=False,
        isProgressive=False,
        ranks={"Alice": 1, "Bob": 2},
        winnings={"Alice": Decimal("12.50")},
    )


def test_summary_from_hand_preserves_tournament_results() -> None:
    db = MagicMock()
    db.get_site_id.return_value = [(9,)]

    summary = PartyPokerSummary.from_hand(db, Config(), _hand())

    assert summary.tourNo == "12345"
    assert summary.entries == 2
    assert summary.prizepool == 1250
    assert summary.ranks == {"Alice": [1], "Bob": [2]}
    assert summary.winnings == {"Alice": [1250], "Bob": [0]}
    assert summary.winningsCurrency == {"Alice": ["EUR"], "Bob": ["EUR"]}


def test_hand_parser_persists_results_only_with_injected_database() -> None:
    parser = PartyPoker(Config(), autostart=False)
    parser.db = MagicMock()
    hand = _hand()

    with patch("fpdb_3_legacy.PartyPokerSummary.PartyPokerSummary.from_hand") as from_hand:
        summary = from_hand.return_value
        parser.readTourneyResults(hand)

    from_hand.assert_called_once_with(parser.db, parser.config, hand, parser.sitename)
    summary.insertOrUpdate.assert_called_once_with()
