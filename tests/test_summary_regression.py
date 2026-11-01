"""File-by-file golden regression harness for tournament summaries.

The hand harness in test_live_parser_regression.py could not be reused: a
TourneySummary subclass parses from its ``__init__``, which also opens a
database, so the scaffolding in tests/helpers/summary_regression.py patches
that out and calls ``parseSummary`` directly.

Every summary the project ships is swept. Files a converter cannot take are
listed by name rather than left to shift a digest silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy.FullTiltPokerSummary import FullTiltPokerSummary
from fpdb_3_legacy.PacificPokerSummary import PacificPokerSummary
from fpdb_3_legacy.PokerStarsSummary import PokerStarsSummary
from fpdb_3_legacy.PokerTrackerSummary import PokerTrackerSummary
from fpdb_3_legacy.WinamaxSummary import WinamaxSummary
from fpdb_3_legacy.WinningSummary import WinningSummary
from tests.helpers.parser_regression import snapshot_digest
from tests.helpers.summary_regression import (
    hhtype_for,
    make_summary,
    read_text,
    summary_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]
SUMMARIES = ROOT / "regression-test-files" / "summaries"
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "summaries" / "summary_snapshots.json"

# Directory -> converter, the site name it reports itself as, and its site id.
SITES = {
    "FTP": (FullTiltPokerSummary, "Fulltilt", 1),
    "PacificPoker": (PacificPokerSummary, "PacificPoker", 15),
    "PokerTracker": (PokerTrackerSummary, "PokerTracker", 22),
    "Stars": (PokerStarsSummary, "PokerStars", 2),
    "Winamax": (WinamaxSummary, "Winamax", 15),
    "Winning": (WinningSummary, "WinningPoker", 24),
}

CASES = [
    (f"{site}/{path.relative_to(SUMMARIES / site).as_posix()}", site, path)
    for site in SITES
    for path in sorted(p for p in (SUMMARIES / site).rglob("*") if p.is_file())
]

# Files this harness cannot drive, none of them a converter defect:
#
#  * the three PokerStars .htm archives and the Winning transaction page hold
#    many tournaments on one page. The importer splits them into chunks before
#    parsing each; handed the whole page, the converters correctly answer that
#    this chunk holds no tournament;
#  * the Full Tilt .xls is a binary workbook, opened with xlrd by the importer
#    rather than decoded to text;
#  * the Winamax freeroll ticket states no value and is refused outright.
KNOWN_UNPARSED = {
    "FTP/HORSE-2max-SnG-USD-200604.xls",
    "Stars/PokerStars-MTT-Archive-201007.htm",
    "Stars/PokerStars-MTT-Archive-2012.ignore.bounties.htm",
    "Stars/PokerStars-SnG-Archive-201007.htm",
    "Winamax/17045686.Freeroll.Ticket.with.no.specified.value.txt",
    "Winning/PlayerTransactionHistory.html",
}

# Two summaries register no player, and in both cases the file itself withholds
# what addPlayer needs, so the converter declines rather than invent it:
#
#  * the freeroll never names anyone -- it has no "Player :" line at all, only
#    "You finished in 3497th place";
#  * the semiturbo names the hero but states the placing as a literal ellipsis,
#    "You finished in ... place", which WinamaxSummary skips explicitly.
#
# The third file in this set was a genuine gap and is now fixed: an emailed
# PokerStars summary states the result in prose, and its hero is registered
# from the greeting and the award line.
HERO_RESULT_WITHHELD_BY_THE_FILE = {
    "Winamax/20110305_Freeroll 150%80(5142226)_real_holdem_no-limit_summary.txt",
    "Winamax/NLHE-EUR-HUSNG-4.70-201302.semiturbo.txt",
}

PARSEABLE = [case for case in CASES if case[0] not in KNOWN_UNPARSED]


@pytest.fixture(scope="module")
def golden_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def fingerprint_of(site: str, path: Path) -> dict:
    summary_class, sitename, site_id = SITES[site]
    summary = make_summary(summary_class, read_text(path), sitename, site_id, hhtype_for(path))
    summary.parseSummary()
    return summary_fingerprint(summary)


@pytest.mark.parametrize(("key", "site", "path"), PARSEABLE, ids=[case[0] for case in PARSEABLE])
def test_summary_matches_its_golden_snapshot(key, site, path, golden_manifest) -> None:
    fingerprint = fingerprint_of(site, path)
    expected = golden_manifest[key]

    assert len(fingerprint["players"]) == expected["player_count"]
    assert snapshot_digest([fingerprint]) == expected["sha256"], json.dumps(
        fingerprint, indent=2, sort_keys=True
    )


def test_the_manifest_covers_every_parseable_summary(golden_manifest) -> None:
    assert set(golden_manifest) == {case[0] for case in PARSEABLE}


@pytest.mark.parametrize("key", sorted(KNOWN_UNPARSED))
def test_the_listed_files_are_still_the_ones_this_harness_cannot_drive(key) -> None:
    site, _, relative = key.partition("/")
    with pytest.raises(Exception):  # noqa: B017, PT011 - each converter refuses in its own way
        fingerprint_of(site, SUMMARIES / site / relative)


@pytest.mark.parametrize(
    ("key", "site", "path"),
    [case for case in PARSEABLE if case[0] not in HERO_RESULT_WITHHELD_BY_THE_FILE],
    ids=[case[0] for case in PARSEABLE if case[0] not in HERO_RESULT_WITHHELD_BY_THE_FILE],
)
def test_every_summary_registers_at_least_one_player(key, site, path) -> None:
    # A summary that registers nobody imports a tournament the hero did not
    # play, which is never what the file says.
    assert fingerprint_of(site, path)["players"]


@pytest.mark.parametrize("key", sorted(HERO_RESULT_WITHHELD_BY_THE_FILE))
def test_a_file_that_names_nobody_registers_nobody(key) -> None:
    site, _, relative = key.partition("/")

    assert fingerprint_of(site, SUMMARIES / site / relative)["players"] == []


def test_an_emailed_summary_registers_its_hero_from_the_prose() -> None:
    # No ranking table: the greeting names the player and the award line states
    # what they won. Both used to be dropped, importing a tournament nobody played.
    fingerprint = fingerprint_of("Stars", SUMMARIES / "Stars" / "NLHE-EUR-STT-0.42-201102.emailed.cp1252.txt")

    assert fingerprint["players"] == [
        {"rank": 2, "name": "Hero", "winnings": 90, "currency": "EUR",
         "rebuys": None, "addons": None, "ko": None},
    ]


@pytest.mark.parametrize(("key", "site", "path"), PARSEABLE, ids=[case[0] for case in PARSEABLE])
def test_every_summary_names_its_tournament_and_costs_nothing_negative(key, site, path) -> None:
    fingerprint = fingerprint_of(site, path)
    tournament = fingerprint["tournament"]

    assert tournament["tourNo"], f"{key} has no tournament number"
    for field in ("buyin", "fee", "prizepool", "entries", "koBounty"):
        value = tournament[field]
        assert value is None or float(value) >= 0, f"{key} has a negative {field}: {value}"
