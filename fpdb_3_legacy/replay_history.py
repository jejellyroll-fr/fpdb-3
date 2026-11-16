"""The replayer's action history: one entry per phase, action and the end of the hand (#825).

Each entry carries the index of the replay state it shows, so the history can
seek the replayer to any decision. Nothing here touches Qt widgets: the entries
are built from the replay states alone (``TableState`` copies, or anything with
the same attributes), which keeps them testable without a display.

After thecrawler1's fork (``personal`` branch, commit af0117a, "add indexed
action-history navigation"), re-implemented on the current replayer.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

PHASE = "phase"
ACTION = "action"
RESULT = "result"
END = "end"

_PHASE_LABELS = {
    "BLINDSANTES": "Blinds and antes",
    "PREFLOP": "Preflop",
    "FLOP": "Flop dealt",
    "TURN": "Turn dealt",
    "RIVER": "River dealt",
    "DEAL": "Cards dealt",
    "DRAWONE": "First draw",
    "DRAWTWO": "Second draw",
    "DRAWTHREE": "Third draw",
    "SECOND": "Second street",
    "THIRD": "Third street",
    "FOURTH": "Fourth street",
    "FIFTH": "Fifth street",
    "SIXTH": "Sixth street",
    "SEVENTH": "Seventh street",
}

# What a posted amount is called; the amount shown is what left the stack.
_POSTS = {
    "small blind": "posts small blind",
    "secondsb": "posts small blind",
    "big blind": "posts big blind",
    "both": "posts small & big blind",
    "ante": "posts ante",
    "bringin": "brings in",
}


@dataclass(frozen=True)
class ReplayHistoryEntry:
    """One line of the history and the replay state it seeks to.

    The street of an entry is the street of the state at *index*.
    """

    index: int
    kind: str
    text: str
    player: str | None = None
    action: str | None = None
    amount: Decimal | None = None
    allin: bool = False


def format_history_amount(value: Decimal | int | float, currency: str, blind: Decimal | None = None) -> str:
    """Format an amount as the replayer does: money, chips, or big blinds when *blind* is given.

    In big blinds the ratio is rounded to the hundredth, without trailing zeros
    (``3 BB``, ``2.5 BB``), as the shared hand writes it.
    """
    # Imported here so that building the entries needs no Qt at import time.
    from fpdb_3_legacy.localized_formats import format_currency, format_number

    if blind:
        ratio = (Decimal(str(value)) / Decimal(str(blind))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ratio = ratio.normalize()
        decimals = max(0, -int(ratio.as_tuple().exponent))
        return f"{format_number(ratio, decimals)} BB"
    if currency in {"", "T$", "play"}:
        return format_number(value)
    return format_currency(value, currency)


def phase_label(street: str | None) -> str:
    """The history line for the start of *street* (``Flop dealt``, ``Flop dealt (run 2)``...)."""
    if not street:
        return "Start of hand"
    label = _PHASE_LABELS.get(street)
    if label is not None:
        return label
    base, run = street.rstrip("123"), street[len(street.rstrip("123")) :]
    if run and base in _PHASE_LABELS:
        return f"{_PHASE_LABELS[base]} (run {run})"
    return street.capitalize()


def _is_run_board(name: str, street: str, board: dict[str, Any]) -> bool:
    """Whether *name* is a numbered board (FLOP1, FLOP2...) of *street* with cards dealt."""
    return name != street and name.rstrip("123") == street and bool(board.get(name))


def _phase_cards(state: Any) -> list[list[str]]:
    """The board cards dealt by the phase *state* starts, one list per board."""
    board = getattr(state, "board", None) or {}
    street = getattr(state, "street", None) or ""
    if board.get(street):
        return [list(board[street])]
    # A double-board bomb pot deals FLOP1 and FLOP2 together under one "FLOP" phase.
    render = getattr(state, "renderBoard", None) or ()
    return [list(board[name]) for name in sorted(render) if _is_run_board(name, street, board)]


def _phase_text(state: Any) -> str:
    label = phase_label(getattr(state, "street", None))
    boards = _phase_cards(state)
    if not boards:
        return label
    return f"{label}: " + " | ".join(" ".join(cards) for cards in boards)


def _players(state: Any) -> list[Any]:
    return list((getattr(state, "players", None) or {}).values())


def _actor(state: Any) -> Any | None:
    acted = [player for player in _players(state) if getattr(player, "justacted", False)]
    return acted[-1] if acted else None


def _stack_drop(previous: Any | None, player: Any) -> Decimal:
    """What left *player*'s stack between the previous state and this one."""
    before = (getattr(previous, "players", None) or {}).get(player.name)
    if before is None:
        return Decimal(0)
    return Decimal(before.stack) - Decimal(player.stack)


