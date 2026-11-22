"""The contract every hand-history converter fulfils, written down as data (#903).

Every converter subclasses :class:`HandHistoryConverter` and implements the same
abstract steps; :class:`Hand.Hand` calls them in order (``readHandInfo``,
``readPlayerStacks``, ``markStreets``, ``readBlinds``...) and each one must fill
the hand in a documented way. Until #903 that contract only lived in the
docstrings of ``HandHistoryConverter.py``. It is stated here once, and read by:

* :meth:`HandHistoryConverter._warn_if_hand_missing_expected_data`, the
  completeness warnings logged at import (:func:`completeness_issues`);
* the Parser Debugger (:mod:`parser_debug`), which shows, step by step, what the
  contract expects next to what the converter produced (:func:`check_hand`);
* ``tests/test_parser_contract.py``, which holds every converter to it over the
  regression corpus.

The contract only says whether a hand is *well formed*: a stack of 40.50 read as
40.05 satisfies it. Whether a well-formed value is the right one is what the
regression sidecars (``.hands`` / ``.hp`` / ``.gt``) answer, for the hands that
have them.

Two severities:

* ``error`` -- the contract is broken: a required output is missing or a value
  is outside the set the rest of fpdb understands. The contract test fails on
  these.
* ``warning`` -- something a hand normally has is absent, but a legitimate hand
  can lack it (a walk has no betting action, a hand may be shown one card at a
  time).
"""

from __future__ import annotations

import datetime
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from fpdb_3_legacy import Card

ERROR: Final = "error"
WARNING: Final = "warning"

#: ``gametype['type']``
GAME_TYPES: Final = frozenset({"ring", "tour"})
#: ``gametype['limitType']``: no limit, capped no limit, pot limit, capped pot limit, fixed limit,
#: and Merge's half pot limit.
LIMIT_TYPES: Final = frozenset({"nl", "cn", "pl", "cp", "fl", "hp"})
#: ``gametype['base']``
BASES: Final = frozenset({"hold", "stud", "draw"})
#: ``gametype['category']``: the games fpdb can store and evaluate (:data:`Card.games`).
CATEGORIES: Final = frozenset(Card.games)
#: Keys ``determineGameType`` must return.
REQUIRED_GAMETYPE_KEYS: Final = ("type", "base", "category", "limitType", "currency", "sb", "bb")

#: Blind types ``Hand.addBlind`` accepts from a converter.
BLIND_TYPES: Final = frozenset({"small blind", "big blind", "both", "secondsb", "button blind", "straddle"})
#: Every action type a converter may store in ``hand.actions``.
ACTION_TYPES: Final = BLIND_TYPES | frozenset(
    {
        "ante",
        "bringin",
        "calls",
        "raises",
        "completes",
        "bets",
        "checks",
        "folds",
        "discards",
        "stands pat",
        "cashout",
    }
)

#: Street names ``markStreets`` must produce, per base.
STREETS_BY_BASE: Final[Mapping[str, tuple[str, ...]]] = {
    "hold": ("PREFLOP", "FLOP", "TURN", "RIVER"),
    "stud": ("THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"),
    "draw": ("DEAL", "DRAWONE", "DRAWTWO", "DRAWTHREE"),
}
#: Community cards dealt on each street of a flop game.
BOARD_SIZES: Final[Mapping[str, int]] = {"FLOP": 3, "TURN": 1, "RIVER": 1}

# A hold'em pot is balanced to the cent, but rooms round rake and side pots
# their own way: the regression harness tolerates five cents too.
POT_TOLERANCE: Final = Decimal("0.05")

# Text markers of streets, for the "marker present but board missing" warning.
_BOARD_MARKERS: Final = (("*** Flop ***", "FLOP"), ("*** Turn ***", "TURN"), ("*** River ***", "RIVER"))
# Position of the all-in flag in a blind action: (player, type, amount, all_in).
_BLIND_ALL_IN_INDEX: Final = 3
# A card fpdb knows: rank then suit. Rooms print placeholders for unseen cards
# ("xx", "0x", "?"), which say nothing about the deal.
_KNOWN_CARD: Final = re.compile(r"^[2-9TJQKA][cdhs]$")


@dataclass(frozen=True)
class StepContract:
    """What one abstract step of :class:`HandHistoryConverter` must produce."""

    step: str
    required: tuple[str, ...]
    optional: tuple[str, ...]
    summary: str
    #: The bases the step applies to; empty means every base.
    bases: tuple[str, ...] = ()


