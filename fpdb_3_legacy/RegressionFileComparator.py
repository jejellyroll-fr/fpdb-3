"""Compare THP regression sidecar files with imported hand statistics."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


def _load_sidecar(filename: Path, suffix: str) -> Any:
    return ast.literal_eval(filename.with_name(filename.name + suffix).read_text(encoding="utf-8"))


def _processed_hands(importer: Any) -> list[Any]:
    hhc = importer.getCachedHHC()
    return hhc.getProcessedHands()


def compare_importer_sidecars(filename: str | Path, importer: Any) -> ComparisonReport:
    """Compare ``.hands``, ``.hp`` and ``.gt`` sidecars for an importer result."""

    path = Path(filename)
    report = ComparisonReport(filename=path)
    hands = _processed_hands(importer)

    if not hands:
        report.issues.append(ComparisonIssue("import", "processedHands", "at least one hand", []))
        return report

    for hand in hands:
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
            if key in IGNORED_HANDSPLAYERS_KEYS:
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
