"""Focused tests for the Merge tournament-summary adapter."""

from fpdb_3_legacy.MergeSummary import MergeSummary


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
