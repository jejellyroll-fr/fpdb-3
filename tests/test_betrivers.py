"""BetRivers Poker text hand-history import (#731).

The fixtures under ``regression-test-files/cash/BetRivers`` are written for
these tests from the format of public 2026 samples (PT4 and DriveHUD forum
posts); the samples themselves are not committed, their licence being
unverified. They cover what differs from PokerStars: a header time without
seconds in a stated US zone, the ``[hero]`` seat marker, Splash the Pot (STP)
including a "Big Splash" with no blinds, side-pot payouts and ``*** SHOWDOWN ***``.
"""

from __future__ import annotations

import datetime
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.BetRiversToFpdb import BetRivers
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.HandHistoryConverter import FpdbParseError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "regression-test-files" / "cash" / "BetRivers" / "Flop"
STP_FILE = FIXTURES / "NLHE-6max-USD-2026.stp.showdown.synthetic.txt"
BIG_SPLASH_FILE = FIXTURES / "NLHE-4max-USD-0.25-0.50-202602.big.splash.synthetic.txt"


@pytest.fixture(scope="module")
def config(tmp_path_factory) -> Config:
    path = tmp_path_factory.mktemp("betrivers") / "HUD_config.xml"
    shutil.copyfile(ROOT / "HUD_config.xml", path)
    return Config(file=str(path))


@pytest.fixture(scope="module")
def hands(config: Config) -> dict[str, object]:
    parsed = {}
    for path in sorted(FIXTURES.glob("*.txt")):
        for hand in BetRivers(config=config, in_path=str(path), autostart=True).getProcessedHands():
            parsed[hand.handid] = hand
    return parsed


def _stats(hand) -> dict[str, dict]:
    hand.playerIds = {p[1]: i for i, p in enumerate(hand.players, start=1)}
    hand.tourneysPlayersIds = {}
    stats = DerivedStats()
    stats.getStats(hand)
    return stats.handsplayers


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------


def test_every_fixture_hand_is_parsed(hands) -> None:
    assert sorted(hands) == ["10000001", "10000002", "10000003"]


def test_game_type(hands) -> None:
    gametype = hands["10000001"].gametype
    assert (gametype["type"], gametype["category"], gametype["limitType"]) == ("ring", "holdem", "nl")
    assert (gametype["currency"], gametype["sb"], gametype["bb"]) == ("USD", "0.10", "0.20")


@pytest.mark.parametrize(
    ("hand_id", "utc"),
    [
        ("10000001", "2026-03-03T02:15:00+00:00"),  # 21:15 EST
        ("10000002", "2026-08-12T18:03:00+00:00"),  # 14:03 EDT
    ],
)
def test_a_time_without_seconds_is_read_in_its_zone(hands, hand_id, utc) -> None:
    assert hands[hand_id].startTime.isoformat() == utc


def test_an_unreadable_time_is_an_error_not_2000() -> None:
    with pytest.raises(FpdbParseError):
        BetRivers._start_time("2026/02/30", "19:46", "EST")


@pytest.mark.parametrize(
    ("time", "zone", "utc"),
    [
        # The hour clocks fall back through happens twice; the zone says which.
        ("01:30", "EDT", datetime.datetime(2026, 11, 1, 5, 30, tzinfo=datetime.UTC)),
        ("01:30", "EST", datetime.datetime(2026, 11, 1, 6, 30, tzinfo=datetime.UTC)),
    ],
)
def test_an_explicit_eastern_zone_is_its_offset(time, zone, utc) -> None:
    assert BetRivers._start_time("2026/11/01", time, zone) == utc


def test_seconds_are_read_when_present() -> None:
    start = BetRivers._start_time("2026/02/11", "19:46:07", "EST")
    assert start == datetime.datetime(2026, 2, 12, 0, 46, 7, tzinfo=datetime.UTC)


def test_table_and_hero(hands) -> None:
    hand = hands["10000002"]
    assert hand.tablename == "500002"
    assert hand.maxseats == 6
    assert hand.buttonpos == 4
    # The [hero] marker names the hero; "Dealt to heidi [...]" does not.
    assert hand.hero == "Hero"
    assert hand.holecards["PREFLOP"]["Hero"][1] == ["Jh", "Jc"]


def test_the_hero_marker_wins_over_the_first_dealt_line(config, tmp_path) -> None:
    text = BIG_SPLASH_FILE.read_text(encoding="utf-8").replace(
        "Dealt to Hero [Ac 5d]\nDealt to kim [Kh Qh]\n", "Dealt to kim [Kh Qh]\nDealt to Hero [Ac 5d]\n"
    )
    path = tmp_path / "reordered.txt"
    path.write_text(text, encoding="utf-8")
    (hand,) = BetRivers(config=config, in_path=str(path), autostart=True).getProcessedHands()
    assert hand.hero == "Hero"
    assert hand.holecards["PREFLOP"]["Hero"][1] == ["Ac", "5d"]


