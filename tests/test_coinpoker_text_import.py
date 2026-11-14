"""CoinPoker text hand-history import (#732).

The fixtures under ``regression-test-files/cash/CoinPoker`` are hands of a real
2026 export, anonymised: fresh pseudonyms, renumbered hands and tables. Hand
91426500343 keeps its number: it is also the live-capture fixture
(``data/coinpoker_hand_events.json``), which is what the duplicate test needs.
"""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.CoinPokerToFpdb import CoinPoker
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "regression-test-files" / "cash" / "CoinPoker" / "Flop"
LIVE_EVENTS = ROOT / "tests" / "data" / "coinpoker_hand_events.json"


@pytest.fixture(scope="module")
def config(tmp_path_factory) -> Config:
    path = tmp_path_factory.mktemp("coinpoker") / "HUD_config.xml"
    shutil.copyfile(ROOT / "HUD_config.xml", path)
    return Config(file=str(path))


@pytest.fixture(scope="module")
def hands(config: Config) -> dict[str, object]:
    parsed = {}
    for path in sorted(FIXTURES.glob("*.txt")):
        for hand in CoinPoker(config=config, in_path=str(path), autostart=True).getProcessedHands():
            parsed[hand.handid] = hand
    return parsed


def _stats(hand) -> dict[str, dict]:
    hand.playerIds = {p[1]: i for i, p in enumerate(hand.players, start=1)}
    hand.tourneysPlayersIds = {}
    stats = DerivedStats()
    stats.getStats(hand)
    return stats.handsplayers


def _acts(hand, street: str) -> list[tuple[str, str, Decimal]]:
    return [(a[0], a[1], a[2]) for a in hand.actions[street] if len(a) > 2]


# ---------------------------------------------------------------------------
# Header and game types
# ---------------------------------------------------------------------------


def test_every_fixture_hand_is_parsed(hands) -> None:
    assert len(hands) == 25


@pytest.mark.parametrize(
    ("hand_id", "category", "limit"),
    [
        ("90000000004", "holdem", "nl"),
        ("90000000001", "omahahi", "pl"),
        ("90000000006", "5_omahahi", "pl"),
        ("90000000008", "6_omahahi", "pl"),
    ],
)
def test_game_types(hands, hand_id, category, limit) -> None:
    gametype = hands[hand_id].gametype
    assert (gametype["type"], gametype["category"], gametype["limitType"]) == ("ring", category, limit)
    # ₮ (USDT) is stored as USD, the currency the live-capture import used.
    assert (gametype["currency"], gametype["sb"], gametype["bb"]) == ("USD", "0.01", "0.02")


def test_hand_header(hands) -> None:
    hand = hands["90000000001"]
    assert hand.tablename == "100001"
    assert hand.maxseats == 6
    assert hand.buttonpos == 1
    assert hand.hero == "Hero"
    # 22:15:58 CEST
    assert hand.startTime.isoformat() == "2026-07-17T20:15:58+00:00"


# ---------------------------------------------------------------------------
# CoinPoker-specific action lines
# ---------------------------------------------------------------------------


def test_allin_is_the_chips_added_read_as_bet_raise_or_call(hands) -> None:
    # "ALLIN 0.06" into a checked flop is a bet.
    assert ("0e181dd8", "bets", Decimal("0.06")) in _acts(hands["90000000015"], "FLOP")
    # "ALLIN 1.86" over a 0.48 bet, then "ALLIN 1.38" from the bettor: a raise
    # and a call -- 0.48 + 1.38 matches 1.86.
    turn = _acts(hands["90000000011"], "TURN")
    assert ("f982d1bf", "raises", Decimal("1.38")) in turn
    assert ("2f982ad8", "calls", Decimal("1.38")) in turn
    # "ALLIN 1.29" against a 1.44 bet: a short call.
    assert ("f45a2378", "calls", Decimal("1.29")) in _acts(hands["90000000010"], "RIVER")


def test_return_is_an_uncalled_bet(hands) -> None:
    hand = hands["90000000009"]
    # Bet 0.45 on the turn, folded to, "RETURN 0.45": the bettor is in for 0.22.
    assert hand.pot.committed["908e52f8"] == Decimal("0.22")
    assert hand.totalpot == Decimal("0.45")


def test_autobb_is_a_live_big_blind(hands) -> None:
    hand = hands["90000000017"]
    assert ("2d28e188", "big blind", Decimal("0.02")) in _acts(hand, "BLINDSANTES")
    # AUTOBB 0.02 then "calls 0.07" facing 0.09: in for 0.09.
    assert hand.pot.committed["2d28e188"] == Decimal("0.09")