#: The steps in the order :class:`Hand.Hand` calls them.
CONTRACT: Final[tuple[StepContract, ...]] = (
    StepContract(
        "determineGameType",
        REQUIRED_GAMETYPE_KEYS,
        ("ante", "mix", "buyinType", "fast", "split", "maxSeats"),
        "A game type dict with type, base, category, limitType, currency, sb and bb from the known sets, "
        "or None; [type, base, limitType] must be one of readSupportedGames().",
    ),
    StepContract(
        "readHandInfo",
        ("handid", "startTime", "tablename"),
        ("buttonpos", "maxseats", "mixed", "tourNo", "buyin", "fee", "buyinCurrency", "koBounty", "isKO", "level"),
        "Hand metadata: handid, startTime (a datetime) and tablename; tourNo as well for a tournament hand.",
    ),
    StepContract(
        "readPlayerStacks",
        ("players",),
        ("sitout",),
        "One hand.addPlayer(seat, name, stack) per seat: unique seats and names, numeric stacks (zero is "
        "valid), at least two players.",
    ),
    StepContract(
        "compilePlayerRegexs",
        (),
        (),
        "Compile the regexes that depend on player names; produces nothing on the hand.",
    ),
    StepContract(
        "markStreets",
        ("streets",),
        (),
        "Cut the hand text into streets named after the base: PREFLOP FLOP TURN RIVER (hold), "
        "THIRD...SEVENTH (stud), DEAL DRAWONE... (draw).",
    ),
    StepContract(
        "readBlinds",
        ("actions.BLINDSANTES",),
        (),
        "hand.addBlind(player, type, amount) with type in small blind / big blind / both / secondsb / "
        "button blind / straddle, consistent with the stakes.",
        ("hold", "draw"),
    ),
    StepContract(
        "readSTP",
        (),
        (),
        "Splash-the-pot money, when the room has it.",
    ),
    StepContract(
        "readAntes",
        (),
        ("actions.BLINDSANTES",),
        "hand.addAnte(player, amount) when the game has antes.",
    ),
    StepContract(
        "readBringIn",
        (),
        ("actions.THIRD",),
        "The bring-in of a stud hand.",
        ("stud",),
    ),
    StepContract(
        "readButton",
        (),
        ("buttonpos",),
        "hand.buttonpos, on an occupied seat, when the history names a dealer.",
    ),
    StepContract(
        "readHoleCards",
        (),
        ("holecards",),
        "The cards dealt to the hero (and any known), as many as the game deals.",
    ),
    StepContract(
        "readShowdownActions",
        (),
        ("shown", "mucked"),
        "Cards shown or mucked at showdown.",
    ),
    StepContract(
        "readCommunityCards",
        (),
        ("board",),
        "The board of each street: three cards on the flop, one on the turn, one on the river.",
        ("hold",),
    ),
    StepContract(
        "readAction",
        ("actions",),
        (),
        "Every action of every street, by a seated player, with a known action type and amount.",
    ),
    StepContract(
        "readCollectPot",
        ("collectees",),
        (),
        "What each winner collected, on seated players; at least one collector.",
    ),
    StepContract(
        "readShownCards",
        (),
        ("shown",),
        "Hands shown, on seated players.",
    ),
    StepContract(
        "readTourneyResults",
        (),
        (),
        "Tournament results printed in the hand, when there are some.",
    ),
)

#: The names of the steps, in pipeline order.
STEP_NAMES: Final = tuple(contract.step for contract in CONTRACT)


@dataclass(frozen=True)
class Violation:
    """One way a parsed hand does not meet the contract."""

    step: str
    field: str
    severity: str
    message: str
    expected: str = ""
    found: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "step": self.step,
            "field": self.field,
            "severity": self.severity,
            "message": self.message,
            "expected": self.expected,
            "found": self.found,
        }


@dataclass
class Check:
    """One whole-hand invariant: ``pass``, ``warn`` or ``fail``."""

    name: str
    status: str
    message: str
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "message": self.message, "details": list(self.details)}


# ---------------------------------------------------------------------------
# Small readers, tolerant of the half-built hands the debugger shows
# ---------------------------------------------------------------------------


