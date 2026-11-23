"""The Parser Debugger's report and its renderings (#903).

:mod:`parser_debug` fills a :class:`ParseDebugReport`; this module holds its
data classes and turns it into text for the terminal, Markdown for a bug report
(player names replaced), JSON, and a list of what changed between two reports.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, Final

ERROR: Final = "error"
WARNING: Final = "warning"
INFO: Final = "info"

# The names players are given in a bug report, after Hero.
_ANON_NAMES: Final = (
    "alice",
    "bob",
    "carol",
    "dave",
    "erin",
    "frank",
    "grace",
    "heidi",
    "ivan",
    "judy",
    "mallory",
    "niaj",
    "olivia",
    "peggy",
    "rupert",
    "sybil",
    "trent",
    "victor",
    "walter",
)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class SiteProbe:  # pylint: disable=too-many-instance-attributes  # a record of facts
    """What one converter makes of the input."""

    converter: str
    site: str
    pattern: str
    identified: bool = False
    line: int | None = None
    hint: str = ""
    body_score: int = 0
    enabled: bool = True


@dataclass
class Detection:  # pylint: disable=too-many-instance-attributes  # a record of facts
    """Which converter the importer would use, and why."""

    site: str | None = None
    converter: str | None = None
    parser_class: str | None = None
    file_type: str | None = None
    encoding: str | None = None
    hero: str | None = None
    archive: bool = False
    archive_head: bool = False
    archive_divider: bool = False
    forced: bool = False
    marker: str = ""
    marker_line: int | None = None
    unsupported_reason: str | None = None
    message: str = ""
    probes: list[SiteProbe] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    closest: list[str] = field(default_factory=list)


@dataclass
class StepTrace:  # pylint: disable=too-many-instance-attributes  # a record of facts
    """One call of a converter step on one hand (or a step that was never called)."""

    step: str
    status: str
    label: str = ""
    duration_ms: float = 0.0
    error_type: str = ""
    error: str = ""
    changes: dict[str, str] = field(default_factory=dict)
    result: str = ""
    matches: dict[str, int] = field(default_factory=dict)


@dataclass
class LineMark:
    """One line of a hand's text and what read it."""

    number: int
    text: str
    status: str
    regexes: list[str] = field(default_factory=list)
    spans: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LogRecord:
    level: str
    logger: str
    message: str


@dataclass
class Diagnostic:
    """Something the user should look at, with where it is."""

    severity: str
    kind: str
    message: str
    hand_index: int | None = None
    line: int | None = None
    line_text: str = ""
    step: str = ""


