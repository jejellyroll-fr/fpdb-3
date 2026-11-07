"""GGPoker hand times, EV Cashout, Cash Drop and run-it-twice rake.

Two sessions of Rush & Cash PLO, trimmed to the hands that went wrong:

- Times. GGPoker names a file after the session start in UTC
  ("GG20261106-2036 - ...") and stamps the hands with the player's local time
  (21:36 in Paris for that session). They were read as US Eastern time, so
  every hand was stored five or six hours late -- on the next day for evening
  play.
- EV Cashout. A player who cashes out is paid their equity whatever the river
  brings. The pot used to be credited instead: the loser got nothing for their
  cash-out, the winner kept the "Cashout Risk" they handed back.
- Cash Drop. The house money seeded into the pot was ignored, so the pot did not
  add up.
- Run it twice. The rake was zeroed to be spread pot by pot, but GGPoker leaves
  no pots to spread it over, so it vanished.
"""

from __future__ import annotations

import datetime
import shutil
import time
from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy import DerivedStats as derived_stats_module
from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.DerivedStats import DerivedStats
from fpdb_3_legacy.GGPokerToFpdb import GGPoker, hand_time_offset

FLOP = Path(__file__).resolve().parents[1] / "regression-test-files/cash/GGPoker/Flop"
# Each file keeps its session's first hand: the time zone is read off it.
CASHOUT_SESSION = FLOP / "PLO-6max-USD-0.05-0.10-202611.ev.cashout.cash.drop.txt"
MIDNIGHT_SESSION = FLOP / "PLO-6max-USD-0.05-0.10-202611.past.midnight.cashout.rit.txt"
# The names the GGPoker client gave the two files.
CASHOUT_SESSION_NAME = "GG20261106-2036 - RushAndCash3506303 - 0.05 - 0.1 - 6max.txt"
MIDNIGHT_SESSION_NAME = "GG20261106-2249 - RushAndCash3520626 - 0.05 - 0.1 - 6max.txt"

UTC = datetime.timezone.utc


def _parse(path: Path) -> dict[str, object]:
    hands = GGPoker(config=Config(), in_path=str(path), autostart=True).getProcessedHands()
    return {str(h.handid): h for h in hands}


@pytest.fixture(scope="module")
def cashout_session(tmp_path_factory) -> dict[str, object]:
    path = tmp_path_factory.mktemp("gg") / CASHOUT_SESSION_NAME
    shutil.copy(CASHOUT_SESSION, path)
    return _parse(path)


@pytest.fixture(scope="module")
def midnight_session(tmp_path_factory) -> dict[str, object]:
    path = tmp_path_factory.mktemp("gg") / MIDNIGHT_SESSION_NAME
    shutil.copy(MIDNIGHT_SESSION, path)
    return _parse(path)


def _stats(hand) -> dict[str, dict]:
    hand.playerIds = {p[1]: i for i, p in enumerate(hand.players, start=1)}
    hand.tourneysPlayersIds = {}
    stats = DerivedStats()
    stats.getStats(hand)
    return stats.handsplayers


# --- Hand times -------------------------------------------------------------


def _utc(*args: int) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=UTC)


def test_hand_times_are_read_in_the_players_zone(cashout_session) -> None:
    # Stamped 21:36:36 and 21:51:06 in Paris (UTC+1), in a session the file
    # name starts at 20:36 UTC.
    assert cashout_session["942723353"].startTime == _utc(2026, 11, 6, 20, 36, 36)  # was 2026-11-07 02:36:36
    assert cashout_session["942724589"].startTime == _utc(2026, 11, 6, 20, 51, 6)


def test_a_hand_past_local_midnight_stays_on_its_utc_day(midnight_session) -> None:
    # Stamped 2026/11/07 00:38:52 in Paris: still the 6th in UTC.
    assert midnight_session["942779641"].startTime == _utc(2026, 11, 6, 23, 38, 52)  # was 2026-11-07 05:38:52


def test_the_offset_comes_from_the_file_name_whatever_the_machine_zone() -> None:
    first_hand = datetime.datetime(2026, 9, 23, 21, 46, 21)  # Paris summer time, UTC+2
    offset = hand_time_offset("GG20260923-1946 - RushAndCash4734899 - 0.1 - 0.25 - 6max.txt", first_hand)
    local = first_hand.astimezone().utcoffset()

    # None means "this computer's zone", which is right only when it is UTC+2 then.
    assert offset == datetime.timedelta(hours=2) or (offset is None and local == datetime.timedelta(hours=2))


