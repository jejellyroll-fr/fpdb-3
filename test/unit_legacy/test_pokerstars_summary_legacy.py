"""Unit tests for the legacy PokerStarsSummary tournament-summary parser.

These exercise PokerStarsSummary.parseSummaryFile() against the real sample
summaries under regression-test-files/summaries/Stars/, plus the error paths.

The harness mirrors test/test_winamax_summary.py: TourneySummary.__init__ is
patched out, and the attributes that __init__ would normally set are seeded
with the same defaults (see TourneySummary.__init__) so the parser behaves
exactly as it does in the real pipeline.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fpdb_3_legacy.Exceptions import FpdbHandPartial, FpdbParseError
from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary
from fpdb_3_legacy.TourneySummary import TourneySummary

SUMMARY_DIR = (Path(__file__).resolve().parents[2] / "regression-test-files" / "summaries" / "Stars")

# Defaults that TourneySummary.__init__ sets; replicated because we patch __init__.
_INIT_DEFAULTS = {
    "tourneyName": None,
    "startTime": None,
    "endTime": None,
    "tourNo": None,
    "currency": None,
    "buyin": 0,
    "fee": 0,
    "maxseats": 0,
    "entries": 0,
    "speed": "Normal",
    "prizepool": 0,
    "isRebuy": False,
    "isAddOn": False,
    "isKO": False,
    "rebuyCost": 0,
    "addOnCost": 0,
    "koBounty": 0,
    "isSng": False,
    "isSplit": False,
    "isSatellite": False,
    "added": None,
    "addedCurrency": None,
    "comment": None,
    "players": {},
    "ranks": {},
    "winnings": {},
    "winningsCurrency": {},
    "rebuyCounts": {},
    "addOnCounts": {},
    "koCounts": {},
}


def _clean_money(value: str) -> str:
    """Stand-in for TourneySummary.clearMoneyString used by the parser."""
    return value.replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()


def make_summary(summary_text: str, *, hhtype: str = "summary") -> PokerStarsSummary:
    """Build a PokerStarsSummary ready to parse `summary_text`."""
    config, db = MagicMock(), MagicMock()
    with patch("fpdb_3_legacy.TourneySummary.TourneySummary.__init__", return_value=None):
        summary = PokerStarsSummary(config=config, db=db, summaryText=summary_text, builtFrom="file")
    summary.config = config
    summary.db = db
    summary.summaryText = summary_text
    summary.hhtype = hhtype
    summary.sitename = "PokerStars"
    summary.siteName = "PokerStars"
    summary.siteId = 2
    summary.gametype = {}
    summary.in_path = "none"
    for attr, value in _INIT_DEFAULTS.items():
        setattr(summary, attr, value.copy() if isinstance(value, dict) else value)
    summary.addPlayer = MagicMock(side_effect=lambda *args, **kwargs: TourneySummary.addPlayer(summary, *args, **kwargs))
    summary.clearMoneyString = MagicMock(side_effect=_clean_money)
    return summary


def parse_file(filename: str) -> PokerStarsSummary:
    text = (SUMMARY_DIR / filename).read_text(encoding="utf-8", errors="ignore")
    summary = make_summary(text)
    summary.parseSummaryFile()
    return summary


# Every standard .txt summary in the corpus parses cleanly via parseSummaryFile.
ALL_SAMPLES = sorted(p.name for p in SUMMARY_DIR.glob("*.txt"))


@pytest.mark.parametrize("filename", ALL_SAMPLES)
def test_sample_summaries_parse(filename: str) -> None:
    """Each sample parses and yields a numeric tour number."""
    summary = parse_file(filename)
    assert summary.tourNo is not None
    assert str(summary.tourNo).isdigit()
    assert summary.buyin >= 0
    assert summary.fee >= 0


def test_knockout_summary_fields() -> None:
    summary = parse_file("NLHE-9max-MTT-USD-2.50-201305.KO.v1.txt")
    assert summary.tourNo == "734695129"
    assert summary.buyin == 250
    assert summary.fee == 20
    assert summary.currency == "USD"
    assert summary.entries == 5305
    # Parser converts the bracketed ET time (15:00 EDT) to UTC and keeps tzinfo.
    assert summary.startTime.replace(tzinfo=None) == datetime.datetime(2013, 5, 26, 19, 0, 0)
    assert summary.addPlayer.call_count == 5309


def test_inr_currency_summary() -> None:
    summary = parse_file("NLHE-9max-MTT-INR-136.50-13.50-201901.txt")
    assert summary.currency == "INR"
    assert summary.buyin == 13650


def test_play_money_summary() -> None:
    summary = parse_file("NLHE-Play-STT-20110405.txt")
    assert summary.currency == "play"


def test_pokerstars_fr_summary_uses_eur_cents_for_cash_prizepool() -> None:
    text = """PokerStars Tournament #4006174726, No Limit Hold'em
