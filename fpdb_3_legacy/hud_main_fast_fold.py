"""Fast-Fold tables: pools, seat maps, coalesced stats requests and their HUD.

One of the mixins HudMain (HUD_main.pyw) is built from. What it calls on the
other mixins is declared, for the type checker, on HudMainBase in hud_main_base.
"""

import contextlib
import re
import time
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QTimer

from fpdb_3_legacy import Hud
from fpdb_3_legacy.fast_fold_engine import (
    FastFoldEngine,
    FastFoldStatsRequest,
    FastFoldStatsResult,
    is_fast_fold_table,
)
from fpdb_3_legacy.hud_main_base import FAST_FOLD_POOL_PREFIX, HudMainBase, log
from fpdb_3_legacy.hud_read_service import (
    HudPreparedHand,
)
from fpdb_3_legacy.table_info import TableInfo


@dataclass(frozen=True)
class FastFoldQualification:
    """What an imported hand says about the window it was played on.

    ``table_no`` is the client's own window index, taken from the log map. It
    is carried out of qualification rather than recomputed because it is also
    how an imported hand finds the HUD the live log already built for that
    window, instead of building a second one.
    """

    info: TableInfo
    table_no: str | None
    site_hand_no: Any



class HudMainFastFoldMixin(HudMainBase):
    """Run the HUD of Fast-Fold tables, whose players change every hand."""

    def _show_loading_hud(self, hand_id: str) -> str | None:
        """Create an empty-but-visible HUD as soon as table identity is known."""
        prepared = self._prepared_hands.get(str(hand_id))
        if prepared is None or prepared.table_info is None:
            return None
        table_info = prepared.table_info
        info = TableInfo.coerce(table_info)
        table_name = info.table_name
        if not isinstance(table_name, str) or not table_name.strip():
            return None

        enabled_sites = self.config.get_supported_sites()
        hud_site_name = self._resolve_hud_config_site(info.site_name, enabled_sites)
        aux_disabled_sites = [
            site for site in enabled_sites if not self.config.get_site_parameters(site)["aux_enabled"]
        ]
        fast_unsupported = info.fast and not self._has_live_seat_source(info.site_name)
        if fast_unsupported or hud_site_name in aux_disabled_sites or hud_site_name not in enabled_sites:
            return None

        qualified = self._qualify_fast_fold_table(info, hand_id)
        if qualified is None:
            return None
        info = qualified.info
        table_name = info.table_name
        table_info = info

        temp_key = self._get_temp_key(info.game_type, info.tour_number, info.tab_number, table_name)
        if info.fast:
            self._fast_fold_tables.add(temp_key)
        resolved_key = self._resolve_fast_fold_key(temp_key, table_no=qualified.table_no)
        if resolved_key != temp_key:
            return resolved_key
        if temp_key in self.hud_dict:
            return temp_key
        if self._handle_tournament_table_changes(info.game_type, temp_key, info.tour_number):
            return None
        self._create_new_hud(
            hand_id,
            temp_key,
            table_info,
            info.site_id,
            info.num_seats,
            hud_site_name,
            loading=True,
        )
        if temp_key in self.hud_dict:
            self._last_table_info[temp_key] = table_info
            return temp_key
        return None

    def _resolve_fast_fold_key(self, temp_key: str, table_no: str | None = None) -> str:
        """Resolve an imported human key to its active window HUD key.

        An imported hand carries the pool's name; the live log built that
        table's HUD under a key qualified by its native window id. Failing to
        connect the two is what makes an import rebuild a HUD that is already
        on screen, so three routes are tried before giving up and returning the
        bare key: the alias learned when the live HUD was created, a single
        window-qualified key under this name, and -- when the client's window
        index is known -- the window itself, which is the only identity that
        cannot be confused between two tables of one pool.
        """
        aliases = getattr(self, "_fast_fold_aliases", {})
        aliased = aliases.get(temp_key)
        hud_dict = getattr(self, "hud_dict", {})
        if isinstance(aliased, str) and aliased in hud_dict:
            return aliased
        candidates = [key for key in hud_dict if key.startswith(f"{temp_key} #")]
        if len(candidates) == 1:
            return candidates[0]

        window_key = self._live_hud_key_for_table_no(table_no)
        if window_key is not None:
            # Remember it so the next hand on this pool takes the cheap route.
            if isinstance(aliases, dict):
                aliases[temp_key] = window_key
            return window_key
        return temp_key

    def _live_hud_key_for_table_no(self, table_no: str | None) -> str | None:
        """Return the HUD key already rendering the client window ``table_no``.

        Asks the resolver which native window carries that client index, then
        the registry which HUD holds it. Silent when the resolver is absent or
        the window has closed: the caller then goes on to create a HUD, which
        is the right outcome when no renderer holds the window.
        """
        if not table_no:
            return None
        reader = getattr(self, "winamax_ax_seats", None)
        if reader is None:
            return None
        try:
            window = reader.find_table_window(table_no)
        except Exception:
            log.exception("Could not resolve Winamax window for client index %s", table_no)
            return None
        if window is None or getattr(window, "window_id", None) is None:
            return None
        registry = getattr(self, "_window_registry", None)
        registered = registry.key_for(window.window_id) if registry is not None else None
        if registered is not None and registered in getattr(self, "hud_dict", {}):
            return registered
        existing = self._find_hud_by_window_id(window.window_id)
        return None if existing is None else existing[0]

    def _clear_fast_fold_table(self, temp_key: str, hud: Hud.Hud, hand_id: str, reason: str) -> None:
        """Take a Fast-Fold table's blocks down and say why.

        The seat windows hide themselves when their seat holds nobody, so
        emptying the seats is what removes them from an idle felt.
        """
        pending = self._fast_fold_pending.pop(temp_key, None)
        pending_requests = getattr(self, "_ff_pending_request", None)
        if pending_requests is not None:
            pending_requests.pop(temp_key, None)
        pending_hands = getattr(self, "_ff_pending_hand", None)
        if pending_hands is not None:
            pending_hands.pop(temp_key, None)
        pending_generations = getattr(self, "_ff_pending_generation", None)
        if pending_generations is not None:
            pending_generations.pop(temp_key, None)
        self._forget_coalesced_fast_fold_stats(temp_key)
        worker = getattr(self, "_db_worker", None)
        if worker is not None:
            with contextlib.suppress(Exception):
                worker.forget_fast_fold_table(temp_key)
        if pending is None and not getattr(hud, "stat_dict", None) and not getattr(hud, "seat_players", None):
            return  # already down
        FastFoldEngine.clear_seats(hud)
        self._ff_trace(hand_id, "cleared", f"table={temp_key} ({reason})")

    def _sweep_stale_fast_fold_tables(self) -> None:
        """Take down blocks left over a table the log has gone quiet on.

        Clearing a Fast-Fold table is otherwise driven entirely by the client
        log: the hand-over line, or the next hand's start. Neither arrives when
        the hero has been moved away and the felt is waiting for players, and
        neither arrives for a hand that was already finished when the reader
        started tailing -- which is why starting the HUD mid-hand left one
        table showing the remains of a hand nobody was playing. Measured on a
        real session, blocks stayed up over an empty table for 50, 80 and 124
        seconds at a stretch.

        So a table nobody has said anything about for a while is asked
        directly. Only a window that answers with the hero drawn and nobody
        else is cleared: the client always draws the hero when it draws the
        table at all, so a read without the hero is a failed or half-finished
        read rather than an empty table, and acting on it would blank a live
        table every time the accessibility API was slow.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        if reader is None:
            return
        now = time.monotonic()
        for temp_key, hud in list(self.hud_dict.items()):
            if not getattr(hud, "is_fast_fold", False):
                continue
            if not (getattr(hud, "stat_dict", None) or getattr(hud, "seat_players", None)):
                continue  # nothing on screen to take down
            idle = now - self._ff_last_activity.get(temp_key, now)
            if idle < self.FF_IDLE_RECHECK_SECONDS:
                continue

            slots = self._read_window_slots(hud)
            # Whatever the answer, do not ask again for another idle period:
            # each read walks another process's accessibility tree.
            self._ff_last_activity[temp_key] = now
            if slots is None or self.HERO_SLOT not in slots:
                continue  # could not read it; leave what is on screen alone
            if len(slots) >= self.MIN_PLAYERS_TO_SHOW:
                continue  # really still being played

            self._clear_fast_fold_table(
                temp_key,
                hud,
                "idle-sweep",
                f"the window seats {len(slots)} player(s) after {idle:.0f}s without a log line",
            )

    def _ff_trace(self, hand_id: str, event: str, detail: str = "") -> None:
        """One timeline line per step of a live Fast-Fold update.

        At WARNING because that is the level this HUD's diagnostics are pinned
        to (see DIAGNOSTIC_LEVEL_CAP): a report of "the seats are wrong" cannot
        be acted on without knowing what was read, when, and from where. ``+Nms``
        is measured from the hand-start line, so a slow step is visible as a
        gap rather than having to be inferred.
        """
        started = self._ff_started.get(hand_id)
        elapsed = "" if started is None else f" +{(time.monotonic() - started) * 1000:.0f}ms"
        log.warning("FF[%s]%s %s %s", hand_id, elapsed, event, detail)

    def _next_fast_fold_request_id(self) -> int:
        """Return a process-local id for the next asynchronous seat read."""
        request_id = int(getattr(self, "_ff_request_sequence", 0)) + 1
        self._ff_request_sequence = request_id
        return request_id

    def _request_fast_fold_stats_coalesced(
        self,
        temp_key: str,
        hud: Hud.Hud,
        seat_map: dict[int, str],
        hand_id: Any,
    ) -> None:
        """Ask now if nothing was asked recently, otherwise merge into one later ask.

        The client log names a player only once they have acted, so a six-handed
        table grows its ring a name at a time. Every growth used to be its own
        request, database round trip and redraw -- fourteen of them in a single
        hand across two tables, in a measured session, each one repainting
        blocks the player was already reading.

        Leading edge, then trailing: the first seat map of a burst goes out
        immediately, so the blocks appear as early as they ever did. The ones
        chasing it inside FF_STATS_COALESCE_MS are held, and only the newest
        survives to be sent when the window closes -- an intermediate ring that
        was already superseded is not worth a round trip.
        """
        now = time.monotonic()
        last = self._ff_last_request_at.get(temp_key)
        elapsed_ms = float("inf") if last is None else (now - last) * 1000

        if elapsed_ms >= self.FF_STATS_COALESCE_MS:
            self._ff_last_request_at[temp_key] = now
            self._ff_coalesced.pop(temp_key, None)
            self._request_fast_fold_stats(temp_key, hud, seat_map, hand_id)
            return

        self._ff_coalesced[temp_key] = (hud, seat_map, hand_id)
        timer = self._ff_coalesce_timers.get(temp_key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda key=temp_key: self._flush_coalesced_fast_fold_stats(key))
            self._ff_coalesce_timers[temp_key] = timer
        if not timer.isActive():
            timer.start(max(0, int(self.FF_STATS_COALESCE_MS - elapsed_ms)))
        self._ff_trace(hand_id, "stats-coalesced", f"table={temp_key} seats={len(seat_map)}")

    def _flush_coalesced_fast_fold_stats(self, temp_key: str) -> None:
        """Send the newest seat map held back for this table, if it still applies."""
        held = self._ff_coalesced.pop(temp_key, None)
        if held is None:
            return
        hud, seat_map, hand_id = held
        current = self.hud_dict.get(temp_key)
        if current is None or current is not hud:
            # The table was cleared or rebuilt while the map waited; the request
            # would be answered against a HUD nobody is looking at.
            return
        self._ff_last_request_at[temp_key] = time.monotonic()
        self._request_fast_fold_stats(temp_key, current, seat_map, hand_id)

    def _forget_coalesced_fast_fold_stats(self, temp_key: str) -> None:
        """Drop anything held for a table that is going away.

        Reached through _clear_fast_fold_table, which is called on HUDs built
        without the full constructor -- so the state is asked for the same
        defensive way its neighbours in that method are, rather than assumed.
        """
        for name in ("_ff_coalesced", "_ff_last_request_at"):
            held = getattr(self, name, None)
            if held is not None:
                held.pop(temp_key, None)
        timers = getattr(self, "_ff_coalesce_timers", None)
        timer = None if timers is None else timers.pop(temp_key, None)
        if timer is not None:
            with contextlib.suppress(RuntimeError):
                timer.stop()
                timer.deleteLater()

    def _request_fast_fold_stats(
        self,
        temp_key: str,
        hud: Hud.Hud,
        seat_map: dict[int, str],
        hand_id: Any,
    ) -> None:
        """Ask the worker for the seated players' statistics.

        Reading them needs the real connection, which lives on the worker
        thread; the answer comes back through ``fast_fold_stats_ready``. The
        request carries the site and pool as well as a reference hand, because
        a table the client log named before any of its hands was imported has
        no hand of its own and would otherwise get no statistics at all.
        """
        worker = getattr(self, "_db_worker", None)
        if worker is None:
            self._ff_trace(hand_id, "stats-skipped", "no database worker")
            return
        request_id = self._next_fast_fold_request_id()
        self._ff_pending_hand[temp_key] = hand_id
        self._ff_pending_request[temp_key] = request_id
        # The generation this read belongs to. A HUD destroyed and rebuilt
        # while the worker is busy gets a new one, and the answer to the old
        # request must not be painted onto the replacement's windows.
        self._ff_pending_generation[temp_key] = getattr(hud, "_fpdb_generation", None)
        reference_hand = self._stats_reference_hand(temp_key)
        self._ff_trace(
            hand_id,
            "stats-requested",
            f"table={temp_key} window_id={getattr(getattr(hud, 'table', None), 'number', None)} "
            f"generation={self._ff_pending_generation[temp_key]} request={request_id} "
            f"reference_hand={reference_hand}",
        )
        worker.submit(
            FastFoldStatsRequest(
                temp_key=temp_key,
                seat_map=seat_map,
                hand_id=reference_hand,
                site_name=getattr(getattr(hud, "table", None), "site", "") or "Winamax",
                pool_name=self._pool_name(temp_key),
                num_seats=getattr(hud, "max", 6) or 6,
                request_id=request_id,
            ),
        )

    @staticmethod
    def _pool_name(temp_key: str) -> str:
        """The table name a hand history records, taken back out of a HUD key.

        A Fast-Fold HUD key is the pool plus the client's window index plus the
        native window id ("Casablanca 5 #61825"); the hands themselves are
        written under the bare pool name. Stripping both suffixes is what lets
        the worker find a hand of this pool when the table has none of its own.
        """
        return re.sub(r"\s+\d+$", "", re.sub(r"\s*#\d+$", "", temp_key)).strip()

    def _stats_reference_hand(self, temp_key: str) -> Any:
        """A hand to take the gametypeId from when reading live player stats.

        This table's own last hand, when it has one. A window that has not had a
        hand imported yet may use another window from the same pool, which is
        still narrower than guessing from the newest global Gametypes row.

        None when nothing has been imported yet -- the first table of a
        session. The worker then resolves the gametypeId from the pool's own
        last hand instead; see ``get_last_gametype_id_for_table``.
        """
        hand_id = self._last_processed_hands.get(temp_key)
        if hand_id is not None:
            return hand_id

        aliases = getattr(self, "_fast_fold_aliases", {})
        for imported_key, live_key in aliases.items():
            if live_key == temp_key:
                hand_id = self._last_processed_hands.get(imported_key)
                if hand_id is not None:
                    return hand_id

        clean_key = re.sub(r"\s*#\d+$", "", temp_key)
        base = re.sub(r"\s+\d+$", "", clean_key)
        for other_key, other_hand in self._last_processed_hands.items():
            clean_other = re.sub(r"\s*#\d+$", "", other_key)
            if re.sub(r"\s+\d+$", "", clean_other) == base:
                return other_hand
        return None

    def _on_fast_fold_stats(self, result: FastFoldStatsResult) -> None:
        """Apply stats the worker read for a Fast-Fold table. Runs on the GUI thread."""
        hand_id = self._ff_pending_hand.get(result.temp_key, "?")
        expected_request = getattr(self, "_ff_pending_request", {}).get(result.temp_key)
        if expected_request is None or result.request_id != expected_request:
            self._ff_trace(
                hand_id,
                "stats-dropped",
                f"table={result.temp_key} stale_request={result.request_id} expected={expected_request}",
            )
            return
        hud = self.hud_dict.get(result.temp_key)
        if hud is None:
            self._ff_trace(hand_id, "stats-dropped", f"table={result.temp_key} has no HUD any more")
            return

        requested_generation = getattr(self, "_ff_pending_generation", {}).get(result.temp_key)
        current_generation = getattr(hud, "_fpdb_generation", None)
        if requested_generation is not None and requested_generation != current_generation:
            # The HUD was torn down and rebuilt while this read was in flight.
            self._ff_trace(
                hand_id,
                "stats-dropped",
                f"table={result.temp_key} stale_generation={requested_generation} now={current_generation}",
            )
            return

        applied = FastFoldEngine.apply_seats(hud, result.seat_map, result.stat_dict)
        with_stats = sum(1 for row in result.stat_dict.values() if row.get("n"))
        self._ff_trace(
            hand_id,
            "stats-applied" if applied else "stats-empty",
            f"table={result.temp_key} players={len(result.stat_dict)} with_history={with_stats}",
        )

    def _next_import_request_id(self) -> int:
        """Return a process-local id for the next imported-hand application.

        Paired with the hand id and the window id in the "FF import applied"
        line, this is what distinguishes one hand applied once from the same
        hand applied twice: two applications carry two request ids.
        """
        request_id = int(getattr(self, "_import_request_sequence", 0)) + 1
        self._import_request_sequence = request_id
        return request_id

    def _qualify_fast_fold_table(self, info: TableInfo, hand_id: Any) -> FastFoldQualification | None:
        """Qualify a Fast-Fold table name with the client window it was played on.

        Every Escape window on a pool writes its hands under the pool's name
        ("Casablanca"), so all of them key one HUD and overwrite each other's
        seats. The client log records which ``[table] N`` dealt each hand, and
        that index is also the suffix in the window title, so appending it both
        separates the HUDs and narrows the existing title search to the single
        matching window ("Winamax Casablanca 5").

        Returns ``None`` when the window cannot be determined -- typically a hand
        already in flight when the log tailing started. Creating a HUD from the
        bare pool name would let it claim whichever window matched first and
        report the wrong table number; the next hand carries the mapping.

        The hand's site id comes from the snapshot rather than a query: by the
        time this runs, ``db_connection`` is the database-free replay facade.

        This decides and says nothing. It runs once for the identity-only
        snapshot and again for the final one, and it used to announce "FF
        import: hand X -> window N" both times -- before the idempotence check
        that stops the second one from being applied. Two lines for one
        applied hand is what made the logs read like a double update. The
        announcement now lives at the point the hand is really applied; see
        :meth:`_log_fast_fold_import_applied`.
        """
        if not info.fast or not self._has_live_seat_source(info.site_name):
            return FastFoldQualification(info=info, table_no=None, site_hand_no=None)

        prepared = self._prepared_hands.get(str(hand_id))
        # The identity-only snapshot carries site_hand_no and nothing else, so
        # prefer it: it arrives a hand earlier than the Hand object does.
        site_hand_no = getattr(prepared, "site_hand_no", None) or getattr(
            getattr(prepared, "hand_instance", None), "handid", None
        )
        log_reader = getattr(self, "winamax_log_reader", None)
        table_no = log_reader.table_no_for_hand(site_hand_no) if log_reader is not None and site_hand_no else None
        if not table_no:
            # WARNING because this is what delays a table's HUD by a hand or two
            # at startup, and the delay is otherwise invisible. Said once per
            # hand: the identity-only and final snapshots both come through here.
            if str(hand_id) not in self._ff_unmapped_logged:
                self._ff_unmapped_logged.add(str(hand_id))
                if len(self._ff_unmapped_logged) > self.FF_UNMAPPED_LOG_MEMORY:
                    self._ff_unmapped_logged.clear()
                log.warning(
                    "FF import: hand %s (site id %s) is not in the log window map, so which window "
                    "it was played on is unknown; skipping it rather than keying a HUD on the bare "
                    "pool name %r. The next hand on that window carries the mapping.",
                    hand_id,
                    site_hand_no,
                    info.table_name,
                )
            return None

        # This hand settles what the pool deals, which is the one thing the log
        # cannot say. Kept so later hands on this pool -- and later sessions --
        # can build their HUD from the log alone.
        pool_games = getattr(self, "winamax_pool_games", None)
        if pool_games is not None:
            pool_games.remember(info.table_name, info.poker_game)
        return FastFoldQualification(
            info=info._replace(table_name=f"{info.table_name} {table_no}"),
            table_no=table_no,
            site_hand_no=site_hand_no,
        )

    def _log_fast_fold_import_applied(self, hand_id: Any, temp_key: str) -> None:
        """Announce an imported Fast-Fold hand at the moment it is applied.

        Carries ``(hand_id, window_id, request_id)`` so two lines for one hand
        can be told apart from one line for each of two hands -- the question
        the previous logging could not answer.
        """
        hud = self.hud_dict.get(temp_key)
        log.warning(
            "FF import applied: hand=%s table=%r window_id=%s request=%s generation=%s",
            hand_id,
            temp_key,
            getattr(getattr(hud, "table", None), "number", None),
            self._next_import_request_id(),
            getattr(hud, "_fpdb_generation", None),
        )

    def _hud_is_fast_fold(self, hud: Hud.Hud, temp_key: str = "") -> bool:
        """Whether this table plays the Fast-Fold format.

        Checked in order of reliability: active fast fold tables, base table
        names with matching table indices, imported hand game types, then window titles.
        """
        if getattr(hud, "is_fast_fold", False) is True:
            return True
        if temp_key and temp_key in self._fast_fold_tables:
            hud.is_fast_fold = True
            return True

        resolved_key = self._resolve_fast_fold_key(temp_key) if temp_key else temp_key
        if resolved_key and resolved_key != temp_key and resolved_key in self.hud_dict:
            hud.is_fast_fold = True
            return True

        clean_key = re.sub(r"\s*#\d+$", "", temp_key or "")
        hud_table_name = getattr(hud, "table_name", None) or ""
        clean_hud_name = re.sub(r"\s*#\d+$", "", hud_table_name if isinstance(hud_table_name, str) else "")

        for ff_table in list(self._fast_fold_tables):
            clean_ff = re.sub(r"\s*#\d+$", "", ff_table)
            for check in (clean_key, clean_hud_name):
                if not check:
                    continue
                if check == clean_ff:
                    hud.is_fast_fold = True
                    return True
                m1 = re.search(r"(\d+)\s*$", check)
                m2 = re.search(r"(\d+)\s*$", clean_ff)
                if m1 and m2 and m1.group(1) == m2.group(1):
                    b1 = re.sub(r"\s*\d+$", "", check)
                    b2 = re.sub(r"\s*\d+$", "", clean_ff)
                    if b1 in b2 or b2 in b1:
                        hud.is_fast_fold = True
                        return True

        table_name = getattr(hud, "table_name", None)
        game_type = getattr(hud, "game_type", None)
        is_ff = is_fast_fold_table(
            table_name if isinstance(table_name, str) and table_name else temp_key,
            game_type=game_type if isinstance(game_type, str) else "",
        )
        if is_ff:
            hud.is_fast_fold = True
        return is_ff

    def _ensure_fast_fold_hud(self, update: Any) -> tuple[str, Hud.Hud] | None:
        """Create the HUD for a Fast-Fold window the log has just reported.

        Display is driven by the log, which names the window the instant a hand
        starts. Hand histories cannot do this job: they arrive seconds to
        minutes later, every window on a pool writes under the same table name,
        and at startup a backlog of already-finished hands would each claim a
        window at random. They are left to do what only they can -- bring the
        statistics.

        The window describes itself ("ESCAPE - 0,01-0,02 EUR - Pot Limit
        Omaha"), which is where the game comes from; everything else is the
        pool's own shape.
        """
        reader = getattr(self, "winamax_ax_seats", None)
        if reader is None:
            self._ff_trace(
                update.hand_id,
                "create-deferred",
                "Winamax table resolver unavailable; waiting for an imported hand",
            )
            return None

        window = reader.find_table_window(update.table_no)
        if window is None:
            self._ff_trace(
                update.hand_id,
                "create-deferred",
                f"no open Winamax window is titled with the client index {update.table_no}; "
                f"waiting for an imported hand",
            )
            return None
        if window.window_id is not None:
            temp_key = f"{window.table_name} #{window.window_id}"
        else:
            temp_key = window.table_name
        aliases = getattr(self, "_fast_fold_aliases", None)
        if aliases is not None:
            aliases[window.table_name] = temp_key
        if temp_key in self.hud_dict and not self._discard_loading_hud(temp_key, update.hand_id):
            return temp_key, self.hud_dict[temp_key]

        # The table title is not unique in Fast-Fold.  The native window id is
        # the stable identity, so reuse a HUD already attached to that window
        # even if an earlier resolver pass produced a different text key.
        existing = self._find_hud_by_window_id(window.window_id)
        if existing is not None:
            existing_key, existing_hud = existing
            if not self._discard_loading_hud(existing_key, update.hand_id):
                if aliases is not None:
                    aliases[window.table_name] = existing_key
                existing_hud.is_fast_fold = True
                self._ff_trace(
                    update.hand_id,
                    "hud-reused",
                    f"table={existing_key} window={window.title!r} window_id={window.window_id}",
                )
                return existing_key, existing_hud

        # The window states the game only when the accessibility API answered.
        # Otherwise fall back on what an imported hand from this pool proved.
        pool_games = getattr(self, "winamax_pool_games", None)
        poker_game = window.poker_game or (pool_games.get(temp_key) or pool_games.get(window.table_name) if pool_games is not None else None)
        if not poker_game:
            self._ff_trace(
                update.hand_id,
                "create-skipped",
                f"{window.title!r} does not say what is being played ({window.description!r}) and "
                f"no hand from this pool has been imported yet; the next one settles it",
            )
            return None

        info = TableInfo(
            table_name=temp_key,
            max_seats=self.FAST_FOLD_MAX_SEATS,
            poker_game=poker_game,
            game_type="ring",
            fast=True,
            site_id=self._winamax_site_id,
            site_name="Winamax",
            num_seats=self.FAST_FOLD_MAX_SEATS,
        )
        # A loading HUD reads nothing from the database, but it does take the
        # hole cards from the prepared hand; there is no hand here, so stand one
        # in rather than sending it to look for one.
        synthetic_hand = f"live:{update.hand_id}"
        self._prepared_hands[synthetic_hand] = HudPreparedHand(hand_id=synthetic_hand)

        self._fast_fold_tables.add(temp_key)
        # A full HUD, not the loading placeholder: that one has no aux windows,
        # so it can only ever show "Loading HUD..." until an import replaces it.
        # The seats arrive from the window moments later.
        create_kwargs: dict[str, Any] = {"stats": {}}
        if window.window_id is not None:
            create_kwargs["resolved_window"] = window
        self._create_new_hud(
            synthetic_hand,
            temp_key,
            info,
            self._winamax_site_id,
            self.FAST_FOLD_MAX_SEATS,
            "Winamax",
            **create_kwargs,
        )
        hud = self.hud_dict.get(temp_key)
        if hud is None:
            self._ff_trace(update.hand_id, "create-failed", f"table={temp_key} window={window.title!r}")
            return None

        hud.is_fast_fold = True
        self._ff_trace(
            update.hand_id,
            "hud-created",
            f"table={temp_key} window={window.title!r} game={poker_game} (from the log, no import needed)",
        )
        return temp_key, hud

    def _discard_loading_hud(self, temp_key: str, hand_id: Any) -> bool:
        """Tear down a loading placeholder so a real HUD can take its window.

        The placeholder an imported hand puts up has ``loading=True``, and
        ``idle_create`` returns from that before building a single aux window
        -- it exists to show "Loading HUD..." and nothing else. Adopting it
        because it holds the right native window, which is what the
        duplicate-renderer guard would otherwise do, leaves the live log
        writing seats into a HUD that has no windows to draw them in: the
        table stays on "Loading HUD..." for as long as it is open.

        Returns whether a placeholder was discarded, in which case the caller
        must go on and create the real HUD.
        """
        hud = self.hud_dict.get(temp_key)
        if hud is None or not getattr(hud, "is_loading", False):
            return False
        self._ff_trace(
            hand_id,
            "loading-replaced",
            f"table={temp_key} had no overlay windows; building the real HUD from the log",
        )
        self.idle_kill(temp_key)
        return temp_key not in self.hud_dict

    def _find_hud_by_window_id(self, window_id: Any) -> tuple[str, Hud.Hud] | None:
        """Return the HUD attached to ``window_id``, if one is already alive."""
        if window_id is None:
            return None
        for key, hud in self.hud_dict.items():
            table = getattr(hud, "table", None)
            if getattr(table, "number", None) == window_id:
                return key, hud
        return None

    def _find_fast_fold_hud(self, update: Any) -> tuple[str, Hud.Hud] | None:
        """Match a log pool to an open Winamax HUD.

        The log is what identifies a table as Fast-Fold: pools are named ``gf.``
        ("go fast"), which covers Escape and HOLD-UP too. The window title cannot
        be used for this -- an Escape table is titled "Winamax Casablanca 3",
        carrying only the display name and the client's table index, with no hint
        of the format.

        That trailing index is what ties a window to a ``[table] N`` line, so it
        is also what pairs a pool with a HUD when several tables are open.
        """
        if not update.pool.startswith(FAST_FOLD_POOL_PREFIX):
            return None

        candidates: list[tuple[str, Hud.Hud]] = [
            (temp_key, hud)
            for temp_key, hud in self.hud_dict.items()
            if str(getattr(hud, "site", "")).lower() == "winamax"
        ]
        if not candidates:
            return self._ensure_fast_fold_hud(update)

        chosen: tuple[str, Hud.Hud] | None = None
        indexed = False
        for temp_key, hud in candidates:
            title = getattr(getattr(hud, "table", None), "title", "") or ""
            m = re.search(r"(\d+)\s*$", title)
            if not m:
                continue
            indexed = True
            if m.group(1) == str(update.table_no):
                chosen = (temp_key, hud)
                break

        # Falling back to "the only table open" is right only when no window
        # title carried an index to match on. Once they do, a pool that matches
        # none of them belongs to a window whose HUD does not exist yet -- taking
        # somebody else's is how the wrong table's players end up on screen.
        if chosen is None and not indexed and len(candidates) == 1:
            chosen = candidates[0]

        if chosen is None:
            remembered = self._winamax_pool_huds.get(update.pool)
            chosen = next(((k, h) for k, h in candidates if k == remembered), None)

        if chosen is None:
            # No HUD for this window yet: build one from the window itself
            # rather than waiting for one of its hands to be imported.
            return self._ensure_fast_fold_hud(update)

        temp_key, hud = chosen

        # Every Escape window on a pool is named after the pool ("Casablanca"), so
        # hands from all of them import under one table name and share a single
        # HUD -- fpdb has no window-level identity to tell them apart. Feeding
        # that one HUD from several pools just makes it flip between tables, so
        # bind it to the first pool and leave the rest alone: one correct table
        # beats two wrong ones.
        bound = self._winamax_pool_huds.get(update.pool)
        if bound is None and temp_key in self._winamax_pool_huds.values():
            if update.pool not in self._unpaired_pools:
                self._unpaired_pools.add(update.pool)
                log.warning(
                    "Winamax pool %s (table %s) shares table name %r with a pool already "
                    "driving that HUD; its seats will not be shown. Multiple Escape tables "
                    "on one pool need per-window HUDs.",
                    update.pool,
                    update.table_no,
                    temp_key,
                )
            return None

        self._winamax_pool_huds[update.pool] = temp_key
        self._fast_fold_tables.add(temp_key)
        # The pool name is the authority, so record it on the HUD: the background
        # import path needs to know this table is Fast-Fold, and the hand history
        # it works from arrives far too late to decide it.
        hud.is_fast_fold = True
        return temp_key, hud
