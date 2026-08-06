"""Compare THP regression sidecar files with imported hand statistics."""

from __future__ import annotations

import ast
import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytz

# The only names a sidecar may name: these files are data, not code.
_SIDECAR_FACTORIES = {
    "Decimal": Decimal,
    "datetime.datetime": datetime.datetime,
    "datetime.date": datetime.date,
    "datetime.time": datetime.time,
    "datetime.timedelta": datetime.timedelta,
}
_SIDECAR_CONSTANTS = {
    "pytz.utc": pytz.utc,
    "datetime.timezone.utc": datetime.timezone.utc,
}

IGNORED_HAND_KEYS = {
    "fileId",
    "gameId",
    "gameSessionId",
    "gametypeId",
    "gsc",
    "id",
    "runItTwice",
    "sc",
    "sessionId",
    "tourneyId",
}
IGNORED_HANDSPLAYERS_KEYS = {"tourneyTypeId", "tourneysPlayersIds"}

GAMETYPE_FIELDS = {
    0: "siteId",
    1: "currency",
    2: "type",
    3: "base",
    4: "game",
    5: "limit",
    6: "hilo",
    7: "mix",
    8: "smallBlind",
    9: "bigBlind",
    10: "smallBet",
    11: "bigBet",
    12: "maxSeats",
    13: "ante",
    14: "cap",
    15: "zoom",
}


@dataclass(frozen=True)
class ComparisonIssue:
    """One mismatch between generated import data and a regression sidecar."""

    sidecar: str
    field: str
    expected: Any
    actual: Any
    player: str | None = None


@dataclass
class ComparisonReport:
    """Aggregate result for one imported hand-history file."""

    filename: Path
    compared: list[str] = field(default_factory=list)
    issues: list[ComparisonIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


def _sidecar_call(node: ast.Call) -> Any:
    """Evaluate one of the constructor calls a sidecar is allowed to contain.

    The THP sidecars are Python reprs, so they hold ``Decimal('1.50')`` and
    ``datetime.datetime(2010, 12, 7, 9, 19, tzinfo=pytz.utc)`` alongside the
    plain literals. ``ast.literal_eval`` rejects any call, which made every
    sidecar holding a timestamp unreadable. Only these constructors are
    accepted - the file is data, never code to execute.
    """
    name = ast.unparse(node.func)
    factory = _SIDECAR_FACTORIES.get(name)
    if factory is None:
        msg = f"unsupported call in sidecar: {name}"
        raise ValueError(msg)
    args = [_sidecar_value(arg) for arg in node.args]
    kwargs = {kw.arg: _sidecar_value(kw.value) for kw in node.keywords if kw.arg}
    return factory(*args, **kwargs)


def _sidecar_value(node: ast.AST) -> Any:
    if isinstance(node, ast.Call):
        return _sidecar_call(node)
    if isinstance(node, ast.Attribute):  # pytz.utc and friends
        name = ast.unparse(node)
        if name in _SIDECAR_CONSTANTS:
            return _SIDECAR_CONSTANTS[name]
        msg = f"unsupported name in sidecar: {name}"
        raise ValueError(msg)
    if isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
        if isinstance(node, ast.Dict):
            return {_sidecar_value(k): _sidecar_value(v) for k, v in zip(node.keys, node.values) if k is not None}
        values = [_sidecar_value(elt) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(values)
        if isinstance(node, ast.Set):
            return set(values)
        return values
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _sidecar_value(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    return ast.literal_eval(node)


def _load_sidecar(filename: Path, suffix: str) -> Any:
    text = filename.with_name(filename.name + suffix).read_text(encoding="utf-8")
    return _sidecar_value(ast.parse(text, mode="eval").body)


def _processed_hands(importer: Any, path: Path) -> list[Any]:
    """Hands the importer parsed for ``path`` (empty when nothing was cached).

    Asks for that file's own converter first: over a directory the importer only
    keeps the last one, which would compare every file against the final one's
    hands.
    """
    hhc = importer.getCachedHHC(str(path)) or importer.getCachedHHC()
    return hhc.getProcessedHands() if hhc is not None else []


def compare_importer_sidecars(filename: str | Path, importer: Any) -> ComparisonReport:
    """Compare ``.hands``, ``.hp`` and ``.gt`` sidecars for an importer result."""

    path = Path(filename)
    report = ComparisonReport(filename=path)
    hands = _processed_hands(importer, path)

    if not hands:
        report.issues.append(ComparisonIssue("import", "processedHands", "at least one hand", []))
        return report

    # A THP sidecar holds the expected data for the *first* hand of the file, so
    # checking every hand against it reported the other hands as thousands of
    # mismatches.
    for hand in hands[:1]:
        if path.with_name(path.name + ".hands").is_file():
            report.compared.append(".hands")
            _compare_hands(path, hand, report)
        if path.with_name(path.name + ".hp").is_file():
            report.compared.append(".hp")
            _compare_handsplayers(path, hand, report)
        if path.with_name(path.name + ".gt").is_file():
            report.compared.append(".gt")
            _compare_gametype(path, hand, report)

    return report


def _compare_hands(path: Path, hand: Any, report: ComparisonReport) -> None:
    expected = _load_sidecar(path, ".hands")
    actual = dict(hand.stats.getHands())
    actual.pop("boards", None)

    for key, actual_value in actual.items():
        if key in IGNORED_HAND_KEYS:
            continue
        expected_value = expected.get(key)
        if actual_value != expected_value:
            report.issues.append(ComparisonIssue(".hands", key, expected_value, actual_value))

    for key in set(expected) - set(actual):
        if key not in IGNORED_HAND_KEYS:
            report.issues.append(ComparisonIssue(".hands", key, expected[key], None))


def _compare_handsplayers(path: Path, hand: Any, report: ComparisonReport) -> None:
    expected = _load_sidecar(path, ".hp")
    actual = hand.stats.getHandsPlayers()

    for player, stats in actual.items():
        expected_stats = expected.get(player)
        if expected_stats is None:
            report.issues.append(ComparisonIssue(".hp", "player", None, player, player=player))
            continue

        for key, actual_value in stats.items():
            # A stat the golden file does not mention is not a mismatch: these
            # sidecars predate most of the columns fpdb derives today, so
            # comparing them all reported ~600 "expected None" issues per hand
            # and buried the handful of real differences.
            if key in IGNORED_HANDSPLAYERS_KEYS or key not in expected_stats:
                continue
            expected_value = expected_stats.get(key)
            if actual_value != expected_value:
                report.issues.append(ComparisonIssue(".hp", key, expected_value, actual_value, player=player))


def _compare_gametype(path: Path, hand: Any, report: ComparisonReport) -> None:
    expected = _load_sidecar(path, ".gt")
    actual = hand.gametyperow

    for idx, actual_value in enumerate(actual):
        expected_value = expected[idx] if idx < len(expected) else None
        if actual_value != expected_value:
            field = GAMETYPE_FIELDS.get(idx, f"field_{idx}")
            report.issues.append(ComparisonIssue(".gt", field, expected_value, actual_value))
