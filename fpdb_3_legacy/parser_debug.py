"""The Parser Debugger's core: everything a converter did with a hand history (#903).

Give it a file, or pasted text, and it returns a :class:`ParseDebugReport`:

* **detection** -- the site and skin the importer would choose, why, which other
  converters were tried, and, when none recognises the text, which came closest;
* for each hand: its **status** (ok, partial, skipped, error), a **step trace**
  of the converter's pipeline (``determineGameType``, ``readHandInfo``,
  ``readPlayerStacks``...: called or not, raised or not, and what each one added
  to the hand), the **contract** of the generic parser checked step by step
  (:mod:`parser_contract`), the **whole-hand checks**, the **log records** the
  parse emitted, a **line coverage** of the hand text (which regex read each
  line, which lines no regex touched), the **extracted hand**, and the
  comparison with the regression **sidecars** when the file has some;
* a flat list of **diagnostics**, each with its severity, kind, hand and line.

Detection and parsing are the importer's own: :class:`IdentifySite` picks the
converter, the converter splits and parses the hands. Nothing touches a
database and nothing is written to the configuration. The tracing only exists
on the converter instances built here: the import path is unchanged.

The CLI (``tools/parser_debugger.py``) and the GUI (*Tools > Parser Debugger*)
both render this report.
"""

from __future__ import annotations

import contextlib
import datetime
import re
import tempfile
import time
import traceback
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from fpdb_3_legacy import parser_contract
from fpdb_3_legacy.Exceptions import FpdbHandPartial, FpdbHandSkipped
from fpdb_3_legacy.IdentifySite import FPDBFile, IdentifySite, Site
from fpdb_3_legacy.iPoker.dispatcher import get_parser_class_for_path as get_ipoker_parser_class_for_path
from fpdb_3_legacy.parser_debug_report import (
    ERROR,
    INFO,
    WARNING,
    Detection,
    Diagnostic,
    HandResult,
    LineMark,
    LogRecord,
    ParseDebugReport,
    SiteProbe,
    StepTrace,
    anonymize,
    bug_report,
    diagnostic_location,
    diff_reports,
    first_line,
    jsonable,
    line_of,
    render_text,
)
from fpdb_3_legacy.parser_registry import get_parser_class
from fpdb_3_legacy.parser_trace import (
    LogCapture,
    Recorder,
    captured_logs,
    error_message,
    regexes_of,
    trace_regexes,
    trace_steps,
)
from fpdb_3_legacy.RegressionFileComparator import compare_hand_sidecars, has_sidecars

# The report and its renderings are part of this module's interface.
__all__ = [
    "ERROR",
    "INFO",
    "WARNING",
    "Detection",
    "Diagnostic",
    "HandResult",
    "LineMark",
    "LogRecord",
    "ParseDebugReport",
    "SiteProbe",
    "StepTrace",
    "anonymize",
    "available_sites",
    "bug_report",
    "debug_parse_file",
    "debug_parse_text",
    "detect",
    "diagnostic_location",
    "diff_reports",
    "extract_hand",
    "render_text",
]

#: The detection of :class:`IdentifySite` only reads the start of a file.
DETECTION_WINDOW: Final = 5000
#: Lines of the input a converter's regexes are tried on to find the closest one.
_BODY_SCORE_LINES: Final = 200
#: At most this many "unread line" diagnostics per hand; the line view has them all.
_MAX_LINE_DIAGNOSTICS: Final = 20

