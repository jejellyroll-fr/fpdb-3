"""File-by-file golden regression harness for actively supported poker rooms."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy.BetOnlineToFpdb import BetOnline
from fpdb_3_legacy.BovadaToFpdb import Bovada
from fpdb_3_legacy.CakeToFpdb import Cake
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.EntractionToFpdb import Entraction
from fpdb_3_legacy.GGPokerToFpdb import GGPoker
from fpdb_3_legacy.iPoker.base import iPoker
from fpdb_3_legacy.KingsClubToFpdb import KingsClub
from fpdb_3_legacy.PacificPokerToFpdb import PacificPoker
from fpdb_3_legacy.PartyPokerToFpdb import PartyPoker
from fpdb_3_legacy.PokerStarsToFpdb import PokerStars
from fpdb_3_legacy.SealsWithClubsToFpdb import SealsWithClubs
from fpdb_3_legacy.UnibetToFpdb import Unibet
from fpdb_3_legacy.WinamaxToFpdb import Winamax
from fpdb_3_legacy.WinningToFpdb import Winning
from tests.helpers.parser_regression import file_snapshot, snapshot_digest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "hands"
REGRESSION_FILES = ROOT / "regression-test-files" / "cash"
MANIFEST_PATH = FIXTURES / "live_parser_snapshots.json"

ROOMS = {
    "bovada": (Bovada, sorted((FIXTURES / "bovada").rglob("*.txt"))),
    "cake": (Cake, sorted((FIXTURES / "cake").rglob("*.txt"))),
    "ggpoker": (GGPoker, [FIXTURES / "ggpoker" / "plo_cash.txt"]),
    "kingclub": (KingsClub, sorted((FIXTURES / "kingclub").rglob("*.txt"))),
    "pacific": (PacificPoker, sorted((FIXTURES / "pacific").rglob("*.txt"))),
    "partypoker": (PartyPoker, sorted((FIXTURES / "partypoker").rglob("*.txt"))),
    "pokerstars": (PokerStars, sorted((FIXTURES / "pokerstars").rglob("*.txt"))),
    "unibet": (Unibet, sorted((FIXTURES / "unibet").rglob("*.txt"))),
    "winamax": (Winamax, [FIXTURES / "winamax" / "nlhe_cash.txt"]),
    "winning": (Winning, sorted((FIXTURES / "winning").rglob("*.txt"))),
}

CASES = [
    (f"{room}/{path.relative_to(FIXTURES / room).as_posix()}", parser_class, path)
    for room, (parser_class, paths) in ROOMS.items()
    for path in paths
]
CASES.append(
    (
        "ipoker/Flop/6+Holdem-EUR-0.25-0.50-201702.txt",
        iPoker,
        REGRESSION_FILES / "iPoker" / "Flop" / "6+Holdem-EUR-0.25-0.50-201702.txt",
    )
)
CASES += [
    (f"betonline/{path.relative_to(REGRESSION_FILES / 'BetOnline').as_posix()}", BetOnline, path)
    for path in sorted((REGRESSION_FILES / "BetOnline").rglob("*.txt"))
]
CASES.append(
    (
        "entraction/Flop/LHE-HU-EUR-10-20-201103.txt",
        Entraction,
        REGRESSION_FILES / "Entraction" / "Flop" / "LHE-HU-EUR-10-20-201103.txt",
    )
)
CASES += [
    (f"swc/{path.relative_to(REGRESSION_FILES / 'SealsWithClubs').as_posix()}", SealsWithClubs, path)
    for path in sorted((REGRESSION_FILES / "SealsWithClubs").rglob("*.txt"))
]


@pytest.fixture(scope="module")
def parser_config() -> Config:
    return Config()


@pytest.fixture(scope="module")
def golden_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("key", "parser_class", "hand_file"), CASES, ids=[case[0] for case in CASES])
def test_live_parser_file_matches_golden_snapshot(
    key: str,
    parser_class,
    hand_file: Path,
    parser_config: Config,
    golden_manifest: dict,
) -> None:
    parser = parser_class(config=parser_config, in_path=str(hand_file), autostart=True)
    snapshot = file_snapshot(parser.getProcessedHands())
    expected = golden_manifest[key]

    assert len(snapshot) == expected["hand_count"]
    assert snapshot_digest(snapshot) == expected["sha256"], json.dumps(snapshot, indent=2, sort_keys=True)


def test_live_parser_manifest_covers_every_fixture(golden_manifest: dict) -> None:
    expected_keys = {key for key, _, _ in CASES}
    assert set(golden_manifest) == expected_keys


def test_partypoker_conversion_does_not_open_a_database(parser_config: Config) -> None:
    hand_file = FIXTURES / "partypoker" / "stud" / "7stud.txt"
    parser = PartyPoker(config=parser_config, in_path=str(hand_file), autostart=True)

    assert parser.getProcessedHands()
    assert not hasattr(parser, "db")
