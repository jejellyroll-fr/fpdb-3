"""The database side of the HUD: batched reads, deferred hands and outage recovery.

One of the mixins HudMain (HUD_main.pyw) is built from. What it calls on the
other mixins is declared, for the type checker, on HudMainBase in hud_main_base.
"""

import contextlib

from PySide6.QtCore import QTimer

from fpdb_3_legacy import db_profile
from fpdb_3_legacy.db_reconnect import is_connection_lost
from fpdb_3_legacy.hud_main_base import HudMainBase, log
from fpdb_3_legacy.hud_read_service import (
    HudBatchReadRequest,
    HudBatchSnapshot,
    HudReplayDatabase,
    HudTableReadContext,
)
from fpdb_3_legacy.hud_workers import DbRecoveryWorker
from fpdb_3_legacy.table_info import TableInfo

# A long outage must not grow memory without bound, but dropping every hand
# means a recovered HUD stays invisible until another hand happens to arrive.
# Keep a generous tail and reduce it to the latest hand per table once the
# database is available again and table identities can be queried safely.
MAX_DEFERRED_HANDS = 1000


MAX_PENDING_HANDS = 1000


DB_BATCH_RETRY_MS = 5000


DB_BATCH_RETRY_BACKOFF_MS = 30000


DB_BATCH_RETRY_BACKOFF_AFTER = 5