_SUMMARY_MARKER: Final = re.compile(r"^\s*(\*+\s*summary\s*\*+|summary\b|-+\s*summary\s*-+)", re.IGNORECASE)
_NOISE_LINE: Final = re.compile(r"^[\W_]*$")
# "*** HOLE CARDS ***", "--- FLOP ---": street markers markStreets cuts on.
_MARKER_LINE: Final = re.compile(r"^\s*(\*{2,}|-{2,}|#{2,}).*(\*{2,}|-{2,}|#{2,})")
# Lines no hand history contains: a regex that matches one of them reads anything.
_CONTROL_LINES: Final = ("The quick brown fox jumps over the lazy dog", "1234567890", "x")
# A log record that says the converter changed a value rather than read it.
_REPAIR_RECORD: Final = re.compile(
    r"auto-balanc|auto-correct|clamp|repair|forc(ed|ing)\b|adjust(ed|ing)\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def available_sites(config: Any) -> list[str]:
    """The sites the importer has a converter for, by name."""
    return sorted(getattr(config, "hhcs", {}) or {})


def _site_enabled(config: Any, name: str) -> bool:
    site = (getattr(config, "supported_sites", None) or {}).get(name)
    return bool(getattr(site, "enabled", True)) if site is not None else True


def _body_score(converter: Any, lines: Sequence[str]) -> int:
    """How many lines of the input the converter's regexes recognise.

    A regex that also matches plain prose (``^(?P<CARDS>.+)$`` reads any line)
    says nothing about the format and is left out.
    """
    patterns = [
        pattern
        for name, pattern in regexes_of(converter)
        if "split" not in name.lower()
        and "identify" not in name.lower()
        and isinstance(pattern.pattern, str)
        and not any(pattern.search(line) for line in _CONTROL_LINES)
    ]
    score = 0
    for line in lines:
        if line.strip() and any(pattern.search(line) for pattern in patterns):
            score += 1
    return score


def _identify_hint(pattern: re.Pattern[str], whole_file: str) -> tuple[str, int | None]:
    """Why ``pattern`` did not identify the file, when it nearly did."""
    if not isinstance(pattern.pattern, str):
        return "", None
    later = pattern.search(whole_file, DETECTION_WINDOW) if len(whole_file) > DETECTION_WINDOW else None
    if later:
        return (
            f"matches on line {line_of(whole_file, later.start())}, beyond the first "
            f"{DETECTION_WINDOW} characters the detection reads",
            line_of(whole_file, later.start()),
        )
    head = whole_file[:DETECTION_WINDOW]
    ignoring_case = re.compile(pattern.pattern, pattern.flags | re.IGNORECASE).search(head)
    if ignoring_case:
        line = line_of(head, ignoring_case.start())
        return f"matches line {line} once case is ignored: '{ignoring_case.group(0).strip()}'", line
    spaced = re.sub(r"[ \t\xa0]+", " ", head)
    with contextlib.suppress(re.error):
        normalized = pattern.search(spaced)
        if normalized:
            line = line_of(spaced, normalized.start())
            return f"matches line {line} once spacing is normalized", line
    return "", None


def _probe(site: Site, name: str, converter: Any, whole_file: str, lines: Sequence[str], enabled: bool) -> SiteProbe:
    pattern = site.re_Identify
    probe = SiteProbe(
        converter=site.filter_name,
        site=name,
        pattern=pattern.pattern if pattern is not None else "",
        enabled=enabled,
    )
    if pattern is not None:
        match = pattern.search(whole_file[:DETECTION_WINDOW])
        if match:
            probe.identified = True
            probe.line = line_of(whole_file, match.start())
        else:
            probe.hint, probe.line = _identify_hint(pattern, whole_file)
    if converter is not None:
        probe.body_score = _body_score(converter, lines)
    return probe


def _probes(identifier: IdentifySite, config: Any, whole_file: str) -> list[SiteProbe]:
    lines = whole_file.splitlines()[:_BODY_SCORE_LINES]
    probes = []
    for site in identifier.sitelist.values():
        converter = None
        with contextlib.suppress(Exception):
            converter = get_parser_class(site.filter_name)
        probes.append(_probe(site, site.name, converter, whole_file, lines, _site_enabled(config, site.name)))
    if identifier.re_Identify_PT is not None:
        match = identifier.re_Identify_PT.search(whole_file[:DETECTION_WINDOW])
        pt_probe = SiteProbe("PokerTracker", "PokerTracker", identifier.re_Identify_PT.pattern)
        if match:
            pt_probe.identified, pt_probe.line = True, line_of(whole_file, match.start())
        with contextlib.suppress(Exception):
            pt_probe.body_score = _body_score(get_parser_class("PokerTracker"), lines)
        probes.append(pt_probe)
    return probes


def _forced_file(path: str, site_name: str, config: Any, kodec: str | None) -> FPDBFile | None:
    """The file as the importer would hold it if ``site_name`` had recognised it."""
    hhc = (getattr(config, "hhcs", None) or {}).get(site_name)
    if hhc is None:
        return None
    filter_name = hhc.converter.replace("ToFpdb", "")
    fobj = FPDBFile(path)
    fobj.site = Site(site_name, hhc.converter, filter_name, hhc.summaryImporter, get_parser_class(filter_name))
    fobj.ftype = "hh"
    fobj.kodec = kodec
    return fobj


def detect(path: str, config: Any, site: str | None = None) -> tuple[Detection, FPDBFile | None, str]:
    """Run the importer's detection on ``path`` and explain it.

    Returns the detection, the file object the importer would parse (None when
    nothing recognised it) and the decoded text.
    """
    identifier = IdentifySite(config)
    whole_file, kodec = identifier.read_file(path)
    detection = Detection(encoding=kodec)
    if not whole_file:
        detection.message = "The file is empty or could not be decoded"
        return detection, None, ""
    whole_file = whole_file.replace("\r\n", "\n")
    detection.probes = _probes(identifier, config, whole_file)
    identified = [probe for probe in detection.probes if probe.identified]
    if len(identified) > 1:
        detection.ambiguous = [f"{probe.site} ({probe.converter})" for probe in identified]

    if site:
        fobj = _forced_file(path, site, config, kodec)
        detection.forced = True
        if fobj is None:
            detection.message = (
                f"'{site}' is not a site with a converter. Known sites: {', '.join(available_sites(config))}"
            )
            return detection, None, whole_file
    else:
        found = identifier.idSite(path, whole_file, kodec)
        fobj = found if isinstance(found, FPDBFile) else None
        detection.unsupported_reason = identifier.unsupported_reason(path)

    if fobj is None or fobj.site is None:
        if detection.unsupported_reason:
            detection.message = detection.unsupported_reason
        else:
            ranked = sorted(detection.probes, key=lambda probe: (bool(probe.hint), probe.body_score), reverse=True)
            detection.closest = [
                f"{probe.site} ({probe.converter}): "
                + (probe.hint or f"{probe.body_score} line(s) read by its regexes")
                + f"; its header pattern is `{probe.pattern}`"
                for probe in ranked[:3]
                if probe.hint or probe.body_score
            ]
            detection.message = "No converter recognised this text"
        return detection, None, whole_file

    detection.site = fobj.site.name
    detection.converter = fobj.site.filter_name
    detection.file_type = fobj.ftype
    detection.hero = fobj.hero
    detection.archive = bool(fobj.archive)
    winner = next((probe for probe in detection.probes if probe.converter == detection.converter), None)
    if winner is not None:
        detection.marker, detection.marker_line = winner.pattern, winner.line
    if not _site_enabled(config, fobj.site.name):
        detection.message = (
            f"{fobj.site.name} is disabled in the site settings: its folders are not offered for import "
            "nor watched by auto-import, but a file imported by hand is still read"
        )
    return detection, fobj, whole_file


def _build_converter(fobj: FPDBFile, config: Any) -> Any:
    site = fobj.site
    if site is None:
        msg = f"Cannot parse unidentified file: {fobj.path}"
        raise ValueError(msg)
    parser_class = get_parser_class(site.filter_name)
    if site.filter_name == "iPoker":
        parser_class = get_ipoker_parser_class_for_path(fobj.path)
    return parser_class(
        config,
        in_path=fobj.path,
        index=0,
        autostart=False,
        starsArchive=fobj.archive,
        ftpArchive=fobj.archive,
        sitename=site.name,
    )


# ---------------------------------------------------------------------------
# Hands
# ---------------------------------------------------------------------------


def extract_hand(hand: Any) -> dict[str, Any]:
    """What the converter read into ``hand``, as plain data."""
    gametype = dict(getattr(hand, "gametype", None) or {})
    holes = parser_contract.hole_cards_by_player(hand)
    sitout = {str(player) for player in getattr(hand, "sitout", None) or ()}
    shown = {str(player) for player in getattr(hand, "shown", None) or ()}
    mucked = {str(player) for player in getattr(hand, "mucked", None) or ()}
    collectees = getattr(hand, "collectees", None) or {}
    hero = getattr(hand, "hero", None)
    players = []
    for player in getattr(hand, "players", None) or []:
        name = str(player[1]) if len(player) > 1 else ""
        players.append(
            {
                "seat": player[0] if player else None,
                "name": name,
                "stack": player[2] if len(player) > 2 else None,
                "position": player[3] if len(player) > 3 else None,
                "bounty": player[4] if len(player) > 4 else None,
                "hero": name == hero,
                "sitting_out": name in sitout,
                "hole_cards": list(dict.fromkeys(holes.get(name, []))),
                "shown": name in shown,
                "mucked": name in mucked,
                "collected": collectees.get(name),
            }
        )
    actions: dict[str, list[dict[str, Any]]] = {}
    for street, street_actions in (getattr(hand, "actions", None) or {}).items():
        if street_actions:
            actions[str(street)] = [_action_dict(action) for action in street_actions]
    pot = getattr(hand, "pot", None)
    start_time = getattr(hand, "startTime", None)
    return jsonable(
        {
            "header": {
                "site": getattr(hand, "sitename", None),
                "handid": getattr(hand, "handid", None),
                "table": getattr(hand, "tablename", None),
                "start_time": start_time,
                "timezone": str(start_time.tzinfo) if isinstance(start_time, datetime.datetime) else None,
                "max_seats": getattr(hand, "maxseats", None),
                "button": getattr(hand, "buttonpos", None),
                "hero": hero,
                "tournament": getattr(hand, "tourNo", None),
                "buyin": getattr(hand, "buyin", None),
                "fee": getattr(hand, "fee", None),
                "buyin_currency": getattr(hand, "buyinCurrency", None),
                "level": getattr(hand, "level", None),
                "knockout": getattr(hand, "isKO", None),
            },
            "gametype": gametype,
            "players": players,
            "actions": actions,
            "board": {str(street): cards for street, cards in (getattr(hand, "board", None) or {}).items() if cards},
            "pot": {
                "total": getattr(hand, "totalpot", None),
                "collected": getattr(hand, "totalcollected", None),
                "rake": getattr(hand, "rake", None),
                "uncalled_returns": dict(getattr(pot, "returned", None) or {}),
                "pots": [
                    {"amount": amount, "players": sorted(contenders)}
                    for amount, contenders in (getattr(pot, "pots", None) or [])
                ],
                "collectees": collectees,
            },
        }
    )


def _action_dict(action: Sequence[Any]) -> dict[str, Any]:
    player = action[0] if action else None
    kind = action[1] if len(action) > 1 else None
    entry: dict[str, Any] = {"player": player, "action": kind}
    if kind in ("raises", "completes") and len(action) > 3:
        entry.update({"by": action[2], "to": action[3], "all_in": bool(action[-1])})
    elif kind == "discards":
        entry.update({"count": action[2] if len(action) > 2 else None, "cards": action[3] if len(action) > 3 else None})
    elif len(action) > 2:
        entry["amount"] = action[2]
        if len(action) > 3:
            entry["all_in"] = bool(action[3])
    return entry


def _derived(hand: Any) -> dict[str, Any]:
    """What fpdb would store for ``hand`` (Hands and HandsPlayers rows), or why not."""
    try:
        hand.assembleHand()
    except Exception as exc:  # the debugger shows any failure of the derivation
        return {"error": f"{type(exc).__name__}: {exc}"}
    return jsonable(
        {"hands": dict(getattr(hand, "hands", {}) or {}), "handsplayers": getattr(hand, "handsplayers", {}) or {}}
    )


def _compare_sidecars(path: str, hand: Any) -> dict[str, Any]:
    try:
        hand.syncMaxSeats()
        hand.gametyperow = hand.gametypeRow()
        if not getattr(hand, "handsplayers", None):
            hand.assembleHand()
        report = compare_hand_sidecars(path, [hand])
    except Exception as exc:  # a sidecar the hand cannot be compared with is reported, not raised
        return {"compared": [], "passed": False, "error": f"{type(exc).__name__}: {exc}", "issues": []}
    return {
        "compared": list(report.compared),
        "passed": report.passed,
        "issues": [jsonable(asdict(issue)) for issue in report.issues],
    }


def _line_marks(recorder: Recorder, text: str, filetype: str) -> tuple[list[LineMark], str]:
    marks: list[LineMark] = []
    in_summary = False
    for number, line in enumerate(text.split("\n")):
        regexes = sorted(recorder.marks.get(number, ()))
        if _SUMMARY_MARKER.match(line):
            in_summary = True
        if regexes:
            status = "read"
        elif _NOISE_LINE.match(line):
            status = "blank"
        elif _MARKER_LINE.match(line):
            status = "marker"
        elif in_summary:
            status = "summary"
        else:
            status = "unread"
        marks.append(LineMark(number + 1, line, status, regexes))
    if filetype != "text":
        note = "XML histories are mostly read by an XML parser, not by regexes: unread lines are expected"
    else:
        note = "Lines no regex of the converter touched are marked unread"
    return marks, note


def _hand_status(exc: BaseException | None) -> str:
    if exc is None:
        return "ok"
    if isinstance(exc, FpdbHandPartial):
        return "partial"
    if isinstance(exc, FpdbHandSkipped):
        return "skipped"
    return "error"


def _not_called(steps: list[StepTrace], failed: bool, base: str | None) -> list[StepTrace]:
    called = {step.step for step in steps}
    missing = []
    for contract in parser_contract.CONTRACT:
        if contract.step in called:
            continue
        if failed:
            missing.append(StepTrace(contract.step, "not reached", contract.step))
        elif not contract.bases or base in contract.bases:
            missing.append(StepTrace(contract.step, "not called", contract.step))
    return missing


def _parse_hand(converter: Any, recorder: Recorder, text: str) -> tuple[Any, BaseException | None, str]:
    recorder.start_hand(text)
    try:
        return converter.processHand(text), None, ""
    except Exception as exc:  # every failure of a hand is what the debugger reports
        return None, exc, traceback.format_exc(limit=12)


def _hand_start_lines(whole_file: str, texts: Sequence[str]) -> list[int]:
    starts = []
    cursor = 0
    normalized = whole_file.replace("\xa0", " ")
    for text in texts:
        first = first_line(text).strip()
        position = normalized.find(first, cursor) if first else -1
        if position < 0:
            starts.append(line_of(normalized, cursor))
            continue
        starts.append(line_of(normalized, position))
        cursor = position + len(first)
    return starts


def _coverage_pass(fobj: FPDBFile, config: Any, texts: Sequence[str]) -> list[Recorder | None]:
    """Parse every hand again with traced regexes, for the line coverage only.

    The authoritative parse runs on an untouched converter: a traced regex is
    not a real ``re.Pattern``, and a converter that hands one to ``re.split()``
    would fail here for a reason of the debugger's own.
    """
    traced: list[Recorder | None] = []
    recorder = Recorder()
    try:
        converter = _build_converter(fobj, config)
        trace_steps(converter, recorder, regexes=True)
        trace_regexes(converter, recorder)
        with captured_logs():
            converter.allHandsAsList()
    except Exception:  # no coverage is a degraded report, not a failed one
        return [None] * len(texts)
    for text in texts:
        with captured_logs():
            _parse_hand(converter, recorder, text)
        # start_hand() gives the recorder fresh containers for the next hand,
        # so this hand's steps and marks can be kept as they are.
        snapshot = Recorder()
        snapshot.steps, snapshot.marks = recorder.steps, recorder.marks
        traced.append(snapshot)
    return traced


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def _failure_kind(error_type: str, message: str) -> tuple[str, str]:
    """The diagnostic kind and severity of a hand the converter raised on."""
    lowered = message.lower()
    if error_type == "FpdbHandPartial":
        return "Partial", ERROR
    if error_type == "FpdbHandSkipped":
        return "Skipped", INFO
    if error_type != "FpdbParseError":
        return "Crash", ERROR
    if "unsupported game" in lowered:
        return "UnsupportedGame", ERROR
    if "game type" in lowered:
        return "GameTypeUnknown", ERROR
    return "StepFailed", ERROR


def _exception_diagnostic(result: HandResult, failure: StepTrace | None) -> Diagnostic:
    """The diagnostic of a hand the converter refused or failed on."""
    message = result.error or result.error_type
    failed_step = failure.step if failure is not None else ""
    header_step = failed_step in ("", "determineGameType", "parseHeader", "readHandInfo")
    kind, severity = _failure_kind(result.error_type, message)
    if kind == "Crash":
        message = f"{result.error_type}: {message} -- the importer would stop on this file"
    return Diagnostic(
        severity,
        kind,
        message,
        result.index,
        result.start_line if header_step else None,
        first_line(result.text) if header_step else "",
        failed_step,
    )


def _hand_diagnostics(result: HandResult) -> list[Diagnostic]:
    diagnostics = [
        Diagnostic(
            violation["severity"],
            "ContractViolation",
            f"{violation['message']} (expected {violation['expected']}, found {violation['found']})"
            if violation["expected"] or violation["found"]
            else violation["message"],
            result.index,
            result.start_line if violation["step"] in ("determineGameType", "readHandInfo") else None,
            "",
            violation["step"],
        )
        for violation in result.violations
    ]
    for check in result.checks:
        if check["status"] != "pass":
            severity = ERROR if check["status"] == "fail" else WARNING
            detail = f": {'; '.join(check['details'][:3])}" if check["details"] else ""
            diagnostics.append(
                Diagnostic(severity, "CheckFailed", f"{check['name']}: {check['message']}{detail}", result.index)
            )
    diagnostics += [
        Diagnostic(WARNING, "Repaired", f"{record.logger}: {record.message}", result.index)
        for record in result.logs
        if _REPAIR_RECORD.search(record.message)
    ]
    if result.sidecars and not result.sidecars["passed"]:
        issues = result.sidecars["issues"]
        message = result.sidecars.get("error") or (
            f"{len(issues)} value(s) differ from the regression sidecars ({', '.join(result.sidecars['compared'])})"
        )
        diagnostics.append(Diagnostic(WARNING, "SidecarMismatch", message, result.index))
    return diagnostics


def _unread_line_diagnostics(results: Sequence[HandResult]) -> list[Diagnostic]:
    """One info diagnostic per line no regex read, at most :data:`_MAX_LINE_DIAGNOSTICS` in all.

    The line view of each hand shows every one of them; the list only points
    the way.
    """
    unread = [
        (result, mark)
        for result in results
        if result.ok and result.coverage.startswith("Lines")
        for mark in result.lines
        if mark.status == "unread"
    ]
    diagnostics = [
        Diagnostic(
            INFO,
            "UnreadLine",
            "No regex of the converter read this line",
            result.index,
            result.start_line + mark.number - 1,
            mark.text.strip(),
        )
        for result, mark in unread[:_MAX_LINE_DIAGNOSTICS]
    ]
    if len(unread) > _MAX_LINE_DIAGNOSTICS:
        diagnostics.append(
            Diagnostic(
                INFO,
                "UnreadLine",
                f"... and {len(unread) - _MAX_LINE_DIAGNOSTICS} more unread line(s): see the line view of each hand",
            )
        )
    return diagnostics


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _detection_diagnostics(detection: Detection, fobj: FPDBFile | None, whole_file: str) -> list[Diagnostic]:
    if fobj is None:
        hints = "; ".join(detection.closest)
        return [
            Diagnostic(
                ERROR,
                "UnsupportedGame" if detection.unsupported_reason else "NotRecognized",
                detection.message + (f". Closest: {hints}" if hints else ""),
                None,
                1,
                first_line(whole_file),
                "detection",
            )
        ]
    diagnostics = []
    if detection.message:
        diagnostics.append(Diagnostic(INFO, "SiteDisabled", detection.message, step="detection"))
    if detection.ambiguous:
        diagnostics.append(
            Diagnostic(
                WARNING,
                "Ambiguous",
                f"Several converters recognise this text: {', '.join(detection.ambiguous)}; "
                f"{detection.site} wins because it comes first",
                step="detection",
            )
        )
    if fobj.ftype == "summary":
        diagnostics.append(
            Diagnostic(
                INFO,
                "Summary",
                "This is a tournament summary, not a hand history: there are no hands to trace",
                step="detection",
            )
        )
    return diagnostics


def _split_hands(converter: Any, report: ParseDebugReport) -> list[str]:
    """The hand texts the converter cuts the file into, with what went wrong doing it."""
    try:
        sane = converter.sanityCheck()
        texts: list[str] = converter.allHandsAsList() if sane else []
    except Exception as exc:  # a file the converter cannot even split is a finding
        report.diagnostics.append(
            Diagnostic(ERROR, "SplitFailed", f"{type(exc).__name__}: {exc}", step="allHandsAsList")
        )
        return []
    if not sane:
        report.diagnostics.append(
            Diagnostic(ERROR, "SanityCheck", "The converter's sanity check failed", step="sanityCheck")
        )
    if texts and converter.isSummary(texts[0]) is not False:
        report.file_kind = "summary"
        report.diagnostics.append(
            Diagnostic(INFO, "Summary", "The converter reads this file as a tournament summary", step="isSummary")
        )
        return []
    if not texts and not report.diagnostics:
        report.diagnostics.append(
            Diagnostic(ERROR, "NoHands", "The converter found no hand in this text", step="allHandsAsList")
        )
    return texts


def _attach_coverage(result: HandResult, traced: Recorder | None, filetype: str) -> None:
    if traced is None:
        result.lines = [LineMark(number + 1, line, "untraced") for number, line in enumerate(result.text.split("\n"))]
        result.coverage = "Line coverage was not traced"
        return
    result.lines, result.coverage = _line_marks(traced, result.text, filetype)
    if not result.ok:
        # The parse stopped: a line no regex read was simply never reached.
        for mark in result.lines:
            if mark.status == "unread":
                mark.status = "not reached"
    matches: dict[str, dict[str, int]] = {}
    for step in traced.steps:
        by_regex = matches.setdefault(step.label, {})
        for regex, count in step.matches.items():
            by_regex[regex] = by_regex.get(regex, 0) + count
    for step in result.steps:
        step.matches = matches.get(step.label, {})


@dataclass
class _Context:
    """What every hand of one file is parsed with."""

    converter: Any
    recorder: Recorder
    path: str
    supported: Any
    derived: bool
    filetype: str


def _hand_result(context: _Context, index: int, text: str, start_line: int, capture: LogCapture) -> HandResult:
    capture.records.clear()
    hand, exc, trace_text = _parse_hand(context.converter, context.recorder, text)
    result = HandResult(
        index=index,
        status=_hand_status(exc),
        start_line=start_line,
        text=text,
        traceback=trace_text,
        steps=list(context.recorder.steps),
    )
    if exc is not None:
        result.error_type, result.error = type(exc).__name__, error_message(exc)
    base = None
    if hand is not None:
        result.handid = str(getattr(hand, "handid", "") or "")
        base = (getattr(hand, "gametype", None) or {}).get("base")
        result.violations = [violation.as_dict() for violation in parser_contract.check_hand(hand, context.supported)]
        result.checks = [check.as_dict() for check in parser_contract.hand_invariants(hand)]
        result.extracted = extract_hand(hand)
        if context.derived:
            result.extracted["derived"] = _derived(hand)
        if index == 0 and has_sidecars(context.path):
            result.sidecars = _compare_sidecars(context.path, hand)
    result.steps += _not_called(result.steps, exc is not None, base)
    for step in result.steps:
        if step.status == "running":
            step.status = "raised"
    result.logs = list(capture.records)
    return result


def debug_parse_file(
    path: str | Path,
    config: Any,
    site: str | None = None,
    *,
    trace_lines: bool = True,
    derived: bool = False,
    source: str | None = None,
) -> ParseDebugReport:
    """Detect, parse and check every hand of ``path``, the way the importer would.

    Args:
        path: the hand-history file.
        config: the loaded :class:`Configuration.Config`; it is only read.
        site: a site name to force instead of the detection.
        trace_lines: also parse a second time with traced regexes, for the line
            coverage (costs a second parse).
        derived: add what fpdb would store for each hand (Hands / HandsPlayers).
        source: how to name the input in the report (defaults to the path).
    """
    started = time.perf_counter()
    path = str(path)
    detection, fobj, whole_file = detect(path, config, site)
    report = ParseDebugReport(source=source or path, detection=detection)
    report.diagnostics += _detection_diagnostics(detection, fobj, whole_file)
    if fobj is None or fobj.ftype == "summary":
        report.file_kind = "summary" if fobj is not None else report.file_kind
        report.duration_ms = _elapsed(started)
        return report

    converter = _build_converter(fobj, config)
    parser_type = type(converter)
    detection.parser_class = f"{parser_type.__module__}.{parser_type.__qualname__}"
    recorder = Recorder()
    trace_steps(converter, recorder, regexes=False)
    supported = None
    with contextlib.suppress(Exception):
        supported = converter.readSupportedGames()
    context = _Context(converter, recorder, path, supported, derived, getattr(converter, "filetype", "text"))

    with captured_logs() as capture:
        texts = _split_hands(converter, report)
        coverage = _coverage_pass(fobj, config, texts) if trace_lines else [None] * len(texts)
        starts = _hand_start_lines(whole_file, texts)
        for index, text in enumerate(texts):
            result = _hand_result(context, index, text, starts[index], capture)
            _attach_coverage(result, coverage[index], context.filetype)
            if result.error_type:
                failure = next((step for step in reversed(result.steps) if step.status == "raised"), None)
                report.diagnostics.append(_exception_diagnostic(result, failure))
            report.diagnostics += _hand_diagnostics(result)
            report.hands.append(result)
        report.diagnostics += _unread_line_diagnostics(report.hands)

    report.duration_ms = _elapsed(started)
    return report


def debug_parse_text(
    text: str,
    config: Any,
    site: str | None = None,
    *,
    name: str = "pasted.txt",
    trace_lines: bool = True,
    derived: bool = False,
) -> ParseDebugReport:
    """:func:`debug_parse_file` on pasted text, through a temporary file the report does not name."""
    suffix = ".xml" if text.lstrip("﻿ \t\r\n").startswith("<") else Path(name).suffix or ".txt"
    with tempfile.TemporaryDirectory(prefix="fpdb-parser-debug-") as directory:
        path = Path(directory) / (Path(name).stem + suffix)
        path.write_text(text, encoding="utf-8")
        return debug_parse_file(path, config, site, trace_lines=trace_lines, derived=derived, source="pasted text")
