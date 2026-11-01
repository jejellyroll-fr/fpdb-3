"""Unit tests for the legacy PacificPokerSummary (888) tournament-summary parser.

Exercises PacificPokerSummary.parseSummary() against the real 888/Pacific
summary corpus under regression-test-files/summaries/PacificPoker/.
TourneySummary.__init__ is patched out and its defaults are seeded so the
parser behaves as in the real pipeline (see test_winamax_summary.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.PacificPokerSummary import PacificPokerSummary

SUMMARY_DIR = Path(__file__).resolve().parents[2] / "regression-test-files" / "summaries" / "PacificPoker"

_INIT_DEFAULTS = {
    "tourneyName": None, "tourneyTypeId": None, "tourneyId": None,
    "startTime": None, "endTime": None, "tourNo": None, "currency": None,
    "buyinCurrency": None, "buyin": 0, "fee": 0, "hero": None, "maxseats": 0,
    "entries": 0, "speed": "Normal", "prizepool": 0, "buyInChips": 0, "mixed": None,
    "isRebuy": False, "isAddOn": False, "isKO": False, "isProgressive": False,
    "isMatrix": False, "isShootout": False, "isFast": False, "rebuyChips": None,
    "addOnChips": None, "rebuyCost": 0, "addOnCost": 0, "totalRebuyCount": None,
    "totalAddOnCount": None, "koBounty": 0, "isSng": False, "isStep": False,
    "stepNo": 0, "isChance": False, "chanceCount": 0, "isMultiEntry": False,
    "isReEntry": False, "isNewToGame": False, "isHomeGame": False, "isSplit": False,
    "isTime": False, "timeAmt": 0, "isSatellite": False, "isDoubleOrNothing": False,
    "isCashOut": False, "isOnDemand": False, "isFlighted": False, "isGuarantee": False,
    "guaranteeAmt": 0, "added": None, "addedCurrency": None, "isLottery": False,
    "comment": None,
}

ALL_SAMPLES = sorted(p.name for p in SUMMARY_DIR.glob("*.txt"))


def _clean_money(value: str) -> str:
    return value.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def make_summary(summary_text: str) -> PacificPokerSummary:
    config, db = MagicMock(), MagicMock()
    with patch("fpdb_3_legacy.TourneySummary.TourneySummary.__init__", return_value=None):
        summary = PacificPokerSummary(config=config, db=db, summaryText=summary_text, builtFrom="file")
    summary.config = config
    summary.db = db
    summary.summaryText = summary_text
    summary.hhtype = "summary"
    summary.sitename = "PacificPoker"
    summary.siteName = "PacificPoker"
    summary.siteId = 15
    summary.gametype = {}
    summary.in_path = "none"
    for attr, value in _INIT_DEFAULTS.items():
        setattr(summary, attr, value)
    summary.addPlayer = MagicMock()
    summary.clearMoneyString = MagicMock(side_effect=_clean_money)
    return summary


def parse_file(filename: str) -> PacificPokerSummary:
    summary = make_summary(_read_text(SUMMARY_DIR / filename))
    summary.parseSummary()
    return summary


@pytest.mark.parametrize("filename", ALL_SAMPLES)
def test_pacific_samples_parse(filename: str) -> None:
    summary = parse_file(filename)
    assert summary.tourNo is not None
    assert str(summary.tourNo).isdigit()
    assert summary.buyin >= 0
    assert summary.fee >= 0


def test_pacific_real_money_fields() -> None:
    summary = parse_file("NLHE-USD-MTT-3-201111.real.money.txt")
    assert summary.tourNo == "34471036"
    assert summary.buyin == 300
    assert summary.currency == "USD"


def test_pacific_freeroll_zero_buyin() -> None:
    summary = parse_file("NLHE-FREE-MTT-$75Freeroll20120217-Summary.txt")
    assert summary.buyin == 0


def test_pacific_rebuy_addon() -> None:
    summary = parse_file("NLHE-USD-MTT-3.15-201111.rebuys.addons.txt")
    assert str(summary.tourNo).isdigit()
    assert summary.buyin > 0


def test_pacific_unparseable_text_raises() -> None:
    summary = make_summary("this is not an 888 tournament summary")
    with pytest.raises(FpdbParseError):
        summary.parseSummary()
