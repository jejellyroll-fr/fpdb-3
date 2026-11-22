"""Tracing a converter for the Parser Debugger (#903).

The converter instances the debugger builds get their pipeline steps wrapped
(:func:`trace_steps`: what each call added to the hand, how long it took, what
it raised) and, for the line coverage, their compiled ``re_*`` patterns swapped
for :class:`TracedPattern` (:func:`trace_regexes`), which reports every match
to a :class:`Recorder`. Only instance attributes are replaced: the classes, and
so the importer, are untouched.
"""

from __future__ import annotations

import bisect
import contextlib
import functools
import logging
import re
import time
from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from typing import Any, Final

from fpdb_3_legacy import Hand, parser_contract
from fpdb_3_legacy.parser_debug_report import LogRecord, StepTrace, first_line


def error_message(exc: BaseException) -> str:
    """The message of ``exc``; FpdbParseError's own str() quotes it with repr()."""
    value = getattr(exc, "value", None)
    if isinstance(value, str) and value:
        hid = getattr(exc, "hid", "")
        return f"HID:{hid}, {value}" if hid else value
    return str(exc)


# Steps of the converter that are traced on top of the contract's.
_EXTRA_STEPS: Final = ("parseHeader", "readOther", "guessMaxSeats")


def regexes_of(converter: Any) -> list[tuple[str, re.Pattern[str]]]:
    """The compiled ``re_*`` patterns of a converter class or instance."""
    found = []
    for name in dir(converter):
        if not name.lower().startswith("re_"):
            continue
        with contextlib.suppress(Exception):
            value = getattr(converter, name)
            if isinstance(value, re.Pattern):
                found.append((name, value))
    return found


# ---------------------------------------------------------------------------
# Tracing the converter
# ---------------------------------------------------------------------------


def _hand_state(hand: Any) -> dict[str, str]:
    """A flat picture of what a hand holds, to tell what a step added."""
    state: dict[str, str] = {}
    for name in ("handid", "tablename", "startTime", "buttonpos", "maxseats", "tourNo", "level"):
        value = getattr(hand, name, None)
        if value not in (None, "", 0):
            state[name] = str(value)
    state["players"] = str(len(getattr(hand, "players", None) or []))
    state.update(_street_state(hand))
    hole = parser_contract.hole_cards_by_player(hand)
    if hole:
        state["holecards"] = str(sum(len(cards) for cards in hole.values()))
    for name in ("collectees", "shown", "mucked", "sitout"):
        value = getattr(hand, name, None)
        if value:
            state[name] = str(len(value))
    for name in ("totalpot", "rake"):
        value = getattr(hand, name, None)
        if value is not None:
            state[name] = str(value)
    return state


def _street_state(hand: Any) -> dict[str, str]:
    state = {
        f"actions.{street}": str(len(actions))
        for street, actions in (getattr(hand, "actions", None) or {}).items()
        if actions
    }
    state.update(
        {
            f"board.{street}": " ".join(str(card) for card in cards)
            for street, cards in (getattr(hand, "board", None) or {}).items()
            if cards
        }
    )
    return state


def _changes(before: Mapping[str, str], after: Mapping[str, str]) -> dict[str, str]:
    changed: dict[str, str] = {}
    for key, value in after.items():
        old = before.get(key)
        if old == value:
            continue
        if old is not None and old.isdigit() and value.isdigit():
            changed[key] = f"+{int(value) - int(old)}"
        else:
            changed[key] = value
    return changed


def _summarise_result(result: Any) -> str:
    if isinstance(result, Mapping):
        keys = ("type", "base", "category", "limitType", "currency", "sb", "bb", "ante")
        return ", ".join(f"{key}={result[key]}" for key in keys if key in result)
    if result is None or isinstance(result, (str, int, Decimal)):
        return "" if result is None else str(result)
    return type(result).__name__