def _action_amount(verb: str, previous: Any | None, player: Any) -> Decimal | None:
    """The amount an action is read with, or None for one without an amount."""
    if verb == "raises":
        # A raise is read "to" the total the player has put in on this street.
        return Decimal(player.chips)
    if verb in {"calls", "bets"} or verb in _POSTS:
        # A call is the amount actually added, not the total committed.
        return _stack_drop(previous, player)
    return None


def _action_text(verb: str, action: str, player: Any, amount: str | None) -> str:
    if verb == "raises":
        return f"{player.name}: raises to {amount}"
    if amount is not None:
        return f"{player.name}: {_POSTS.get(verb, verb)} {amount}"
    cards = list(getattr(player, "discardCards", None) or []) if verb == "discards" else []
    return f"{player.name}: {action}" + (f" [{' '.join(cards)}]" if cards else "")


def _action_entry(index: int, previous: Any | None, player: Any, money: Callable[[Decimal], str]) -> ReplayHistoryEntry:
    action = str(player.action or "")
    verb = action.split(" ", 1)[0] if action.startswith("discards") else action
    became_allin = bool(getattr(player, "allin", False)) and verb not in {"folds", "checks", "discards", "stands pat"}
    amount = _action_amount(verb, previous, player)
    text = _action_text(verb, action, player, None if amount is None else money(amount))
    return ReplayHistoryEntry(
        index=index,
        kind=ACTION,
        text=text + (" (all-in)" if became_allin else ""),
        player=player.name,
        action=verb,
        amount=amount,
        allin=became_allin,
    )


def _end_entries(index: int, state: Any, money: Callable[[Decimal], str]) -> list[ReplayHistoryEntry]:
    """``Hand complete``, then what each winner collected, all seeking to the last state."""
    entries = [ReplayHistoryEntry(index=index, kind=END, text="Hand complete")]
    for player in _players(state):
        if getattr(player, "justacted", False) and player.action == "collected" and player.chips:
            amount = Decimal(player.chips)
            entries.append(
                ReplayHistoryEntry(
                    index=index,
                    kind=RESULT,
                    text=f"{player.name}: collected {money(amount)}",
                    player=player.name,
                    action="collected",
                    amount=amount,
                )
            )
    return entries


def _state_entries(
    index: int, state: Any, previous: Any | None, money: Callable[[Decimal], str]
) -> list[ReplayHistoryEntry]:
    """The entries one replay state gives: the end of the hand, a new street, or an action."""
    if getattr(state, "ended", False):
        return _end_entries(index, state, money)
    if previous is None or getattr(state, "street", None) != getattr(previous, "street", None):
        return [ReplayHistoryEntry(index=index, kind=PHASE, text=_phase_text(state))]
    player = _actor(state)
    if player is None or not player.action:
        return []
    return [_action_entry(index, previous, player, money)]


def replay_history_entries(
    states: Sequence[Any],
    currency: str,
    blind: Decimal | None = None,
) -> list[ReplayHistoryEntry]:
    """The hand's history, in order, each entry pointing at the replay state to seek.

    A phase (``Flop dealt``, ``Third street``, ``First draw``) is the state that
    starts a street; every other state is one player's action. The last state
    of a finished hand gives ``Hand complete`` followed by what each winner
    collected, all seeking to that state. Amounts are in *currency*, or in big
    blinds when *blind* is given.
    """

    def money(value: Decimal) -> str:
        return format_history_amount(value, currency, blind)

    entries: list[ReplayHistoryEntry] = []
    for index, state in enumerate(states):
        entries.extend(_state_entries(index, state, states[index - 1] if index else None, money))
    return entries


def history_row_for_index(entries: Sequence[ReplayHistoryEntry], index: int) -> int | None:
    """The row to highlight while the replayer shows state *index*.

    That is the entry of the latest state shown so far; when several entries
    share it (``Hand complete`` and the winners), the first of them.
    """
    best: int | None = None
    for row, entry in enumerate(entries):
        if entry.index > index:
            break
        if best is None or entry.index != entries[best].index:
            best = row
    return best