def test_raises_after_autobb_add_the_blind_back(hands) -> None:
    # "AUTOBB 0.02 / raises 0.03 to 0.05": the next player "calls 0.07".
    assert hands["90000000018"].pot.committed["75ee8c10"] == Decimal("0.07")
    # Every preflop raise of that player leaves it out: "raises 0.49 to 0.73",
    # called by "calls 0.51" from 0.24 -- in for 0.75.
    hand = hands["90000000019"]
    assert hand.pot.committed["02500148"] == Decimal("0.75")
    assert hand.totalpot == Decimal("1.53")


def test_straddle(hands) -> None:
    assert ("9fad69b5", "straddle", Decimal("0.04")) in _acts(hands["90000000020"], "BLINDSANTES")


# ---------------------------------------------------------------------------
# Splash
# ---------------------------------------------------------------------------


def test_splash_is_promotional_money_beside_the_pot(hands) -> None:
    hand = hands["90000000009"]
    # "Total pot 0.49 | Rake 0.02" counts the 0.04 drop; nobody bet it.
    assert hand.splashPot == 4
    assert hand.totalpot == Decimal("0.45")
    assert hand.rake == Decimal("0.02")
    assert hand.collectees == {"908e52f8": Decimal("0.43")}
    # The pot winner takes the drop (seen in the hero's next stack).
    assert hand.splashWinnings == {"908e52f8": Decimal("0.04")}


def test_splash_counts_in_the_winners_profit(hands) -> None:
    hand = hands["90000000010"]
    stats = _stats(hand)
    # The hero put in 2.00 and collected 3.82, plus the 0.04 drop.
    assert stats["Hero"]["splashWinnings"] == 4
    assert stats["Hero"]["totalProfit"] == 186


def test_mega_splash(hands) -> None:
    hand = hands["90000000011"]
    assert hand.splashPot == 100
    assert hand.splashWinnings == {"f982d1bf": Decimal("1.00")}


def test_a_splash_fee_is_charged_with_the_rake() -> None:
    # No export seen so far carries one; the line is read wherever the summary puts it.
    parser = CoinPoker.__new__(CoinPoker)
    text = "*** SUMMARY ***\nTotal pot ₮1.05 | Rake ₮0.05 | Splash Fee ₮0.01\n"
    assert parser._summary_rake(text) == Decimal("0.06")


# ---------------------------------------------------------------------------
# Bomb pots, double boards, run it twice
# ---------------------------------------------------------------------------


def test_bomb_pot_double_board(hands) -> None:
    hand = hands["90000000012"]
    assert hand.bombPot == 30  # five antes of 0.06
    assert hand.runItTimes == 2
    assert not _acts(hand, "PREFLOP")
    # Both flops are dealt before the betting, which stays on FLOP.
    assert ("Hero", "bets", Decimal("0.15")) in _acts(hand, "FLOP")
    assert not _acts(hand, "FLOP2")
    assert DerivedStats().getBoardsList(hand) == [
        ["7s", "2c", "7c", "5s", "Qh"],
        ["5h", "Qs", "4s", "2h", "6c"],
    ]
    assert hand.collectees == {"78a5b943": Decimal("0.85"), "Hero": Decimal("0.86")}


def test_bomb_pots_give_no_vpip_chance(hands) -> None:
    stats = _stats(hands["90000000012"])
    assert not any(player["street0VPIChance"] for player in stats.values())
    assert not any(player["street0VPI"] for player in stats.values())


def test_plo6_bomb_pot(hands) -> None:
    hand = hands["90000000014"]
    assert hand.gametype["category"] == "6_omahahi"
    assert hand.bombPot == 8


def test_run_it_twice_after_a_shared_flop(hands) -> None:
    hand = hands["90000000015"]
    assert hand.runItTimes == 2
    assert DerivedStats().getBoardsList(hand) == [
        ["3c", "4s", "Qd", "Qs", "6d"],
        ["3c", "4s", "Qd", "9h", "5s"],
    ]
    # One payout per board.
    assert hand.collectees == {"Hero": Decimal("0.30"), "0e181dd8": Decimal("0.30")}


def test_run_it_twice_from_preflop(hands) -> None:
    hand = hands["90000000016"]
    assert [len(board) for board in DerivedStats().getBoardsList(hand)] == [5, 5]
    assert hand.board["FLOP2"] == ["5c", "4s", "8h"]


# ---------------------------------------------------------------------------
# EV cash-out (all-in insurance)
# ---------------------------------------------------------------------------


def test_an_insured_loser_is_paid_beside_the_pot(hands) -> None:
    hand = hands["90000000022"]
    assert hand.cashOutAmounts == {"a11bf874": Decimal("0.12")}
    assert hand.totalcollected == Decimal("1.56")
    assert hand.rake == Decimal("0.08")
    assert hand.totalpot == Decimal("1.64")