class Recorder:  # pylint: disable=too-many-instance-attributes  # the state of one traced hand
    """Collects the step calls and regex matches of the hand being parsed."""

    def __init__(self) -> None:
        self.steps: list[StepTrace] = []
        self.current_step = ""
        self.hand_text = ""
        self.line_starts: list[int] = [0]
        self.marks: dict[int, set[str]] = {}
        self.spans: list[dict[str, Any]] = []
        self._located: dict[tuple[str, int], int] = {}
        self._streets: dict[int, tuple[str, int]] = {}
        self.street_starts: dict[str, int] = {}
        self.current_street = ""

    def start_hand(self, text: str) -> None:
        self.steps = []
        self.current_step = ""
        self.hand_text = text
        self.line_starts = [0] + [index + 1 for index, char in enumerate(text) if char == "\n"]
        self.marks = {}
        self.spans = []
        self._located = {}
        self._streets = {}
        self.street_starts = {}
        self.current_street = ""

    def locate_streets(self, hand: Any) -> None:
        """Where each street text cut by ``markStreets`` sits in the hand text.

        A street's text can repeat an earlier one ("Big Blind : Checks" on the
        flop and on the turn), so searching for it would find the earlier
        street. The streets are located once, in order, and recognised later by
        identity: the converter hands these very strings to its regexes.
        """
        streets = getattr(hand, "streets", None)
        if not isinstance(streets, Mapping):
            return
        order = list(getattr(hand, "allStreets", None) or []) or list(streets)
        cursor = 0
        for street in order:
            text = streets.get(street)
            if not isinstance(text, str) or not text:
                continue
            position = self.hand_text.find(text, cursor)
            if position >= 0:
                self._streets[id(text)] = (text, position)
            else:
                # The converter rewrote the street (Bovada drops the cards of a
                # showdown line): its first line still says where it starts.
                head = first_line(text)
                position = self.hand_text.find(head, cursor) if head else -1
                if position < 0:
                    continue
            self.street_starts[street] = position
            # Some converters cut overlapping streets (a turn that runs on to
            # the end of the hand): the next street may start inside this one.
            cursor = position + 1

    def match(self, regex: str, string: Any, match: re.Match[str] | None) -> None:
        if match is None or not isinstance(string, str) or not self.hand_text:
            return
        if self.steps and self.current_step and self.steps[-1].status == "running":
            matches = self.steps[-1].matches
            matches[regex] = matches.get(regex, 0) + 1
        span = self._span_in_hand(string, match)
        if span is None:
            return
        start, end = span
        self.spans.append(
            {
                "regex": regex,
                "start": start,
                "end": end,
                "line": bisect.bisect_right(self.line_starts, start),
                "text": self.hand_text[start:end],
                "step": self.current_step,
            }
        )
        first = bisect.bisect_right(self.line_starts, start) - 1
        last = bisect.bisect_right(self.line_starts, end - 1) - 1
        for line in range(first, last + 1):
            self.marks.setdefault(line, set()).add(regex)

    def _base_of(self, string: str) -> int:
        """Where ``string`` starts in the hand text, -1 when it is not part of it."""
        if string is self.hand_text or string == self.hand_text:
            return 0
        street = self._streets.get(id(string))
        if street is not None and street[0] is string:
            return street[1]
        # A converter may hand its regex a copy of the street's text: look for
        # it from the street being read, not from the top of the hand.
        origin = self.street_starts.get(self.current_street, 0)
        key = (string, origin)
        if key not in self._located:
            found = self.hand_text.find(string, origin) if len(string) <= len(self.hand_text) else -1
            self._located[key] = found if found >= 0 else self.hand_text.find(string)
        return self._located[key]

    def _span_in_hand(self, string: str, match: re.Match[str]) -> tuple[int, int] | None:
        start, end = match.span()
        if end <= start:
            return None
        base = self._base_of(string)
        if base >= 0:
            return start + base, end + base
        # The text was rewritten: find what matched instead.
        found = self.hand_text.find(match.group(0), self.street_starts.get(self.current_street, 0))
        if found < 0:
            found = self.hand_text.find(match.group(0))
        return (found, found + (end - start)) if found >= 0 else None


class TracedPattern:
    """A compiled regex that reports its matches; everything else is the regex's."""

    __slots__ = ("_name", "_pattern", "_recorder")

    def __init__(self, pattern: re.Pattern[str], name: str, recorder: Recorder) -> None:
        self._pattern = pattern
        self._name = name
        self._recorder = recorder

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._pattern, attr)

    def search(self, string: Any, *args: Any, **kwargs: Any) -> re.Match[str] | None:
        found = self._pattern.search(string, *args, **kwargs)
        self._recorder.match(self._name, string, found)
        return found

    def match(self, string: Any, *args: Any, **kwargs: Any) -> re.Match[str] | None:
        found = self._pattern.match(string, *args, **kwargs)
        self._recorder.match(self._name, string, found)
        return found

    def fullmatch(self, string: Any, *args: Any, **kwargs: Any) -> re.Match[str] | None:
        found = self._pattern.fullmatch(string, *args, **kwargs)
        self._recorder.match(self._name, string, found)
        return found

    def finditer(self, string: Any, *args: Any, **kwargs: Any) -> Iterator[re.Match[str]]:
        for found in self._pattern.finditer(string, *args, **kwargs):
            self._recorder.match(self._name, string, found)
            yield found

    def findall(self, string: Any, *args: Any, **kwargs: Any) -> list[Any]:
        for found in self._pattern.finditer(string, *args, **kwargs):
            self._recorder.match(self._name, string, found)
        return self._pattern.findall(string, *args, **kwargs)


