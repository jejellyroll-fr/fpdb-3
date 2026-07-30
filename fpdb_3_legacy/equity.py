"""Optional poker-equity engine integration.

The rest of fpdb talks to this module instead of importing the historical
``pokereval`` extension directly.  That keeps the native dependency optional
and gives callers values on a documented 0..1 scale.
"""

from __future__ import annotations

import ctypes
from collections import Counter, OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
from itertools import product
from math import prod
from random import Random
from threading import Lock
from typing import Any, Protocol

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("equity")

COMMUNITY_CARD_GAMES = frozenset({"holdem", "holdem8", "omaha", "omaha8", "omaha5", "omaha5_8", "omaha6", "shortdeck"})
POCKET_CARD_COUNTS = {
    "holdem": 2,
    "holdem8": 2,
    "shortdeck": 2,
    "omaha": 4,
    "omaha8": 4,
    "omaha5": 5,
    "omaha5_8": 5,
    "omaha6": 6,
}
DEFAULT_EQUITY_ITERATIONS = 20_000
DEFAULT_EQUITY_CACHE_SIZE = 256
DEFAULT_RANGE_ENUMERATION_LIMIT = 10_000
EQUITY_ENGINE_VERSION = 1


def _seed_native_rng(seed: int) -> None:
    """Seed the C library PRNG so the native poker-eval Monte Carlo is reproducible.

    The native ``poker_eval`` backend calls ``rand()`` (from the C standard
    library) internally to deal unknown cards.  This function seeds that RNG
    via ``srand()`` so that callers see the same result for the same seed.
    Best-effort: on platforms where the C library handle cannot be obtained
    the seed is silently ignored.
    """
    try:
        ctypes.CDLL(None).srand(ctypes.c_uint(seed))
    except Exception:
        try:
            libc = ctypes.CDLL("libc.so.6")
            libc.srand(ctypes.c_uint(seed))
        except Exception:
            pass


class EquityUnavailableError(RuntimeError):
    """Raised when an equity calculation is requested without a backend."""


class PokerEvalBackend(Protocol):
    def poker_eval(self, **kwargs) -> dict: ...

    def best(self, *args: Any, **kwargs: Any) -> Any: ...

    def card2string(self, card: Any) -> str: ...

    def winners(self, **kwargs: Any) -> dict: ...


@dataclass(frozen=True)
class PlayerEquity:
    """One player's normalized equity and the backend's sample counters."""

    equity: Decimal
    wins: int
    ties: int
    losses: int


@dataclass(frozen=True)
class EquityResult:
    """Normalized result returned by :func:`calculate_equity`."""

    players: tuple[PlayerEquity, ...]
    samples: int
    exhaustive: bool


@dataclass(frozen=True)
class WeightedPocket:
    """One concrete pocket and its positive relative range weight."""

    cards: tuple[str, ...]
    weight: Decimal = Decimal(1)


def load_poker_eval() -> PokerEvalBackend | None:
    """Return a pypoker-eval instance, or ``None`` when it is not installed."""
    try:
        module = import_module("pokereval")
        backend_class = module.PokerEval
        return backend_class()
    except (AttributeError, ImportError, OSError):
        # OSError covers a Python wrapper whose native shared library cannot load.
        return None


def _validate_cards(pockets: list[list[str]], board: list[str], dead: list[str]) -> None:
    cards = [card for pocket in pockets for card in pocket] + board + dead
    known_cards = [card for card in cards if card != "__"]
    if len(known_cards) != len(set(known_cards)):
        msg = "A known card cannot occur more than once"
        raise ValueError(msg)
    for card in known_cards:
        if len(card) != 2 or card[0].upper() not in "23456789TJQKA" or card[1].lower() not in "hdcs":
            msg = f"Invalid card: {card!r}"
            raise ValueError(msg)


