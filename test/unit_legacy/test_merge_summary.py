"""Focused tests for the Merge tournament-summary adapter."""

import pytest

from fpdb_3_legacy.Exceptions import FpdbParseError
from fpdb_3_legacy.MergeSummary import MergeSummary


def _html_summary(status: str) -> str:
    return f"""
    <html><body>
      <table>
        <tr><th>Status:</th>
          <td>{status}</td></tr>
        <tr><th>Game Type </th>
          <td>No Limit Texas Holdem </td></tr>
        <tr><th>Game ID</th>
          <td>12345-1</td></tr>
        <tr><th>Name </th>
          <td>$10 Test Tournament </td></tr>
        <tr><th>Total Prizepool </th>
          <td>100.00 </td></tr>
        <tr><th>Buy In </th>
          <td>10.00 </td></tr>
        <tr><th>Entry Fee </th>
          <td>1.00 </td></tr>
      </table>
      <table>
        <tr><td align="center"> 1</td>
          <td>Alice</td>
          <td>$100.00</td>
        </tr>
      </table>
    </body></html>
    """


def _summary(status: str) -> MergeSummary:
    summary = object.__new__(MergeSummary)
    summary.resetInfo()
    summary.summaryText = _html_summary(status)
    return summary


def test_split_regex_is_callable_as_instance_method() -> None:
    summary = object.__new__(MergeSummary)

    split_re = summary.getSplitRe("")

    assert split_re.search("PokerStars Tournament 123") is not None


def test_reset_info_restores_optional_identifiers() -> None:
    summary = object.__new__(MergeSummary)
    summary.startTime = object()
    summary.tourNo = "123"

    summary.resetInfo()

    assert summary.startTime is None
    assert summary.tourNo is None
    assert summary.gametype == {"category": None, "limitType": None, "mix": "none"}


def test_parse_summary_file_requires_finished_status() -> None:
    with pytest.raises(FpdbParseError, match="not finished"):
        _summary("Running").parseSummaryFile()


def test_parse_summary_file_reads_finished_tournament() -> None:
    summary = _summary("Finished")

    summary.parseSummaryFile()

    assert summary.tourNo == "12345"
    assert summary.gametype == {"category": "holdem", "limitType": "nl", "mix": "none"}
    assert (summary.buyin, summary.fee, summary.prizepool) == (1000, 100, 100)
    assert summary.entries == 1
    assert summary.winnings == {"Alice": [10000]}
