"""The Parser Debugger's core (#903): detection, step trace, contract, lines, diagnostics."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from fpdb_3_legacy import parser_debug, parser_trace
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.parser_debug import (
    bug_report,
    debug_parse_file,
    debug_parse_text,
    diff_reports,
    render_text,
)
from fpdb_3_legacy.parser_debug_report import Diagnostic, StepTrace

ROOT = Path(__file__).resolve().parents[1]
SOKO = ROOT / "regression-test-files" / "unsupported-sites" / "soko"
SOKO_COMPLETE = SOKO / "soko_2005_001_complete_anonymized.txt"
SOKO_HEADERLESS = SOKO / "soko_2005_002_header_missing_anonymized.txt"
STARS = ROOT / "regression-test-files" / "cash" / "Stars" / "Flop" / "NLHE-6max-USD-0.05-0.10-200912.Allin-pre.txt"
BOVADA = ROOT / "tests" / "fixtures" / "hands" / "bovada" / "zone_poker.txt"


@pytest.fixture(scope="module")
def config_file(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("config") / "HUD_config.xml"
    shutil.copyfile(ROOT / "HUD_config.xml", path)
    return path


@pytest.fixture(scope="module")
def config(config_file) -> Config:
    return Config(file=str(config_file))


@pytest.fixture(scope="module")
def stars(config):
    return debug_parse_file(STARS, config)


def _kinds(report) -> set[str]:
    return {diagnostic.kind for diagnostic in report.diagnostics}


# ---------------------------------------------------------------------------
# The Sökö excerpts of #891: a refused game, and a text nobody recognises
# ---------------------------------------------------------------------------


def test_an_unsupported_game_is_named_at_its_line_and_step(config) -> None:
    report = debug_parse_file(SOKO_COMPLETE, config)

    assert report.verdict == "failed"
    assert report.detection.converter == "Entraction"
    assert report.detection.marker_line == 1
    [diagnostic] = [item for item in report.diagnostics if item.kind == "UnsupportedGame"]
    assert diagnostic.line == 1
    assert diagnostic.step == "determineGameType"
    assert "Soko Pot Limit EUR 0,25" in diagnostic.message
    assert diagnostic.line_text.startswith("Game # 90000001 - Soko")


def test_the_steps_after_a_failure_are_not_reached(config) -> None:
    [hand] = debug_parse_file(SOKO_COMPLETE, config).hands

    statuses = {step.step: step.status for step in hand.steps}
    assert statuses["determineGameType"] == "raised"
    assert statuses["readHandInfo"] == statuses["readCollectPot"] == "not reached"
    assert hand.status == "error"
    assert hand.error_type == "FpdbParseError"


def test_the_log_of_a_hand_is_captured(config) -> None:
    [hand] = debug_parse_file(SOKO_COMPLETE, config).hands

    assert any("determineGameType" in record.message for record in hand.logs)


def test_an_unrecognised_text_names_the_closest_converter(config) -> None:
    report = debug_parse_file(SOKO_HEADERLESS, config)

    assert report.detection.site is None
    assert not report.hands
    assert _kinds(report) == {"NotRecognized"}
    assert report.detection.closest[0].startswith("Entraction (Entraction)")
    assert "`Game\\s\\#\\s\\d+\\s\\-\\s`" in report.detection.closest[0]


def test_a_header_with_the_wrong_case_is_hinted(config, tmp_path) -> None:
    text = (
        SOKO_COMPLETE.read_text(encoding="utf-8").replace("Game # ", "GAME # ", 1).replace("Game ended", "GAME ENDED")
    )
    path = tmp_path / "upper.txt"
    path.write_text(text, encoding="utf-8")

    probes = {probe.converter: probe for probe in debug_parse_file(path, config).detection.probes}

    assert "once case is ignored" in probes["Entraction"].hint


# ---------------------------------------------------------------------------
# A hand that parses
# ---------------------------------------------------------------------------


def test_a_clean_hand_is_ok(stars) -> None:
    assert stars.verdict == "ok"
    assert stars.counts()["ok"] == 1
    assert stars.detection.converter == "PokerStars"
    assert stars.hands[0].violations == []
    assert {check["status"] for check in stars.hands[0].checks} == {"pass"}


def test_each_step_says_what_it_added(stars) -> None:
    steps = {step.label: step for step in stars.hands[0].steps}

    assert steps["readHandInfo"].changes["handid"] == "37165169101"
    assert steps["readPlayerStacks"].changes["players"] == "+6"
    assert steps["readCommunityCards(TURN)"].changes == {"board.TURN": "Ts"}
    assert "category=holdem" in steps["determineGameType"].result
    assert steps["readAction(PREFLOP)"].changes["actions.PREFLOP"] == "10"
    assert steps["readAction(PREFLOP)"].matches["re_action"] >= 10
    assert "readBringIn" not in steps  # a stud step: not expected of a hold'em hand


def test_every_line_says_which_regex_read_it(stars) -> None:
    lines = {mark.text: mark for mark in stars.hands[0].lines}

    assert "re_player_info" in lines["Seat 5: Hero ($29.85 in chips)"].regexes
    assert lines["*** HOLE CARDS ***"].status == "marker"
    assert lines["*** SUMMARY ***"].status == "marker"
    assert lines["Board [3d 7h Kh Ts 5c]"].status == "summary"
    assert lines["AAALISAAAA collected $39.35 from pot"].status == "unread"
    assert "UnreadLine" in _kinds(stars)


def test_the_extracted_hand_is_plain_data(stars) -> None:
    extracted = stars.hands[0].extracted

    assert extracted["header"]["handid"] == "37165169101"
    assert extracted["gametype"]["category"] == "holdem"
    assert [player["name"] for player in extracted["players"] if player["hero"]] == ["Hero"]
    assert extracted["players"][4]["hole_cards"] == ["Ac", "As"]
    assert extracted["board"]["FLOP"] == ["3d", "7h", "Kh"]
    assert extracted["pot"]["total"] == "41.40"
    json.dumps(extracted)


def test_the_regression_sidecars_are_compared(stars) -> None:
    sidecars = stars.hands[0].sidecars

    assert sidecars is not None
    assert sidecars["compared"] == [".hp"]
    assert {issue["sidecar"] for issue in sidecars["issues"]} <= {".hp"}
    assert ("SidecarMismatch" in _kinds(stars)) == (not sidecars["passed"])


def test_derived_stats_are_optional(config) -> None:
    report = debug_parse_file(STARS, config, trace_lines=False, derived=True)

    assert "Hero" in report.hands[0].extracted["derived"]["handsplayers"]
    assert report.hands[0].coverage == "Line coverage was not traced"


def test_pasted_text_is_debugged_like_its_file(config, stars) -> None:
    report = debug_parse_text(STARS.read_text(encoding="utf-8"), config)

    assert report.source == "pasted text"
    assert report.detection.site == stars.detection.site
    assert report.hands[0].extracted["players"] == stars.hands[0].extracted["players"]


# ---------------------------------------------------------------------------
# Several hands, rewritten streets, forced sites, crashes
# ---------------------------------------------------------------------------


def test_a_repeated_street_text_is_read_where_it_is(config) -> None:
    """Flop, turn and river can all read "Big Blind : Checks": each is mapped to its own lines."""
    report = debug_parse_file(BOVADA, config)
    hand = report.hands[1]
    by_number = {hand.start_line + mark.number - 1: mark for mark in hand.lines}
    river = next(number for number, mark in by_number.items() if mark.text.startswith("*** RIVER ***"))

    assert by_number[river + 1].regexes == ["re_action"]
    assert by_number[river + 2].regexes == ["re_action"]


def test_a_file_of_many_hands_keeps_its_line_numbers(config) -> None:
    report = debug_parse_file(BOVADA, config, trace_lines=False)
    lines = BOVADA.read_text(encoding="utf-8").splitlines()

    assert len(report.hands) == report.counts()["ok"]
    for hand in report.hands[:20]:
        assert lines[hand.start_line - 1].strip() == parser_debug.first_line(hand.text).strip()


def test_the_contract_debt_of_bovada_is_reported(config) -> None:
    report = debug_parse_file(BOVADA, config, trace_lines=False)

    broken = [item for item in report.diagnostics if item.kind == "ContractViolation" and item.severity == "error"]
    assert broken
    assert {item.step for item in broken} == {"readCommunityCards"}
    assert report.verdict == "failed"


def test_unread_lines_are_capped_in_the_list(config) -> None:
    report = debug_parse_file(BOVADA, config)

    unread = [item for item in report.diagnostics if item.kind == "UnreadLine"]
    assert len(unread) == parser_debug._MAX_LINE_DIAGNOSTICS + 1
    assert unread[-1].message.startswith("... and")


def test_a_forced_site_bypasses_the_detection(config) -> None:
    report = debug_parse_file(STARS, config, site="Winamax")

    assert report.detection.forced
    assert report.detection.converter == "Winamax"
    assert report.verdict == "failed"


def test_an_unknown_forced_site_lists_the_known_ones(config) -> None:
    report = debug_parse_file(STARS, config, site="Nowhere Poker")

    assert report.detection.site is None
    assert "Known sites:" in report.detection.message
    known_sites = report.detection.message.partition("Known sites: ")[2].split(", ")
    assert any(site == "PokerStars.COM" for site in known_sites)


def test_a_converter_crash_is_reported_as_one(config, monkeypatch) -> None:
    from fpdb_3_legacy.PokerStarsToFpdb import PokerStars

    def broken(self, hand):
        raise ValueError("boom")

    monkeypatch.setattr(PokerStars, "readPlayerStacks", broken)
    report = debug_parse_file(STARS, config, trace_lines=False)

    [crash] = [item for item in report.diagnostics if item.kind == "Crash"]
    assert crash.step == "readPlayerStacks"
    assert "the importer would stop on this file" in crash.message
    statuses = {step.step: step.status for step in report.hands[0].steps}
    assert statuses["readPlayerStacks"] == "raised"
    assert statuses["readAction"] == "not reached"


def test_an_empty_file_is_reported(config, tmp_path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    report = debug_parse_file(path, config)

    assert report.verdict == "failed"
    assert "empty" in report.detection.message


def test_the_configuration_is_not_written(config, config_file) -> None:
    before = config_file.read_bytes()

    debug_parse_file(STARS, config)
    debug_parse_file(SOKO_COMPLETE, config, site="PokerStars.COM")

    assert config_file.read_bytes() == before


# ---------------------------------------------------------------------------
# The traced regex
# ---------------------------------------------------------------------------


def test_a_traced_regex_behaves_like_the_regex() -> None:
    recorder = parser_trace.Recorder()
    recorder.start_hand("Seat 1: alice\nSeat 2: bob\n")
    pattern = re.compile(r"^Seat (\d+): (\w+)$", re.MULTILINE)
    traced = parser_trace.TracedPattern(pattern, "re_seat", recorder)

    assert traced.findall(recorder.hand_text) == pattern.findall(recorder.hand_text)
    assert [match.group(2) for match in traced.finditer(recorder.hand_text)] == ["alice", "bob"]
    assert traced.search("nothing") is None
    assert traced.pattern == pattern.pattern
    assert traced.flags == pattern.flags
    assert traced.sub("x", "Seat 3: carol") == "x"
    assert recorder.marks == {0: {"re_seat"}, 1: {"re_seat"}}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_the_text_report_names_the_verdict_and_the_failure(config) -> None:
    text = render_text(debug_parse_file(SOKO_COMPLETE, config), lines=True)

    assert "Verdict: FAILED" in text
    assert "UnsupportedGame" in text
    assert "raised       determineGameType" in text


def test_the_json_report_round_trips(stars) -> None:
    data = json.loads(stars.to_json())

    assert data["verdict"] == "ok"
    assert data["counts"]["ok"] == 1
    assert data["hands"][0]["extracted"]["header"]["handid"] == "37165169101"


def test_the_bug_report_replaces_player_names(stars) -> None:
    stars.diagnostics.append(Diagnostic("warning", "SeatWarning", "AAALISAAAA has a seat warning", hand_index=0))
    stars.hands[0].steps.append(
        StepTrace("readPlayers", "raised", error_type="ParseError", error="AAALISAAAA has an invalid seat")
    )
    report = bug_report(stars)

    assert "Blåveis" not in report
    assert "AAALISAAAA" not in report
    assert "Seat 5: Hero ($29.85 in chips)" in report
    assert "alice" in report
    assert "has a seat warning" in report
    assert "has an invalid seat" in report
    assert "Not anonymized" not in report


def test_a_bug_report_without_names_says_it_is_not_anonymized(config) -> None:
    report = bug_report(debug_parse_file(SOKO_COMPLETE, config))

    assert "Not anonymized" in report
    assert "UnsupportedGame" in report


def test_anonymize_replaces_whole_names_only() -> None:
    text = "Bob: calls\nBobby: folds\nHero2: bets"

    assert parser_debug.anonymize(text, ["Bob", "Bobby", "Hero2"], "Hero2") == "alice: calls\nbob: folds\nHero: bets"


def test_two_reports_are_compared_hand_by_hand(stars) -> None:
    previous = stars.to_dict()
    current = json.loads(json.dumps(previous))
    current["hands"][0]["extracted"]["pot"]["rake"] = "1.00"
    current["hands"][0]["status"] = "error"

    changes = diff_reports(previous, current)

    assert "hand 0: status ok -> error" in changes
    assert "hand 0: pot.rake: '2.05' -> '1.00'" in changes
    assert diff_reports(previous, previous) == []