@dataclass
class HandResult:  # pylint: disable=too-many-instance-attributes  # a record of facts
    """Everything known about one hand of the input."""

    index: int
    status: str
    start_line: int
    text: str
    handid: str = ""
    error_type: str = ""
    error: str = ""
    traceback: str = ""
    steps: list[StepTrace] = field(default_factory=list)
    violations: list[dict[str, str]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    logs: list[LogRecord] = field(default_factory=list)
    lines: list[LineMark] = field(default_factory=list)
    coverage: str = ""
    extracted: dict[str, Any] = field(default_factory=dict)
    sidecars: dict[str, Any] | None = None
    fingerprint: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class ParseDebugReport:
    """The whole answer for one input."""

    source: str
    detection: Detection
    hands: list[HandResult] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    duration_ms: float = 0.0
    file_kind: str = "hh"
    snapshot: dict[str, Any] | None = None

    @property
    def verdict(self) -> str:
        """``ok`` when every hand parsed and nothing is an error, ``failed`` otherwise."""
        if not self.hands or any(not hand.ok for hand in self.hands):
            return "failed"
        if any(diagnostic.severity == ERROR for diagnostic in self.diagnostics):
            return "failed"
        return "ok"

    def counts(self) -> dict[str, int]:
        counts = {"ok": 0, "partial": 0, "skipped": 0, "error": 0}
        for hand in self.hands:
            counts[hand.status] = counts.get(hand.status, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["verdict"] = self.verdict
        data["counts"] = self.counts()
        return jsonable(data)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def jsonable(value: Any) -> Any:
    """``value`` with Decimals, dates, sets and tuples turned into JSON types."""
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((jsonable(item) for item in value), key=str)
    return _jsonable_scalar(value)


def _jsonable_scalar(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def first_line(text: str) -> str:
    return next((line for line in text.splitlines() if line.strip()), "")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_detection(report: ParseDebugReport) -> list[str]:
    detection = report.detection
    out = [
        f"Parser Debugger -- {report.source}",
        f"Verdict: {report.verdict.upper()}   hands: "
        + ", ".join(f"{count} {status}" for status, count in report.counts().items() if count)
        + f"   ({report.duration_ms:.0f} ms)",
        "",
        "Detection",
        f"  site: {detection.site or '-'}   converter: {detection.converter or '-'}"
        + ("   (forced)" if detection.forced else "")
        + f"   encoding: {detection.encoding or '-'}",
    ]
    if detection.marker:
        out.append(f"  recognised by {detection.marker!r} on line {detection.marker_line}")
    out.append(
        f"  archive flags: archive={detection.archive}, head={detection.archive_head}, divider={detection.archive_divider}"
    )
    if detection.hero:
        out.append(f"  hero: {detection.hero}")
    if detection.message:
        out.append(f"  {detection.message}")
    out += [f"  closest: {item}" for item in detection.closest]
    out += [f"  ambiguous: {item}" for item in detection.ambiguous]
    return out


def _render_sidecars(sidecars: Mapping[str, Any]) -> list[str]:
    out = [f"  Sidecars {', '.join(sidecars['compared'])}: {'pass' if sidecars['passed'] else 'FAIL'}"]
    if sidecars.get("error"):
        out.append(f"    {sidecars['error']}")
    for issue in sidecars["issues"][:30]:
        player = f" ({issue['player']})" if issue.get("player") else ""
        out.append(
            f"    {issue['sidecar']} {issue['field']}{player}: expected {issue['expected']!r}, got {issue['actual']!r}"
        )
    return out


def _render_hand(result: HandResult, *, lines: bool) -> list[str]:
    out = ["", f"Hand {result.index} ({result.handid or 'no id'}) -- {result.status}, line {result.start_line}"]
    if result.error:
        out.append(f"  {result.error_type}: {result.error}")
    out.append("  Steps")
    for step in result.steps:
        changes = ", ".join(f"{key} {value}" for key, value in step.changes.items())
        out.append(f"    {step.status:<12} {step.label or step.step:<26} {step.error or step.result or changes}"[:160])
    if result.violations:
        out.append("  Contract")
        out += [f"    {item['severity']:<8} {item['step']:<20} {item['message']}" for item in result.violations]
    if result.checks:
        out.append("  Checks")
        out += [f"    {check['status']:<5} {check['name']}: {check['message']}" for check in result.checks]
    if result.sidecars:
        out += _render_sidecars(result.sidecars)
    if result.logs:
        out.append("  Log")
        out += [f"    {record.level:<8} {record.logger}: {record.message}"[:200] for record in result.logs]
    if lines:
        out.append(f"  Lines ({result.coverage})")
        out += [
            f"    {result.start_line + mark.number - 1:>5} {mark.status:<8} {mark.text}"[:160]
            + (f"   <- {', '.join(mark.regexes)}" if mark.regexes else "")
            for mark in result.lines
        ]
        out += [
            f"      span {span['regex']} [{span['start']}:{span['end']}] {span['text']!r}"
            for mark in result.lines
            for span in mark.spans
        ]
    return out


def diagnostic_location(diagnostic: Diagnostic) -> str:
    """Where a diagnostic is: hand, line and step, as far as they are known."""
    where = []
    if diagnostic.hand_index is not None:
        where.append(f"hand {diagnostic.hand_index}")
    if diagnostic.line is not None:
        where.append(f"line {diagnostic.line}")
    if diagnostic.step:
        where.append(diagnostic.step)
    return ", ".join(where)


def render_text(report: ParseDebugReport, *, hand: int | None = None, lines: bool = False) -> str:
    """A plain-text report, for the terminal."""
    out = _render_detection(report)
    for result in report.hands:
        if hand is None or result.index == hand:
            out += _render_hand(result, lines=lines)
    if report.snapshot:
        status = "PASS" if report.snapshot.get("passed") else "FAIL"
        out += ["", f"Live parser snapshot {status}: {report.snapshot.get('key', '')}"]
        if report.snapshot.get("expected_sha256"):
            out.append(
                f"  expected {report.snapshot.get('expected_hand_count')} hands, {report.snapshot['expected_sha256']}"
            )
            out.append(
                f"  actual   {report.snapshot.get('actual_hand_count')} hands, {report.snapshot.get('actual_sha256')}"
            )
        elif report.snapshot.get("error"):
            out.append(f"  {report.snapshot['error']}")
    if report.diagnostics:
        out += ["", "Diagnostics"]
        for diagnostic in report.diagnostics:
            out.append(
                f"  {diagnostic.severity:<8} {diagnostic.kind:<18} [{diagnostic_location(diagnostic)}] {diagnostic.message}"
            )
            if diagnostic.line_text:
                out.append(f"  {'':<27} > {diagnostic.line_text}")
    return "\n".join(out)


def anonymize(text: str, names: Sequence[str], hero: str | None) -> str:
    """``text`` with ``hero`` renamed Hero and the other players alice, bob..."""
    mapping: dict[str, str] = {}
    others = iter(_ANON_NAMES)
    real_names = set(names)
    for name in names:
        if not name or name in mapping:
            continue
        if name == hero:
            mapping[name] = "Hero"
            continue
        fake = next(
            (candidate for candidate in others if candidate not in real_names and candidate not in mapping.values()),
            None,
        )
        fallback = 0
        while fake is None:
            fallback += 1
            candidate = f"player{fallback}"
            if candidate not in real_names and candidate not in mapping.values():
                fake = candidate
        mapping[name] = fake
    # Longest first, so a name that contains another is replaced whole.
    for name in sorted(mapping, key=len, reverse=True):
        text = re.sub(rf"(?<![\w-]){re.escape(name)}(?![\w-])", mapping[name], text)
    return text


def _history_player_names(text: str) -> list[str]:
    """Find seated players and common table-event names in the source text."""
    names: list[str] = []
    patterns = (
        re.compile(r"^Seat\s+\d+:\s*(.+?)\s+\([^\r\n]*\)"),
        re.compile(r"^(.+?):\s*(?:is\s+sitting\s+out|sits?\s+out)\b", re.IGNORECASE),
        re.compile(r"^(.+?)\s+(?:joins?|leaves?)\s+(?:the\s+)?table\b", re.IGNORECASE),
    )
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                name = match.group(1).strip()
                if name and name not in names:
                    names.append(name)
                break
    return names


def bug_report(report: ParseDebugReport, hand: int | None = None) -> str:
    """Markdown ready to paste into a GitHub issue, with player names replaced."""
    selected = [result for result in report.hands if hand is None or result.index == hand] or report.hands
    names: list[str] = []
    names_outside_parsed_players: set[str] = set()
    hero = report.detection.hero
    for result in report.hands:
        parsed_names = [str(player["name"]) for player in result.extracted.get("players", [])]
        history_names = _history_player_names(result.text)
        names += parsed_names
        names += history_names
        if result in selected:
            names_outside_parsed_players.update(set(history_names) - set(parsed_names))
        hero = result.extracted.get("header", {}).get("hero") or hero
    texts = "\n\n".join(result.text for result in selected) if selected else ""
    player_names_unavailable = [
        result.index for result in selected if not result.extracted.get("players")
    ]
    anonymized = bool(names) and not player_names_unavailable
    hand_text = texts
    detection = report.detection
    lines = [
        "### Parser Debugger report",
        "",
        f"- Verdict: **{report.verdict}**",
        f"- Site / converter: {detection.site or 'not recognised'} / {detection.converter or '-'}"
        + (" (forced)" if detection.forced else ""),
        f"- Hands: {', '.join(f'{count} {status}' for status, count in report.counts().items() if count) or 'none'}",
    ]
    if detection.closest:
        lines += ["- Closest converters:"] + [f"  - {item}" for item in detection.closest]
    problems = [diagnostic for diagnostic in report.diagnostics if diagnostic.severity != INFO]
    if problems:
        lines += ["", "#### Diagnostics", ""]
        for diagnostic in problems[:40]:
            where = f"hand {diagnostic.hand_index}" if diagnostic.hand_index is not None else "file"
            where += f", line {diagnostic.line}" if diagnostic.line is not None else ""
            step = f" `{diagnostic.step}`" if diagnostic.step else ""
            lines.append(f"- **{diagnostic.severity}** {diagnostic.kind}{step} ({where}): {diagnostic.message}")
    failed_steps = [
        f"- hand {result.index}: `{step.label or step.step}` raised {step.error_type}: {step.error}"
        for result in selected
        for step in result.steps
        if step.status == "raised"
    ]
    if failed_steps:
        lines += ["", "#### Failed steps", "", *failed_steps]
    lines += ["", "#### Hand history", ""]
    if not anonymized or names_outside_parsed_players:
        if player_names_unavailable:
            indices = ", ".join(str(index) for index in player_names_unavailable)
            lines.append(
                f"> **Manual privacy review required**: player names could not be extracted for hand(s) {indices}. "
                "Review the complete report and replace any real names before posting."
            )
        elif names_outside_parsed_players:
            lines.append(
                "> **Manual privacy review recommended**: names found in seat or table-event lines outside the parsed "
                "player list were redacted too. Review unusual room-specific events before posting."
            )
        else:
            lines.append("> **Not anonymized**: no player name could be read. Replace the names before posting.")
        lines.append("")
    lines += ["```text", hand_text or anonymize(first_line(texts), [], None), "```"]
    rendered = "\n".join(lines)
    # Redact every name we did extract even when another hand in the report
    # failed before its players could be identified.  The warning above asks
    # the reporter to review the names that could not be found automatically.
    return anonymize(rendered, names, hero) if names else rendered


def diff_reports(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[str]:
    """What changed between two saved reports of the same input, hand by hand."""
    changes: list[str] = []
    if previous.get("verdict") != current.get("verdict"):
        changes.append(f"verdict: {previous.get('verdict')} -> {current.get('verdict')}")
    old_hands = {hand["index"]: hand for hand in previous.get("hands", [])}
    new_hands = {hand["index"]: hand for hand in current.get("hands", [])}
    for index in sorted(set(old_hands) | set(new_hands)):
        old, new = old_hands.get(index), new_hands.get(index)
        if old is None or new is None:
            changes.append(f"hand {index}: {'added' if old is None else 'removed'}")
            continue
        if old.get("status") != new.get("status"):
            changes.append(f"hand {index}: status {old.get('status')} -> {new.get('status')}")
        changes += [
            f"hand {index}: {item}" for item in _diff_values(old.get("extracted", {}), new.get("extracted", {}), "")
        ]
        changes += [
            f"hand {index}: {item}"
            for item in _diff_values(old.get("fingerprint", {}), new.get("fingerprint", {}), "fingerprint")
        ]
        old_violations = {json.dumps(item, sort_keys=True) for item in old.get("violations", [])}
        new_violations = {json.dumps(item, sort_keys=True) for item in new.get("violations", [])}
        changes += [
            f"hand {index}: contract fixed: {json.loads(item)['message']}"
            for item in sorted(old_violations - new_violations)
        ]
        changes += [
            f"hand {index}: contract broken: {json.loads(item)['message']}"
            for item in sorted(new_violations - old_violations)
        ]
    return changes


def _diff_values(old: Any, new: Any, prefix: str) -> list[str]:
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        changes = []
        for key in sorted(set(old) | set(new), key=str):
            changes += _diff_values(old.get(key), new.get(key), f"{prefix}.{key}" if prefix else str(key))
        return changes
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        changes = []
        for position, (old_item, new_item) in enumerate(zip(old, new, strict=True)):
            changes += _diff_values(old_item, new_item, f"{prefix}[{position}]")
        return changes
    if old != new:
        return [f"{prefix}: {old!r} -> {new!r}"]
    return []