def test_a_half_hour_zone_is_kept() -> None:
    first_hand = datetime.datetime(2026, 11, 6, 23, 17, 5)  # India, UTC+5:30
    offset = hand_time_offset("GG20261106-1747 - RushAndCash1 - 0.05 - 0.1 - 6max.txt", first_hand)
    local = first_hand.astimezone().utcoffset()

    assert offset == datetime.timedelta(hours=5, minutes=30) or (
        offset is None and local == datetime.timedelta(hours=5, minutes=30)
    )


def test_without_a_gg_file_name_the_local_zone_is_used() -> None:
    assert hand_time_offset("hands.txt", datetime.datetime(2026, 11, 6, 18, 0)) is None
    assert hand_time_offset("GG20261106-1747 - x.txt", None) is None


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="needs time.tzset to switch the process zone")
def test_without_a_gg_file_name_hands_follow_this_computers_zone(monkeypatch) -> None:
    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    try:
        hands = _parse(CASHOUT_SESSION)  # the repository name: nothing to read the zone from
        assert hands["942724589"].startTime == _utc(2026, 11, 6, 20, 51, 6)
    finally:
        monkeypatch.undo()
        time.tzset()


# --- EV Cashout -------------------------------------------------------------


def test_a_cashed_out_loser_is_paid_the_cash_out(cashout_session) -> None:
    # 28ee072e cashes out on the turn, loses the pot, "Receives Cashout ($6.72)".
    hand = cashout_session["942724589"]
    players = _stats(hand)

    assert hand.cashOutAmounts == {"28ee072e": Decimal("6.72")}
    assert players["28ee072e"]["totalProfit"] == 672 - 503  # was -503, the stack put in
    assert players["28ee072e"]["isCashOut"] is True
    # The pot is the winner's alone, as the summary says.
    assert players["a7175c42"]["winnings"] == 971


def test_a_cashed_out_winner_keeps_the_cash_out_not_the_pot(midnight_session) -> None:
    # 43791fcd cashes out on the flop and wins: "collected $20.85 from pot",
    # then "Pays Cashout Risk ($3.89)". They take home 16.96 for a 10.00 stake.
    hand = midnight_session["942779641"]
    players = _stats(hand)

    assert hand.cashOutAmounts == {"43791fcd": Decimal("16.96")}
    assert hand.cashOutFees == {}  # the risk is not a fee
    assert players["43791fcd"]["winnings"] == 1696
    assert players["43791fcd"]["totalProfit"] == 696  # was 1085, the risk counted as won
    assert players["43791fcd"]["isCashOut"] is True
    assert players["Hero"]["totalProfit"] == -1000


def test_a_cash_out_won_over_several_pots_adds_them_up(midnight_session) -> None:
    # 30d32bac collects $0.87 and $1.73, then pays a $0.12 risk.
    hand = midnight_session["942820056"]
    assert hand.cashOutAmounts == {"30d32bac": Decimal("2.48")}


# --- Cash Drop --------------------------------------------------------------


def test_a_cash_drop_is_part_of_the_pot(cashout_session) -> None:
    # "Cash Drop to Pot : total $1": dfa53b9e collects 1.27 of a 1.35 pot built
    # from 0.35 of blinds and calls and the 1.00 drop.
    hand = cashout_session["942726142"]
    hand.totalPot()
    paid = sum(hand.pot.committed.values()) + sum(hand.pot.common.values()) + hand.pot.stp

    assert hand.pot.stp == Decimal("1")
    assert paid == hand.totalpot == Decimal("1.35")  # paid was 0.35
    assert paid == hand.totalcollected + hand.rake
    assert _stats(hand)["dfa53b9e"]["totalProfit"] == 127 - 10


# --- Run it twice -----------------------------------------------------------


@pytest.mark.skipif(derived_stats_module.pokereval is None, reason="requires the native poker-eval engine")
def test_a_hand_run_twice_keeps_its_rake(midnight_session) -> None:
    # $0.30 rake + $0.15 jackpot, taken from a pot run twice.
    hand = midnight_session["942820423"]
    players = _stats(hand)

    assert hand.rake == Decimal("0.45")  # was 0
    assert sum(p["rake"] for p in players.values()) == 45  # was 0
