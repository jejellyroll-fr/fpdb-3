"""iPoker lost uncalled bets, and mistook a raised blind level for dead money.

Both defects unbalanced the hand: what players put in no longer matched what
came out as winnings plus rake. On the local bwin corpus (289 hands) money
conservation was 16% and is 100% with these two fixes.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from fpdb_3_legacy.Configuration import Config
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.iPoker.base import iPoker

# Level 15/30, while the session header (and so the gametype) opened at 10/20.
# The small blind folds, so only 15 of the 30 big blind is ever called: the rest
# has to go back to its owner.
WALK_AT_A_RAISED_LEVEL = """<?xml version="1.0" encoding="utf-8"?>
<session sessioncode="5867402179">
 <general>
  <client_version>26.1.1.31</client_version>
  <mode>real</mode>
  <gametype>Holdem NL</gametype>
  <tablename>1193390834 Twister, 5867402179</tablename>
  <smallblind>10</smallblind>
  <bigblind>20</bigblind>
  <duration>00:03:01</duration>
  <gamecount>1</gamecount>
  <startdate>2026-07-11 16:17:00</startdate>
  <currency>EUR</currency>
  <nickname>jejesat76</nickname>
  <tournamentcode>5867402178</tournamentcode>
  <tournamentname>Twister</tournamentname>
  <place>2</place>
  <buyin>0€ + 0,02€ + 0,23€</buyin>
  <totalbuyin>0,25€</totalbuyin>
  <win>0€</win>
  <tablesize>3</tablesize>
 </general>
 <game gamecode="9014087509">
  <general>
   <startdate>2026-07-11 16:18:05</startdate>
   <smallblind>15</smallblind>
   <bigblind>30</bigblind>
   <players>
    <player bet="30" chips="1060" dealer="0" name="GTS64" seat="3" win="30"/>
    <player bet="15" chips="440" dealer="1" name="jejesat76" seat="6" win="0"/>
   </players>
  </general>
  <round no="0">
   <action no="1" player="jejesat76" sum="15" type="1"/>
   <action no="2" player="GTS64" sum="30" type="2"/>
  </round>
  <round no="1">
   <cards player="GTS64" type="Pocket">X X</cards>
   <cards player="jejesat76" type="Pocket">S9 H4</cards>
   <action no="3" player="jejesat76" sum="0" type="0"/>
  </round>
 </game>
</session>"""


@pytest.fixture(scope="module")
def isolated_config():
    """A config whose database is a throwaway SQLite file.

    Parsing an iPoker *tournament* hand stores its TourneySummary, so a bare
    ``Config()`` made these tests write into whatever database the user has
    configured - their real one.
    """
    config = Config()
    db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    db_file.close()
    params = config.get_db_parameters().copy()
    params.update(
        {
            "db-backend": Database.SQLITE,
            "db-server": "sqlite",
            "db-databaseName": db_file.name,
            "db-host": "",
            "db-user": "",
            "db-password": "",
        },
    )
    config.get_db_parameters = lambda: params
    database = Database(config)
    database.recreate_tables()
    database.close_connection()
    yield config
    Path(db_file.name).unlink(missing_ok=True)


@pytest.fixture
def walk_hand(isolated_config, tmp_path):
    path = tmp_path / "5867402179.xml"
    path.write_text(WALK_AT_A_RAISED_LEVEL, encoding="utf-8")
    return iPoker(config=isolated_config, in_path=str(path), autostart=True).getProcessedHands()[0]


def test_a_raised_blind_level_is_not_dead_money(walk_hand) -> None:
    """A 30 big blind at level 15/30 is a plain blind, not blind + dead.

    gametype keeps the level the table opened at (10/20), so comparing the post
    against it made every later level look oversized and booked part of it as
    dead money.
    """
    kinds = {a[1] for a in walk_hand.actions["BLINDSANTES"]}

    assert "both" not in kinds
    assert kinds == {"small blind", "big blind"}
    assert sum(walk_hand.pot.common.values()) == 0  # nothing landed in dead money


def test_the_uncalled_part_of_a_walk_is_returned(walk_hand) -> None:
    # 30 posted, only 15 called: 15 comes back.
    walk_hand.totalPot()

    assert walk_hand.pot.returned["GTS64"] == Decimal("15")
    assert walk_hand.pot.committed["GTS64"] == Decimal("15")


def test_the_hand_balances(walk_hand) -> None:
    walk_hand.totalPot()
    paid = sum(walk_hand.pot.committed.values()) + sum(walk_hand.pot.common.values())
    out = sum(walk_hand.collectees.values()) + Decimal(str(walk_hand.rake or 0))

    assert paid == out == Decimal("30")


def test_the_tournament_summary_is_stored_with_its_game_category(isolated_config, walk_hand) -> None:
    """TourneyTypes.category/limitType are NOT NULL.

    The summary was built with the TourneySummary defaults (None), so the insert
    died with "Column 'category' cannot be null" on MySQL/PostgreSQL - and the
    error propagated out of the summary code into the parse, making iPoker
    tournament hands unimportable on those backends.
    """
    database = Database(isolated_config)  # kept alive: dropping it closes the connection
    cursor = database.get_cursor()
    cursor.execute("SELECT category, limitType FROM TourneyTypes")
    categories = cursor.fetchall()
    database.close_connection()

    assert (walk_hand.gametype["category"], walk_hand.gametype["limitType"]) in [tuple(row) for row in categories]
    assert all(row[0] and row[1] for row in categories)


def test_ring_hand_rake_is_the_money_the_room_kept(isolated_config) -> None:
    """A ring hand with no rakeamount attribute still has its rake derived.

    The regression file puts 13.50 in and pays 13.10 out; the 0.40 difference is
    the rake. Pre-setting totalpot from the winnings hid it and reported 0.
    """
    hand_file = Path("regression-test-files/cash/iPoker/Flop/6+Holdem-EUR-0.25-0.50-201702.txt")
    hand = iPoker(config=isolated_config, in_path=str(hand_file), autostart=True).getProcessedHands()[0]
    hand.totalPot()

    assert hand.rake == Decimal("0.40")
    assert hand.totalpot == Decimal("13.50")
