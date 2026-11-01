"""Winamax live tables: the log's table updates and the seats read off the window.

One of the mixins HudMain (HUD_main.pyw) is built from. What it calls on the
other mixins is declared, for the type checker, on HudMainBase in hud_main_base.
"""

import contextlib
import time
from typing import Any

from PySide6.QtCore import QTimer

from fpdb_3_legacy import Hud
from fpdb_3_legacy.fast_fold_engine import (
    FastFoldEngine,
    build_seat_map,
)
from fpdb_3_legacy.hud_main_base import FAST_FOLD_POOL_PREFIX, HudMainBase, TableReadState, log


class HudMainWinamaxMixin(HudMainBase):
    """Follow Winamax tables from the client log and from the table windows."""

    def _read_window_slots(self, hud: Hud.Hud) -> dict[int, str] | None:
        """Read a table window's seats now, bypassing the per-hand cache.

        None when there is nothing to read from -- no resolver, or a HUD whose
        table has no title -- which the caller must not confuse with an empty
        table.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        table = getattr(hud, "table", None)
        title = getattr(table, "title", "") or ""
        if reader is None or not title:
            return None
        # The same two answers the per-hand path respects. Without them the idle
        # sweep kept walking another process's accessibility tree every
        # FF_IDLE_RECHECK_SECONDS, for the life of the session, on exactly the
        # clients the breaker exists to stop reading -- and for a table nobody
        # was even playing. Reported by Codex on the pull request.
        table_key = getattr(table, "key", None) or title
        reads = getattr(self, "_table_reads", {}).get(table_key)
        if not getattr(self, "_ax_reader_enabled", True) or (reads is not None and reads.gave_up):
            return None
        try:
            return reader.read_window(
                title,
                getattr(hud, "max", 6) or 6,
                window_id=getattr(table, "number", None),
            ) or {}
        except Exception:
            log.exception("Could not re-read the Fast-Fold window %r while sweeping idle tables", title)
            return None

    def _schedule_seat_wait_recheck(self, update: Any, elapsed: float) -> None:
        """Come back when the seat wait is up, once per hand and table.

        Only needed when the configured wait outlasts AX_RECHECK_DELAYS_MS. Below
        that, the rechecks already scheduled at hand start arrive after the
        deadline and this would be a second timer saying the same thing.

        The test is on the setting, not on what is left of it. Comparing the
        remaining time instead left a band just above the last recheck with no
        wakeup at all: at a 2000ms wait, a ring arriving at 600ms leaves 1400,
        which reads as "the rechecks have this" -- and they do not, because they
        all fire before 2000ms. Every later call inside the hand makes the same
        wrong judgement, so nothing looked again until the hand ended. Reported
        by Codex on the pull request.
        """
        if self._fast_fold_seat_wait_ms <= max(self.AX_RECHECK_DELAYS_MS):
            return
        remaining_ms = max(0, int(self._fast_fold_seat_wait_ms - elapsed * 1000))
        pending = self._ff_seat_wait_scheduled
        key = (update.pool, update.hand_id)
        if key in pending:
            return
        pending.add(key)
        if len(pending) > self.FF_SEAT_WAIT_MEMO_LIMIT:
            pending.clear()
            pending.add(key)
        QTimer.singleShot(remaining_ms, lambda pool=update.pool: self._recheck_window(pool))

    def _recheck_window(self, pool: str) -> None:
        """Re-run a table's live update once the client has had time to draw it."""
        reader = getattr(self, "winamax_log_reader", None)
        table = reader.get_table(pool) if reader is not None else None
        if table is not None:
            self._on_winamax_table_update(table)

    def _on_winamax_regular_table_update(self, update: Any) -> None:
        """Publish an observed Winamax street to the matching ordinary HUD.

        The application log contains explicit ``round flop/turn/river`` events.
        Imported histories arrive after the hand, so they cannot drive the HUD
        at the live decision. Pair the client's table index with its window;
        never send a street from one table to another merely because one HUD is
        open. Repeated action notifications within a street need no redraw.
        """
        if update.hand_over:
            self._retire_winamax_regular_hand(update)
            return
        street = getattr(update, "street", "preflop")
        if street not in ("preflop", "flop", "turn", "river"):
            return
        seen: dict[Any, tuple[Any, ...]] = getattr(self, "_winamax_regular_seen", {})
        self._winamax_regular_seen = seen
        # A hand can publish several meaningful snapshots on the same street:
        # the open, calls, and 3-bet all change the live pot context before the
        # flop. Folds also change the multiway situation postflop. Deduplicate
        # identical state, not merely repeated notifications for a street.
        signature: tuple[Any, ...] = (
            update.hand_id,
            str(street),
            int(getattr(update, "preflop_raises", 0) or 0),
            int(getattr(update, "preflop_calls", 0) or 0),
            int(getattr(update, "preflop_calls_after_raise", 0) or 0),
            str(getattr(update, "preflop_aggressor", "") or ""),
            tuple(sorted(getattr(update, "folded_players", ()))),
        )
        if seen.get(update.pool) == signature:
            return

        key = self._winamax_regular_hud_key(update)
        hud = self.hud_dict.get(key) if key is not None else None
        if hud is None or str(getattr(hud, "site", "")).casefold() != "winamax":
            if street != "preflop" and any(
                str(getattr(item, "site", "")).casefold() == "winamax"
                and not getattr(item, "is_fast_fold", False)
                for item in self.hud_dict.values()
            ):
                missed: set[tuple[Any, str]] = getattr(self, "_winamax_regular_unmatched", set())
                self._winamax_regular_unmatched = missed
                if signature not in missed:
                    missed.add(signature)
                    if len(missed) > 256:
                        missed.clear()
                    log.warning(
                        "Winamax live %s could not be attached to a HUD: table index=%s label=%r",
                        street, update.table_no, getattr(update, "table_label", ""),
                    )
            return
        if getattr(hud, "is_fast_fold", False):
            return

        from fpdb_3_legacy.winamax_live_log_reader import fpdb_hand_id

        hand_id = fpdb_hand_id(update.hand_id) or str(update.hand_id)
        if getattr(hud, "_winamax_live_hand_id", None) != hand_id:
            hud.live_state.clear()
            hud._winamax_live_hand_id = hand_id
        preflop_raises = int(getattr(update, "preflop_raises", 0) or 0)
        calls_after_raise = int(getattr(update, "preflop_calls_after_raise", 0) or 0)
        pot_type = getattr(update, "pot_type", "") or ""
        facing_action = None
        labels: tuple[str, ...] = ()
        if street == "preflop":
            # The resolver rules describe the pot before the action Hero faces:
            # one raise means an unopened pot facing a raise; two means a
            # single-raised pot facing a 3-bet. Winamax's pot_type describes
            # the resulting pot, so translate those first two counts here.
            if preflop_raises == 1:
                pot_type = "unopened"
            elif preflop_raises == 2:
                pot_type = "single_raised"
            if preflop_raises:
                facing_action = "raises"
            if preflop_raises == 1 and calls_after_raise:
                labels = ("squeeze_defence",)
        hud.set_live_state(
            street=street,
            street_index=("preflop", "flop", "turn", "river").index(street),
            pot_type=pot_type,
            facing_action=facing_action,
            labels=labels,
            preflop_aggressor=getattr(update, "preflop_aggressor", "") or None,
            folded_players=tuple(getattr(update, "folded_players", ())),
            source="street_live",
        )
        hud.refresh_dynamic_panels()
        seen[update.pool] = signature
        if len(seen) > 256:
            seen.clear()
        log.debug("Winamax HUD street update: table=%s street=%s pot=%s", key, street, getattr(update, "pot_type", ""))

    def _retire_winamax_regular_hand(self, update: Any) -> None:
        """Forget this hand's live street when its matching table reports completion.

        A delayed hand-over event from a previous hand must not clear the new
        hand's live state, so retire only an exact normalized-ID match.
        """
        key = self._winamax_regular_hud_key(update)
        hud = self.hud_dict.get(key) if key is not None else None
        if hud is None or str(getattr(hud, "site", "")).casefold() != "winamax":
            return

        from fpdb_3_legacy.winamax_live_log_reader import fpdb_hand_id

        hand_id = fpdb_hand_id(update.hand_id) or str(update.hand_id)
        if getattr(hud, "_winamax_live_hand_id", None) != hand_id:
            return

        hud.live_state.clear()
        hud._winamax_live_hand_id = None
        for aux in getattr(hud, "aux_windows", ()):
            forget = getattr(aux, "forget_dynamic_panels", None)
            if callable(forget):
                forget()
        hud.refresh_dynamic_panels()

    def _winamax_regular_hud_key(self, update: Any) -> str | None:
        """Find a classic Winamax window even when its title has no log index.

        Fast-Fold windows carry ``[table] N`` in their title, but ordinary
        cash windows such as ``Winamax Casablanca`` do not. Match the last
        imported hand through the log's site-hand map first, then the client's
        explicit table label. Never guess when more than one HUD matches.
        """
        key = self._live_hud_key_for_table_no(str(update.table_no))
        if key is not None:
            return key

        ordinary = {
            name: hud for name, hud in self.hud_dict.items()
            if str(getattr(hud, "site", "")).casefold() == "winamax"
            and not getattr(hud, "is_fast_fold", False)
        }
        reader = getattr(self, "winamax_log_reader", None)
        if reader is not None:
            by_hand = [
                name for name, hud in ordinary.items()
                if isinstance((site_hand := getattr(getattr(hud, "hand_instance", None), "handid", None)), (str, int))
                and reader.table_no_for_hand(str(site_hand)) == str(update.table_no)
            ]
            if len(by_hand) == 1:
                return by_hand[0]
            if len(by_hand) > 1:
                return None

        label = str(getattr(update, "table_label", "") or "").strip().casefold()
        if not label:
            return None
        by_label = [
            name for name, hud in ordinary.items()
            if str(getattr(hud.table, "key", "") or "").strip().casefold() == label
            or str(getattr(hud.table, "title", "") or "").strip().casefold() == f"winamax {label}"
        ]
        return by_label[0] if len(by_label) == 1 else None

    def _on_winamax_table_update(self, update: Any) -> None:
        """Apply a live Winamax log update. Runs on the GUI thread."""
        if not update.pool.startswith(FAST_FOLD_POOL_PREFIX):
            self._on_winamax_regular_table_update(update)
            return

        if update.hand_id not in self._ff_started:
            # The hand-start line: the clock for everything that follows.
            if len(self._ff_started) > 200:
                self._ff_started.clear()
            self._ff_started[update.hand_id] = time.monotonic()
            lag = ""
            if update.logged_at_ms:
                lag = f" (read {time.time() * 1000 - update.logged_at_ms:.0f}ms after the client wrote it)"
            self._ff_trace(
                update.hand_id,
                "hand-start",
                f"pool={update.pool} [table] {update.table_no}{lag}",
            )
            # The client writes the hand-start line before it has drawn the new
            # table, and the blinds and hole cards follow in the same
            # millisecond -- so every log line of this hand arrives too early to
            # see the players. Come back once the window has caught up.
            for delay_ms in self.AX_RECHECK_DELAYS_MS:
                QTimer.singleShot(delay_ms, lambda pool=update.pool: self._recheck_window(pool))

        found = self._find_fast_fold_hud(update)
        if found is None:
            return
        temp_key, hud = found
        # What the idle sweep measures staleness against.
        self._ff_last_activity[temp_key] = time.monotonic()

        if update.finished:
            # The hand is over, or the hero folded and was moved on. Either way
            # nobody is at this table now, and leaving the blocks up over an
            # empty felt is the one thing worse than showing nothing.
            reason = "hero folded, moving on" if update.hero_left else "hand over"
            self._clear_fast_fold_table(temp_key, hud, update.hand_id, reason)
            return

        last_hand = getattr(hud, "ff_last_hand_id", None)
        if last_hand != update.hand_id:
            setattr(hud, "ff_last_hand_id", update.hand_id)
            if getattr(hud, "stat_dict", None) or getattr(hud, "seat_players", None):
                self._clear_fast_fold_table(temp_key, hud, update.hand_id, "new hand start")

        max_seats = getattr(hud, "max", 6) or 6
        engine = FastFoldEngine(config=self.config)
        hero_seat = engine.pin_hero_seat(hud)

        # The window itself is the better source: it names every player at the
        # chair they are drawn in, so the table is right from the moment it is
        # dealt, empty chairs included. The log ring stays as the fallback for
        # platforms with no accessibility reader.
        slots = self._ax_slots(hud, update.hand_id, max_seats)
        # The client draws the hero in the bottom chair whenever the table is
        # drawn at all, sitting out included. A read without it caught the
        # window mid-redraw, and acting on it seats the wrong people for a
        # fraction of a second before the next read corrects them.
        drawn = self.HERO_SLOT in slots
        if drawn and len(slots) >= self.MIN_PLAYERS_TO_SHOW:
            # Slot 0 is the bottom-center chair where the client draws the hero.
            # Map slot 0 to the layout anchor seat (seat 3 for 6-max Winamax layouts).
            anchor_seat = engine._anchor_slot(hud) or 3
            seat_map = {((slot + anchor_seat - 1) % max_seats) + 1: login for slot, login in slots.items()}
            source = "window"
        elif slots and not self._ax_reads_spent(hud, update.hand_id):
            # Either the window holds nobody but the hero -- between hands, or
            # waiting for players -- or it was caught half-drawn. Either way
            # there is no table to describe yet; the rechecks will come back.
            self._clear_fast_fold_table(temp_key, hud, update.hand_id, "table not dealt yet")
            return
        elif update.ring and update.hero:
            hand_start_time = self._ff_started.get(update.hand_id, 0)
            elapsed = time.monotonic() - hand_start_time if hand_start_time else 1.0
            if len(update.ring) < max_seats and elapsed * 1000 < self._fast_fold_seat_wait_ms:
                # The client log names a player only once they have acted, so a
                # six-handed table is named over several seconds. Showing what is
                # known so far means blocks appearing one at a time; waiting means
                # they appear together, later. Which of the two is worse is the
                # player's call, not ours -- hud_ui/@fast_fold_seat_wait_ms.
                #
                # And something has to come back at the deadline. The only other
                # rechecks of a hand are AX_RECHECK_DELAYS_MS, which stop at
                # 1500ms: with the wait set beyond that, as the setting documents,
                # a short-handed table whose last ring update lands before the
                # deadline would never be drawn at all -- nothing would look
                # again until the hand was over, and then it is cleared.
                # Reported by Codex on the pull request.
                self._schedule_seat_wait_recheck(update, elapsed)
                return
            seat_map = build_seat_map(update.ring, update.hero, max_seats=max_seats, hero_seat=hero_seat)
            source = "log-ring"
        else:
            # Nothing to show yet: a new hand has started and neither the window
            # nor the log has said who is at the new table.
            self._clear_fast_fold_table(temp_key, hud, update.hand_id, "no players known yet")
            return

        if not seat_map or seat_map == self._fast_fold_pending.get(temp_key):
            return
        self._fast_fold_pending[temp_key] = seat_map

        self._ff_trace(
            update.hand_id,
            "seats",
            f"table={temp_key} source={source} hero_seat={hero_seat} "
            f"seats={ {s: seat_map[s] for s in sorted(seat_map)} }",
        )
        self._request_fast_fold_stats_coalesced(temp_key, hud, seat_map, update.hand_id)

    def _forget_window_seat_state(self, table_key: str, hwnd: int | None = None) -> None:
        """Drop what was learned about reading a table, when that table retires.

        The breaker's verdict, the fruitless count and the per-hand ring are all
        keyed by the table's name, which a pool hands back: close a table and
        Winamax gives the next one the same "Colorado 3", so a HUD built after a
        restart inherited "this client will not answer" from a client that is no
        longer running. It never read its window, never asked for accessibility,
        and went straight to the log-derived seats for the rest of the session.

        The accessibility cache was taught the same lesson one round earlier, by
        the owning process rather than by the key -- and I said in reply that
        these were safe because they are keyed by name rather than by handle.
        That was the reason they are not. Reported by Codex on the pull request.
        """
        learned = getattr(self, "_table_reads", None)
        if learned is not None:
            learned.pop(table_key, None)

        # And the window's own: whether its accessibility request was accepted,
        # whether one is in the air, and where its table's centre was measured.
        # Nothing released that in production, so a handle Winamax handed to
        # another of its tables -- same process, so the owner check says nothing
        # -- inherited an accepted request it never received, an outstanding one
        # nobody would ever clear, and a centre belonging to a table that had
        # closed. Reported by Codex on the pull request.
        if hwnd:
            with contextlib.suppress(Exception):
                from fpdb_3_legacy.winamax_ax_seats import forget_window_state

                forget_window_state(int(hwnd))

    def _ax_slots(self, hud: Hud.Hud, hand_id: str, max_seats: int) -> dict[int, str]:
        """Players drawn on this table's window, keyed by layout slot from the bottom.

        Read once per hand and remembered: the seats cannot change within one,
        while the log emits a line for every action, and each read is a
        synchronous walk of another process's accessibility tree (~20ms).

        Empty when the platform has no reader, or the window could not be read;
        the caller then falls back to the log-derived ring.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        table = getattr(hud, "table", None)
        title = getattr(table, "title", "") or ""
        if reader is None or not title or not self._ax_reader_enabled:
            return {}

        table_key = getattr(table, "key", None) or title
        state = self._table_reads.get(table_key)
        if state is not None and state.gave_up:
            return {}
        if state is None:
            state = self._table_reads.setdefault(table_key, TableReadState())
        state.start_hand(hand_id)
        cached_slots, reads = state.ring, state.reads

        # The hand-start line beats the client to the draw: read then and only
        # the hero is on the table yet. So keep re-reading on later lines of the
        # same hand, taking the fullest answer, until the table is full or the
        # budget runs out -- caching that first partial read is what left the
        # overlay showing one player for a whole hand.
        if (self.HERO_SLOT in cached_slots and len(cached_slots) >= max_seats - 1) or len(cached_slots) >= max_seats or reads >= self.AX_READS_PER_HAND:
            return cached_slots

        table_pos = None
        if table is not None and getattr(table, "x", None) is not None and getattr(table, "y", None) is not None:
            table_pos = (float(table.x), float(table.y))

        started = time.monotonic()
        # The window id is the table's identity: every window of a Fast-Fold
        # pool carries the same name, and resolving one by title again -- on
        # every read of every hand -- means enumerating the whole desktop.
        slots = reader.read_window(
            title,
            max_seats,
            table_pos=table_pos,
            window_id=getattr(table, "number", None),
        )
        took = (time.monotonic() - started) * 1000
        # A read holding the hero's chair beats one without it even when the
        # one without it names more players: the second caught the window
        # half-drawn, and its extra names are the previous table's.
        best = max(
            (cached_slots, slots),
            key=lambda answer: (self.HERO_SLOT in answer, len(answer)),
        )
        state.ring, state.reads = best, reads + 1

        # Traced on every read, not only when the answer changed. A reader that
        # returns nothing returns the same nothing every time, so the one case
        # worth reporting -- the window telling us about no players at all, for
        # every hand of a session -- was the one case that logged absolutely
        # nothing, even with FPDB_HUD_TRACE=1. The seats then come from the log
        # ring, which names a player only once they have acted, and the blocks
        # arrive one at a time; that is what gets reported, with no trace of why.
        # A client that publishes nothing publishes nothing every time, and each
        # read is a synchronous walk of another process's tree on the GUI
        # thread, at hand-start, which is exactly when the HUD is trying to
        # draw. Measured on a live session: six reads a hand, on two tables,
        # 15-62ms each, every one of them players=0. Stop paying for it.
        # Fruitless means "could not be acted on", not "came back empty". This
        # counted empty reads, and a client that answers with the hero and one
        # neighbour -- never the bottom-centre chair, never enough of the ring --
        # answers non-empty every single time. The counter reset on every read,
        # the breaker never tripped, and six reads a hand went on being paid for
        # on two tables at 94-172ms each: about 1.5s of GUI thread per hand, for
        # a seat map the caller discards. The test is the caller's own.
        usable = self.HERO_SLOT in best and len(best) >= self.MIN_PLAYERS_TO_SHOW
        if usable:
            state.fruitless = 0
        else:
            state.fruitless += 1
            fruitless = state.fruitless
            if fruitless >= self.AX_FRUITLESS_READS_BEFORE_GIVING_UP:
                state.gave_up = True
                log.warning(
                    "Giving up on the window seat reader for %s after %d reads that could not seat "
                    "anyone: this client is not publishing enough of that table through the "
                    "accessibility API to place the hero. Its Fast-Fold seats come from the client "
                    "log, which names a player only once they have acted.",
                    table_key,
                    fruitless,
                )

        empty = sorted(set(range(max_seats)) - set(best))
        self._ff_trace(
            hand_id,
            "window-read",
            f"{title!r} (key={table_key}) {took:.0f}ms read#{reads + 1} players={len(best)} "
            f"slots={ {s: best[s] for s in sorted(best)} } empty={empty}",
        )
        return best

    def _ax_reads_spent(self, hud: Hud.Hud, hand_id: str) -> bool:
        """Whether this hand's budget of window reads is used up for this table.

        Once it is, re-reading cannot improve the answer within this hand, so a
        window read that never showed a dealt table has said all it is going to
        say -- and the log-derived ring, slow as it is, describes the table
        better than nothing. Without this, a client that answers the
        accessibility API only partially (or not at all, while still yielding a
        label or two) would leave the overlay permanently blank, which is worse
        than the ring it replaced.
        """
        table = getattr(hud, "table", None)
        table_key = getattr(table, "key", None) or getattr(table, "title", "") or ""
        state = self._table_reads.get(table_key)
        return state is not None and state.hand_id == hand_id and state.reads >= self.AX_READS_PER_HAND

    def _has_live_seat_source(self, site_name: str) -> bool:
        """Whether a real-time seat source is running for this site.

        Only Winamax has one: its client writes a log this HUD tails. Without it
        a Fast-Fold HUD can only ever show the players of an already-finished
        hand, which is why such tables are still skipped elsewhere.
        """
        if str(site_name).lower() != "winamax":
            return False
        reader = getattr(self, "winamax_log_reader", None)
        return bool(reader is not None and reader.is_tailing)