def to_decimal(value: Any) -> Decimal | None:
    """``value`` as a Decimal, or None when it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def player_names(hand: Any) -> list[str]:
    """The names of the seated players, in seat order of the history."""
    return [str(player[1]) for player in (getattr(hand, "players", None) or []) if len(player) > 1]


def known_cards(cards: Iterable[Any]) -> list[str]:
    """``cards`` without the placeholders rooms print for unseen cards."""
    return [str(card) for card in cards if _KNOWN_CARD.match(str(card))]


def hole_cards_by_player(hand: Any) -> dict[str, list[str]]:
    """Every card known to have been dealt to each player, all streets together."""
    dealt: dict[str, list[str]] = {}
    for by_player in (getattr(hand, "holecards", None) or {}).values():
        if not isinstance(by_player, Mapping):
            continue
        for player, parts in by_player.items():
            cards = dealt.setdefault(str(player), [])
            for part in parts if isinstance(parts, (list, tuple)) else [parts]:
                if isinstance(part, (list, tuple)):
                    cards.extend(known_cards(part))
                elif part:
                    cards.extend(known_cards([part]))
    return dealt


def hole_card_count(category: str | None) -> int | None:
    """How many hole cards a flop game deals (2 hold'em, 4 Omaha...), None for the others."""
    game = Card.games.get(category or "")
    if not game or game[0] != "hold":
        return None
    start, end = game[5][0]
    return int(end - start)


def is_walk(hand: Any) -> bool:
    """Tell whether a hand ended on the blinds with a single winner.

    In a walk everyone folds to the big blind. Some rooms (Full Tilt Matrix,
    #869) only say so in the summary, so the hand holds no betting action
    although it is complete. No board card was dealt and one player took the
    whole pot.
    """
    board = getattr(hand, "board", {}) or {}
    if any(board.values()):
        return False
    if getattr(hand, "shown", None):
        return False
    collectees = getattr(hand, "collectees", {}) or {}
    return len(collectees) == 1


def _gametype(hand: Any) -> Mapping[str, Any]:
    gametype = getattr(hand, "gametype", None)
    return gametype if isinstance(gametype, Mapping) else {}


def _actions(hand: Any) -> Mapping[str, Sequence[Sequence[Any]]]:
    actions = getattr(hand, "actions", None)
    return actions if isinstance(actions, Mapping) else {}


def _blind_all_in(blind_actions: Sequence[Sequence[Any]]) -> bool:
    return any(len(act) > _BLIND_ALL_IN_INDEX and bool(act[_BLIND_ALL_IN_INDEX]) for act in blind_actions)


def _betting_action_count(hand: Any) -> int:
    actions = _actions(hand)
    streets = getattr(hand, "actionStreets", None) or list(actions)
    return sum(len(actions.get(street, [])) for street in streets if street != "BLINDSANTES")


# ---------------------------------------------------------------------------
# Completeness: the warnings the importer logs for a hand that parsed cleanly
# ---------------------------------------------------------------------------


def completeness_issues(hand: Any) -> list[str]:
    """The data a cleanly parsed hand is expected to have and does not.

    These are the messages :meth:`HandHistoryConverter._warn_if_hand_missing_expected_data`
    logs at import; their wording is what users and tests know.
    """
    issues: list[str] = []
    gametype = _gametype(hand)
    base = gametype.get("base")
    sb = to_decimal(gametype.get("sb") or "0") or Decimal(0)
    bb = to_decimal(gametype.get("bb") or "0") or Decimal(0)
    actions = _actions(hand)

    for name in ("handid", "startTime", "tablename"):
        if not getattr(hand, name, None):
            issues.append(f"missing required {name}")
    if gametype.get("type") == "tour" and not getattr(hand, "tourNo", None):
        issues.append("missing required tourNo")

    if len(getattr(hand, "players", []) or []) < 2:
        issues.append("fewer than two players")

    blind_actions = list(actions.get("BLINDSANTES", []))
    if base in ("hold", "draw") and (sb > 0 or bb > 0) and not blind_actions:
        issues.append("no blind/ante actions")

    # A blind posted all-in ends the betting there: with the short stack
    # already covered, nobody has anything left to act on and the board simply
    # runs out. Such a hand really does hold no betting action, so flagging it
    # reports a parser failure that did not happen.
    if (
        base in ("hold", "draw", "stud")
        and _betting_action_count(hand) == 0
        and not _blind_all_in(blind_actions)
        and not is_walk(hand)
    ):
        issues.append("no betting actions")

    hand_text = getattr(hand, "handText", "") or ""
    board = getattr(hand, "board", {}) or {}
    for marker, street in _BOARD_MARKERS:
        if marker in hand_text and street in board and not board.get(street):
            issues.append(f"{street.lower()} marker present but board cards missing")
    return issues


# ---------------------------------------------------------------------------
# The contract, step by step
# ---------------------------------------------------------------------------


def check_gametype(
    gametype: Mapping[str, Any] | None,
    supported_games: Iterable[Sequence[str]] | None = None,
) -> list[Violation]:
    """What ``determineGameType`` returned, against its contract."""
    step = "determineGameType"
    if gametype is None:
        return [Violation(step, "gametype", ERROR, "No game type: the header was not understood", "a dict", "None")]
    violations = [
        Violation(step, f"gametype.{key}", ERROR, f"Required key '{key}' is missing", "present", "missing")
        for key in REQUIRED_GAMETYPE_KEYS
        if gametype.get(key) in (None, "")
    ]
    for key, allowed in (("type", GAME_TYPES), ("limitType", LIMIT_TYPES), ("base", BASES), ("category", CATEGORIES)):
        value = gametype.get(key)
        if value not in (None, "") and value not in allowed:
            violations.append(
                Violation(
                    step,
                    f"gametype.{key}",
                    ERROR,
                    f"'{value}' is not a known {key}",
                    ", ".join(sorted(allowed)) if len(allowed) < 12 else f"one of {len(allowed)} known values",
                    str(value),
                )
            )
    category, base = gametype.get("category"), gametype.get("base")
    if category in Card.games and base in BASES and Card.games[category][0] != base:
        violations.append(
            Violation(
                step,
                "gametype.base",
                ERROR,
                f"Category '{category}' is a {Card.games[category][0]} game, not {base}",
                Card.games[category][0],
                str(base),
            )
        )
    for key in ("sb", "bb"):
        value = gametype.get(key)
        if value not in (None, "") and to_decimal(value) is None:
            violations.append(
                Violation(step, f"gametype.{key}", ERROR, f"'{value}' is not an amount", "a number", str(value))
            )
    if supported_games is not None:
        details = [gametype.get("type"), gametype.get("base"), gametype.get("limitType")]
        if all(details) and details not in [list(game) for game in supported_games]:
            violations.append(
                Violation(
                    step,
                    "gametype",
                    ERROR,
                    "This game is not one the converter supports (readSupportedGames)",
                    "one of readSupportedGames()",
                    "/".join(str(item) for item in details),
                )
            )
    return violations


def _check_hand_info(hand: Any, gametype: Mapping[str, Any]) -> list[Violation]:
    step = "readHandInfo"
    violations = [
        Violation(step, name, ERROR, f"Required '{name}' is missing", "present", "missing")
        for name in ("handid", "tablename")
        if not getattr(hand, name, None)
    ]
    start_time = getattr(hand, "startTime", None)
    if not isinstance(start_time, datetime.datetime):
        violations.append(
            Violation(step, "startTime", ERROR, "startTime is not a date", "a datetime", repr(start_time))
        )
    elif start_time.year < 1990:
        violations.append(
            Violation(
                step, "startTime", WARNING, "startTime looks like a default value", "a real date", str(start_time)
            )
        )
    if gametype.get("type") == "tour" and not getattr(hand, "tourNo", None):
        violations.append(Violation(step, "tourNo", ERROR, "A tournament hand needs its tourNo", "present", "missing"))
    return violations


def _check_players(hand: Any) -> list[Violation]:
    step = "readPlayerStacks"
    players = list(getattr(hand, "players", None) or [])
    violations: list[Violation] = []
    if len(players) < 2:
        violations.append(
            Violation(step, "players", ERROR, "Fewer than two players were seated", ">= 2", str(len(players)))
        )
    seats = Counter(player[0] for player in players if player)
    names = Counter(str(player[1]) for player in players if len(player) > 1)
    violations += [
        Violation(step, "players.seat", ERROR, f"Seat {seat} is taken twice", "unique seats", str(count))
        for seat, count in seats.items()
        if count > 1
    ]
    violations += [
        Violation(step, "players.name", ERROR, f"Player '{name}' is seated twice", "unique names", str(count))
        for name, count in names.items()
        if count > 1
    ]
    for player in players:
        seat, name = (player[0], player[1]) if len(player) > 1 else (None, None)
        stack = player[2] if len(player) > 2 else None
        if not name:
            violations.append(
                Violation(step, "players.name", ERROR, f"Seat {seat} has no player name", "a name", repr(name))
            )
        amount = to_decimal(stack)
        if amount is None or amount < 0:
            violations.append(
                Violation(step, "players.stack", ERROR, f"Stack of '{name}' is not an amount", ">= 0", repr(stack))
            )
    maxseats = getattr(hand, "maxseats", None)
    if isinstance(maxseats, int) and maxseats > 0:
        violations += [
            Violation(
                step,
                "players.seat",
                WARNING,
                f"Seat {player[0]} is above the table size",
                f"<= {maxseats}",
                str(player[0]),
            )
            for player in players
            if isinstance(player[0], int) and player[0] > maxseats
        ]
    return violations


def _check_streets(hand: Any, base: Any) -> list[Violation]:
    step = "markStreets"
    expected = STREETS_BY_BASE.get(str(base))
    streets = getattr(hand, "streets", None)
    if expected is None or not isinstance(streets, Mapping):
        return []
    violations: list[Violation] = []
    board = getattr(hand, "board", None) or {}
    for street in expected:
        if board.get(street) and not streets.get(street):
            violations.append(
                Violation(
                    step,
                    f"streets.{street}",
                    WARNING,
                    f"{street} has board cards but no text was marked for it",
                    "the street's text",
                    "empty",
                )
            )
    return violations


def _check_blinds(hand: Any, gametype: Mapping[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    base = gametype.get("base")
    blind_actions = list(_actions(hand).get("BLINDSANTES", []))
    sb = to_decimal(gametype.get("sb") or "0") or Decimal(0)
    bb = to_decimal(gametype.get("bb") or "0") or Decimal(0)
    if base in ("hold", "draw") and (sb > 0 or bb > 0) and not blind_actions:
        violations.append(
            Violation("readBlinds", "actions.BLINDSANTES", WARNING, "No blind or ante was posted", "blinds", "none")
        )
    ante = to_decimal(gametype.get("ante") or "0") or Decimal(0)
    if ante > 0 and not any(len(act) > 1 and act[1] == "ante" for act in blind_actions):
        violations.append(
            Violation(
                "readAntes",
                "actions.BLINDSANTES",
                WARNING,
                f"The game has a {ante} ante, none was posted",
                "antes",
                "none",
            )
        )
    return violations


def _check_button(hand: Any) -> list[Violation]:
    button = getattr(hand, "buttonpos", None)
    if button in (None, 0, "0", ""):
        return []
    seats = {str(player[0]) for player in getattr(hand, "players", None) or [] if player}
    if str(button) not in seats:
        return [
            Violation(
                "readButton",
                "buttonpos",
                WARNING,
                f"The button is on seat {button}, where nobody sits",
                "an occupied seat",
                str(button),
            )
        ]
    return []


def _check_hole_cards(hand: Any, gametype: Mapping[str, Any]) -> list[Violation]:
    expected = hole_card_count(gametype.get("category"))
    if expected is None:
        return []
    violations: list[Violation] = []
    names = set(player_names(hand))
    for player, cards in hole_cards_by_player(hand).items():
        if player not in names:
            violations.append(
                Violation(
                    "readHoleCards",
                    "holecards",
                    ERROR,
                    f"Cards dealt to '{player}', who is not seated",
                    "a seated player",
                    player,
                )
            )
        unique = list(dict.fromkeys(cards))
        if len(unique) > expected:
            violations.append(
                Violation(
                    "readHoleCards",
                    "holecards",
                    ERROR,
                    f"'{player}' holds {len(unique)} cards in a {expected}-card game",
                    str(expected),
                    " ".join(unique),
                )
            )
        elif 0 < len(unique) < expected:
            violations.append(
                Violation(
                    "readHoleCards",
                    "holecards",
                    WARNING,
                    f"Only {len(unique)} of the {expected} cards of '{player}' are known",
                    str(expected),
                    " ".join(unique),
                )
            )
    return violations


def _check_board(hand: Any, base: Any) -> list[Violation]:
    if base != "hold":
        return []
    board = getattr(hand, "board", None) or {}
    violations: list[Violation] = []
    for street, size in BOARD_SIZES.items():
        cards = known_cards(board.get(street) or [])
        if cards and len(cards) != size:
            violations.append(
                Violation(
                    "readCommunityCards",
                    f"board.{street}",
                    ERROR,
                    f"{street} has {len(cards)} cards",
                    str(size),
                    " ".join(cards),
                )
            )
    order = list(BOARD_SIZES)
    for later_index, street in enumerate(order[1:], start=1):
        if board.get(street) and not all(board.get(earlier) for earlier in order[:later_index]):
            violations.append(
                Violation(
                    "readCommunityCards",
                    f"board.{street}",
                    ERROR,
                    f"{street} cards without the streets before it",
                    "flop, then turn, then river",
                    street,
                )
            )
    return violations


def _check_actions(hand: Any) -> list[Violation]:
    step = "readAction"
    names = set(player_names(hand))
    violations: list[Violation] = []
    for street, street_actions in _actions(hand).items():
        for act in street_actions:
            if not act:
                continue
            player = act[0]
            kind = act[1] if len(act) > 1 else None
            reader = "readBlinds" if street == "BLINDSANTES" else step
            if player is not None and str(player) not in names:
                violations.append(
                    Violation(
                        reader,
                        f"actions.{street}",
                        ERROR,
                        f"'{player}' acts without being seated",
                        "a seated player",
                        str(player),
                    )
                )
            if kind not in ACTION_TYPES:
                violations.append(
                    Violation(
                        reader, f"actions.{street}", ERROR, f"Unknown action type '{kind}'", "a known action", str(kind)
                    )
                )
            if kind in {"calls", "bets", "raises", "completes", "ante", "bringin"} | BLIND_TYPES and len(act) > 2:
                amount = to_decimal(act[2])
                if amount is None or amount < 0:
                    violations.append(
                        Violation(
                            reader, f"actions.{street}", ERROR, f"'{player}' {kind} a non-amount", ">= 0", repr(act[2])
                        )
                    )
    if (
        _betting_action_count(hand) == 0
        and not _blind_all_in(list(_actions(hand).get("BLINDSANTES", [])))
        and not is_walk(hand)
    ):
        violations.append(Violation(step, "actions", WARNING, "The hand holds no betting action", "actions", "none"))
    return violations


def _check_collected(hand: Any) -> list[Violation]:
    step = "readCollectPot"
    names = set(player_names(hand))
    collectees = getattr(hand, "collectees", None) or {}
    violations = [
        Violation(
            step, "collectees", ERROR, f"'{player}' collects without being seated", "a seated player", str(player)
        )
        for player in collectees
        if str(player) not in names
    ]
    violations += [
        Violation(step, "collectees", ERROR, f"'{player}' collects a non-amount", ">= 0", repr(amount))
        for player, amount in collectees.items()
        if to_decimal(amount) is None or (to_decimal(amount) or Decimal(0)) < 0
    ]
    if not collectees and not getattr(hand, "cancelled", False):
        violations.append(Violation(step, "collectees", WARNING, "Nobody collects the pot", "a winner", "none"))
    for player in getattr(hand, "shown", None) or ():
        if str(player) not in names:
            violations.append(
                Violation(
                    "readShownCards",
                    "shown",
                    ERROR,
                    f"'{player}' shows cards without being seated",
                    "a seated player",
                    str(player),
                )
            )
    return violations


def check_hand(hand: Any, supported_games: Iterable[Sequence[str]] | None = None) -> list[Violation]:
    """Every way a parsed hand does not meet the contract, in pipeline order."""
    gametype = _gametype(hand)
    base = gametype.get("base")
    violations = check_gametype(gametype or None, supported_games)
    violations += _check_hand_info(hand, gametype)
    violations += _check_players(hand)
    violations += _check_streets(hand, base)
    violations += _check_blinds(hand, gametype)
    violations += _check_button(hand)
    violations += _check_hole_cards(hand, gametype)
    violations += _check_board(hand, base)
    violations += _check_actions(hand)
    violations += _check_collected(hand)
    order = {name: index for index, name in enumerate(STEP_NAMES)}
    return sorted(violations, key=lambda violation: order.get(violation.step, len(order)))


def contract_errors(hand: Any, supported_games: Iterable[Sequence[str]] | None = None) -> list[Violation]:
    """Only the violations that break the contract (severity ``error``)."""
    return [violation for violation in check_hand(hand, supported_games) if violation.severity == ERROR]


# ---------------------------------------------------------------------------
# Whole-hand invariants
# ---------------------------------------------------------------------------


def _all_dealt_cards(hand: Any) -> list[str]:
    cards = [card for dealt in hole_cards_by_player(hand).values() for card in dict.fromkeys(dealt)]
    # Run-it-twice boards (FLOP1, FLOP2...) repeat the shared cards: only the
    # streets of the deal itself are counted.
    for street, street_cards in (getattr(hand, "board", None) or {}).items():
        if not str(street)[-1:].isdigit():
            cards.extend(known_cards(street_cards or []))
    return cards


def _pot_check(hand: Any) -> Check:
    collected = sum(
        (to_decimal(amount) or Decimal(0) for amount in (getattr(hand, "collectees", None) or {}).values()), Decimal(0)
    )
    rake = to_decimal(getattr(hand, "rake", None))
    total = to_decimal(getattr(hand, "totalpot", None))
    if rake is None or total is None:
        return Check("chip conservation", "warn", "The pot or the rake was not computed")
    details = [f"collected {collected} + rake {rake} = {collected + rake}", f"total pot {total}"]
    if rake < 0:
        return Check("chip conservation", "fail", f"Negative rake {rake}", details)
    if abs(collected + rake - total) > POT_TOLERANCE:
        return Check("chip conservation", "fail", "What was collected plus the rake is not the pot", details)
    return Check("chip conservation", "pass", "Collected + rake = total pot", details)


def _betting_order_check(hand: Any) -> Check:
    folded: set[str] = set()
    problems: list[str] = []
    streets = getattr(hand, "actionStreets", None) or list(_actions(hand))
    for street in streets:
        for act in _actions(hand).get(street, []):
            if len(act) < 2:
                continue
            player, kind = str(act[0]), act[1]
            if player in folded and kind != "cashout":
                problems.append(f"{street}: '{player}' {kind} after folding")
            if kind == "folds":
                folded.add(player)
    for player, stack in (getattr(hand, "stacks", None) or {}).items():
        remaining = to_decimal(stack)
        if remaining is not None and remaining < 0:
            problems.append(f"'{player}' committed {-remaining} more than the starting stack")
    if problems:
        return Check("betting order", "warn", "Some actions are not possible as read", problems)
    return Check("betting order", "pass", "No action after a fold, nobody bets more than the stack")


def _winners_check(hand: Any) -> Check:
    folded = {str(player) for player in getattr(hand, "folded", None) or ()}
    collectees = getattr(hand, "collectees", None) or {}
    if not collectees:
        return Check("winners", "warn", "Nobody collects the pot")
    folded_winners = sorted(
        str(player) for player, amount in collectees.items() if str(player) in folded and (to_decimal(amount) or 0) > 0
    )
    if folded_winners:
        return Check("winners", "warn", "A player who folded collects", folded_winners)
    return Check("winners", "pass", f"{len(collectees)} player(s) collect")


def hand_invariants(hand: Any) -> list[Check]:
    """The checks a whole, coherent hand passes."""
    checks = [_pot_check(hand)]
    duplicates = sorted(card for card, count in Counter(_all_dealt_cards(hand)).items() if count > 1)
    checks.append(
        Check("no duplicated card", "fail", "A card is dealt twice", duplicates)
        if duplicates
        else Check("no duplicated card", "pass", "Every known card appears once")
    )
    checks.append(_betting_order_check(hand))
    checks.append(_winners_check(hand))
    hero = getattr(hand, "hero", None)
    if hero:
        found = str(hero) in set(player_names(hand))
        checks.append(
            Check("hero seated", "pass", f"Hero '{hero}' is seated")
            if found
            else Check("hero seated", "warn", f"Hero '{hero}' is not among the seated players")
        )
    total = to_decimal(getattr(hand, "totalpot", None))
    collected = to_decimal(getattr(hand, "totalcollected", None))
    if total is not None and collected is not None and collected > total + POT_TOLERANCE:
        checks.append(
            Check(
                "pot repaired",
                "warn",
                "More was collected than the pot holds: fpdb forces the rake to 0",
                [f"collected {collected}", f"pot {total}"],
            )
        )
    return checks
