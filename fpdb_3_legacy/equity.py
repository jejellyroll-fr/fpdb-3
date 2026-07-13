"""Optional poker-equity engine integration.

The rest of fpdb talks to this module instead of importing the historical
``pokereval`` extension directly.  That keeps the native dependency optional
and gives callers values on a documented 0..1 scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from importlib import import_module
from typing import Protocol

COMMUNITY_CARD_GAMES = frozenset(
    {"holdem", "holdem8", "omaha", "omaha8", "omaha5", "omaha5_8", "omaha6", "shortdeck"}
)


class EquityUnavailableError(RuntimeError):
    """Raised when an equity calculation is requested without a backend."""


class PokerEvalBackend(Protocol):
    def poker_eval(self, **kwargs) -> dict: ...


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
