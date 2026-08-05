"""Database-only preparation for HUD updates.

The Qt HUD process used to interleave database reads and widget mutations on
the main thread.  This module provides the other half of that boundary: it
loads every value the GUI update path can ask for and exposes an in-memory
database facade while the result is applied.
"""

from __future__ import annotations

import contextlib
import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fpdb_3_legacy import Database, Hand
from fpdb_3_legacy.db_reconnect import is_connection_lost
from fpdb_3_legacy.loggingFpdb import get_logger
from fpdb_3_legacy.table_info import TableInfo

log = get_logger("hud_read_service")


def _hand_key(value: Any) -> str:
    return str(value)


def _lookup(mapping: dict[str, Any], hand_id: Any, default: Any = None) -> Any:
    return mapping.get(_hand_key(hand_id), default)


def _snapshot_hand(prepared: HudPreparedHand) -> HudPreparedHand:
    """Detach mutable payloads without trying to deepcopy the opaque Hand."""
    return HudPreparedHand(
        hand_id=prepared.hand_id,
        table_info=prepared.table_info,
        stat_dict=copy.deepcopy(prepared.stat_dict),
        positions=copy.deepcopy(prepared.positions),
        seat_players=copy.deepcopy(prepared.seat_players),
        table_stats=copy.deepcopy(prepared.table_stats),
        cards=copy.deepcopy(prepared.cards),
        hand_instance=prepared.hand_instance,
        winners=copy.deepcopy(prepared.winners),
        actions=copy.deepcopy(prepared.actions),
        loaded_fields=prepared.loaded_fields,
    )


def hud_temp_key(table_info: tuple) -> str:
    """Return the table identity used by ``HudMain.hud_dict``."""
    info = TableInfo.coerce(table_info)
    table_name, game_type = info.table_name, info.game_type
    tour_number, tab_number = info.tour_number, info.tab_number
    if game_type != "tour":
        return table_name
    try:
        suffix = tab_number.rsplit(" ", 1)[-1]
    except (AttributeError, ValueError):
        return table_name
    return f"{tour_number} Table {suffix}"


def hud_poker_game(poker_game: str) -> str:
    """Map imported game names to HUD layout names."""
    return {"fusion": "holdem"}.get(poker_game, poker_game)


@dataclass(frozen=True)
class HudTableReadContext:
    """Read parameters captured from one already-visible HUD."""

    temp_key: str
    last_hand_id: str
    hud_params: dict[str, Any]
    poker_game: str
    game_type: str
    site_id: int
    num_seats: int
    needs_mucked_data: bool = False


@dataclass(frozen=True)
class HudBatchReadRequest:
    """Everything the worker needs without dereferencing a Qt object."""

    sequence: int
    hand_ids: tuple[str, ...]
    hud_params: dict[str, Any]
    tables: tuple[HudTableReadContext, ...] = ()


@dataclass
class HudPreparedHand:
    """All database-derived state needed to paint one new hand."""

    hand_id: str
    table_info: tuple | None = None
    stat_dict: dict[Any, Any] = field(default_factory=dict)
    positions: dict[Any, Any] = field(default_factory=dict)
    seat_players: dict[Any, Any] = field(default_factory=dict)
    table_stats: dict[str, Any] = field(default_factory=dict)
    cards: dict[str, Any] = field(default_factory=dict)
    hand_instance: Any = None
    winners: dict[Any, Any] = field(default_factory=dict)
    actions: list[Any] = field(default_factory=list)
    loaded_fields: frozenset[str] = frozenset()


@dataclass
class HudBatchSnapshot:
    """A completed worker result, safe for the Qt thread to consume."""

    sequence: int
    requested_hand_ids: tuple[str, ...]
    primary_order: tuple[str, ...]
    hands: dict[str, HudPreparedHand]
    site_rows: dict[str, Any]
    player_ids: dict[tuple[str, str], int | None]
    hero: dict[int, str]
    hero_ids: dict[int, int]
    failed_hand_ids: tuple[str, ...] = ()
    revision: int = 0
    final: bool = True
    identity_only: bool = False


class _NullConnection:
    def rollback(self) -> None:
        """The worker already ended the real transaction."""

    def close(self) -> None:
        """There is no connection on the Qt side."""