Buy-In: €0.91/€0.09 EUR
3 players
Total Prize Pool: €9.50 EUR
Tournament started 2026/06/05 22:43:55 CET [2026/06/05 16:43:55 ET]
Tournament finished 2026/06/05 22:52:21 CET [2026/06/05 16:52:21 ET]
  1: jeje_sat (France), €9.50 (100%)
  2: PeraLimones (Spain),
  3: krubiis (Spain),

You finished in 1st place.
"""
    summary = make_summary(text)
    summary.in_path = (
        "/Users/jde/Library/Application Support/PokerStarsFR/HandHistory/jeje_sat/"
        "TS20260605 T4006174726 No Limit Hold'em.txt"
    )

    summary.parseSummaryFile()

    assert summary.tourNo == "4006174726"
    assert summary.buyin == 91
    assert summary.fee == 9
    assert summary.currency == "EUR"
    assert summary.buyinCurrency == "EUR"
    assert summary.prizepool == 950
    assert summary.ranks["jeje_sat"] == [1]
    assert summary.winnings["jeje_sat"] == [950]
    assert summary.winningsCurrency["jeje_sat"] == ["EUR"]


def test_pokerstars_fr_summary_with_ticket_prizepool_stays_eur() -> None:
    """Regression: a non-numeric "ticket" prize pool must not break Buy-In parsing.

    The main regex used to fail when the prize pool was a Power Path ticket
    ("Total Prize Pool: €1 Step 2 MTT Power Path ticket"), falling back to a
    looser pattern that mis-read "€0.46/€0.04 EUR" as buyin=6/fee=4 and currency
    USD (stored as 600/400 cents under PokerStars.EU). It must stay EUR 46/4.
    """
    text = """PokerStars Tournament #4006175219, No Limit Hold'em
Buy-In: €0.46/€0.04 EUR
3 players
Total Prize Pool: €1 Step 2 MTT Power Path ticket
Tournament started 2026/06/05 22:42:58 CET [2026/06/05 16:42:58 ET]
Tournament finished 2026/06/05 22:52:41 CET [2026/06/05 16:52:41 ET]
  1: currican83 (Spain), €1 Step 2 MTT Power Path ticket
  2: jeje_sat (France),
  3: mikolaiv26 (Portugal),

You finished in 2nd place.
"""
    summary = make_summary(text)
    summary.in_path = (
        "/Users/jde/Library/Application Support/PokerStarsFR/HandHistory/jeje_sat/"
        "TS20260605 T4006175219 No Limit Hold'em.txt"
    )

    summary.parseSummaryFile()

    assert summary.tourNo == "4006175219"
    assert summary.buyin == 46
    assert summary.fee == 4
    assert summary.currency == "EUR"
    assert summary.buyinCurrency == "EUR"
    assert summary.ranks["jeje_sat"] == [2]


def test_pokerstars_kick_off_summary_variant_parses() -> None:
    text = """PokerStars Kick-Off Tournament #4006178830, No Limit Hold'em