def test_an_insured_winner_gives_up_a_fee(hands) -> None:
    hand = hands["90000000023"]
    # Pot 0.79, rake 0.04: 0.75 owed, 0.42 paid.
    assert hand.cashOutAmounts == {"bafbf591": Decimal("0.42")}
    assert hand.cashOutFees == {"bafbf591": Decimal("0.33")}
    assert hand.rake == Decimal("0.04")  # not the fee


def test_an_insured_loser_across_side_pots(hands) -> None:
    hand = hands["90000000024"]
    assert hand.cashOutAmounts == {"85352c96": Decimal("1.74")}
    assert hand.totalcollected + hand.rake == hand.totalpot


def test_ordinary_hands_balance(hands) -> None:
    for hand in hands.values():
        if hand.cashOutAmounts:
            continue
        assert hand.totalcollected + hand.rake == hand.totalpot, hand.handid


# ---------------------------------------------------------------------------
# A hand imported from live capture and from the text export
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
            "db-databaseName": str(tmp_path / "coinpoker.sqlite3"),
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


def test_a_hand_already_captured_live_is_a_duplicate(importer) -> None:
    from fpdb_3_legacy.coinpoker_hand_builder import build_hands
    from fpdb_3_legacy.http_capture_hand_builder import HttpCaptureHandConfig, build_fpdb_hand, import_fpdb_hand

    events = [tuple(event) for event in json.loads(LIVE_EVENTS.read_text(encoding="utf-8"))]
    live = next(hand for hand in build_hands(events, "PLO4") if hand["hand_id"] == "91426500343")
    hand = build_fpdb_hand(live, config=HttpCaptureHandConfig(site_ids={"CoinPoker": CoinPoker.siteId}))
    import_fpdb_hand(hand, importer.database, file_id=1, doinsert=True, printtest=False, starting_hand_id=1)
    importer.database.commit()

    importer.addImportFile(str(FIXTURES / "PLO-6max-USD-0.01-0.02-202607.txt"), "auto")
    stored, duplicates, _partial, _skipped, errors, _time = importer.runImport()

    assert (stored, duplicates, errors) == (3, 1, 0)
    cursor = importer.database.get_cursor()
    cursor.execute("select count(*) from Hands where siteHandNo = '91426500343'")
    assert cursor.fetchone()[0] == 1


@pytest.mark.parametrize(
    ("zone", "utc"),
    [
        ("CEST", "2026-07-17T20:15:58+00:00"),
        ("EDT", "2026-07-18T02:15:58+00:00"),
        ("UTC", "2026-07-17T22:15:58+00:00"),
        ("-04", "2026-07-18T02:15:58+00:00"),
        ("+05:30", "2026-07-17T16:45:58+00:00"),
    ],
)
def test_the_clients_zone_is_read(zone, utc) -> None:
    import datetime

    start = datetime.datetime(2026, 7, 17, 22, 15, 58)  # noqa: DTZ001 - as written in the file
    assert CoinPoker._to_utc(start, zone).isoformat() == utc


def test_identify_site_names_coinpoker_not_ggpoker(config) -> None:
    # GGPoker's "Poker Hand #" used to claim "CoinPoker Hand #" files first.
    from fpdb_3_legacy.IdentifySite import IdentifySite

    identify = IdentifySite(config)
    path = FIXTURES / "PLO-6max-USD-0.01-0.02-202607.txt"
    found = identify.idSite(str(path), path.read_text(encoding="utf-8"), "utf-8")

    assert found.site.name == "CoinPoker"
    assert found.hero == "Hero"


def test_ggpoker_still_identifies_its_own_files() -> None:
    from fpdb_3_legacy.GGPokerToFpdb import GGPoker

    assert GGPoker.re_identify.search("Poker Hand #RC1234567890: Hold'em No Limit ($0.01/$0.02) - 2026/07/17")
    assert GGPoker.re_identify.search("﻿Poker Hand #HD123: PLO ($0.05/$0.10)")
    assert not GGPoker.re_identify.search("CoinPoker Hand #91198200457: PLO 4 (₮0.01/₮0.02)")
    assert not GGPoker.re_identify.search("SwCPoker Hand #183411552:  Omaha Pot Limit (0.02/0.04)")


def test_a_header_without_a_zone_does_not_borrow_the_next_line() -> None:
    # A "\s+" before the zone crossed the newline and read the "T" of "Table".
    header = "CoinPoker Hand #1: PLO 4 (₮0.01/₮0.02) 2026/07/17 22:15:58\nTable '1' 6-max Seat #1 is the button"
    match = CoinPoker.re_GameInfo.search(header)
    assert match is not None
    assert match.group("TZ") is None
    assert CoinPoker.re_GameInfo.search(header.replace(":58\n", ":58 CEST\n")).group("TZ") == "CEST"