def calculate_equity(
    game: str,
    pockets: list[list[str]],
    board: list[str] | None = None,
    *,
    dead: list[str] | None = None,
    iterations: int | None = None,
    backend: PokerEvalBackend | None = None,
    seed: int | None = None,
) -> EquityResult:
    """Calculate player equities, normalized from pypoker-eval's 0..1000 EV."""
    if len(pockets) < 2:
        msg = "Equity requires at least two pockets"
        raise ValueError(msg)
    board = list(board or [])
    dead = list(dead or [])
    if game in COMMUNITY_CARD_GAMES:
        if len(board) > 5:
            msg = f"{game} cannot have more than five board cards"
            raise ValueError(msg)
        # poker-eval only enumerates missing community cards when they are
        # represented explicitly. A three-card list otherwise means a final
        # three-card board, even when ``iterations`` is provided.
        board.extend(["__"] * (5 - len(board)))
    _validate_cards(pockets, board, dead)

    engine = backend or load_poker_eval()
    if engine is None:
        msg = "pypoker-eval is not installed or its native extension cannot be loaded"
        raise EquityUnavailableError(msg)

    arguments: dict[str, object] = {"game": game, "pockets": pockets, "board": board, "dead": dead}
    if iterations is not None:
        if iterations <= 0:
            msg = "iterations must be positive"
            raise ValueError(msg)
        arguments["iterations"] = iterations
    if seed is not None:
        _seed_native_rng(seed)
    raw = engine.poker_eval(**arguments)
    samples = int(raw["info"][0])
    players = tuple(
        PlayerEquity(
            equity=Decimal(int(item["ev"])) / Decimal(1000),
            wins=int(item.get("winhi", 0)) + int(item.get("winlo", 0)),
            ties=int(item.get("tiehi", 0)) + int(item.get("tielo", 0)),
            losses=int(item.get("losehi", 0)) + int(item.get("loselo", 0)),
        )
        for item in raw["eval"]
    )
    return EquityResult(players=players, samples=samples, exhaustive=iterations is None)


def expected_pot_share(equity: Decimal, pot: Decimal, rake: Decimal = Decimal(0)) -> Decimal:
    """Return the expected amount won from a pot for a normalized equity."""
    if not Decimal(0) <= equity <= Decimal(1):
        msg = "equity must be between 0 and 1"
        raise ValueError(msg)
    if pot < 0 or rake < 0 or rake > pot:
        msg = "pot and rake must describe a non-negative net pot"
        raise ValueError(msg)
    return equity * (pot - rake)


