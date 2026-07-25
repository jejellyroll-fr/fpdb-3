"""A file must parse the same whether its lines end in LF or CRLF.

Git rewrites line endings on a Windows checkout for every file it considers
text -- which excludes the UTF-16 and NUL-bearing exports, and includes plain
ASCII ones. Two converters read those rewritten files differently, and the CI
Windows job was the first thing to notice.

Both defects changed data rather than raising:

* Winamax read the tournament speed as ``"semiturbo\\r"``, which matches no
  known speed, so every turbo tournament was filed as a normal one;
* PokerTracker halves runs of blank lines to undo an export quirk, counts them
  with ``\\n+``, and under CRLF sees no run longer than one -- so the halving
  never fires and the file splits into one fragment per doubled blank line,
  yielding no hand at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.PokerTrackerToFpdb import PokerTracker
from fpdb_3_legacy.WinamaxSummary import WinamaxSummary
from tests.helpers.parser_regression import file_snapshot, snapshot_digest
from tests.helpers.summary_regression import (
    hhtype_for,
    make_summary,
    read_text,
    summary_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]
POKERTRACKER = ROOT / "regression-test-files/cash/PokerTracker/Flop/PLO-EUR-0.25-0.50-201601.all.in.call.txt"
WINAMAX = ROOT / "regression-test-files/summaries/Winamax/NLHE-EUR-HUSNG-4.70-201302.semiturbo.txt"


def as_crlf(path: Path, into: Path) -> Path:
    """Write *path* out with CRLF endings, as a Windows checkout would."""
    copy = into / path.name
    copy.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return copy


@pytest.fixture
def config() -> Any:
    return Config()


def test_a_hand_history_parses_the_same_with_either_line_ending(config, tmp_path) -> None:
    original = snapshot_digest(
        file_snapshot(PokerTracker(config=config, in_path=str(POKERTRACKER), autostart=True).getProcessedHands())
    )

    rewritten = snapshot_digest(
        file_snapshot(
            PokerTracker(config=config, in_path=str(as_crlf(POKERTRACKER, tmp_path)), autostart=True).getProcessedHands()
        )
    )

    assert rewritten == original


def test_a_hand_history_still_yields_its_hand_under_crlf(config, tmp_path) -> None:
    # The failure mode was silent: no hand, no error, an empty import.
    hands = PokerTracker(config=config, in_path=str(as_crlf(POKERTRACKER, tmp_path)), autostart=True).getProcessedHands()

    assert len(hands) == 1


def summary_of(path: Path) -> Any:
    summary = make_summary(WinamaxSummary, read_text(path), "Winamax", 15, hhtype_for(path))
    summary.parseSummary()
    return summary


def test_a_summary_parses_the_same_with_either_line_ending(tmp_path) -> None:
    original = snapshot_digest([summary_fingerprint(summary_of(WINAMAX))])

    rewritten = snapshot_digest([summary_fingerprint(summary_of(as_crlf(WINAMAX, tmp_path)))])

    assert rewritten == original


def test_a_turbo_tournament_stays_turbo_under_crlf(tmp_path) -> None:
    # "Speed : semiturbo" is compared against a bare literal, so a trailing
    # carriage return silently downgraded the tournament to Normal.
    assert summary_of(as_crlf(WINAMAX, tmp_path)).speed == "Turbo"


def test_the_summary_reader_strips_carriage_returns(tmp_path) -> None:
    copy = as_crlf(WINAMAX, tmp_path)

    assert b"\r\n" in copy.read_bytes()
    assert "\r" not in read_text(copy)
