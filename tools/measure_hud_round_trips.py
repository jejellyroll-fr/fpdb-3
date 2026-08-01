"""Measure how many database round trips the HUD makes per hand and per table.

Over a VPN a statement costs one network latency whatever the server does with
it, so what decides how the HUD feels is the *count*, which no CPU-time
benchmark reports. This imports a directory of regression hands into a throwaway
SQLite database, replays the sequence of Database calls HUD_main makes for one
dealt hand with N tables open -- modelling its TTLCaches, so the number is
statements that would reach the network rather than statements the code writes
-- and prints the profile.

    python tools/measure_hud_round_trips.py [--tables 12]

The round-trip count is a property of the code path rather than of the data, so
the small regression corpus answers the question as well as a season of real
history would, and parses reliably.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Must be set before Database opens a connection: that is where the counting
# wrapper is installed.
os.environ["FPDB_DB_PROFILE"] = "1"

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)

from fpdb_3_legacy import db_profile  # noqa: E402
from fpdb_3_legacy.Configuration import Config  # noqa: E402

HANDS_DIR = REPO / "regression-test-files" / "cash" / "Stars" / "Flop"
SITE = "PokerStars.COM"
DEFAULT_TABLES = 12
RTTS_MS = (1, 20, 40, 80)


def build_config(tmpdir: str) -> Config:
    """A config pointed at a throwaway SQLite database."""
    cfg = Config(file="HUD_config.xml")
    params = cfg.get_db_parameters()
    params.update(
        {
            "db-host": "localhost",
            "db-server": "sqlite",
            "db-backend": 4,
            "db-databaseName": str(Path(tmpdir) / "measure.sqlite3"),
            "db-path": "",
        },
    )
    cfg.get_db_parameters = lambda: params
    return cfg


def populate(cfg: Config):
    """Build a database with the regression hands imported into it.

    Returns:
        The database and the importer. The importer must be kept alive by the
        caller: its ``__del__`` disconnects ``importer.database``, which is the
        very database being returned here.
    """
    from fpdb_3_legacy.Database import Database
    from fpdb_3_legacy.Importer import Importer

    db = Database(cfg)
    db.recreate_tables()

    importer = Importer(None, {"threads": 1}, cfg, sql=db.sql)
    importer.database = db
    importer.setCallHud(False)
    importer.setMode("bulk")
    importer.addBulkImportImportFileOrDir(str(HANDS_DIR), site=SITE)
    importer.runImport()
    db.connection.commit()
    return db, importer


class HudReplay:
    """Replays HUD_main's per-batch database calls, TTLCaches included.

    Modelling the caches is what separates "statements the code issues" from
    "statements that reach the network", and only the second is the answer to
    how the HUD behaves over a VPN.
    """

    def __init__(self, db, hud_params, table_hands) -> None:
        self.db = db
        self.hud_params = hud_params
        self.table_hands = table_hands
        self._table_info: dict[int, object] = {}
        self._positions: dict[int, object] = {}

    def _table_info_for(self, hand_id):
        if hand_id not in self._table_info:
            self._table_info[hand_id] = self.db.get_table_info(hand_id)
        return self._table_info[hand_id]

    def _positions_for(self, hand_id):
        if hand_id not in self._positions:
            self._positions[hand_id] = self.db.get_hand_positions(hand_id)
        return self._positions[hand_id]

    def _stats_for(self, hand_id) -> None:
        self.db.init_hud_stat_vars(self.hud_params["hud_days"], self.hud_params["h_hud_days"])
        self.db.get_stats_from_hand(hand_id, "ring", self.hud_params, -1, 6)

    def batch(self, active_hand) -> None:
        """One drained batch: the table that dealt, then every other table."""
        with db_profile.scope("batch"):
            with db_profile.scope("hand"), db_profile.scope("update_hud"):
                self._table_info_for(active_hand)
                self._stats_for(active_hand)
                self._positions_for(active_hand)
                self.db.get_seat_players(active_hand)
                self.db.get_table_min_stack_bb(active_hand)
                self.db.get_cards(active_hand)
                self.db.get_common_cards(active_hand)

            # Every other open table, whose statistics HUD_main now fetches for
            # all of them at once (_batch_secondary_stats).
            others = self.table_hands[1:]
            with db_profile.scope("batched_stats"):
                self.db.init_hud_stat_vars(self.hud_params["hud_days"], self.hud_params["h_hud_days"])
                self.db.get_stats_from_hands(others, "ring", self.hud_params, -1, 6)
            for other_hand in others:
                with db_profile.scope("secondary_refresh"):
                    self._table_info_for(other_hand)
                    self._positions_for(other_hand)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", type=int, default=DEFAULT_TABLES, help="open tables to simulate")
    args = parser.parse_args()
    tables = max(1, args.tables)

    if not HANDS_DIR.is_dir():
        print(f"no hand histories at {HANDS_DIR}")
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = build_config(tmpdir)
        db, importer = populate(cfg)  # importer kept alive: see populate()

        c = db.connection.cursor()
        # Each open table shows its own last hand, so give every table one --
        # all at the same stake, because that is what multi-tabling is, and
        # because gametype is what decides whether tables can share a
        # statistics query. Drawing from the regression corpus at large would
        # give twelve different games, which no session ever looks like.
        c.execute(
            "SELECT gametypeId FROM Hands GROUP BY gametypeId ORDER BY COUNT(*) DESC LIMIT 1",
        )
        row = c.fetchone()
        if row is None:
            print("no hands imported")
            return 1
        c.execute("SELECT id FROM Hands WHERE gametypeId = ? ORDER BY id DESC LIMIT ?", (row[0], tables))
        table_hands = [r[0] for r in c.fetchall()]
        if len(table_hands) < tables:
            print(f"only {len(table_hands)} hands at the busiest stake, need {tables}")
            return 1

        db.get_hero_player_ids()
        replay = HudReplay(db, cfg.get_hud_ui_parameters(), table_hands)
        profile = db_profile.get_profile()

        # The first batch pays the cache misses; the ones after it are what the
        # player actually lives with, hand after hand.
        profile.reset()
        replay.batch(table_hands[0])
        cold = profile.by_scope["batch"].queries

        profile.reset()
        for _ in range(3):
            replay.batch(table_hands[0])
        steady = profile.by_scope["batch"].queries_per_entry

        print()
        print(f"=== one hand dealt, {tables} tables open ===")
        print(f"first batch (cold caches): {cold} statements")
        print(profile.report())
        print()
        print(f"steady state: {steady:.0f} statements per hand dealt")
        for rtt in RTTS_MS:
            print(f"  at {rtt:>3}ms RTT: {steady * rtt / 1000:.2f}s per hand on the UI thread")

        db.disconnect()
        del importer
    return 0


if __name__ == "__main__":
    sys.exit(main())
