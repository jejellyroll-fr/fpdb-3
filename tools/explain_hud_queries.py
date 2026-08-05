"""Run EXPLAIN (ANALYZE, BUFFERS) on the queries the HUD issues per hand.

The round-trip counter (tools/measure_hud_round_trips.py) answers how many
statements the HUD sends. This answers what each one costs once it arrives --
which only your own database, with your own volume of hands and your own
planner statistics, can say. Run it against the database your HUD actually
uses:

    python tools/explain_hud_queries.py                  # the configured database
    python tools/explain_hud_queries.py --hand 123456    # a specific hand

It reports, per query, the total time, the rows the planner expected against the
rows it got, and the buffers read. It then flags what usually matters:

  * sequential scans over the big tables (HudCache, HandsPlayers, Hands)
  * row estimates off by more than 10x, which is what makes a planner pick a
    nested loop over a hash join and lose an order of magnitude
  * blocks read from disk rather than cache

PostgreSQL only: EXPLAIN ANALYZE with buffer accounting is what makes this
worth running, and SQLite's EXPLAIN QUERY PLAN does not carry the same
information. Nothing is written; every statement runs inside a transaction that
is rolled back.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fpdb_3_legacy.Configuration import Config  # noqa: E402
from fpdb_3_legacy.Database import Database  # noqa: E402

# Tables where a sequential scan is worth knowing about; the small lookup
# tables (Gametypes, Sites) are supposed to be scanned.
BIG_TABLES = ("hudcache", "handsplayers", "hands", "players")

# How far a row estimate may be out before the plan is worth distrusting.
ESTIMATE_TOLERANCE = 10

DEFAULT_HUD_PARAMS = {
    "stat_range": "A",
    "agg_bb_mult": 1000,
    "seats_style": "A",
    "seats_cust_nums_low": 1,
    "seats_cust_nums_high": 10,
    "h_stat_range": "A",
    "h_agg_bb_mult": 1000,
    "h_seats_style": "A",
    "h_seats_cust_nums_low": 1,
    "h_seats_cust_nums_high": 10,
}


def latest_hand(db) -> int | None:
    c = db.get_cursor()
    c.execute("SELECT id FROM Hands ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    return row[0] if row else None


def hero_of(db, hand_id: int) -> int:
    """The hero's playerId, preferring one actually seated in ``hand_id``.

    The aggregate splits players into hero and villains with different filters,
    so a hero who is not at the table would explain a plan the HUD never runs.
    """
    c = db.get_cursor()
    c.execute(
        "SELECT p.id FROM Players p "
        "INNER JOIN HandsPlayers hp ON hp.playerId = p.id "
        "WHERE hp.handId = %s AND p.hero = TRUE LIMIT 1",
        (hand_id,),
    )
    row = c.fetchone()
    if row:
        return int(row[0])
    c.execute("SELECT id FROM Players WHERE hero = TRUE LIMIT 1")
    row = c.fetchone()
    return int(row[0]) if row else -1


def hud_queries(db, hand_id: int, hero_id: int):
    """The statements a single table's HUD refresh issues, with real parameters.

    Returns (name, sql, params) triples in the order the HUD sends them.
    """
    gameinfo = db.get_gameinfo_from_hid(hand_id)
    if gameinfo is None:
        msg = f"hand {hand_id} has no game info"
        raise SystemExit(msg)
    gametype_id = gameinfo["gametypeId"]
    placeholder = db.sql.query["placeholder"]

    aggregated = db._inject_hud_chipev_columns(db.sql.query["get_stats_from_hand_aggregated"])
    agg_params = (
        hand_id,
        hero_id,
        "0000000",
        DEFAULT_HUD_PARAMS["agg_bb_mult"],
        DEFAULT_HUD_PARAMS["agg_bb_mult"],
        gametype_id,
        0,
        10,
        hero_id,
        "0000000",
        DEFAULT_HUD_PARAMS["h_agg_bb_mult"],
        DEFAULT_HUD_PARAMS["h_agg_bb_mult"],
        gametype_id,
        0,
        10,
    )

    gameinfo_sql = db.sql.query["get_gameinfo_from_hid"].replace("%s", placeholder)
    return [
        ("get_stats_from_hand_aggregated", aggregated, agg_params),
        ("get_table_name", db.sql.query["get_table_name"], (hand_id,)),
        ("get_gameinfo_from_hid", gameinfo_sql, (hand_id,)),
        ("get_hand_1day_ago", db.sql.query["get_hand_1day_ago"], ()),
    ]


def explain(db, sql: str, params) -> list[str]:
    """Return the EXPLAIN (ANALYZE, BUFFERS) plan lines for one statement."""
    c = db.get_cursor()
    c.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql, params)
    return [row[0] for row in c.fetchall()]


def review(plan: list[str]) -> list[str]:
    """Pick out of a plan the things usually worth acting on."""
    findings = []
    for line in plan:
        lowered = line.lower()

        if "seq scan on" in lowered:
            table = lowered.split("seq scan on", 1)[1].strip().split()[0]
            if table in BIG_TABLES:
                findings.append(f"sequential scan over {table}: {line.strip()}")

        estimate = re.search(r"rows=(\d+).*?rows=(\d+)", line)
        if estimate and "actual" in lowered:
            expected, actual = int(estimate.group(1)), int(estimate.group(2))
            worse = max(expected, actual)
            better = max(min(expected, actual), 1)
            if worse / better > ESTIMATE_TOLERANCE:
                findings.append(f"row estimate off by {worse // better}x: {line.strip()}")

        read = re.search(r"Buffers:.*read=(\d+)", line)
        if read and int(read.group(1)) > 0:
            findings.append(f"{read.group(1)} blocks read from disk: {line.strip()}")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="HUD_config.xml to use")
    parser.add_argument("--hand", type=int, default=None, help="hand id to explain against")
    parser.add_argument("--plans", action="store_true", help="print the full plans, not just the findings")
    args = parser.parse_args()

    cfg = Config(file=args.config) if args.config else Config()
    db = Database(cfg)
    try:
        if db.backend != Database.PGSQL:
            print(f"This needs PostgreSQL; the configured backend is {db.get_backend_name()}.")
            return 1

        hand_id = args.hand or latest_hand(db)
        if hand_id is None:
            print("No hands in the database.")
            return 1

        hero_id = hero_of(db, hand_id)
        print(f"Explaining against hand {hand_id} (hero id {hero_id}) on {db.database}@{db.host}\n")

        all_findings = []
        for name, sql, params in hud_queries(db, hand_id, hero_id):
            plan = explain(db, sql, params)
            total = next((line for line in plan if line.startswith("Execution Time")), "")
            print(f"--- {name} {total}")
            if args.plans:
                for line in plan:
                    print(f"    {line}")
            findings = review(plan)
            for finding in findings:
                print(f"  ! {finding}")
            if not findings:
                print("  nothing to flag")
            print()
            all_findings.extend(findings)

        # Nothing here should have written anything, but EXPLAIN ANALYZE does
        # execute the statement, so end the transaction explicitly.
        db.rollback(force=True)

        print(f"{len(all_findings)} thing(s) flagged.")
        if any("hudcache" in f for f in all_findings):
            print(
                "\nHudCache showing up is expected to be the interesting one: the aggregate\n"
                "already uses hudcache_playerid_idx for the join. If rows are then removed\n"
                "by the gametype filter, inspect the hashed SubPlan: resolving the similar\n"
                "gametype ids in the application can turn that filter into an index condition.\n"
                "Measured plans show that removing `hc.gametypeId+0` alone does not fix it.",
            )
    finally:
        db.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
