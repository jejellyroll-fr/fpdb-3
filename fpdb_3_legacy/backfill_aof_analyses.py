#!/usr/bin/env python3
"""Backfill All-in or Fold analyses for decisions that lack them.

Scans decisions whose analysis results are missing for the current backend
version, submits each hand to the async analysis coordinator, and drains the
queue.  The coordinator owns persistence so the script only coordinates reads
and submission -- it does not write directly.

Safe to replay: the analysis pipeline is idempotent (unique key on
(decisionId, backend, backendVersion, rangeModel, rangeVersion,
analysisVersion)).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from fpdb_3_legacy import Configuration, Database
from fpdb_3_legacy.aof_equity import KNOWN_BACKEND, KNOWN_BACKEND_VERSION, KnownCardsAnalysisCoordinator
from fpdb_3_legacy.autonotes_aof import extract_decisions
from fpdb_3_legacy.equity import EquityEngine
from fpdb_3_legacy.equity_async import AsyncEquityService


def _hand_ids_with_missing_analyses(db: Any, after_id: int, limit: int) -> list[int]:
    placeholder = db.sql.query["placeholder"]
    query = (
        "SELECT DISTINCT D.handId FROM AofDecisions D "
        "LEFT JOIN AofDecisionAnalyses A "
        "  ON A.decisionId=D.id AND A.backend=%s AND A.backendVersion=%s "
        " AND A.rangeModel='actual_known' AND A.rangeVersion=1 AND A.analysisVersion=1 "
        f"WHERE D.handId>{placeholder} AND A.id IS NULL "
        "  AND D.decision='allin' AND D.cardsObservable=TRUE "
        f"ORDER BY D.handId ASC LIMIT {placeholder}"
    )
    cursor = db.get_cursor()
    cursor.execute(
        query.replace("%s", placeholder),
        (KNOWN_BACKEND, KNOWN_BACKEND_VERSION, int(after_id), int(limit)),
    )
    return [int(row[0]) for row in cursor.fetchall()]


def _submit_hand(
    db: Any,
    coordinator: KnownCardsAnalysisCoordinator,
    hand_id: int,
    stats: dict[str, int],
) -> None:
    hand = _load_hand(db, hand_id)
    if hand is None:
        return
    decisions = extract_decisions(hand)
    if not decisions:
        return
    decision_ids = db.storeAofDecisions(decisions, doinsert=True)
    if coordinator.submit_hand(hand, decisions, decision_ids) is not None:
        stats["hands_submitted"] += 1
        stats["decisions"] += len(decisions)
    db.commit()


def backfill_analyses(
    *,
    db: Any | None = None,
    config_file: str = "HUD_config.xml",
    commit: bool = False,
    batch_size: int = 50,
    limit: int | None = None,
    start_after: int = 0,
    status_callback: Callable[[str], None] | None = None,
    db_factory: Callable[[], Any] | None = None,
    engine: EquityEngine | None = None,
) -> dict[str, int]:
    """Submit hands with missing analyses to the async analysis pipeline.

    When *commit* is *False* the method is a scan-only dry run that counts
    eligible hands and decisions without writing anything.
    """
    config = Configuration.Config(file=config_file)
    owns_db = db is None
    if owns_db:
        db = Database.Database(config)
    assert db is not None
    if hasattr(db, "ensure_feature_tables"):
        db.ensure_feature_tables()

    coordinator: KnownCardsAnalysisCoordinator | None = None
    if commit:
        factory = db_factory or (lambda: Database.Database(config))
        coordinator = KnownCardsAnalysisCoordinator(
            AsyncEquityService(engine or EquityEngine()),
            db_factory=factory,
        )

    stats = _run_batches(
        db=db,
        coordinator=coordinator,
        batch_size=batch_size,
        limit=limit,
        start_after=start_after,
        status_callback=status_callback,
    )

    if coordinator is not None:
        coordinator.close()
    if owns_db:
        db.close_connection()
    return stats


def _run_batches(
    db: Any,
    coordinator: KnownCardsAnalysisCoordinator | None,
    batch_size: int,
    limit: int | None,
    start_after: int,
    status_callback: Callable[[str], None] | None,
) -> dict[str, int]:
    stats = {
        "hands": 0,
        "hands_submitted": 0,
        "decisions": 0,
        "last_hand_id": int(start_after),
    }
    batch_size = max(1, int(batch_size))
    remaining = None if limit is None else max(0, int(limit))
    while remaining is None or remaining > 0:
        fetch_size = batch_size if remaining is None else min(batch_size, remaining)
        hand_ids = _hand_ids_with_missing_analyses(db, int(stats["last_hand_id"]), fetch_size)
        if not hand_ids:
            break
        for hand_id in hand_ids:
            stats["hands"] += 1
            stats["last_hand_id"] = hand_id
            if coordinator is not None:
                _submit_hand(db, coordinator, hand_id, stats)
        if status_callback:
            status_callback(
                f"submitted {stats['hands_submitted']}/{stats['hands']} hands "
                f"({stats['decisions']} decisions) "
                f"last_hand_id={stats['last_hand_id']}",
            )
        if remaining is not None:
            remaining -= len(hand_ids)
    return stats


def _load_hand(db: Any, hand_id: int) -> Any:
    from fpdb_3_legacy.backfill_autonotes import load_hand_from_database

    return load_hand_from_database(db, hand_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill AoF analyses for decisions that lack them",
    )
    parser.add_argument("--config", default="HUD_config.xml", help="FPDB configuration file")
    parser.add_argument("--commit", action="store_true", help="Persist analyses; default is a dry run")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-after", type=int, default=0, help="Resume after this hand id")
    args = parser.parse_args(argv)
    stats = backfill_analyses(
        config_file=args.config,
        commit=args.commit,
        batch_size=args.batch_size,
        limit=args.limit,
        start_after=args.start_after,
        status_callback=print,
    )
    print(
        f"Scanned {stats['hands']} hands, submitted {stats['hands_submitted']} "
        f"({stats['decisions']} decisions) for analysis; "
        f"last hand id {stats['last_hand_id']}.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