def trace_regexes(converter: Any, recorder: Recorder) -> None:
    """Swap the converter's compiled ``re_*`` patterns for traced ones (instance only)."""
    for name, pattern in regexes_of(converter):
        # The hand splitter is handed to re.split(), which only takes real patterns.
        if "split" in name.lower() or not isinstance(pattern.pattern, str):
            continue
        with contextlib.suppress(AttributeError, TypeError):
            setattr(converter, name, TracedPattern(pattern, name, recorder))


def trace_steps(converter: Any, recorder: Recorder, *, regexes: bool) -> None:
    """Wrap the pipeline steps of ``converter`` (instance attributes only)."""
    for name in (*parser_contract.STEP_NAMES, *_EXTRA_STEPS):
        original = getattr(converter, name, None)
        if not callable(original):
            continue
        setattr(converter, name, _traced_step(converter, name, original, recorder, regexes=regexes))


def _traced_step(
    converter: Any,
    name: str,
    original: Callable[..., Any],
    recorder: Recorder,
    *,
    regexes: bool,
) -> Callable[..., Any]:
    @functools.wraps(original)
    def traced(*args: Any, **kwargs: Any) -> Any:
        hand = args[0] if args and isinstance(args[0], Hand.Hand) else None
        # readAction and readCommunityCards run once per street: name it.
        label = f"{name}({args[1]})" if len(args) > 1 and isinstance(args[1], str) else name
        before = _hand_state(hand) if hand is not None else {}
        trace = StepTrace(step=name, status="running", label=label)
        recorder.steps.append(trace)
        previous, recorder.current_step = recorder.current_step, name
        street_before = recorder.current_street
        if len(args) > 1 and isinstance(args[1], str):
            recorder.current_street = args[1]
        started = time.perf_counter()
        try:
            result = original(*args, **kwargs)
        except BaseException as exc:
            trace.status = "raised"
            trace.error_type = type(exc).__name__
            trace.error = error_message(exc)
            raise
        else:
            trace.status = "ok"
            trace.result = _summarise_result(result)
            return result
        finally:
            trace.duration_ms = round((time.perf_counter() - started) * 1000, 3)
            if hand is not None:
                trace.changes = _changes(before, _hand_state(hand))
                if name == "markStreets":
                    recorder.locate_streets(hand)
            recorder.current_step = previous
            recorder.current_street = street_before
            if regexes:
                # compilePlayerRegexs() and friends assign fresh patterns.
                trace_regexes(converter, recorder)

    return traced


class LogCapture(logging.Handler):
    """Collects the records emitted while a hand is parsed."""

    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):
            message = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                message += f" ({type(record.exc_info[1]).__name__}: {record.exc_info[1]})"
            self.records.append(LogRecord(record.levelname, record.name, message))


@contextlib.contextmanager
def captured_logs() -> Iterator[LogCapture]:
    capture = LogCapture()
    root = logging.getLogger()
    detached: list[logging.Logger] = []
    root.addHandler(capture)
    # fpdb's logging configuration can mark a logger non-propagating and give
    # it its own console/file handlers. Capture those records too, temporarily,
    # without changing levels or suppressing the app's existing handlers.
    for name, candidate in logging.Logger.manager.loggerDict.items():
        if not isinstance(candidate, logging.Logger) or candidate.propagate:
            continue
        if (
            name == "hand_history_converter"
            or name.startswith("hand_history_converter.")
            or name.startswith("fpdb_3_legacy.")
        ):
            candidate.addHandler(capture)
            detached.append(candidate)
    try:
        yield capture
    finally:
        root.removeHandler(capture)
        for logger in detached:
            logger.removeHandler(capture)
