"""The 2026 Unibet client (Relax Gaming): its export folder, its hero, its Power Spins (#729).

* The client writes one file per table or tournament, and the tournament
  summaries, to ``Documents/Unibet Poker/History/Exports/Automatic`` on Windows
  and macOS alike; hands requested from its History tab go to ``Manual``, which
  auto-import must not watch.
* The hero is the one player named with the account token,
  ``name[Unibet_<hex>]``.
* Power Spins are lottery sit-and-gos that neither hands nor summaries name:
  a three-handed tournament whose prize pool is not the three buy-ins.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DetectInstalledSites import UnibetDetector
from fpdb_3_legacy.UnibetSummary import power_spin_multiplier
from fpdb_3_legacy.UnibetToFpdb import Unibet

ROOT = Path(__file__).resolve().parents[1]
POWER_SPIN = ROOT / "tests" / "fixtures" / "hands" / "unibet" / "power_spin_2026.txt"
AUTOMATIC = ("Documents", "Unibet Poker", "History", "Exports", "Automatic")

CASH_HAND = """Unibet Hand #1756096430 - 0.03/0.05 - Pot Limit Omaha - UTC 13:23:13 2026/11/07
Table "99433705" 6-max
*** Seated players ***
Seat 1: bob (€5.58)
Seat 4: alice[Unibet_0123456789abcdef] (€5.24)
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _detector() -> UnibetDetector:
    detector = UnibetDetector(SimpleNamespace(os_family="Mac"))
    detector.platform = "Darwin"
    return detector


def test_the_automatic_folder_and_its_hero_are_found(home: Path) -> None:
    folder = home.joinpath(*AUTOMATIC)
    folder.mkdir(parents=True)
    (folder / "H20261107 T99433705 €5 PL - 0.03-0.05 - Pot Limit Omaha.txt").write_text(CASH_HAND, encoding="utf-8")

    found = _detector().detect()

    assert found == {"detected": True, "hhpath": str(folder), "heroname": "alice", "tspath": str(folder)}


def test_an_empty_automatic_folder_is_found_without_a_hero(home: Path) -> None:
    folder = home.joinpath(*AUTOMATIC)
    folder.mkdir(parents=True)

    found = _detector().detect()

    assert found["detected"] is True
    assert found["hhpath"] == str(folder)
    assert found["heroname"] == ""


def test_the_manual_folder_alone_is_not_an_auto_import_folder(home: Path) -> None:
    manual = home / "Documents" / "Unibet Poker" / "History" / "Exports" / "Manual"
    manual.mkdir(parents=True)
    (manual / "19248-0123456789abcdef-20260717_100131-hands.txt").write_text(CASH_HAND, encoding="utf-8")

    assert _detector().detect()["detected"] is False


def test_windows_documents_redirected_to_onedrive_are_searched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile = tmp_path / "profile"
    folder = profile.joinpath("OneDrive", *AUTOMATIC)
    folder.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "elsewhere"))
    monkeypatch.setenv("USERPROFILE", str(profile))
    detector = _detector()
    detector.platform = "Windows"

    assert detector.detect()["hhpath"] == str(folder)


@pytest.mark.parametrize(
    ("players", "buyin", "fee", "prizepool", "multiplier"),
    [
        (3, 930, 70, 3000, 3),  # 10 EUR spin, 30 EUR pool
        (3, 930, 70, 2000, 2),
        (3, 93, 7, 400, 4),
        (3, 23, 2, 50, 2),  # 0.25 EUR spin, 0.50 EUR pool
        # Not a lottery: the pool is the three buy-ins, or not three players.
        (3, 930, 70, 2790, None),
        (6, 930, 70, 3000, None),
        (3, 0, 0, 0, None),
    ],
)
def test_power_spin_multiplier(players: int, buyin: int, fee: int, prizepool: int, multiplier: int | None) -> None:
    assert power_spin_multiplier(players, buyin, fee, prizepool) == multiplier


def test_power_spin_hands_are_a_lottery_sit_and_go() -> None:
    hands = Unibet(config=Config(), in_path=str(POWER_SPIN), autostart=True).getProcessedHands()

    assert hands
    assert {(hand.isSng, hand.isLottery, hand.tourneyMultiplier) for hand in hands} == {(True, True, 3)}
