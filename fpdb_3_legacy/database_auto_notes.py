"""Player auto-note storage and retrieval.

Split out of Database.py: these methods own the PlayerAutoNotes table, which
holds the notes the rule engine generates about players, keyed by rule and hand.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("db")


class DatabaseAutoNotesMixin:
    """Reads and writes the notes the auto-note rules generate.

    Mixed into Database, which provides the connection, the query catalogue and
    the pending-note buffer.
    """

    # Provided by Database.
    sql: Any
    panbulk: list[Any]

    if TYPE_CHECKING:

        def get_cursor(self, connect: bool = False) -> Any: ...

        def rollback(self) -> None: ...

    def storePlayerAutoNotes(self, notes, doinsert=False) -> None:
        """Persist generated player notes idempotently."""
        self.panbulk += list(notes or [])
        if not doinsert or not self.panbulk:
            return

        find_q = self.sql.query["find_player_auto_note"].replace("%s", self.sql.query["placeholder"])
        insert_q = self.sql.query["store_player_auto_note"].replace("%s", self.sql.query["placeholder"])
        update_q = self.sql.query["update_player_auto_note"].replace("%s", self.sql.query["placeholder"])
        c = self.get_cursor()

        try:
            for note in self.panbulk:
                evidence = json.dumps(note.evidence, sort_keys=True, default=str)
                key = (note.player_id, note.hand_id, note.rule_id, note.rule_version)
                c.execute(find_q, key)
                existing = c.fetchone()
                if existing:
                    c.execute(update_q, (note.note_text, evidence, existing[0]))
                else:
                    c.execute(
                        insert_q,
                        (
                            note.player_id,
                            note.hand_id,
                            note.rule_id,
                            note.rule_version,
                            note.note_text,
                            evidence,
                        ),
                    )
            self.panbulk = []
        except Exception:  # noqa: BLE001 - DB-API drivers expose different exception hierarchies.
            log.exception("Error storing generated player auto notes")
            raise

    def getPlayerAutoNoteCount(self, player_id: int) -> int:
        """Return the number of generated notes for a player."""
        try:
            q = self.sql.query["count_player_auto_notes"].replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.execute(q, (player_id,))
            result = c.fetchone()
            return int(result[0]) if result else 0
        except Exception:  # noqa: BLE001 - legacy DBs may not have the autonote table yet.
            log.warning("Unable to count auto notes for player %s", player_id, exc_info=True)
            self.rollback()
            return 0

    def getPlayerAutoNotes(
        self,
        player_id: int,
        limit: int | None = None,
        rule_set_ids: set[str] | None = None,
        rule_ids: set[str] | None = None,
    ) -> list[dict]:
        """Return generated notes for a player, newest first."""
        from fpdb_3_legacy.AutoNotes import (
            available_rule_id_to_rule_set_id,
            filter_generated_notes,
            format_note_evidence,
        )

        rule_to_rule_set = available_rule_id_to_rule_set_id()
        try:
            q = self.sql.query["get_player_auto_notes"].replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.execute(q, (player_id,))
            rows = c.fetchall()
        except Exception:  # noqa: BLE001 - legacy DBs may not have the autonote table yet.
            log.warning("Unable to load auto notes for player %s", player_id, exc_info=True)
            self.rollback()
            return []

        notes = []
        for row in rows:
            evidence = row[5] or "{}"
            try:
                evidence = json.loads(evidence)
            except (json.JSONDecodeError, TypeError):
                log.warning("Invalid auto-note evidence JSON for note %s", row[0], exc_info=True)
                evidence = {}
            notes.append(
                {
                    "id": row[0],
                    "handId": row[1],
                    "ruleSet": rule_to_rule_set.get(row[2], "unknown"),
                    "ruleId": row[2],
                    "ruleVersion": row[3],
                    "noteText": row[4],
                    "evidence": evidence,
                    "evidenceText": format_note_evidence(evidence),
                    "createdTs": row[6],
                    "updatedTs": row[7],
                    "siteHandNo": row[8],
                    "handStartTime": row[9],
                },
            )
        notes = filter_generated_notes(notes, rule_set_ids=rule_set_ids, rule_ids=rule_ids)
        if limit is not None:
            return notes[: max(0, int(limit))]
        return notes

    def searchPlayersWithAutoNotes(self, name_filter: str = "") -> list[dict]:
        """Return players with generated notes matching a name fragment."""
        try:
            q = self.sql.query["search_players_with_auto_notes"].replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.execute(q, (f"%{name_filter or ''}%",))
            return [{"playerId": row[0], "playerName": row[1], "siteId": row[2]} for row in c.fetchall()]
        except Exception:  # noqa: BLE001 - legacy DBs may not have the autonote table yet.
            log.warning("Unable to search players with auto notes", exc_info=True)
            self.rollback()
            return []

    def getRecentPlayerAutoNotes(
        self,
        limit: int = 200,
        player_filter: str = "",
        date_from: str | None = None,
        date_to: str | None = None,
        site_id: int | None = None,
        limit_type: str | None = None,
    ) -> list[dict]:
        """Return recent generated notes across all players."""
        from fpdb_3_legacy.AutoNotes import available_rule_id_to_rule_set_id, format_note_evidence

        rule_to_rule_set = available_rule_id_to_rule_set_id()
        try:
            q = self.sql.query["get_recent_player_auto_notes"].replace("%s", self.sql.query["placeholder"])
            q, params = self._auto_note_filter_query(
                q,
                player_filter=player_filter,
                date_from=date_from,
                date_to=date_to,
                site_id=site_id,
                limit_type=limit_type,
            )
            params.append(max(1, int(limit)))
            c = self.get_cursor()
            c.execute(q, tuple(params))
            rows = c.fetchall()
        except Exception:  # noqa: BLE001 - legacy DBs may not have the autonote table yet.
            log.warning("Unable to load recent player auto notes", exc_info=True)
            self.rollback()
            return []

        notes = []
        for row in rows:
            evidence = row[8] or "{}"
            try:
                evidence = json.loads(evidence)
            except (json.JSONDecodeError, TypeError):
                log.warning("Invalid auto-note evidence JSON for note %s", row[0], exc_info=True)
                evidence = {}
            notes.append(
                {
                    "id": row[0],
                    "playerId": row[1],
                    "playerName": row[2],
                    "handId": row[3],
                    "siteHandNo": row[4],
                    "ruleSet": rule_to_rule_set.get(row[5], "unknown"),
                    "ruleId": row[5],
                    "ruleVersion": row[6],
                    "noteText": row[7],
                    "evidence": evidence,
                    "evidenceText": format_note_evidence(evidence),
                    "createdTs": row[9],
                    "updatedTs": row[10],
                    "handStartTime": row[11],
                },
            )
        return notes

    def getAutoNotePlayerSummary(
        self,
        limit: int = 50,
        player_filter: str = "",
        date_from: str | None = None,
        date_to: str | None = None,
        site_id: int | None = None,
        limit_type: str | None = None,
    ) -> list[dict]:
        """Return generated-note counts by player."""
        try:
            q = self.sql.query["get_auto_note_player_summary"].replace("%s", self.sql.query["placeholder"])
            q, params = self._auto_note_filter_query(
                q,
                player_filter=player_filter,
                date_from=date_from,
                date_to=date_to,
                site_id=site_id,
                limit_type=limit_type,
            )
            params.append(max(1, int(limit)))
            c = self.get_cursor()
            c.execute(q, tuple(params))
            return [
                {
                    "playerId": row[0],
                    "playerName": row[1],
                    "noteCount": row[2],
                    "lastNoteTs": row[3],
                }
                for row in c.fetchall()
            ]
        except Exception:  # noqa: BLE001 - legacy DBs may not have the autonote table yet.
            log.warning("Unable to summarize auto notes by player", exc_info=True)
            self.rollback()
            return []

    def getAutoNoteRuleSummary(
        self,
        limit: int = 50,
        player_filter: str = "",
        date_from: str | None = None,
        date_to: str | None = None,
        site_id: int | None = None,
        limit_type: str | None = None,
    ) -> list[dict]:
        """Return generated-note counts by rule and derived rule set."""
        from fpdb_3_legacy.AutoNotes import available_rule_id_to_rule_set_id

        rule_to_rule_set = available_rule_id_to_rule_set_id()
        try:
            q = self.sql.query["get_auto_note_rule_summary"].replace("%s", self.sql.query["placeholder"])
            q, params = self._auto_note_filter_query(
                q,
                player_filter=player_filter,
                date_from=date_from,
                date_to=date_to,
                site_id=site_id,
                limit_type=limit_type,
            )
            params.append(max(1, int(limit)))
            c = self.get_cursor()
            c.execute(q, tuple(params))
            return [
                {
                    "ruleId": row[0],
                    "ruleSet": rule_to_rule_set.get(row[0], "unknown"),
                    "noteCount": row[1],
                }
                for row in c.fetchall()
            ]
        except Exception:  # noqa: BLE001 - legacy DBs may not have the autonote table yet.
            log.warning("Unable to summarize auto notes by rule", exc_info=True)
            self.rollback()
            return []

    def _auto_note_filter_query(
        self,
        query: str,
        player_filter: str = "",
        date_from: str | None = None,
        date_to: str | None = None,
        site_id: int | None = None,
        limit_type: str | None = None,
    ) -> tuple[str, list[Any]]:
        placeholder = self.sql.query["placeholder"]
        filters: list[str] = []
        params: list[Any] = []
        if player_filter:
            filters.append(f"lower(p.name) like lower({placeholder})")
            params.append(f"%{player_filter}%")
        if date_from:
            filters.append(f"h.startTime >= {placeholder}")
            params.append(f"{date_from} 00:00:00")
        if date_to:
            filters.append(f"h.startTime <= {placeholder}")
            params.append(f"{date_to} 23:59:59")
        if site_id is not None:
            filters.append(f"g.siteId = {placeholder}")
            params.append(site_id)
        if limit_type:
            filters.append(f"g.limitType = {placeholder}")
            params.append(limit_type)
        if not filters:
            return query, params
        return query.replace("/*AUTONOTE_FILTERS*/", " where " + " and ".join(filters)), params

    def playerHasNotes(self, player_id: int) -> bool:
        """Return true when a player has manual or generated notes."""
        try:
            q = self.sql.query["player_has_any_notes"].replace("%s", self.sql.query["placeholder"])
            c = self.get_cursor()
            c.execute(q, (player_id, player_id))
            result = c.fetchone()
            return bool(result and result[0])
        except Exception:  # noqa: BLE001 - fall back to manual comments on legacy DBs.
            log.debug("Generated auto-note lookup failed for player %s", player_id, exc_info=True)
            self.rollback()
            try:
                q = self.sql.query["get_player_comment"].replace("%s", self.sql.query["placeholder"])
                c = self.get_cursor()
                c.execute(q, (player_id,))
                result = c.fetchone()
                return bool(result and result[0])
            except Exception:  # noqa: BLE001 - DB-API drivers expose different exception hierarchies.
                log.warning("Unable to check manual notes for player %s", player_id, exc_info=True)
                self.rollback()
                return False
