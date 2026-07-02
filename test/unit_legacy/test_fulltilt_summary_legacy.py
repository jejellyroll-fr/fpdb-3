"""Unit tests for the legacy FullTiltPokerSummary tournament-summary parser.

Exercises FullTiltPokerSummary.parseSummary()/parseSummaryFile() against the
real Full Tilt summary corpus under regression-test-files/summaries/FTP/.

As in test/test_winamax_summary.py, TourneySummary.__init__ is patched out and
the attributes it would set are seeded with the same defaults so the parser
behaves as in the real pipeline.

Note: several corpus files are stored as misaligned UTF-16 and cannot be
decoded into the format the parser expects; those raise FpdbParseError in the
real pipeline too, so we parametrize over the files that decode cleanly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.FullTiltPokerSummary import FullTiltPokerSummary

SUMMARY_DIR = Path(__file__).resolve().parents[2] / "regression-test-files" / "summaries" / "FTP"

# Defaults that TourneySummary.__init__ sets (replicated because we patch it).
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

# Files in the corpus that decode cleanly and parse via parseSummaryFile.
PARSEABLE_SAMPLES = [
    "10Game-USD-SnG-8-201404.Satellite.to.Mini.FTOPS.line.error.txt",
    "27SD-USD-MTT-1-201303.txt",
    "3-Draw-Limit-USD-STT-2max-10-201211.Hero.loses.txt",
    "NLHE-2max-SnG-USD-20-201404.no.limitType.txt",
    "NLHE-6max-Matrix-USD-26-201211.match1.txt",
    "NLHE-6max-Matrix-USD-26-201211.match2.txt",
    "NLHE-6max-Matrix-USD-26-201211.match3.txt",
    "NLHE-6max-Matrix-USD-26-201211.match4.txt",
    "NLHE-6max-Matrix-USD-26-201211.txt",
    "NLHE-6max-SnG-USD-5-201305.txt",
    "NLHE-9max-MTT-USD-10-201301.rush.rebuy.10K.guar.txt",
    "NLHE-9max-MTT-USD-4-201104.rush.onDemand.txt",
    "NLHE-9max-MTT-USD-5-201304.chance.txt",
    "NLHE-9max-MTT-USD-50-201301.turbo.rush.guar.txt",
    "NLHE-9max-MTT-USD-70-2013.ko.guar.txt",
    "NLHE-9max-USD-4-201104.Rush.txt",
    "NLHE-Freeroll-MTT-201212.txt",
    "NLHE-MTT-USD-100-201005.cashout.txt",
    "NLHE-MTT-USD-255-201408.KO.count.bounties.txt",
    "NLHE-USD-SnG-6man-201101.Hero.cashes.txt",
    "NLHE-USD-SnG-9man-201101.Hero.cashes.txt",
    "NLHE-play-250-MTT-201211.txt",
    "Razz-USD-SnG-2man-201211.super.turbo.heads.up.txt",
]


def _clean_money(value: str) -> str:
    return value.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")


def make_summary(summary_text: str) -> FullTiltPokerSummary:
    config, db = MagicMock(), MagicMock()
    with patch("fpdb_3_legacy.TourneySummary.TourneySummary.__init__", return_value=None):
        summary = FullTiltPokerSummary(config=config, db=db, summaryText=summary_text, builtFrom="file")
    summary.config = config
    summary.db = db
    summary.summaryText = summary_text
    summary.hhtype = "summary"
    summary.sitename = "Full Tilt Poker"
    summary.siteName = "Full Tilt Poker"
    summary.siteId = 1
    summary.gametype = {}
    summary.in_path = "none"
    for attr, value in _INIT_DEFAULTS.items():
        setattr(summary, attr, value)
    summary.addPlayer = MagicMock()
    summary.clearMoneyString = MagicMock(side_effect=_clean_money)
    return summary


def parse_file(filename: str) -> FullTiltPokerSummary:
    summary = make_summary(_read_text(SUMMARY_DIR / filename))
    summary.parseSummary()
    return summary


@pytest.mark.parametrize("filename", PARSEABLE_SAMPLES)
def test_ftp_samples_parse(filename: str) -> None:
    summary = parse_file(filename)
    assert summary.tourNo is not None
    assert str(summary.tourNo).isdigit()
    assert summary.buyin >= 0
    assert summary.fee >= 0


def test_ftp_basic_mtt_fields() -> None:
    summary = parse_file("27SD-USD-MTT-1-201303.txt")
    assert summary.tourNo == "251286379"
    assert summary.buyin == 100
    assert summary.currency == "USD"


def test_ftp_knockout_summary() -> None:
    summary = parse_file("NLHE-MTT-USD-255-201408.KO.count.bounties.txt")
    assert summary.isKO is True
    assert summary.koBounty > 0


def test_ftp_cashout_summary() -> None:
    summary = parse_file("NLHE-MTT-USD-100-201005.cashout.txt")
    assert str(summary.tourNo).isdigit()


def test_ftp_utf16_misaligned_raises_parse_error() -> None:
    # A file stored as misaligned UTF-16 cannot be parsed; the parser raises.
    summary = make_summary(_read_text(SUMMARY_DIR / "27TD-USD-HUSnG-201101.Hero.wins.txt"))
    with pytest.raises(FpdbParseError):
        summary.parseSummary()


def test_ftp_unparseable_text_raises() -> None:
    summary = make_summary("this is not a full tilt summary")
    with pytest.raises(FpdbParseError):
        summary.parseSummary()