class HudMainDbMixin(HudMainBase):
    """Read hands from the database in batches and survive the database going away."""

    def handle_worker_error(self, error_message: str) -> None:
        """Handle errors from the ZMQ worker."""
        log.error("ZMQWorker encountered an error: %s", error_message)

    def note_db_error(self, exc: BaseException) -> bool:
        """Open the breaker if ``exc`` means the connection is gone.

        Returns:
            True when the database is now considered unavailable, so the caller
            can stop working on a hand it has no way of finishing.

        Database already reconnects and replays a query transparently; an error
        still reaching here means that failed too, and the link is genuinely
        down rather than merely interrupted.
        """
        if not is_connection_lost(self.db_connection.backend, exc):
            return False
        if getattr(self, "_db_worker", None) is not None:
            # Runtime SQL recovery belongs exclusively to HudReadWorker. The
            # Qt side holds only HudReplayDatabase, which cannot and must not
            # be handed to the legacy DbRecoveryWorker.
            log.error("Unexpected connection-style error from HUD replay data: %s", exc)
            return False
        if self._db_available:
            log.error("Database unreachable; HUD updates are paused until it returns (%s)", exc)
            self._db_available = False
            self._start_db_recovery()
        return True

    def _start_db_recovery(self) -> None:
        """Legacy synchronous-test recovery; runtime uses HudReadWorker."""
        if not hasattr(self.db_connection, "recover_connection"):
            log.error("Refusing legacy DB recovery for an in-memory HUD replay facade")
            return
        if self._db_recovery_worker is not None and self._db_recovery_worker.isRunning():
            return
        worker = DbRecoveryWorker(self.db_connection, parent=self)
        worker.recovered.connect(self._on_db_recovered)
        self._db_recovery_worker = worker
        worker.start()

    def _on_db_recovered(self) -> None:
        """Resume querying once the recovery thread has restored the link."""
        # Runs on the UI thread (queued signal), and the worker has already
        # returned from run(), so the connection is unowned at this point.
        self._db_available = True
        log.info("Database available again; HUD updates resumed")
        deferred, self._deferred_hands = self._deferred_hands, []
        if deferred:
            log.info("Replaying %d hand notification(s) deferred during the outage", len(deferred))
            self._pending_hands.extend(deferred)
            if not self._hand_batch_timer.isActive():
                self._hand_batch_timer.start()

    def _on_db_worker_ready(self, backend: int) -> None:
        """Resume submissions after the worker connected or reconnected."""
        recovered = not self._db_available
        self._db_backend = backend
        self._db_available = True
        if recovered:
            log.info("HUD database worker is ready; updates resumed")
        deferred, self._deferred_hands = self._deferred_hands, []
        if deferred:
            self._pending_hands.extend(deferred)
        if self._pending_hands and not self._db_batch_inflight and not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _on_db_worker_unavailable(self, message: str) -> None:
        """Open the UI-side breaker without touching the worker's connection."""
        if self._db_available:
            log.error("HUD database unavailable; updates remain responsive (%s)", message)
        else:
            log.debug("HUD database still unavailable: %s", message)
        self._db_available = False

    def _retry_hands(self, hand_ids: tuple[str, ...]) -> None:
        if self._shutdown_started:
            return
        for hand_id in hand_ids:
            with contextlib.suppress(ValueError):
                self._pending_hands.remove(hand_id)
            self._pending_hands.append(hand_id)
        if self._db_available and not self._db_batch_inflight and not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _on_db_batch_failed(self, request: HudBatchReadRequest, message: str) -> None:
        """Retry an ordinary timeout later while the Qt loop stays available."""
        self._db_batch_inflight = False
        self._db_consecutive_failures += 1
        retry_ms = (
            DB_BATCH_RETRY_BACKOFF_MS
            if self._db_consecutive_failures > DB_BATCH_RETRY_BACKOFF_AFTER
            else DB_BATCH_RETRY_MS
        )
        log.warning(
            "HUD database batch %d failed (%d consecutive failure(s)); "
            "the loading HUD stays visible and stats will retry in %d seconds: %s",
            request.sequence,
            self._db_consecutive_failures,
            retry_ms // 1000,
            message,
        )
        if self._db_consecutive_failures == DB_BATCH_RETRY_BACKOFF_AFTER + 1:
            log.error(
                "HUD database remains too slow after %d batches; reducing retries to every %d seconds",
                self._db_consecutive_failures,
                retry_ms // 1000,
            )
        QTimer.singleShot(retry_ms, lambda hands=request.hand_ids: self._retry_hands(hands))

    def _table_read_contexts(self) -> tuple[HudTableReadContext, ...]:
        contexts = []
        for temp_key, hud in list(self.hud_dict.items()):
            last_hand_id = self._last_processed_hands.get(temp_key)
            if not last_hand_id:
                continue
            table_info = self._last_table_info.get(temp_key) or self.cache.get(last_hand_id)
            if table_info is None:
                continue
            info = TableInfo.coerce(table_info)
            needs_mucked = any(type(aux).__module__.rsplit(".", 1)[-1] == "Mucked" for aux in hud.aux_windows)
            contexts.append(
                HudTableReadContext(
                    temp_key=temp_key,
                    last_hand_id=last_hand_id,
                    hud_params=dict(hud.hud_params),
                    poker_game=hud.poker_game,
                    game_type=info.game_type,
                    site_id=info.site_id,
                    num_seats=info.num_seats,
                    needs_mucked_data=needs_mucked,
                ),
            )
        return tuple(contexts)

    def _build_batch_request(self, hand_ids: list[str]) -> HudBatchReadRequest:
        self._db_batch_sequence += 1
        return HudBatchReadRequest(
            sequence=self._db_batch_sequence,
            hand_ids=tuple(hand_ids),
            hud_params=dict(self.hud_params),
            tables=self._table_read_contexts(),
        )

    def _on_db_snapshot(self, snapshot: HudBatchSnapshot) -> None:
        """Apply a database-free snapshot on the Qt thread."""
        if self._shutdown_started:
            return
        if snapshot.sequence < self._last_applied_sequence:
            return
        if snapshot.sequence == self._last_applied_sequence and snapshot.revision <= self._last_applied_revision:
            return
        if snapshot.sequence > self._last_applied_sequence:
            self._last_applied_sequence = snapshot.sequence
            self._last_applied_revision = -1
            self._db_progress_refreshed = set()
        self._last_applied_revision = snapshot.revision
        self.db_connection = HudReplayDatabase(snapshot, self._db_backend)
        self._prepared_hands = snapshot.hands
        if not snapshot.identity_only:
            self.hero = dict(snapshot.hero)
            self.hero_ids = dict(snapshot.hero_ids)

        for prepared in snapshot.hands.values():
            if prepared.table_info is None:
                continue
            self.cache[prepared.hand_id] = prepared.table_info
            self._hand_players[("seats", prepared.hand_id)] = prepared.seat_players
            self._hand_players[("positions", prepared.hand_id)] = prepared.positions

        if snapshot.identity_only:
            for hand_id in snapshot.primary_order:
                self._show_loading_hud(hand_id)
            return

        refreshed = set(self._db_progress_refreshed)
        apply_failed: list[str] = []
        failed = set(snapshot.failed_hand_ids)
        for hand_id in snapshot.primary_order:
            if hand_id in failed:
                continue
            try:
                served = self.read_stdin(hand_id)
            except Exception:
                log.exception("Error applying prepared HUD hand %s", hand_id)
                apply_failed.append(hand_id)
            else:
                if served is not None:
                    refreshed.add(served)
                    self._db_progress_refreshed.add(served)
                    applied = snapshot.hands.get(str(hand_id))
                    if applied is not None and applied.table_info is not None:
                        self._last_table_info[served] = applied.table_info

        if not snapshot.final:
            return

        self._db_batch_inflight = False
        self._db_consecutive_failures = 0
        # A secondary read that failed must leave that HUD's previous stats on
        # screen. Excluding it from the replay refresh prevents a missing
        # snapshot entry from looking like a legitimate empty result.
        unavailable_secondary = {
            context.temp_key
            for context in self._table_read_contexts()
            if str(context.last_hand_id) not in snapshot.hands
        }
        self._refresh_other_huds(refreshed | unavailable_secondary)
        self._report_batch_round_trips(len(snapshot.requested_hand_ids), len(self.hud_dict))

        retry_hands = tuple(dict.fromkeys((*snapshot.failed_hand_ids, *apply_failed)))
        if retry_hands:
            QTimer.singleShot(5000, lambda hands=retry_hands: self._retry_hands(hands))
        if self._pending_hands and self._db_available and not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()
        self._db_progress_refreshed = set()

    def _stop_db_recovery(self) -> None:
        """Stop the recovery thread, if one is running."""
        worker = getattr(self, "_db_recovery_worker", None)
        if worker is None:
            return
        self._db_recovery_worker = None
        with contextlib.suppress(RuntimeError):
            worker.stop()

    def _enqueue_hand(self, hand_id: str) -> None:
        """Hold a hand briefly so the tables dealing alongside it join the batch."""
        with contextlib.suppress(ValueError):
            self._pending_hands.remove(hand_id)
        self._pending_hands.append(hand_id)
        overflow = len(self._pending_hands) - MAX_PENDING_HANDS
        if overflow > 0:
            del self._pending_hands[:overflow]
            log.warning("HUD pending-hand queue reached %d; oldest notification(s) were dropped", MAX_PENDING_HANDS)
        if not self._hand_batch_timer.isActive():
            self._hand_batch_timer.start()

    def _defer_hands(self, hand_ids: list[str]) -> None:
        """Keep recent hand notifications until the recovery worker succeeds."""
        for hand_id in hand_ids:
            if not hand_id:
                continue
            # A duplicate notification should move to the end rather than use
            # two slots in the bounded outage queue.
            with contextlib.suppress(ValueError):
                self._deferred_hands.remove(hand_id)
            self._deferred_hands.append(hand_id)
        overflow = len(self._deferred_hands) - MAX_DEFERRED_HANDS
        if overflow > 0:
            del self._deferred_hands[:overflow]

    def _finish_read_batch(self) -> None:
        """Release the successful HUD read transaction and any pooled server slot."""
        if not self._db_available:
            # Recovery owns the connection as soon as the breaker opens.
            return
        try:
            self.db_connection.connection.rollback()
        except Exception as exc:
            if not self.note_db_error(exc):
                log.exception("Could not finish the HUD read transaction")

    def _latest_hand_per_table(self, hand_ids: list[str]) -> tuple[dict[str, str], list[str]]:
        """Reduce a batch to the last hand of each table.

        Processing an earlier hand of a table only to overwrite it with the
        next one is work nobody sees, and the HUD shows the latest hand either
        way. Hands whose table cannot be resolved are handed back untouched so
        they take the normal path and log what they normally log.
        """
        latest: dict[str, str] = {}
        unresolved: list[str] = []
        for index, hand_id in enumerate(hand_ids):
            table_info = self._get_table_info(hand_id)
            if table_info is None:
                unresolved.append(hand_id)
                if not self._db_available:
                    unresolved.extend(hand_ids[index + 1 :])
                    break
                continue
            info = TableInfo.coerce(table_info)
            latest[self._get_temp_key(info.game_type, info.tour_number, info.tab_number, info.table_name)] = hand_id
        return latest, unresolved

    def _drain_pending_hands(self) -> None:
        """Submit one batch without running a database call on the Qt thread."""
        worker = getattr(self, "_db_worker", None)
        if worker is None:
            # Narrow compatibility seam for focused legacy unit tests. Runtime
            # construction always installs HudReadWorker.
            self._drain_pending_hands_sync()
            return
        if self._db_batch_inflight:
            return
        pending, self._pending_hands = self._pending_hands, []
        if not pending:
            return
        if not self._db_available:
            self._defer_hands(pending)
            return
        request = self._build_batch_request(pending)
        self._db_batch_inflight = True
        worker.submit(request)

    def _drain_pending_hands_sync(self) -> None:
        """Process one batch of hands, then refresh every other HUD once.

        The refresh is what this exists for: it used to run per hand, so a
        round of twelve tables cost twelve refreshes of twelve HUDs. One batch
        means one refresh each.
        """
        pending, self._pending_hands = self._pending_hands, []
        if not pending:
            return
        if not self._db_available:
            self._defer_hands(pending)
            log.debug("Deferring %d pending hand(s): database unavailable", len(pending))
            return

        try:
            with db_profile.scope("batch"):
                latest, unresolved = self._latest_hand_per_table(pending)
                if not self._db_available:
                    self._defer_hands(pending)
                    log.warning("Deferring this batch: database went away during table lookup")
                    return
                log.debug("Draining %d hand(s) into %d table(s)", len(pending), len(latest))

                refreshed: set[str] = set()
                for hand_id in [*latest.values(), *unresolved]:
                    try:
                        with db_profile.scope("hand"):
                            served = self.read_stdin(hand_id)
                    except Exception as exc:
                        if self.note_db_error(exc):
                            self._defer_hands(pending)
                            log.warning("Deferring this batch: database went away while processing hand %s", hand_id)
                            return
                        log.exception("Error processing hand %s", hand_id)
                        with contextlib.suppress(Exception):
                            self.db_connection.connection.rollback()
                    else:
                        if served is not None:
                            refreshed.add(served)

                # Only the tables actually brought up to date are left out of the
                # statistics refresh; one that failed still needs it.
                self._refresh_other_huds(refreshed)
                if not self._db_available:
                    self._defer_hands(pending)
                    log.warning("Deferring this batch: database went away during the HUD refresh")
                    return
        finally:
            self._finish_read_batch()

        self._report_batch_round_trips(len(pending), len(self.hud_dict))

    def _report_batch_round_trips(self, hands: int, tables: int) -> None:
        """Log what this batch cost in statements, when profiling is on.

        Per batch rather than per process: what decides how the HUD feels is the
        cost of one round of hands with the tables the player actually has open,
        and that is the number a cumulative total hides.
        """
        if not db_profile.is_enabled():
            return
        profile = db_profile.get_profile()
        batch = profile.by_scope.get("batch")
        hand_scope = profile.by_scope.get("hand")
        if batch is None:
            return
        log.info(
            "Round trips: batch of %d hand(s) over %d table(s) -- %d statements in this run "
            "(running average %.1f per batch, %.1f per hand)",
            hands,
            tables,
            batch.queries - getattr(self, "_last_batch_queries", 0),
            batch.queries_per_entry,
            hand_scope.queries_per_entry if hand_scope else 0.0,
        )
        self._last_batch_queries = batch.queries