4 players
Tournament started 2026/06/05 22:53:48 CET [2026/06/05 16:53:48 ET]
Tournament finished 2026/06/05 22:58:56 CET [2026/06/05 16:58:56 ET]
  1: rouxyrox (France),
  2: Moninp (France),
  3: ManuelRialdo (France),
  4: jeje_sat (France),

You finished in 4th place.You started with a value of €0.88 and finished with no value.
"""
    summary = make_summary(text)

    assert PokerStarsSummary.re_identify.search(text)
    summary.parseSummaryFile()

    assert summary.tourNo == "4006178830"
    assert summary.entries == 4
    assert summary.ranks["jeje_sat"] == [4]
    assert summary.winnings["jeje_sat"] == [0]


def test_reentry_ko_summary() -> None:
    summary = parse_file("NLHE-MTT-USD-250-250-30-202005.reentry.ko.txt")
    assert str(summary.tourNo).isdigit()
    assert summary.buyin > 0


def test_empty_text_raises_parse_error() -> None:
    summary = make_summary("this is not a pokerstars summary at all")
    with pytest.raises(FpdbParseError):
        summary.parseSummaryFile()


def test_history_request_header_raises_partial() -> None:
    summary = make_summary("History Request - some body that follows the header")
    with pytest.raises(FpdbHandPartial):
        summary.parseSummaryFile()


def test_email_header_raises_partial() -> None:
    summary = make_summary("Delivered-To: someone@example.com\nbody")
    with pytest.raises(FpdbHandPartial):
        summary.parseSummaryFile()


def test_multiple_tournaments_raises_partial() -> None:
    text = (
        "PokerStars Tournament #111, No Limit Hold'em\n"
        "PokerStars Tournament #222, No Limit Hold'em\n"
    )
    summary = make_summary(text)
    with pytest.raises(FpdbHandPartial):
        summary.parseSummaryFile()


def test_parse_summary_dispatch_unknown_type_raises() -> None:
    summary = make_summary("anything")
    summary.hhtype = "bogus"
    summary._cleanEmailFormat = MagicMock(side_effect=lambda t: t)
    with pytest.raises(FpdbParseError):
        summary.parseSummary()


def test_parse_summary_from_hh_not_supported() -> None:
    summary = make_summary("anything")
    with pytest.raises(FpdbParseError):
        summary.parseSummaryFromHH()


def test_clean_email_format_empty_returns_empty() -> None:
    summary = make_summary("x")
    assert summary._cleanEmailFormat("") == ""


def test_clean_email_format_non_email_unchanged() -> None:
    summary = make_summary("x")
    text = "PokerStars Tournament #999, No Limit Hold'em\nBuy-In: $1.00 USD"
    assert summary._cleanEmailFormat(text) == text


def test_clean_email_format_extracts_single_tournament() -> None:
    summary = make_summary("x")
    text = (
        "Delivered-To: hero@example.com\n"
        "Subject: your summary\n"
        "\n"
        "PokerStars Tournament #12345, No Limit Hold'em\n"
        "Buy-In: $1.00 USD\n"
    )
    cleaned = summary._cleanEmailFormat(text)
    assert cleaned.startswith("PokerStars Tournament #12345")
    assert "Delivered-To" not in cleaned


def test_clean_email_format_multiple_tournaments_returns_first() -> None:
    summary = make_summary("x")
    text = (
        "Delivered-To: hero@example.com\n"
        "\n"
        "PokerStars Tournament #111, No Limit Hold'em\n"
        "Buy-In: $1.00 USD\n"
        "PokerStars Tournament #222, No Limit Hold'em\n"
        "Buy-In: $2.00 USD\n"
    )
    cleaned = summary._cleanEmailFormat(text)
    assert "#111" in cleaned
    assert "#222" not in cleaned
