"""GGPoker tournament summaries, and the GG export variant fpdb refuses (#868).

A bulk import of a GG folder reported two files as "siteId Failed":

* the tournament summary the client writes beside a Spin&Gold's hands, which
  no converter read, so a GG tournament never got its place or prize;
* a cash hand numbered "Poker Hand #ring_...", the output of a third-party
  converter (hexadecimal ids, seats out of order, bets with no verb). It is
  now refused by name instead.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.GGPokerSummary import GGPokerSummary, split_buyin
from fpdb_3_legacy.IdentifySite import UNSUPPORTED_GG_VARIANT, IdentifySite
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden
from tests.helpers.summary_regression import make_summary, summary_fingerprint

REPO = Path(__file__).resolve().parent.parent
SPIN_SUMMARY = REPO / "regression-test-files" / "summaries" / "GGPoker" / "NLHE-USD-SpinGold-0.25-202512.lottery.txt"
SPIN_HANDS = REPO / "tests" / "fixtures" / "hands" / "ggpoker" / "spin_gold_2025.txt"

# The head of the third-party file from the report: ids and amounts as found.
RING_VARIANT = """Poker Hand #ring_623971570: NLH No Limit ($0.5/$1) - 2024/12/08 20:15:26
Table 'NLH - $.50 / $1' 9-max Seat #7 is the button
Seat 7: 26b546ba ($111.82 in chips)
Seat 8: 62877a2a ($88.4 in chips)
Seat 1: Hero ($100.45 in chips)
62877a2a: posts small blind $0.5
17bbb47: posts big blind $1
*** HOLE CARDS ***
Dealt to Hero [8h 8c]
Hero: $2 to $3
"""


def _parse(text: str) -> dict:
    summary = make_summary(GGPokerSummary, text, "GGPoker", 27)
    summary.parseSummary()
    return summary_fingerprint(summary)


# --------------------------------------------------------------------------
# Reading a summary
# --------------------------------------------------------------------------


def test_a_spin_and_gold_summary_is_a_lottery_with_the_hero_s_place() -> None:
    fingerprint = _parse(SPIN_SUMMARY.read_text(encoding="utf-8"))
    tournament = fingerprint["tournament"]

    assert tournament["tourNo"] == "249773363"
    assert tournament["tourneyName"] == "Spin&Gold #7"
    assert (tournament["buyin"], tournament["fee"], tournament["buyinCurrency"]) == (25, 0, "USD")
    assert (tournament["entries"], tournament["prizepool"], tournament["maxseats"]) == (3, 50, 3)
    assert tournament["isSng"] and tournament["isLottery"]
    assert fingerprint["players"] == [
        {"rank": 2, "name": "Hero", "winnings": 0, "currency": "USD", "rebuys": None, "addons": None, "ko": None},
    ]


def test_a_spin_and_gold_multiplier_is_the_prize_pool_over_the_buyin() -> None:
    summary = make_summary(GGPokerSummary, SPIN_SUMMARY.read_text(encoding="utf-8"), "GGPoker", 27)
    summary.parseSummary()

    assert summary.tourneyMultiplier == 2  # a $0.50 pool for a $0.25 spin
    assert summary.gametype == {"base": "hold", "category": "holdem", "limitType": "nl"}


def test_a_regular_tournament_keeps_its_fee_and_the_whole_name() -> None:
    # Commas in the name and in the amounts: only the last ", <game> <limit>" is the game.
    fingerprint = _parse(
        "Tournament #9364957, WSOP #77: $5,000 Main Event [Flight W], $25M GTD, Hold'em No Limit\n"
        "Buy-in: $4,700+$300\n"
        "1,234 Players\n"
        "Total Prize Pool: $5,800,000\n"
        "Tournament started 2020/08/30 15:49:08 \n"
        "112th : Hero, $12,345.6\n"
        "You finished the tournament in 112th place.\n"
        "You received a total of $12,345.6.\n"
    )
    tournament = fingerprint["tournament"]

    assert tournament["tourneyName"] == "WSOP #77: $5,000 Main Event [Flight W], $25M GTD"
    assert (tournament["buyin"], tournament["fee"], tournament["koBounty"]) == (470000, 30000, 0)
    assert (tournament["entries"], tournament["prizepool"]) == (1234, 580000000)
    assert not tournament["isLottery"] and not tournament["isKO"]
    assert [(p["rank"], p["name"], p["winnings"]) for p in fingerprint["players"]] == [(112, "Hero", 1234560)]


def test_an_omaha_bounty_tournament_counts_its_bounty_in_the_buyin() -> None:
    summary = make_summary(
        GGPokerSummary,
        "Tournament #5259595, Bounty Hunters $10.80, Omaha Pot Limit\n"
        "Buy-in: $5+$0.8+$5\n"
        "300 Players\n"
        "Total Prize Pool: $3,000\n"
        "Tournament started 2020/06/02 19:17:33\n"
        "3rd : Hero, $150\n",
        "GGPoker",
        27,
    )
    summary.parseSummary()

    assert (summary.buyin, summary.fee, summary.koBounty, summary.isKO) == (1000, 80, 500, True)
    assert summary.gametype == {"base": "hold", "category": "omahahi", "limitType": "pl"}


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([25], (25, 0, 0)),
        ([180, 20], (180, 20, 0)),
        ([500, 80, 500], (1000, 80, 500)),
        ([500, 500, 80], (1000, 80, 500)),  # the rake is the small part, wherever it stands
    ],
)
def test_the_buyin_parts_split_into_buyin_fee_and_bounty(parts, expected) -> None:
    assert split_buyin(parts) == expected


def test_without_a_ranking_line_the_closing_sentences_give_the_result() -> None:
    fingerprint = _parse(
        "Tournament #1, Daily Hyper, Hold'em No Limit\n"
        "Buy-in: $1.8+$0.2\n"
        "50 Players\n"
        "Tournament started 2025/01/01 20:00:00\n"
        "You finished the tournament in 4th place.\n"
        "You received a total of $7.5.\n"
    )

    assert [(p["rank"], p["name"], p["winnings"]) for p in fingerprint["players"]] == [(4, "Hero", 750)]


def test_a_text_that_is_not_a_summary_is_refused() -> None:
    from fpdb_3_legacy.HandHistoryConverter import FpdbParseError

    with pytest.raises(FpdbParseError):
        _parse("Tournament #1, nothing else\n")


# --------------------------------------------------------------------------
# Identification
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def identifier() -> IdentifySite:
    return IdentifySite(Config(file=str(REPO / "HUD_config.xml")))


def test_a_gg_summary_is_identified_as_one(identifier) -> None:
    identifier.clear_filelist()
    identifier.processFile(str(SPIN_SUMMARY))
    found = identifier.get_fobj(str(SPIN_SUMMARY))

    assert found
    assert (found.ftype, found.site.name, found.site.summary) == ("summary", "GGPoker", "GGPokerSummary")


def test_the_gg_hands_are_still_hands(identifier) -> None:
    identifier.clear_filelist()
    identifier.processFile(str(SPIN_HANDS))
    found = identifier.get_fobj(str(SPIN_HANDS))

    assert found
    assert (found.ftype, found.site.filter_name) == ("hh", "GGPoker")


def test_the_ring_variant_is_refused_by_name(identifier, tmp_path) -> None:
    ring = tmp_path / "hand2.txt"
    ring.write_text(RING_VARIANT, encoding="utf-8")

    identifier.clear_filelist()
    identifier.processFile(str(ring))

    assert not identifier.get_fobj(str(ring))
    assert identifier.unsupported_reason(str(ring)) == UNSUPPORTED_GG_VARIANT


def test_a_genuine_gg_hand_has_no_unsupported_reason(identifier) -> None:
    identifier.clear_filelist()
    identifier.processFile(str(SPIN_HANDS))

    assert identifier.unsupported_reason(str(SPIN_HANDS)) is None


# --------------------------------------------------------------------------
# Importing
# --------------------------------------------------------------------------


def _importer(directory: Path):
    config = golden.build_config(directory)
    Database(config).recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = Database(config)
    return config, importer


def _rows(db, statement: str) -> list[tuple]:
    cursor = db.get_cursor()
    cursor.execute(statement)
    return [tuple(row) for row in cursor.fetchall()]


@pytest.mark.parametrize(
    "files",
    [(SPIN_HANDS, SPIN_SUMMARY), (SPIN_SUMMARY, SPIN_HANDS)],
    ids=["hands-first", "summary-first"],
)
def test_a_spin_and_gold_imports_as_one_lottery_tournament(tmp_path: Path, files) -> None:
    config, importer = _importer(tmp_path)
    for path in files:
        assert importer.addImportFile(str(path), "auto"), f"{path.name} was not recognised"
    importer.runImport()
    db = Database(config)

    assert _rows(db, "SELECT buyin, fee, currency, maxSeats, sng, lottery, multiplier FROM TourneyTypes") == [
        (25, 0, "USD", 3, 1, 1, 2)
    ]
    assert _rows(db, "SELECT siteTourneyNo, entries, prizepool FROM Tourneys") == [(249773363, 3, 50)]
    results = _rows(
        db,
        "SELECT p.name, tp.rank, tp.winnings FROM TourneysPlayers tp JOIN Players p ON p.id = tp.playerId "
        "WHERE tp.rank IS NOT NULL",
    )
    assert results == [("Hero", 2, 0)]
    hero_hands = _rows(
        db,
        "SELECT COUNT(*) FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId "
        "JOIN Hands h ON h.id = hp.handId WHERE p.name = 'Hero' AND h.tourneyId IS NOT NULL",
    )
    assert hero_hands == [(10,)]


def test_the_importer_names_why_the_ring_variant_is_not_imported(tmp_path: Path, caplog) -> None:
    ring = tmp_path / "hand2.txt"
    ring.write_text(RING_VARIANT, encoding="utf-8")
    _config, importer = _importer(tmp_path)

    with caplog.at_level(logging.WARNING):
        assert not importer.addImportFile(str(ring), "auto")

    assert "unsupported GG export variant" in caplog.text
    assert "siteId Failed" not in caplog.text
