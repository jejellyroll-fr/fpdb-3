"""The PokerStars tournament archive page: dates, and what is not a summary.

Importing an archive page stored every tournament with the placeholder date
2000-01-01 and reported its HTML furniture as partially imported summaries.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

from fpdb_3_legacy.Exceptions import FpdbSummaryNotFound
from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary

ARCHIVE = Path("regression-test-files/summaries/Stars/PokerStars-MTT-Archive-201007.htm")


@pytest.mark.parametrize(
    "text",
    ["1/1/2012 11:45:57 PM", "3/18/2005 11:09:43 PM", "12/31/2021 1:05:00 AM"],
)
def test_the_archive_timestamp_is_read(text: str) -> None:
    """The pattern spanned two source lines without re.VERBOSE.

    Its newline and indentation were therefore part of the pattern and no row
    ever matched, so every tournament of an archive page was dated 2000-01-01.
    """
    match = PokerStarsSummary.re_html_date_time.search(text)

    assert match is not None
    assert match.group("Y") == text.split("/")[2].split(" ")[0]


def test_the_date_of_an_archive_row_is_its_own() -> None:
    match = PokerStarsSummary.re_html_date_time.search("1/1/2012 11:45:57 PM")

    assert match is not None
    parsed = datetime.datetime(  # noqa: DTZ001 - the page states no timezone in this column
        int(match.group("Y")),
        int(match.group("M")),
        int(match.group("D")),
    )
    assert parsed.date() == datetime.date(2012, 1, 1)


@pytest.mark.skipif(not ARCHIVE.is_file(), reason="archive fixture missing")
def test_the_head_of_the_page_is_not_a_partial_summary() -> None:
    """The chunk before the first tournament holds no summary at all.

    Reported as partial, it told the user that summaries had failed in a file
    whose tournaments all imported.
    """
    text = ARCHIVE.read_text(encoding="cp1252", errors="replace")
    head = re.split(r"(?i)</tr\s*>", text)[0]
    summary = PokerStarsSummary.__new__(PokerStarsSummary)
    summary.header = head
    summary.summaryText = head

    with pytest.raises(FpdbSummaryNotFound):
        summary.parseSummaryHtml()
