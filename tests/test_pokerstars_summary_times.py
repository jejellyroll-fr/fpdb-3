"""Start and end times of a PokerStars tournament summary (#894).

The start date used to be captured from "Tournament started" to the end of the
file, and the last date in it kept. A "Tournament finished" line therefore
became the start time, and the end time was never read.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary
from tests.helpers.summary_regression import make_summary, read_text

STARS = Path(__file__).resolve().parents[1] / "regression-test-files" / "summaries" / "Stars"


def utc(*parts: int) -> datetime.datetime:
    return datetime.datetime(*parts, tzinfo=datetime.UTC)


def parse(name: str) -> PokerStarsSummary:
    summary = make_summary(PokerStarsSummary, read_text(STARS / name), "PokerStars", 2)
    summary.parseSummary()
    return summary


@pytest.mark.parametrize(
    ("name", "start", "end"),
    [
        # Tournament started 2018/12/13 4:30:00 ET / finished 2018/12/13 6:53:40 ET
        ("NLHE-9max-MTT-INR-136.50-13.50-201901.txt", utc(2018, 12, 13, 9, 30), utc(2018, 12, 13, 11, 53, 40)),
        # Both lines state a local time first and ET in brackets: ET is read.
        (
            "NLHE-MTT-USD-250-250-30-202005.reentry.ko.txt",
            utc(2020, 5, 5, 22, 0),
            utc(2020, 5, 6, 3, 4, 30),
        ),
    ],
)
def test_a_finished_tournament_has_its_own_start_and_end(
    name: str, start: datetime.datetime, end: datetime.datetime
) -> None:
    summary = parse(name)

    assert summary.startTime == start
    assert summary.endTime == end


def test_a_summary_without_a_finished_line_has_no_end_time() -> None:
    # Tournament started 2019/07/31 21:07:43 WET [2019/07/31 16:07:43 ET]
    summary = parse("6+Holdem-3max-STT-USD-1.00-201907.txt")

    assert summary.startTime == utc(2019, 7, 31, 20, 7, 43)
    assert summary.endTime is None


def test_an_email_of_several_tournaments_ends_the_first_one_with_its_own_finish() -> None:
    summary = parse("PokerStars Tournament History Request - Last 3 tournaments.eml")

    assert summary.startTime == utc(2020, 5, 4, 21, 37)
    assert summary.endTime == utc(2020, 5, 4, 22, 2, 50)
