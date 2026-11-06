"""Page furniture must not be reported as partially imported summaries.

A summary file is split into chunks and several of them hold no tournament: the
head of an archive page, its column headers, its totals row, a mail header. The
importer counted each as "partial", so a transaction history with 5 tournaments
- all imported - was reported as "Stored: 5, Partial: 15".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fpdb_3_legacy.Exceptions import FpdbHandPartial, FpdbSummaryNotFound
from fpdb_3_legacy.WinningSummary import WinningSummary

ACR_PAGE = Path("regression-test-files/summaries/Winning/PlayerTransactionHistory.html")


def test_not_a_summary_is_still_a_partial_for_older_callers() -> None:
    """Subclassing keeps every ``except FpdbHandPartial`` working."""
    assert issubclass(FpdbSummaryNotFound, FpdbHandPartial)


@pytest.mark.skipif(not ACR_PAGE.is_file(), reason="transaction history fixture missing")
def test_only_the_tournament_rows_of_a_transaction_history_are_summaries() -> None:
    text = ACR_PAGE.read_text(encoding="utf-8", errors="replace")
    chunks = re.split(WinningSummary.getSplitRe(WinningSummary, text), text)

    rows = [c for c in chunks if WinningSummary.re_html_tourney_info.search(c)]
    furniture = [c for c in chunks if not WinningSummary.re_html_tourney_info.search(c)]

    # The page itself states "[Records 1-5] of 5".
    assert len(rows) == 5
    assert len(furniture) == 15

    for chunk in furniture:
        summary = WinningSummary.__new__(WinningSummary)
        summary.header = text
        summary.summaryText = chunk
        with pytest.raises(FpdbSummaryNotFound):
            summary.parseSummary()