class EquityEngine:
    """Validated, cached access to the optional pypoker-eval backend.

    Exact evaluation enumerates every missing board card for concrete pockets.
    A uniform unknown range uses native pocket placeholders. Weighted ranges
    are reduced to legal concrete pocket combinations, then sent to
    ``poker_eval`` in batches rather than evaluated one board at a time in
    Python.
    """

    def __init__(
        self,
        backend: PokerEvalBackend | None = None,
        *,
        cache_size: int = DEFAULT_EQUITY_CACHE_SIZE,
        range_enumeration_limit: int = DEFAULT_RANGE_ENUMERATION_LIMIT,
    ) -> None:
        if cache_size < 0:
            msg = "cache_size cannot be negative"
            raise ValueError(msg)
        if range_enumeration_limit <= 0:
            msg = "range_enumeration_limit must be positive"
            raise ValueError(msg)
        self._backend = backend
        self._backend_loaded = backend is not None
        self._unavailable_reported = False
        self._cache_size = cache_size
        self._range_enumeration_limit = range_enumeration_limit
        self._cache: OrderedDict[tuple[Any, ...], EquityResult] = OrderedDict()
        self._cache_lock = Lock()

    @property
    def available(self) -> bool:
        """Whether the optional native backend can be loaded."""
        try:
            self._require_backend()
        except EquityUnavailableError:
            return False
        return True

    def evaluate_exact(
        self,
        game: str,
        pockets: Sequence[Sequence[str]],
        board: Sequence[str] | None = None,
        *,
        dead: Sequence[str] | None = None,
    ) -> EquityResult:
        """Enumerate every missing board card for fully known pockets."""
        normalized_pockets = _normalize_pockets(pockets)
        normalized_board = _normalize_cards(board or ())
        normalized_dead = _normalize_cards(dead or ())
        _validate_pocket_shapes(game, normalized_pockets)
        _validate_cards(
            [list(pocket) for pocket in normalized_pockets],
            list(normalized_board),
            list(normalized_dead),
        )
        if any("__" in pocket for pocket in normalized_pockets):
            msg = "Exact equity requires every pocket card to be known"
            raise ValueError(msg)
        key = (EQUITY_ENGINE_VERSION, "exact", game, normalized_pockets, normalized_board, normalized_dead)
        return self._cached(
            key,
            lambda: calculate_equity(
                game,
                [list(pocket) for pocket in normalized_pockets],
                list(normalized_board),
                dead=list(normalized_dead),
                backend=self._require_backend(),
            ),
        )

    def evaluate_uniform_unknown(
        self,
        game: str,
        hero: Sequence[str],
        board: Sequence[str] | None = None,
        *,
        opponents: int = 1,
        dead: Sequence[str] | None = None,
        iterations: int = DEFAULT_EQUITY_ITERATIONS,
        seed: int | None = None,
    ) -> EquityResult:
        """Estimate equity against uniformly distributed legal unknown pockets."""
        if opponents <= 0:
            msg = "opponents must be positive"
            raise ValueError(msg)
        if iterations <= 0:
            msg = "iterations must be positive"
            raise ValueError(msg)
        pocket_size = _pocket_size(game)
        normalized_hero = _normalize_cards(hero)
        normalized_board = _normalize_cards(board or ())
        normalized_dead = _normalize_cards(dead or ())
        _validate_pocket_shapes(game, (normalized_hero,))
        _validate_cards([list(normalized_hero)], list(normalized_board), list(normalized_dead))
        if "__" in normalized_hero:
            msg = "The hero pocket must be fully known"
            raise ValueError(msg)
        pockets = (normalized_hero, *((("__",) * pocket_size) for _ in range(opponents)))
        key = (
            EQUITY_ENGINE_VERSION,
            "uniform",
            game,
            pockets,
            normalized_board,
            normalized_dead,
            iterations,
            seed,
        )
        return self._cached(
            key,
            lambda: calculate_equity(
                game,
                [list(pocket) for pocket in pockets],
                list(normalized_board),
                dead=list(normalized_dead),
                iterations=iterations,
                backend=self._require_backend(),
                seed=seed,
            ),
        )

    def evaluate_weighted_range(
        self,
        game: str,
        hero: Sequence[str],
        opponent_ranges: Sequence[Sequence[WeightedPocket]],
        board: Sequence[str] | None = None,
        *,
        dead: Sequence[str] | None = None,
        iterations: int = DEFAULT_EQUITY_ITERATIONS,
        seed: int = 0,
        range_model: str = "explicit",
        range_version: int = 1,
    ) -> EquityResult:
        """Estimate equity against one named weighted range per opponent.

        Small Cartesian products are apportioned deterministically from their
        exact relative weights. Large products are sampled with ``seed`` and
        rejection of card collisions. In both cases identical concrete
        matchups are grouped into one native call.
        """
        if not opponent_ranges:
            msg = "At least one opponent range is required"
            raise ValueError(msg)
        if iterations <= 0:
            msg = "iterations must be positive"
            raise ValueError(msg)
        if not range_model:
            msg = "range_model cannot be empty"
            raise ValueError(msg)
        if range_version <= 0:
            msg = "range_version must be positive"
            raise ValueError(msg)
        normalized_hero = _normalize_cards(hero)
        normalized_board = _normalize_cards(board or ())
        normalized_dead = _normalize_cards(dead or ())
        _validate_pocket_shapes(game, (normalized_hero,))
        _validate_cards([list(normalized_hero)], list(normalized_board), list(normalized_dead))
        if "__" in normalized_hero:
            msg = "The hero pocket must be fully known"
            raise ValueError(msg)
        known_cards = frozenset((*normalized_hero, *normalized_board, *normalized_dead)) - {"__"}
        ranges = tuple(_prepare_range(game, entries, known_cards) for entries in opponent_ranges)
        range_key = tuple(
            tuple((entry.cards, str(entry.weight)) for entry in opponent_range) for opponent_range in ranges
        )
        key = (
            EQUITY_ENGINE_VERSION,
            "weighted",
            game,
            normalized_hero,
            range_key,
            range_model,
            range_version,
            normalized_board,
            normalized_dead,
            iterations,
            seed,
        )
        return self._cached(
            key,
            lambda: self._evaluate_weighted_uncached(
                game,
                normalized_hero,
                ranges,
                normalized_board,
                normalized_dead,
                iterations,
                seed,
                known_cards,
            ),
        )

    def _evaluate_weighted_uncached(
        self,
        game: str,
        hero: tuple[str, ...],
        ranges: tuple[tuple[WeightedPocket, ...], ...],
        board: tuple[str, ...],
        dead: tuple[str, ...],
        iterations: int,
        seed: int,
        known_cards: frozenset[str],
    ) -> EquityResult:
        if prod(len(opponent_range) for opponent_range in ranges) <= self._range_enumeration_limit:
            combinations = _enumerate_legal_combinations(ranges, known_cards)
            counts = _apportion_combinations(combinations, iterations)
        else:
            counts = _sample_legal_combinations(ranges, known_cards, iterations, seed)
        backend = self._require_backend()
        results = []
        for i, (pockets, count) in enumerate(counts.items()):
            result = calculate_equity(
                game,
                [list(hero), *[list(pocket) for pocket in pockets]],
                list(board),
                dead=list(dead),
                iterations=count,
                backend=backend,
                seed=seed + i if seed is not None else None,
            )
            results.append((result, count))
        return _merge_weighted_results(results, iterations)

    def _require_backend(self) -> PokerEvalBackend:
        if not self._backend_loaded:
            self._backend = load_poker_eval()
            self._backend_loaded = True
        if self._backend is None:
            if not self._unavailable_reported:
                log.warning(
                    "pokereval is unavailable; objective AoF statistics remain enabled but equity is disabled",
                )
                self._unavailable_reported = True
            msg = "pypoker-eval is not installed or its native extension cannot be loaded"
            raise EquityUnavailableError(msg)
        return self._backend

    def _cached(self, key: tuple[Any, ...], calculate: Callable[[], EquityResult]) -> EquityResult:
        if self._cache_size:
            with self._cache_lock:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return cached
        result = calculate()
        if self._cache_size:
            with self._cache_lock:
                self._cache[key] = result
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return result


