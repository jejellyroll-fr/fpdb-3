#!/usr/bin/env python3
"""Backfill structured All-in or Fold decisions from imported hands.

The cursor is the last committed Hands.id. Runs are safe to repeat because the
database key is ``(handId, playerId, classifierVersion)``; ``--start-after``
allows an operator to resume without rescanning older hands.
"""

from __future__ import annotations

import argparse
from typing import Any

from fpdb_3_legacy import Configuration, Database
from fpdb_3_legacy.autonotes_aof import AOF_CATEGORIES, AofDecision, extract_decisions
from fpdb_3_legacy.backfill_autonotes import load_hand_from_database


def _hand_ids_after(db: Any, after_id: int, limit: int) -> list[int]:
    placeholder = db.sql.query["placeholder"]
    # The categories come from the ruleset registry rather than a literal, so a
    # newly registered variant is backfilled without editing this query. They
    # are still parameter-bound, not interpolated into the SQL text.
    categories = sorted(AOF_CATEGORIES)
    category_placeholders = ", ".join([placeholder] * len(categories))
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT H.id FROM Hands H "
        "JOIN Gametypes G ON H.gametypeId=G.id "
        f"WHERE H.id>{placeholder} AND G.category IN ({category_placeholders}) "
        f"ORDER BY H.id ASC LIMIT {placeholder}",
        (int(after_id), *categories, int(limit)),
    )
    return [int(row[0]) for row in cursor.fetchall()]


def backfill_database(
    *,
    db: Any | None = None,
    config_file: str = "HUD_config.xml",
    commit: bool = False,
    batch_size: int = 100,
    limit: int | None = None,
    start_after: int = 0,
    status_callback=None,
) -> dict[str, int]:
    """Scan AoF hands in ascending id order and persist decisions by batch."""
    owns_db = db is None
    if owns_db:
        config = Configuration.Config(file=config_file)
        db = Database.Database(config)
    assert db is not None
    if hasattr(db, "ensure_feature_tables"):
        db.ensure_feature_tables()

    stats = {
        "hands": 0,
        "matched_hands": 0,
        "decisions": 0,
        "observable": 0,
        "last_hand_id": int(start_after),
    }
    batch_size = max(1, int(batch_size))
    remaining = None if limit is None else max(0, int(limit))
    try:
        while remaining is None or remaining > 0:
            fetch_size = batch_size if remaining is None else min(batch_size, remaining)
            hand_ids = _hand_ids_after(db, stats["last_hand_id"], fetch_size)
            if not hand_ids:
                break
            pending = _read_batch(db, hand_ids, stats)
            if commit:
                try:
                    db.storeAofDecisions(pending, doinsert=True)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            if status_callback:
                status_callback(
                    f"AoF hands={stats['hands']} decisions={stats['decisions']} last_hand_id={stats['last_hand_id']}",
                )
            if remaining is not None:
                remaining -= len(hand_ids)
        return stats
    finally:
        if owns_db:
            db.close_connection()


def _read_batch(db: Any, hand_ids: list[int], stats: dict[str, int]) -> list[AofDecision]:
    pending: list[AofDecision] = []
    for hand_id in hand_ids:
        stats["hands"] += 1
        hand = load_hand_from_database(db, hand_id)
        decisions = extract_decisions(hand) if hand is not None else []
        if decisions:
            stats["matched_hands"] += 1
            stats["decisions"] += len(decisions)
            stats["observable"] += sum(decision.cards_observable for decision in decisions)
            pending.extend(decisions)
        stats["last_hand_id"] = hand_id
    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill structured All-in or Fold decisions")
    parser.add_argument("--config", default="HUD_config.xml", help="FPDB configuration file")
    parser.add_argument("--commit", action="store_true", help="Write rows; the default is a dry run")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-after", type=int, default=0, help="Resume after this committed Hands.id")
    args = parser.parse_args(argv)
    stats = backfill_database(
        config_file=args.config,
        commit=args.commit,
        batch_size=args.batch_size,
        limit=args.limit,
        start_after=args.start_after,
        status_callback=print,
    )
    print(
        f"Scanned {stats['hands']} hands, produced {stats['decisions']} decisions "
        f"({stats['observable']} observable); last hand id {stats['last_hand_id']}.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
