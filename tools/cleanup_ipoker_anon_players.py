"""Remove the placeholder players a live iPoker import used to invent.

iPoker anonymises the hands the hero was not dealt into, and the seat -> name
map that recovers their opponents is learned from the hands the hero did play.
Live import reaching the first observed hand of a session had neither, so every
seat fell back to "anon_<sessioncode>_<seat>" and those names were written to
Players. The importer no longer does that -- such a hand is skipped and comes
back with the real names on a later full import of the file -- but databases
already carry the rows it wrote.

This removes them: the hands in which every single player is a placeholder, the
rows that hang off those hands, and then the placeholder players themselves. A
placeholder still seated in a hand that is kept (which the importer never
produced, but a hand-edited database might) is reported and left alone, along
with its hands.

    python tools/cleanup_ipoker_anon_players.py              # report only
    python tools/cleanup_ipoker_anon_players.py --apply      # delete

Re-import the hand history files afterwards. The hands removed here are stored
again under their real opponents, because by now the session files hold the
named hands the seat map is learned from.
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

# What the importer generated, matched in full. "anon_hunter" is a screen name
# somebody may well be sitting under, and this tool deletes players: a prefix
# test would take a real one, and every hand they played, with it. The LIKE is
# only a cheap pre-filter -- "!" escapes the underscore, which is a LIKE
# wildcard, and ESCAPE is understood by PostgreSQL, MySQL and SQLite alike.
PLACEHOLDER_RE = re.compile(r"^anon_\d+_\d+$")
SELECT_PLACEHOLDERS = (
    "SELECT p.id, p.name, s.name FROM Players p "
    "JOIN Sites s ON s.id = p.siteId "
    "WHERE p.name LIKE 'anon!_%' ESCAPE '!' ORDER BY p.id"
)
SELECT_HANDS_OF_PLAYER = "SELECT DISTINCT handId FROM HandsPlayers WHERE playerId = %s"
SELECT_PLAYERS_OF_HAND = (
    "SELECT p.id, p.name FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId WHERE hp.handId = %s"
)
SELECT_HAND = "SELECT id, tableName, startTime FROM Hands WHERE id = %s"
SELECT_REMAINING_HANDS_OF_PLAYER = "SELECT COUNT(*) FROM HandsPlayers WHERE playerId = %s"

# Everything hanging off a hand, children before parents. Written out one
# statement per table rather than built from a table name, so what runs is
# exactly what is read here.
DELETE_BY_HAND = (
    ("HandsStove", "DELETE FROM HandsStove WHERE handId = %s"),
    ("HandsActions", "DELETE FROM HandsActions WHERE handId = %s"),
    ("HandsShowdown", "DELETE FROM HandsShowdown WHERE handId = %s"),
    ("HandsPots", "DELETE FROM HandsPots WHERE handId = %s"),
    ("HandsCashout", "DELETE FROM HandsCashout WHERE handId = %s"),
    ("AoFDecisions", "DELETE FROM AoFDecisions WHERE handId = %s"),
    ("Boards", "DELETE FROM Boards WHERE handId = %s"),
    ("RawHands", "DELETE FROM RawHands WHERE handId = %s"),
    ("PlayerAutoNotes", "DELETE FROM PlayerAutoNotes WHERE handId = %s"),
    ("HandsPlayers", "DELETE FROM HandsPlayers WHERE handId = %s"),
    ("Hands", "DELETE FROM Hands WHERE id = %s"),
)

# Everything keyed on a player, the caches included: a placeholder's HudCache
# row is what a statistic would otherwise still be read out of.
DELETE_BY_PLAYER = (
    ("HudCache", "DELETE FROM HudCache WHERE playerId = %s"),
    ("CardsCache", "DELETE FROM CardsCache WHERE playerId = %s"),
    ("PositionsCache", "DELETE FROM PositionsCache WHERE playerId = %s"),
    ("SessionsCache", "DELETE FROM SessionsCache WHERE playerId = %s"),
    ("TourneysCache", "DELETE FROM TourneysCache WHERE playerId = %s"),
    ("TourneysPlayers", "DELETE FROM TourneysPlayers WHERE playerId = %s"),
    ("AutoRates", "DELETE FROM AutoRates WHERE playerId = %s"),
    ("Backings", "DELETE FROM Backings WHERE playerId = %s"),
    ("PlayerAutoNotes", "DELETE FROM PlayerAutoNotes WHERE playerId = %s"),
    ("Players", "DELETE FROM Players WHERE id = %s"),
)


def _sql(statement: str, placeholder: str) -> str:
    """Adapt a statement to the backend's parameter marker ("%s" or "?")."""
    return statement.replace("%s", placeholder)