# ---------------------------------------------------------------------------
# Splash the Pot
# ---------------------------------------------------------------------------


def test_stp_is_room_money_in_the_pot(hands) -> None:
    hand = hands["10000001"]
    # "Total pot $4.30 | Main pot $3.70 | STP $0.60 | Rake $0.19"
    assert hand.splashPot == 60
    assert hand.pot.stp == Decimal("0.60")
    assert hand.totalpot == Decimal("4.30")
    assert hand.rake == Decimal("0.19")
    assert hand.collectees == {"Hero": Decimal("4.11")}
    # Bets only: the STP is no one's bet.
    assert sum(hand.pot.committed.values()) == Decimal("3.70")


def test_the_uncalled_bet_goes_back(hands) -> None:
    assert hands["10000001"].pot.committed["Hero"] == Decimal("1.50")


def test_a_big_splash_has_no_blinds_and_pays_side_pots(hands) -> None:
    hand = hands["10000003"]
    assert not hand.actions["BLINDSANTES"]
    assert hand.splashPot == 2000
    assert hand.totalpot == Decimal("20.00")
    assert hand.collectees == {
        "leo": Decimal("14.00"),
        "Hero": Decimal("2.00"),
        "kim": Decimal("2.00"),
        "mia": Decimal("2.00"),
    }
    assert hand.totalcollected + hand.rake == hand.totalpot


def test_stp_is_counted_once_in_profit(hands) -> None:
    # Hero put nothing in and took $2.00 of the splash: +$2.00, not +$4.00.
    stats = _stats(hands["10000003"])
    assert stats["Hero"]["totalProfit"] == 200
    assert stats["leo"]["totalProfit"] == 1400


def test_every_hand_balances(hands) -> None:
    for hand in hands.values():
        assert hand.totalcollected + hand.rake == hand.totalpot, hand.handid


# ---------------------------------------------------------------------------
# Showdown
# ---------------------------------------------------------------------------


def test_shown_and_mucked_cards(hands) -> None:
    hand = hands["10000002"]
    assert "Hero" in hand.shown
    assert "heidi" in hand.mucked
    assert hand.holecards["PREFLOP"]["heidi"][1] == ["Ad", "Kh"]


# ---------------------------------------------------------------------------
# Identification and room policy
# ---------------------------------------------------------------------------


def test_identify_site_names_betrivers_not_ggpoker(config) -> None:
    # GGPoker's "Poker Hand #" used to match "BetRivers Poker Hand #" too.
    from fpdb_3_legacy.IdentifySite import IdentifySite

    found = IdentifySite(config).idSite(str(STP_FILE), STP_FILE.read_text(encoding="utf-8"), "utf-8")

    assert found.site.name == "BetRivers"


def test_ggpoker_still_identifies_its_own_files() -> None:
    from fpdb_3_legacy.GGPokerToFpdb import GGPoker

    assert GGPoker.re_identify.search("Poker Hand #RC1234567890: Hold'em No Limit ($0.01/$0.02) - 2026/07/17")
    assert GGPoker.re_identify.search("﻿Poker Hand #HD123: PLO ($0.05/$0.10)")
    assert not GGPoker.re_identify.search("BetRivers Poker Hand #10000001: Hold'em No Limit ($0.10/$0.20)")


def test_betrivers_is_import_only() -> None:
    from fpdb_3_legacy.disabled_sites import allows_live_use, is_site_import_only

    assert is_site_import_only("BetRivers")
    assert not allows_live_use("BetRivers")


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


@pytest.fixture
def importer(tmp_path):
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    shutil.copyfile(ROOT / "HUD_config.xml", tmp_path / "HUD_config.xml")
    config = Config(file=str(tmp_path / "HUD_config.xml"))
    params = config.get_db_parameters()
    params.update(
        {
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(tmp_path / "betrivers.sqlite3"),
            "db-path": "",
        }
    )
    config.get_db_parameters = lambda: params
    schema = Database(config)
    schema.recreate_tables()
    schema.close_connection()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.setCallHud(False)
    yield importer
    importer.close()


def test_import_stores_the_hands_once_under_betrivers(importer) -> None:
    for path in (STP_FILE, BIG_SPLASH_FILE):
        importer.addImportFile(str(path), "auto")
    stored, duplicates, _partial, _skipped, errors, _time = importer.runImport()
    assert (stored, duplicates, errors) == (3, 0, 0)

    cursor = importer.database.get_cursor()
    cursor.execute(
        "SELECT DISTINCT s.name FROM Hands h JOIN Gametypes g ON h.gametypeId = g.id JOIN Sites s ON g.siteId = s.id"
    )
    assert [row[0] for row in cursor.fetchall()] == ["BetRivers"]
    cursor.execute("SELECT siteHandNo, splashPot FROM Hands ORDER BY siteHandNo")
    assert [(str(no), splash) for no, splash in cursor.fetchall()] == [
        ("10000001", 60),
        ("10000002", 0),
        ("10000003", 2000),
    ]