def _normalize_card(card: str) -> str:
    value = str(card)
    if value == "__":
        return value
    if len(value) != 2:
        return value
    return f"{value[0].upper()}{value[1].lower()}"


def _normalize_cards(cards: Sequence[str]) -> tuple[str, ...]:
    return tuple(_normalize_card(card) for card in cards)


def _normalize_pockets(pockets: Sequence[Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    return tuple(_normalize_cards(pocket) for pocket in pockets)


def _pocket_size(game: str) -> int:
    try:
        return POCKET_CARD_COUNTS[game]
    except KeyError:
        msg = f"Uniform and weighted ranges are not configured for game {game!r}"
        raise ValueError(msg) from None


def _validate_pocket_shapes(game: str, pockets: Sequence[Sequence[str]]) -> None:
    pocket_size = _pocket_size(game)
    if any(len(pocket) != pocket_size for pocket in pockets):
        msg = f"{game} requires exactly {pocket_size} cards in every pocket"
        raise ValueError(msg)
    _validate_cards([list(pocket) for pocket in pockets], [], [])


def _prepare_range(
    game: str,
    entries: Sequence[WeightedPocket],
    known_cards: frozenset[str],
) -> tuple[WeightedPocket, ...]:
    pocket_size = _pocket_size(game)
    merged: dict[tuple[str, ...], Decimal] = {}
    for entry in entries:
        # Pocket order has no poker meaning. Canonicalizing it makes two
        # differently ordered copies one weighted holding and one cache key.
        cards = tuple(sorted(_normalize_cards(entry.cards)))
        weight = Decimal(entry.weight)
        if len(cards) != pocket_size:
            msg = f"{game} requires exactly {pocket_size} cards in every range pocket"
            raise ValueError(msg)
        if "__" in cards:
            msg = "Weighted range pockets must be concrete"
            raise ValueError(msg)
        if not weight.is_finite() or weight <= 0:
            msg = "Range weights must be finite and positive"
            raise ValueError(msg)
        _validate_cards([list(cards)], [], [])
        if known_cards.isdisjoint(cards):
            merged[cards] = merged.get(cards, Decimal(0)) + weight
    if not merged:
        msg = "No legal range pocket remains after removing known cards"
        raise ValueError(msg)
    return tuple(WeightedPocket(cards, weight) for cards, weight in sorted(merged.items()))


def _enumerate_legal_combinations(
    ranges: tuple[tuple[WeightedPocket, ...], ...],
    known_cards: frozenset[str],
) -> tuple[tuple[tuple[tuple[str, ...], ...], Decimal], ...]:
    legal = []
    for entries in product(*ranges):
        pockets = tuple(entry.cards for entry in entries)
        cards = [card for pocket in pockets for card in pocket]
        if len(cards) != len(set(cards)) or not known_cards.isdisjoint(cards):
            continue
        weight = prod((entry.weight for entry in entries), start=Decimal(1))
        legal.append((pockets, weight))
    if not legal:
        msg = "The opponent ranges have no collision-free combination"
        raise ValueError(msg)
    return tuple(legal)


def _apportion_combinations(
    combinations: tuple[tuple[tuple[tuple[str, ...], ...], Decimal], ...],
    iterations: int,
) -> dict[tuple[tuple[str, ...], ...], int]:
    total_weight = sum((weight for _, weight in combinations), start=Decimal(0))
    quotas = [(pockets, Decimal(iterations) * weight / total_weight) for pockets, weight in combinations]
    counts = {pockets: int(quota) for pockets, quota in quotas}
    remaining = iterations - sum(counts.values())
    ranked = sorted(quotas, key=lambda item: (item[1] - int(item[1]), item[0]), reverse=True)
    for pockets, _quota in ranked[:remaining]:
        counts[pockets] += 1
    return {pockets: count for pockets, count in counts.items() if count}


def _sample_legal_combinations(
    ranges: tuple[tuple[WeightedPocket, ...], ...],
    known_cards: frozenset[str],
    iterations: int,
    seed: int,
) -> dict[tuple[tuple[str, ...], ...], int]:
    # Prove that rejection can terminate before starting a potentially large
    # sample. This searches one legal path, not the whole Cartesian product.
    def has_legal_path(index: int, used: frozenset[str]) -> bool:
        if index == len(ranges):
            return True
        return any(
            used.isdisjoint(entry.cards) and has_legal_path(index + 1, used | frozenset(entry.cards))
            for entry in ranges[index]
        )

    if not has_legal_path(0, known_cards):
        msg = "The opponent ranges have no collision-free combination"
        raise ValueError(msg)

    rng = Random(seed)
    populations = [list(opponent_range) for opponent_range in ranges]
    weights = []
    for opponent_range in ranges:
        total_weight = sum((entry.weight for entry in opponent_range), start=Decimal(0))
        weights.append([float(entry.weight / total_weight) for entry in opponent_range])
    counts: Counter[tuple[tuple[str, ...], ...]] = Counter()
    attempts = 0
    accepted = 0
    attempt_limit = max(iterations * 100, 1_000)
    while accepted < iterations and attempts < attempt_limit:
        attempts += 1
        entries = tuple(
            rng.choices(population, weights=range_weights, k=1)[0]
            for population, range_weights in zip(populations, weights, strict=True)
        )
        pockets = tuple(entry.cards for entry in entries)
        cards = [card for pocket in pockets for card in pocket]
        if len(cards) == len(set(cards)) and known_cards.isdisjoint(cards):
            counts[pockets] += 1
            accepted += 1
    if accepted != iterations:
        msg = "Could not sample enough collision-free weighted pockets"
        raise ValueError(msg)
    return dict(counts)


def _merge_weighted_results(
    results: Sequence[tuple[EquityResult, int]],
    iterations: int,
) -> EquityResult:
    if not results:
        msg = "Weighted equity produced no result"
        raise ValueError(msg)
    player_count = len(results[0][0].players)
    equity_totals = [Decimal(0)] * player_count
    wins = [0] * player_count
    ties = [0] * player_count
    losses = [0] * player_count
    for result, weight in results:
        if len(result.players) != player_count:
            msg = "The equity backend returned an inconsistent player count"
            raise ValueError(msg)
        sample_scale = Decimal(weight) / Decimal(result.samples)
        for index, player in enumerate(result.players):
            equity_totals[index] += player.equity * weight
            wins[index] += int(Decimal(player.wins) * sample_scale)
            ties[index] += int(Decimal(player.ties) * sample_scale)
            losses[index] += int(Decimal(player.losses) * sample_scale)
    players = tuple(
        PlayerEquity(
            equity=equity_totals[index] / iterations,
            wins=wins[index],
            ties=ties[index],
            losses=losses[index],
        )
        for index in range(player_count)
    )
    return EquityResult(players=players, samples=iterations, exhaustive=False)
