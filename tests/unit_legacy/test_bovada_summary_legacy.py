"""Regression tests for Bovada tournament summaries embedded in hand histories."""

from pathlib import Path
from unittest.mock import MagicMock

from fpdb_3_legacy.BovadaSummary import BovadaSummary

SAMPLE = (
    Path(__file__).resolve().parents[2]
    / "regression-test-files"
    / "tour"
    / "Bovada"
    / "Flop"
    / "NLHE-9max-USD-MTT - $1.000 Guaranteed (Rebuy) - $3-$0.30 - 201211.txt"
)


def test_bovada_embedded_summary_uses_current_converter_regexes() -> None:
    config = MagicMock()
    config.get_import_parameters.return_value = {}
    db = MagicMock()
    db.get_site_id.return_value = [(21,)]

    summary = BovadaSummary(
        db=db,
        config=config,
        siteName="Bovada",
        summaryText=SAMPLE.read_text(encoding="utf-8"),
        in_path=str(SAMPLE),
    )

    assert summary.tourNo == "1447554"
    assert summary.buyin == 300
    assert summary.fee == 30
    assert summary.currency == "USD"
    assert summary.ranks["Hero"] == [30]
    assert summary.winnings["Hero"] == [1302]
    assert summary.koCounts["Hero"] == [None]


def test_bovada_split_regex_matches_bovada_not_pokerstars() -> None:
    summary = object.__new__(BovadaSummary)
    split_re = summary.getSplitRe("")

    assert split_re.search("Bovada Hand #2691609440: HOLDEM Tournament #1447554")
    assert not split_re.search("PokerStars Tournament #1447554")