class HudReplayDatabase:
    """Serve a worker snapshot through the legacy Database read API."""

    def __init__(self, snapshot: HudBatchSnapshot, backend: int) -> None:
        self.snapshot = snapshot
        self.backend = backend
        self.connection = _NullConnection()

    def _prepared(self, hand_id: Any) -> HudPreparedHand | None:
        return _lookup(self.snapshot.hands, hand_id)

    def _read(self, hand_id: Any, field_name: str, default: Any) -> Any:
        prepared = self._prepared(hand_id)
        if prepared is None or field_name not in prepared.loaded_fields:
            if not self.snapshot.identity_only:
                log.debug(
                    "HUD replay miss: field=%s hand=%s sequence=%s revision=%s",
                    field_name,
                    hand_id,
                    self.snapshot.sequence,
                    self.snapshot.revision,
                )
            return copy.deepcopy(default)
        return copy.deepcopy(getattr(prepared, field_name))

    def init_hud_stat_vars(self, _hud_days: int, _hero_days: int) -> None:
        return None

    def get_site_id(self, site: str) -> Any:
        if site not in self.snapshot.site_rows and not self.snapshot.identity_only:
            log.debug("HUD replay miss: site=%s", site)
        return self.snapshot.site_rows.get(site)

    def get_player_id(self, _config: Any, site: str, screen_name: str) -> int | None:
        if (site, screen_name) not in self.snapshot.player_ids and not self.snapshot.identity_only:
            log.debug("HUD replay miss: player site=%s screen_name=%s", site, screen_name)
        return self.snapshot.player_ids.get((site, screen_name))

    def get_table_info(self, hand_id: Any) -> tuple | None:
        return self._read(hand_id, "table_info", None)

    def get_stats_from_hand(self, hand_id: Any, *_args: Any, **_kwargs: Any) -> dict:
        return self._read(hand_id, "stat_dict", {})

    def get_stats_from_hands(self, hand_ids: list[Any], *_args: Any, **_kwargs: Any) -> dict:
        return {hand_id: self._read(hand_id, "stat_dict", {}) for hand_id in hand_ids}

    def get_seat_players(self, hand_id: Any) -> dict:
        return self._read(hand_id, "seat_players", {})

    def get_hand_positions(self, hand_id: Any) -> dict:
        return self._read(hand_id, "positions", {})

    def get_table_min_stack_bb(self, hand_id: Any) -> Any:
        table_stats = self._read(hand_id, "table_stats", {})
        return table_stats.get("live_min_stack_bb")

    def get_cards(self, hand_id: Any) -> dict:
        cards = self._read(hand_id, "cards", {})
        cards.pop("common", None)
        return cards

    def get_common_cards(self, hand_id: Any) -> dict:
        cards = self._read(hand_id, "cards", {})
        return {"common": cards.get("common", [])}

    def get_winners_from_hand(self, hand_id: Any) -> dict:
        return self._read(hand_id, "winners", {})

    def get_action_from_hand(self, hand_id: Any) -> list:
        return self._read(hand_id, "actions", [])


