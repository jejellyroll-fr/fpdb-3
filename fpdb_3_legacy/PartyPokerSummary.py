"""PartyPoker tournament results stored at the end of hand histories."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fpdb_3_legacy.TourneySummary import TourneySummary


class PartyPokerSummary(TourneySummary):
    """Adapt tournament result fields parsed by ``PartyPokerToFpdb``."""

    sitename = "PartyPoker"
    siteId = 9
    hhtype = "summary"

    def parseSummary(self) -> None:
        """Party results are parsed by the hand converter before construction."""

    @classmethod
    def from_hand(cls, db: Any, config: Any, hand: Any, site_name: str = "PartyPoker") -> PartyPokerSummary:
        """Build a database-ready summary from one parsed tournament hand."""
        summary = cls(
            db=db,
            config=config,
            siteName=site_name,
            summaryText=hand.handText,
            in_path=getattr(hand, "in_path", "-"),
            builtFrom="HHC",
            header="",
        )
        summary.tourNo = hand.tourNo
        summary.tourneyName = getattr(hand, "tourneyName", None) or getattr(hand, "tablename", None)
        summary.buyin = hand.buyin
        summary.fee = hand.fee
        summary.buyinCurrency = hand.buyinCurrency
        summary.currency = hand.buyinCurrency
        summary.startTime = hand.startTime
        summary.endTime = getattr(hand, "endTime", hand.startTime)
        summary.gametype = hand.gametype
        summary.maxseats = hand.maxseats
        summary.entries = hand.entries
        summary.prizepool = int(Decimal(hand.prizepool) * 100)
        summary.speed = getattr(hand, "speed", "Normal") or "Normal"
        summary.isSng = hand.isSng
        summary.isRebuy = hand.isRebuy
        summary.isAddOn = hand.isAddOn
        summary.isKO = hand.isKO
        summary.isProgressive = getattr(hand, "isProgressive", False)

        for name, rank in hand.ranks.items():
            winnings = int(Decimal(hand.winnings.get(name, 0)) * 100)
            summary.addPlayer(rank, name, winnings, summary.currency, 0, 0, 0)
        return summary