def survey(db) -> tuple[list, dict, list]:
    """Report the placeholders, the hands made only of them, and what is kept.

    Returns (placeholders, hands_by_id, kept), where `kept` holds the
    placeholders that share a hand with a real player: deleting those would take
    a hand with real information down with them, so they are left in place.
    """
    ph = db.sql.query["placeholder"]
    cursor = db.get_cursor()

    cursor.execute(SELECT_PLACEHOLDERS)
    placeholders = [(int(row[0]), row[1], row[2]) for row in cursor.fetchall() if PLACEHOLDER_RE.match(str(row[1]))]

    hands: dict[int, tuple] = {}
    kept: list[tuple[int, str, int]] = []
    for player_id, name, _site in placeholders:
        cursor.execute(_sql(SELECT_HANDS_OF_PLAYER, ph), (player_id,))
        for (hand_id,) in cursor.fetchall():
            if hand_id in hands:
                continue
            cursor.execute(_sql(SELECT_PLAYERS_OF_HAND, ph), (hand_id,))
            seated = cursor.fetchall()
            if any(not PLACEHOLDER_RE.match(str(seat_name)) for _pid, seat_name in seated):
                kept.append((player_id, name, int(hand_id)))
                continue
            cursor.execute(_sql(SELECT_HAND, ph), (hand_id,))
            hands[int(hand_id)] = cursor.fetchone()

    return placeholders, hands, kept


def delete(db, hand_ids: list[int], player_ids: list[int], *, commit: bool = True) -> dict[str, int]:
    """Delete the hands and then the players, in one transaction.

    ``commit=False`` runs the whole thing and rolls it back, which is the only
    way to find out what the real database says -- a foreign key nobody thought
    of, a table this schema does not have -- without writing to it.
    """
    ph = db.sql.query["placeholder"]
    cursor = db.get_cursor()
    removed: dict[str, int] = {}

    for hand_id in hand_ids:
        for table, statement in DELETE_BY_HAND:
            cursor.execute(_sql(statement, ph), (hand_id,))
            if cursor.rowcount and cursor.rowcount > 0:
                removed[table] = removed.get(table, 0) + cursor.rowcount

    for player_id in player_ids:
        cursor.execute(_sql(SELECT_REMAINING_HANDS_OF_PLAYER, ph), (player_id,))
        (remaining,) = cursor.fetchone()
        if remaining:
            # Should not happen: survey() only offers players whose every hand
            # is being removed. Refuse rather than orphan a hand.
            db.connection.rollback()
            msg = f"player {player_id} is still seated in {remaining} hand(s); nothing was deleted"
            raise SystemExit(msg)
        for table, statement in DELETE_BY_PLAYER:
            cursor.execute(_sql(statement, ph), (player_id,))
            if cursor.rowcount and cursor.rowcount > 0:
                removed[table] = removed.get(table, 0) + cursor.rowcount

    if commit:
        db.connection.commit()
    else:
        db.connection.rollback()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="HUD_config.xml to read the database from (default: the configured one)")
    parser.add_argument("--apply", action="store_true", help="delete; without it nothing is written")
    parser.add_argument(
        "--rehearse",
        action="store_true",
        help="run the deletion against the real database and roll it back, reporting what it did",
    )
    args = parser.parse_args()

    config = Config(file=args.config) if args.config else Config()
    db = Database(config)
    print(f"Database {db.database}@{db.host}\n")

    placeholders, hands, kept = survey(db)
    if not placeholders:
        print("No placeholder players found; nothing to clean up.")
        return 0

    print(f"{len(placeholders)} placeholder player(s):")
    for player_id, name, site in placeholders:
        print(f"  {player_id:>7}  {name}  ({site})")

    print(f"\n{len(hands)} hand(s) whose every player is a placeholder:")
    for hand_id, row in sorted(hands.items()):
        print(f"  {hand_id:>7}  {row[1]}  {row[2]}")

    if kept:
        print("\nLeft alone, because the hand also seats a real player:")
        for player_id, name, hand_id in kept:
            print(f"  player {player_id} ({name}) in hand {hand_id}")

    deletable = sorted({pid for pid, _n, _s in placeholders} - {pid for pid, _n, _h in kept})
    if not deletable:
        print("\nNothing can be removed without taking a real hand with it.")
        return 0

    if not (args.apply or args.rehearse):
        print(f"\nDry run. {len(deletable)} player(s) and {len(hands)} hand(s) would be removed. Re-run with --apply.")
        return 0

    removed = delete(db, sorted(hands), deletable, commit=args.apply)
    print("\nRemoved:" if args.apply else "\nWould remove (rolled back):")
    for table, count in sorted(removed.items()):
        print(f"  {count:>5}  {table}")
    if args.apply:
        print("\nRe-import the hand history files: those hands come back under their real opponents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