class HudReadService:
    """Load HUD batches on a connection owned by the calling worker thread."""

    def __init__(
        self,
        config: Any,
        database: Database.Database,
        hand_factory: Callable[..., Any] = Hand.hand_factory,
    ) -> None:
        self.config = config
        self.database = database
        self.hand_factory = hand_factory
        self._hero_cache: tuple[
            dict[str, Any],
            dict[tuple[str, str], int | None],
            dict[int, str],
            dict[int, int],
        ] | None = None

    @staticmethod
    def _site_aliases(site: str) -> tuple[str, ...]:
        if site != "PokerStars":
            return (site,)
        return (
            "PokerStars",
            "PokerStars.COM",
            "PokerStars.FR",
            "PokerStars.IT",
            "PokerStars.ES",
            "PokerStars.PT",
            "PokerStars.EU",
            "PokerStars.DE",
        )

    def _hero_data(self) -> tuple[dict[str, Any], dict[tuple[str, str], int | None], dict[int, str], dict[int, int]]:
        if self._hero_cache is not None:
            return self._hero_cache
        site_rows: dict[str, Any] = {}
        player_ids: dict[tuple[str, str], int | None] = {}
        hero: dict[int, str] = {}
        hero_ids: dict[int, int] = {}
        configured_sites = self.config.get_supported_sites()
        resolved_sites: set[str] = set()
        for configured_site in configured_sites:
            screen_name = self.config.supported_sites[configured_site].screen_name
            for db_site in self._site_aliases(configured_site):
                rows = self.database.get_site_id(db_site)
                site_rows[db_site] = rows
                if not rows:
                    continue
                site_id = rows[0][0]
                player_id = self.database.get_player_id(self.config, db_site, screen_name)
                player_ids[(db_site, screen_name)] = player_id
                hero[site_id] = screen_name
                hero_ids[site_id] = player_id if player_id is not None else -1
                if player_id is not None:
                    resolved_sites.add(configured_site)
        result = site_rows, player_ids, hero, hero_ids
        # The importer may create the hero after the HUD process connects. Do
        # not make an early -1 permanent; cache only once every configured
        # site's player row exists.
        if not configured_sites or resolved_sites == set(configured_sites):
            self._hero_cache = result
        return result

    def _needs_mucked_data(self, poker_game: str, game_type: str) -> bool:
        params = self.config.get_supported_games_parameters(poker_game, game_type)
        if not params:
            return False
        aux_names = params.get("aux", "")
        if isinstance(aux_names, list):
            aux_names = ",".join(aux_names)
        for name in str(aux_names).split(","):
            name = name.strip()
            if not name:
                continue
            with contextlib.suppress(Exception):
                if self.config.get_aux_parameters(name).get("module") == "Mucked":
                    return True
        return False

    def _cards(self, hand_id: str, poker_game: str) -> dict:
        cards = self.database.get_cards(hand_id)
        if poker_game in {"holdem", "omahahi", "omahahilo"}:
            cards["common"] = self.database.get_common_cards(hand_id)["common"]
        return cards

    def _hand_instance(self, hand_id: str) -> Any:
        """Build aux-window input without making one bad hand fail the HUD."""
        try:
            return self.hand_factory(hand_id, self.config, self.database)
        except Exception as exc:
            self._handle_read_error(exc)
            return None

    def _mucked_data(self, hand_id: str, needed: bool) -> tuple[dict, list]:
        """Best-effort aux data that must never suppress the primary HUD."""
        if not needed:
            return {}, []

        winners = {}
        try:
            winners = self.database.get_winners_from_hand(hand_id)
        except Exception as exc:
            self._handle_read_error(exc)
            log.warning("Could not preload HUD winners for hand %s: %s", hand_id, exc)

        # Mucked.py deliberately leaves action rendering disabled until this
        # query exists.  Calling Database.get_action_from_hand unconditionally
        # raises KeyError on every current backend and used to invalidate the
        # complete prepared hand, leaving only an invisible loading HUD.
        queries = getattr(getattr(self.database, "sql", None), "query", {})
        if "get_action_from_hand" not in queries:
            return winners, []

        try:
            actions = self.database.get_action_from_hand(hand_id)
        except Exception as exc:
            self._handle_read_error(exc)
            log.warning("Could not preload HUD actions for hand %s: %s", hand_id, exc)
            actions = []
        return winners, actions

    def _read_hand(
        self,
        hand_id: str,
        table_info: tuple,
        hud_params: dict[str, Any],
        poker_game: str,
        hero_id: int,
        needs_mucked_data: bool,
    ) -> HudPreparedHand:
        info = TableInfo.coerce(table_info)
        game_type, num_seats = info.game_type, info.num_seats
        self.database.init_hud_stat_vars(hud_params["hud_days"], hud_params["h_hud_days"])
        stat_dict = self.database.get_stats_from_hand(
            hand_id,
            game_type,
            hud_params,
            hero_id,
            num_seats,
            poker_game=poker_game,
        )
        winners, actions = self._mucked_data(hand_id, needs_mucked_data)
        loaded_fields = {
            "table_info",
            "stat_dict",
            "positions",
            "seat_players",
            "table_stats",
            "cards",
            "hand_instance",
        }
        if needs_mucked_data:
            loaded_fields.update({"winners", "actions"})
        return HudPreparedHand(
            hand_id=hand_id,
            table_info=table_info,
            stat_dict=stat_dict,
            positions=self.database.get_hand_positions(hand_id),
            seat_players=self.database.get_seat_players(hand_id),
            table_stats={"live_min_stack_bb": self.database.get_table_min_stack_bb(hand_id)},
            cards=self._cards(hand_id, poker_game),
            hand_instance=self._hand_instance(hand_id),
            winners=winners,
            actions=actions,
            loaded_fields=frozenset(loaded_fields),
        )

    def _handle_read_error(self, exc: BaseException) -> None:
        # PostgreSQL statement/lock timeouts leave the connection usable after
        # rollback, but continuing with eleven more tables could turn one
        # bounded 10-second wait into minutes. Abort this batch and let the UI
        # retry the latest notifications later.
        if getattr(exc, "sqlstate", None) in {"57014", "55P03"}:
            raise exc
        if is_connection_lost(self.database.backend, exc):
            raise exc
        with contextlib.suppress(Exception):
            self.database.connection.rollback()

    def _resolve_primary_hands(
        self,
        request: HudBatchReadRequest,
        hands: dict[str, HudPreparedHand],
        failed: list[str],
        progress_callback: Callable[[HudBatchSnapshot], None] | None,
    ) -> tuple[dict[str, str], list[str], int]:
        latest: dict[str, str] = {}
        unresolved: list[str] = []
        revision = 0
        for hand_id in request.hand_ids:
            try:
                table_info = self.database.get_table_info(hand_id)
            except Exception as exc:
                self._handle_read_error(exc)
                log.exception("HUD primary preload failed for hand %s", hand_id)
                failed.append(hand_id)
                continue
            if table_info is None:
                hands[_hand_key(hand_id)] = HudPreparedHand(hand_id=hand_id)
                unresolved.append(hand_id)
                continue
            prepared = HudPreparedHand(
                hand_id=hand_id,
                table_info=table_info,
                loaded_fields=frozenset({"table_info"}),
            )
            hands[_hand_key(hand_id)] = prepared
            latest[hud_temp_key(table_info)] = hand_id
            if progress_callback is not None:
                revision += 1
                with contextlib.suppress(Exception):
                    self.database.connection.rollback()
                progress_callback(
                    HudBatchSnapshot(
                        sequence=request.sequence,
                        requested_hand_ids=request.hand_ids,
                        primary_order=(hand_id,),
                        hands={_hand_key(hand_id): _snapshot_hand(prepared)},
                        site_rows={},
                        player_ids={},
                        hero={},
                        hero_ids={},
                        revision=revision,
                        final=False,
                        identity_only=True,
                    ),
                )
        return latest, unresolved, revision

    def _load_primary_hands(
        self,
        latest: dict[str, str],
        request: HudBatchReadRequest,
        contexts: dict[str, HudTableReadContext],
        hero_ids: dict[int, int],
        hands: dict[str, HudPreparedHand],
        failed: list[str],
        site_rows: dict[str, Any],
        player_ids: dict[tuple[str, str], int | None],
        hero: dict[int, str],
        progress_callback: Callable[[HudBatchSnapshot], None] | None,
        revision: int,
    ) -> tuple[set[str], int]:
        loaded_tables: set[str] = set()
        for hand_id in latest.values():
            table_info = hands[_hand_key(hand_id)].table_info
            if table_info is None:
                continue
            info = TableInfo.coerce(table_info)
            temp_key = hud_temp_key(info)
            context = contexts.get(temp_key)
            poker_game = context.poker_game if context else hud_poker_game(info.poker_game)
            params = context.hud_params if context else request.hud_params
            needs_mucked = (
                context.needs_mucked_data if context else self._needs_mucked_data(poker_game, info.game_type)
            )
            try:
                hands[_hand_key(hand_id)] = self._read_hand(
                    hand_id,
                    table_info,
                    params,
                    poker_game,
                    hero_ids.get(info.site_id, -1),
                    needs_mucked,
                )
                loaded_tables.add(temp_key)
            except Exception as exc:
                self._handle_read_error(exc)
                failed.append(hand_id)
            if progress_callback is not None:
                revision += 1
                # End this table's transaction before asking Qt to paint it.
                # Besides releasing pooled slots early, this makes the emitted
                # Python objects immutable from the worker's point of view.
                with contextlib.suppress(Exception):
                    self.database.connection.rollback()
                progress_callback(
                    HudBatchSnapshot(
                        sequence=request.sequence,
                        requested_hand_ids=request.hand_ids,
                        primary_order=(hand_id,) if hand_id not in failed else (),
                        hands={_hand_key(hand_id): _snapshot_hand(hands[_hand_key(hand_id)])},
                        site_rows=site_rows,
                        player_ids=player_ids,
                        hero=hero,
                        hero_ids=hero_ids,
                        failed_hand_ids=(hand_id,) if hand_id in failed else (),
                        revision=revision,
                        final=False,
                    ),
                )
        return loaded_tables, revision

    def _load_secondary_hands(
        self,
        request: HudBatchReadRequest,
        updated_tables: set[str],
        hero_ids: dict[int, int],
        hands: dict[str, HudPreparedHand],
        failed: list[str],
    ) -> None:
        groups: dict[str, tuple[HudTableReadContext, int, list[HudPreparedHand]]] = {}
        for context in request.tables:
            if context.temp_key in updated_tables or not context.last_hand_id:
                continue
            try:
                table_info = self.database.get_table_info(context.last_hand_id)
                if table_info is None:
                    continue
                prepared = HudPreparedHand(
                    hand_id=context.last_hand_id,
                    table_info=table_info,
                    positions=self.database.get_hand_positions(context.last_hand_id),
                    seat_players=self.database.get_seat_players(context.last_hand_id),
                    loaded_fields=frozenset({"table_info", "positions", "seat_players"}),
                )
                hands[_hand_key(context.last_hand_id)] = prepared
                hero_id = hero_ids.get(context.site_id, -1)
                key = repr(
                    (
                        sorted(context.hud_params.items(), key=str),
                        hero_id,
                        context.num_seats,
                        context.poker_game,
                        context.game_type,
                    ),
                )
                if key not in groups:
                    groups[key] = (context, hero_id, [])
                groups[key][2].append(prepared)
            except Exception as exc:
                self._handle_read_error(exc)
                failed.append(context.last_hand_id)

        for context, hero_id, prepared_hands in groups.values():
            hand_ids = [prepared.hand_id for prepared in prepared_hands]
            try:
                self.database.init_hud_stat_vars(
                    context.hud_params["hud_days"],
                    context.hud_params["h_hud_days"],
                )
                stats = self.database.get_stats_from_hands(
                    hand_ids,
                    context.game_type,
                    context.hud_params,
                    hero_id,
                    context.num_seats,
                    poker_game=context.poker_game,
                )
            except Exception as exc:
                self._handle_read_error(exc)
                self._load_secondary_stats_individually(
                    context,
                    hero_id,
                    prepared_hands,
                    hands,
                    failed,
                )
                continue

            stats_by_key = {_hand_key(hand_id): value for hand_id, value in stats.items()}
            for prepared in prepared_hands:
                prepared.stat_dict = stats_by_key.get(_hand_key(prepared.hand_id), {})
                prepared.loaded_fields = prepared.loaded_fields | {"stat_dict"}

    def _load_secondary_stats_individually(
        self,
        context: HudTableReadContext,
        hero_id: int,
        prepared_hands: list[HudPreparedHand],
        hands: dict[str, HudPreparedHand],
        failed: list[str],
    ) -> None:
        """Preserve the old best-effort fallback when a grouped query fails."""
        for prepared in prepared_hands:
            try:
                self.database.init_hud_stat_vars(
                    context.hud_params["hud_days"],
                    context.hud_params["h_hud_days"],
                )
                prepared.stat_dict = self.database.get_stats_from_hand(
                    prepared.hand_id,
                    context.game_type,
                    context.hud_params,
                    hero_id,
                    context.num_seats,
                    poker_game=context.poker_game,
                )
                prepared.loaded_fields = prepared.loaded_fields | {"stat_dict"}
            except Exception as exc:
                self._handle_read_error(exc)
                hands.pop(_hand_key(prepared.hand_id), None)
                failed.append(prepared.hand_id)

    def read_batch(
        self,
        request: HudBatchReadRequest,
        progress_callback: Callable[[HudBatchSnapshot], None] | None = None,
    ) -> HudBatchSnapshot:
        """Read one coalesced batch and release its transaction before returning."""
        contexts = {context.temp_key: context for context in request.tables}
        hands: dict[str, HudPreparedHand] = {}
        failed: list[str] = []
        site_rows: dict[str, Any] = {}
        player_ids: dict[tuple[str, str], int | None] = {}
        hero: dict[int, str] = {}
        hero_ids: dict[int, int] = {}

        try:
            latest, unresolved, revision = self._resolve_primary_hands(
                request,
                hands,
                failed,
                progress_callback,
            )
            site_rows, player_ids, hero, hero_ids = self._hero_data()
            primary_order = [*latest.values(), *unresolved]
            updated_tables, revision = self._load_primary_hands(
                latest,
                request,
                contexts,
                hero_ids,
                hands,
                failed,
                site_rows,
                player_ids,
                hero,
                progress_callback,
                revision,
            )
            self._load_secondary_hands(request, updated_tables, hero_ids, hands, failed)
        finally:
            with contextlib.suppress(Exception):
                self.database.connection.rollback()

        return HudBatchSnapshot(
            sequence=request.sequence,
            requested_hand_ids=request.hand_ids,
            primary_order=tuple(primary_order),
            hands=hands,
            site_rows=site_rows,
            player_ids=player_ids,
            hero=hero,
            hero_ids=hero_ids,
            failed_hand_ids=tuple(dict.fromkeys(failed)),
            revision=revision + 1 if progress_callback is not None else 0,
        )
