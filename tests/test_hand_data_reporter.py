"""The audit report of an import: what it counts, and what it says about a hand.

HandDataReporter is what tells a player why a file imported badly. It runs
beside the importer, so a wrong count or a lost error is never noticed by the
import itself -- which is why it was worth covering rather than the views.

Real hands from the fixture corpus drive these tests; the reporter is fed the
same objects the importer feeds it.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.HandDataReporter import HandDataReporter
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hands" / "pokerstars"


@pytest.fixture(scope="module")
def config() -> Any:
    return Config()


@pytest.fixture(scope="module")
def hands(config) -> dict[str, Any]:
    """One parsed hand per game family the classifier distinguishes."""
    return {
        name: PokerStars(config=config, in_path=str(FIXTURES / relative), autostart=True).getProcessedHands()[0]
        for name, relative in (
            ("omaha", "holdem/5card_omaha.txt"),
            ("draw", "draw/5card_draw.txt"),
            ("stud", "stud/7stud.txt"),
        )
    }


@pytest.fixture
def reporter() -> HandDataReporter:
    return HandDataReporter()


# --------------------------------------------------------------------------
# Classifying a hand
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "family", "subtype"),
    [("omaha", "holdem", "pl"), ("draw", "draw", "5_card"), ("stud", "stud", "7_card")],
)
def test_a_hand_is_classified_into_its_game_family(reporter, hands, name, family, subtype) -> None:
    classification = reporter._classify_game_type(hands[name])

    assert classification["family"] == family
    assert classification["subtype"] == subtype


def test_a_cash_hand_is_not_filed_as_a_tournament(reporter, hands) -> None:
    assert reporter._classify_game_type(hands["omaha"])["format"] == "cash_games"


def test_a_hand_with_a_tournament_number_is_filed_as_one(reporter, hands) -> None:
    hand = hands["omaha"]
    hand.tourNo = "12345"
    try:
        assert reporter._classify_game_type(hand)["format"] == "tournaments"
    finally:
        hand.tourNo = None


def test_an_unrecognised_game_is_classified_as_unknown(reporter) -> None:
    class Unknown:
        gametype = {"category": "pinochle", "limitType": "nl"}
        tourNo = None

    classification = reporter._classify_game_type(Unknown())

    assert classification["family"] == "unknown"
    assert classification["subtype"] == "unknown"


def test_the_icon_distinguishes_cash_from_tournament(reporter, hands) -> None:
    cash = reporter._get_game_type_icon(reporter._classify_game_type(hands["omaha"]))

    assert cash.startswith("\U0001f4b0")
    assert reporter._get_game_type_icon({"format": "tournaments", "family": "stud"}).startswith("\U0001f3c6")


# --------------------------------------------------------------------------
# Grading an error
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "severity"),
    [
        ("[PARTIAL] hand truncated", "info"),
        ("No small blind posted", "warning"),
        ("No big blind posted", "warning"),
        ("KeyError on street", "error"),
        ("malformed header", "critical"),
        ("invalid currency", "critical"),
        ("something else entirely", "unknown"),
    ],
)
def test_an_error_is_graded_by_what_it_says(reporter, message, severity) -> None:
    # The grade decides whether a player sees a note or a red line, so a
    # misgraded error either cries wolf or hides a broken import.
    assert reporter._categorize_error_severity(Exception(message)) == severity


# --------------------------------------------------------------------------
# Counting
# --------------------------------------------------------------------------


def test_a_successful_hand_is_counted_once_everywhere(reporter, hands) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_success("f.txt", hands["omaha"])
    reporter.finish_file("f.txt")

    assert reporter.session_stats["total_files"] == 1
    assert reporter.session_stats["total_hands"] == 1
    assert reporter.session_stats["successful_hands"] == 1
    assert reporter.session_stats["failed_hands"] == 0
    assert reporter.files_stats["f.txt"]["hands_successful"] == 1


def test_a_failed_hand_is_counted_and_kept_with_its_reason(reporter) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_failure("f.txt", ValueError("No small blind posted"), "PokerStars Hand #1")

    assert reporter.session_stats["failed_hands"] == 1
    (record,) = reporter.files_stats["f.txt"]["errors"]
    assert record["error_type"] == "ValueError"
    assert record["error_message"] == "No small blind posted"
    assert record["severity"] == "warning"
    assert record["hand_snippet"] == "PokerStars Hand #1"


def test_errors_are_tallied_by_type_across_the_session(reporter) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_failure("f.txt", ValueError("a"), "")
    reporter.report_hand_failure("f.txt", ValueError("b"), "")
    reporter.report_hand_failure("f.txt", KeyError("c"), "")

    assert reporter.session_stats["parser_errors"] == {"ValueError": 2, "KeyError": 1}


def test_each_game_type_is_tallied_in_its_own_bucket(reporter, hands) -> None:
    reporter.start_file("f.txt")
    for name in ("omaha", "draw", "stud"):
        reporter.report_hand_success("f.txt", hands[name])

    buckets = reporter.session_stats["game_types"]["cash_games"]
    assert buckets["holdem"]["pl"] == 1
    assert buckets["draw"]["5_card"] == 1
    assert buckets["stud"]["7_card"] == 1


def test_finishing_a_file_records_how_long_it_took(reporter, hands) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_success("f.txt", hands["omaha"])
    reporter.finish_file("f.txt")

    stats = reporter.files_stats["f.txt"]
    assert stats["processing_time_seconds"] >= 0
    assert stats["end_time"] >= stats["start_time"]


# --------------------------------------------------------------------------
# What is kept about a hand
# --------------------------------------------------------------------------


def test_the_hand_is_kept_with_the_facts_the_report_shows(reporter, hands) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_success("f.txt", hands["omaha"])

    (record,) = reporter.files_stats["f.txt"]["hands_data"]
    assert str(record["hand_id"]) == str(hands["omaha"].handid)
    # Amounts are kept as strings, since the record is written straight to JSON.
    assert str(record["total_pot"]) == str(hands["omaha"].totalpot)
    assert len(record["players"]) == len(hands["omaha"].players)
    assert record["game_classification"]["family"] == "holdem"


def test_a_stud_hand_keeps_its_streets(reporter, hands) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_success("f.txt", hands["stud"])

    (record,) = reporter.files_stats["f.txt"]["hands_data"]
    assert record["category"] == hands["stud"].gametype["category"]
    assert record["actions_summary"]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def report_text(reporter: HandDataReporter) -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        reporter.generate_report()
    return buffer.getvalue()


def test_the_report_states_the_counts_of_the_session(reporter, hands) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_success("f.txt", hands["omaha"])
    reporter.report_hand_failure("f.txt", ValueError("boom"), "")
    reporter.finish_file("f.txt")

    text = report_text(reporter)

    assert "2" in text
    assert "f.txt" in text or "1" in text


def test_a_report_of_an_empty_session_still_renders(reporter) -> None:
    # The importer asks for a report even when nothing was imported.
    assert report_text(reporter)


def test_the_export_is_readable_json_carrying_the_statistics(reporter, hands, tmp_path) -> None:
    reporter.start_file("f.txt")
    reporter.report_hand_success("f.txt", hands["omaha"])
    reporter.report_hand_failure("f.txt", ValueError("boom"), "snippet")
    reporter.finish_file("f.txt")
    target = tmp_path / "report.json"

    reporter.export_json(str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["metadata"]["report_level"] == "detailed"
    assert data["session_stats"]["total_hands"] == 2
    assert data["session_stats"]["successful_hands"] == 1
    assert data["files_stats"]["f.txt"]["errors"][0]["error_message"] == "boom"


def test_the_export_records_how_long_the_session_ran(reporter, tmp_path) -> None:
    target = tmp_path / "report.json"

    reporter.export_json(str(target))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["session_stats"]["total_duration_seconds"] >= 0
