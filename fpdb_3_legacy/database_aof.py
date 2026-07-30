"""Persistence for structured All-in or Fold decisions and analyses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.aof_ranges import ActionObservation, RangeObservation
from fpdb_3_legacy.autonotes_aof import AOF_CLASSIFIER_VERSION, KNOWN_BACKEND, KNOWN_BACKEND_VERSION


class DatabaseAofMixin:
    """Idempotent relational storage for AoF decisions and derived results."""

    sql: Any

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def get_last_insert_id(self, cursor: Any) -> int: ...

    def storeAofDecisions(self, decisions, doinsert: bool = False) -> list[int]:
        """Insert or refresh decisions, returning their persistent ids."""
        if not doinsert:
            return []
        find_q = self.sql.query["find_aof_decision"]
        insert_q = self.sql.query["store_aof_decision"]
        update_q = self.sql.query["update_aof_decision"]
        cursor = self.get_cursor()
        ids = []
        for decision in decisions or ():
            cursor.execute(find_q, decision.idempotency_key)
            existing = cursor.fetchone()
            values = _decision_values(decision)
            if existing:
                decision_id = int(existing[0])
                cursor.execute(update_q, (*values[2:-1], decision_id))
            else:
                cursor.execute(insert_q, values)
                decision_id = int(self.get_last_insert_id(cursor))
            ids.append(decision_id)
        return ids

    def storeAofDecisionAnalyses(self, analyses, doinsert: bool = False) -> list[int]:
        """Insert or refresh recalculable analysis rows."""
        if not doinsert:
            return []
        find_q = self.sql.query["find_aof_decision_analysis"]
        insert_q = self.sql.query["store_aof_decision_analysis"]
        update_q = self.sql.query["update_aof_decision_analysis"]
        cursor = self.get_cursor()
        ids = []
        for analysis in analyses or ():
            cursor.execute(find_q, analysis.idempotency_key)
            existing = cursor.fetchone()
            values = _analysis_values(analysis)
            if existing:
                analysis_id = int(existing[0])
                cursor.execute(update_q, (*values[6:], analysis_id))
            else:
                cursor.execute(insert_q, values)
                analysis_id = int(self.get_last_insert_id(cursor))
            ids.append(analysis_id)
        return ids

    def getAofDecisionScope(self, decision_id: int) -> tuple[int, str] | None:
        """Return the room and hand time that bound one range model."""
        cursor = self.get_cursor()
        cursor.execute(self.sql.query["get_aof_decision_scope"], (int(decision_id),))
        row = cursor.fetchone()
        return (int(row[0]), str(row[1])) if row else None

    def getAofDecisionSite(self, decision_id: int) -> int | None:
        """Compatibility accessor for callers needing only the room."""
        scope = self.getAofDecisionScope(decision_id)
        return scope[0] if scope is not None else None

    def getAofRangeObservations(
        self,
        site_id: int,
        category: str,
        role: str,
        active_opponents: int,
        before_hand_id: int,
        maximum_observations: int = 5_000,
    ) -> tuple[RangeObservation, ...]:
        """Load only historical revealed pockets for one range population."""
        cursor = self.get_cursor()
        cursor.execute(
            self.sql.query["get_aof_range_observations"],
            (
                int(before_hand_id),
                int(site_id),
                category,
                role,
                int(active_opponents),
                int(maximum_observations),
            ),
        )
        return tuple(
            RangeObservation(
                hand_id=int(row[0]),
                player_id=int(row[1]),
                site_id=int(row[2]),
                category=str(row[3]),
                role=str(row[4]),
                active_opponents=int(row[5]),
                hole_cards=str(row[6]),
                started_at=str(row[7]),
            )
            for row in cursor.fetchall()
        )

    def getAofActionObservations(
        self,
        site_id: int,
        category: str,
        role: str,
        active_opponents: int,
        before_hand_id: int,
        maximum_observations: int = 5_000,
    ) -> tuple[ActionObservation, ...]:
        """Load bounded historical fold/all-in answers for one table state."""
        cursor = self.get_cursor()
        cursor.execute(
            self.sql.query["get_aof_action_observations"],
            (
                int(before_hand_id),
                int(site_id),
                category,
                role,
                int(active_opponents),
                int(maximum_observations),
            ),
        )
        return tuple(
            ActionObservation(
                hand_id=int(row[0]),
                player_id=int(row[1]),
                site_id=int(row[2]),
                category=str(row[3]),
                role=str(row[4]),
                active_opponents=int(row[5]),
                decision=str(row[6]),
                started_at=str(row[7]),
            )
            for row in cursor.fetchall()
        )

    def getAofProfileStats(
        self,
        player_ids,
        category: str,
        classifier_version: int = AOF_CLASSIFIER_VERSION,
        backend_version: str = KNOWN_BACKEND_VERSION,
    ) -> dict[int, dict[str, int]]:
        """Return all objective AoF aggregates for a table in one query.

        Includes splash (one row per hand) by pre-aggregating in a subquery
        then using MAX() in the outer GROUP BY to avoid double-counting
        when the splash subquery's single row per player multiplies across
        the multiple decisions per player in AofDecisions.
        """
        ids = sorted({int(player_id) for player_id in player_ids})
        if not ids:
            return {}
        placeholder = self.sql.query["placeholder"]
        query = self.sql.query["get_aof_profile_stats"].replace(
            "<player_ids>",
            ", ".join(placeholder for _ in ids),
        )
        cursor = self.get_cursor()
        cursor.execute(
            query,
            (
                KNOWN_BACKEND,
                backend_version,
                KNOWN_BACKEND,
                backend_version,
                KNOWN_BACKEND,
                backend_version,
                category,
                *ids,
                category,
                int(classifier_version),
                *ids,
            ),
        )
        names = [description[0].lower() for description in cursor.description]
        return {
            int(row[0]): {name: int(value or 0) for name, value in zip(names[1:], row[1:], strict=True)}
            for row in cursor.fetchall()
        }


def _decision_values(decision: Any) -> tuple[Any, ...]:
    return (
        decision.hand_id,
        decision.player_id,
        decision.category,
        decision.decision,
        decision.role,
        decision.active_opponents,
        decision.pot_before,
        decision.amount_to_commit,
        decision.blind_committed,
        decision.cards_observable,
        decision.hole_cards,
        decision.flop_cards,
        decision.made_hand,
        decision.flush_draw,
        decision.straight_outs,
        decision.classifier_version,
    )


def _analysis_values(analysis: Any) -> tuple[Any, ...]:
    return (
        analysis.decision_id,
        analysis.backend,
        analysis.backend_version,
        analysis.range_model,
        analysis.range_version,
        analysis.analysis_version,
        analysis.equity_ppm,
        analysis.ev_chips,
        analysis.ev_bb_ppm,
        analysis.break_even_ppm,
        analysis.samples,
        analysis.stderr_ppm,
        analysis.status,
        analysis.error_text,
    )
