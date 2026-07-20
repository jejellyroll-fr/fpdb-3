"""Bridge from normalized HTTP capture envelopes toward Hand.py objects."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO
from typing import Any

from fpdb_3_legacy.http_capture_importability import ImportabilityDecision, evaluate_capture_importability


class CaptureNotImportableError(ValueError):
    """Raised when a normalized capture cannot truthfully become a Hand.py hand."""


@dataclass(frozen=True)
class HandBuildPlan:
    """Describes which Hand.py class should eventually receive an importable capture."""

    hand_class: str
    base: str
    category: str
    decision: ImportabilityDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "hand_class": self.hand_class,
            "base": self.base,
            "category": self.category,
            "importability": self.decision.to_dict(),
        }


class HttpCaptureHandConfig:
    """Small config adapter for constructing Hand.py instances outside Importer."""

    def __init__(self, site_ids: dict[str, int] | None = None, import_parameters: dict[str, Any] | None = None) -> None:
        self.site_ids = site_ids or {}
        self.import_parameters = {
            "saveActions": True,
            "callFpdbHud": False,
            "cacheSessions": False,
            "publicDB": False,
        }
        if import_parameters:
            self.import_parameters.update(import_parameters)

    def get_import_parameters(self) -> dict[str, Any]:
        return dict(self.import_parameters)

    def get_site_id(self, sitename: str) -> int:
        return self.site_ids.get(sitename, self.site_ids.get("default", 1))


class HttpCaptureHHC:
    """Minimal HandHistoryConverter-like object used for HTTP capture hands."""

    def __init__(self, in_path: str = "http-capture") -> None:
        self.in_path = in_path


HAND_CLASS_BY_BASE = {
    "hold": "HoldemOmahaHand",
    "draw": "DrawHand",
    "stud": "StudHand",
}

ACTION_METHOD_BY_TYPE = {
    "ante": "addAnte",
    "small blind": "addBlind",
    "big blind": "addBlind",
    "secondsb": "addBlind",
    "both": "addBlind",
    "calls": "addCall",
    "bets": "addBet",
    "raises": "addRaiseTo",
    "folds": "addFold",
    "checks": "addCheck",
    "collects": "addCollectPot",
    "bringin": "addBringIn",
    "bring-in": "addBringIn",
    "discards": "addDiscard",
    "uncalled": "addUncalled",
}

HAND_CLASS_IMPORTS = {
    "HoldemOmahaHand": "HoldemOmahaHand",
    "DrawHand": "DrawHand",
    "StudHand": "StudHand",
}


def plan_hand_build(hand_data: dict[str, Any]) -> HandBuildPlan:
    """Return the Hand.py target class for an importable capture, or raise."""

    decision = evaluate_capture_importability(hand_data)
    game = hand_data.get("game", {})
    base = game.get("base") or hand_data.get("gametype", {}).get("base")
    category = game.get("category") or hand_data.get("gametype", {}).get("category")
    hand_class = HAND_CLASS_BY_BASE.get(base)

    reasons = list(decision.reasons)
    if not hand_class:
        reasons.append(f"no Hand.py builder for base '{base}'")

    if reasons:
        raise CaptureNotImportableError("; ".join(reasons))

    assert hand_class is not None
    return HandBuildPlan(hand_class=hand_class, base=base, category=category, decision=decision)


def build_hand_input(hand_data: dict[str, Any]) -> dict[str, Any]:
    """Return a Hand.py-oriented projection for an importable normalized capture."""

    plan = plan_hand_build(hand_data)
    return {
        "hand_class": plan.hand_class,
        "site": hand_data.get("site"),
        "hand_id": hand_data.get("hand_id"),
        "table_id": hand_data.get("table_id"),
        "gametype": hand_data.get("gametype", {}),
        "players": hand_data.get("players", []),
        "streets": hand_data.get("streets", {}),
        "actions": hand_data.get("actions", []),
        "steps": hand_data.get("steps", []),
        "showdown": hand_data.get("showdown"),
        "collections": hand_data.get("collections", []),
        "operations": build_hand_operations(hand_data),
    }


def build_hand_operations(hand_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate normalized capture data into an ordered Hand.py operation plan."""

    operations: list[dict[str, Any]] = []

    for player in hand_data.get("players", []):
        operations.append(
            {
                "method": "addPlayer",
                "args": [
                    player.get("seat_idx"),
                    player.get("name"),
                    str(player.get("starting_stack", 0)),
                ],
                "source": "players",
            }
        )

    operations.extend(_build_card_operations(hand_data))

    for action in hand_data.get("actions", []):
        action_type = action.get("type")
        method = ACTION_METHOD_BY_TYPE.get(action_type)
        if not method:
            operations.append(
                {"method": None, "source": "actions", "action": action, "reason": "unsupported action type"}
            )
            continue

        if method == "addBlind":
            operations.append(
                {
                    "method": method,
                    "args": [action.get("player"), action_type, str(action.get("amount", "0"))],
                    "source": "actions",
                }
            )
        elif method == "addAnte":
            operations.append(
                {
                    "method": method,
                    "args": [action.get("player"), str(action.get("amount", "0"))],
                    "source": "actions",
                }
            )
        elif method == "addRaiseTo":
            operations.append(
                {
                    "method": method,
                    "args": [
                        action.get("street"),
                        action.get("player"),
                        str(action.get("to", action.get("amount", "0"))),
                    ],
                    "source": "actions",
                }
            )
        elif method in {"addCall", "addBet"}:
            operations.append(
                {
                    "method": method,
                    "args": [action.get("street"), action.get("player"), str(action.get("amount", "0"))],
                    "source": "actions",
                }
            )
        elif method in {"addFold", "addCheck"}:
            operations.append(
                {
                    "method": method,
                    "args": [action.get("street"), action.get("player")],
                    "source": "actions",
                }
            )
        elif method == "addCollectPot":
            operations.append(
                {
                    "method": method,
                    "args": [action.get("player"), str(action.get("pot", action.get("amount", "0")))],
                    "source": "actions",
                }
            )
        elif method == "addBringIn":
            operations.append(
                {
                    "method": method,
                    "args": [action.get("player"), str(action.get("amount", "0"))],
                    "source": "actions",
                }
            )
        elif method == "addDiscard":
            cards = action.get("cards") or []
            operations.append(
                {
                    "method": method,
                    "args": [action.get("street"), action.get("player"), str(action.get("num", len(cards))), cards],
                    "source": "actions",
                }
            )
        elif method == "addUncalled":
            operations.append(
                {
                    "method": method,
                    "args": [action.get("street"), action.get("player"), str(action.get("amount", "0"))],
                    "source": "actions",
                }
            )

    for collection in _iter_collections(hand_data):
        operations.append(
            {
                "method": "addCollectPot",
                "args": [collection.get("player"), str(collection.get("pot", "0"))],
                "source": collection.get("source", "collections"),
            }
        )

    return operations


def _build_card_operations(hand_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Create Hand.py card operations from canonical board and hole-card fields."""

    operations: list[dict[str, Any]] = []
    game = hand_data.get("game", {})
    base = game.get("base") or hand_data.get("gametype", {}).get("base")

    for street, cards in _community_cards_by_street(hand_data).items():
        operations.append({"method": "setCommunityCards", "args": [street, cards], "source": "community"})

    for entry in _iter_hole_cards(hand_data):
        player = entry.get("player")
        street = entry.get("street") or _default_hole_street(base, hand_data)
        open_cards = entry.get("open") or []
        closed_cards = entry.get("closed") or entry.get("cards") or []
        shown = bool(entry.get("shown", False))
        mucked = bool(entry.get("mucked", False))
        dealt = bool(entry.get("dealt", False))
        if base == "stud":
            operations.append(
                {
                    "method": "addPlayerCards",
                    "args": [player, street],
                    "kwargs": {"open": open_cards, "closed": closed_cards},
                    "source": "holecards",
                }
            )
        else:
            operations.append(
                {
                    "method": "addHoleCards",
                    "args": [street, player],
                    "kwargs": {
                        "open": open_cards,
                        "closed": closed_cards,
                        "shown": shown,
                        "mucked": mucked,
                        "dealt": dealt,
                    },
                    "source": "holecards",
                }
            )

    return operations


def _community_cards_by_street(hand_data: dict[str, Any]) -> dict[str, list[str]]:
    community = hand_data.get("community")
    if isinstance(community, dict):
        return {street: list(cards) for street, cards in community.items() if cards}

    board = hand_data.get("board")
    if not board and hand_data.get("steps"):
        board = hand_data["steps"][-1].get("board")
    board = list(board or [])
    if not board:
        return {}

    streets: dict[str, list[str]] = {}
    if len(board) >= 3:
        streets["FLOP"] = board[:3]
    if len(board) >= 4:
        streets["TURN"] = [board[3]]
    if len(board) >= 5:
        streets["RIVER"] = [board[4]]
    return streets


def _iter_hole_cards(hand_data: dict[str, Any]) -> list[dict[str, Any]]:
    entries = []
    for entry in hand_data.get("holecards", []):
        entries.append(dict(entry))

    for player in hand_data.get("players", []):
        cards = player.get("cards") or player.get("hole_cards")
        if cards:
            entries.append({"player": player.get("name"), "cards": cards, "dealt": player.get("dealt", True)})

    if not entries and hand_data.get("steps"):
        placed = hand_data["steps"][-1].get("placed", {})
        for player, data in placed.items():
            cards = data.get("cards") if isinstance(data, dict) else None
            if cards:
                entries.append({"player": player, "cards": cards, "dealt": True})
    return entries


def _default_hole_street(base: str | None, hand_data: dict[str, Any]) -> str:
    streets = hand_data.get("streets", {})
    hole_streets = streets.get("holeStreets") or []
    if hole_streets:
        return hole_streets[0]
    if base == "draw":
        return "DEAL"
    if base == "stud":
        return "THIRD"
    return "PREFLOP"


def _iter_collections(hand_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized pot collections from known envelope locations."""

    collections = []
    for collection in hand_data.get("collections", []):
        collections.append(
            {
                "player": collection.get("player") or collection.get("name"),
                "pot": collection.get(
                    "pot",
                    collection.get("amount", collection.get("amount_native", collection.get("collected", "0"))),
                ),
                "source": "collections",
            }
        )

    showdown = hand_data.get("showdown") or {}
    for collection in showdown.get("collections", []):
        collections.append(
            {
                "player": collection.get("player") or collection.get("name"),
                "pot": collection.get(
                    "pot",
                    collection.get("amount", collection.get("amount_native", collection.get("collected", "0"))),
                ),
                "source": "showdown.collections",
            }
        )
    return collections


def validate_hand_operations(operations: list[dict[str, Any]]) -> list[str]:
    """Return validation errors for a Hand.py operation plan."""

    errors = []
    for index, operation in enumerate(operations, start=1):
        method = operation.get("method")
        args = operation.get("args", [])
        if not method:
            errors.append(f"operation {index}: missing Hand.py method")
            continue
        if method == "addPlayer":
            if len(args) < 3 or args[1] in (None, ""):
                errors.append(f"operation {index}: addPlayer requires seat, name, chips")
        elif method in {"addCall", "addBet", "addRaiseTo", "addFold", "addCheck"}:
            if len(args) < 2 or args[0] in (None, "", "UNKNOWN") or args[1] in (None, ""):
                errors.append(f"operation {index}: {method} requires street and player")
        elif method in {"addBlind", "addAnte", "addCollectPot"}:
            if len(args) < 2 or args[0] in (None, ""):
                errors.append(f"operation {index}: {method} requires player")
        elif method == "setCommunityCards":
            if len(args) < 2 or args[0] in (None, "", "UNKNOWN"):
                errors.append(f"operation {index}: setCommunityCards requires street and cards")
        elif method in {"addHoleCards", "addPlayerCards"}:
            if len(args) < 2 or args[0] in (None, "") or args[1] in (None, ""):
                errors.append(f"operation {index}: {method} requires street/player and cards")
        elif method == "addBringIn":
            if len(args) < 2 or args[0] in (None, ""):
                errors.append(f"operation {index}: addBringIn requires player")
        elif method == "addDiscard":
            if len(args) < 3 or args[0] in (None, "", "UNKNOWN") or args[1] in (None, ""):
                errors.append(f"operation {index}: addDiscard requires street, player, and count")
    return errors


def execute_hand_operations(hand: Any, operations: list[dict[str, Any]]) -> Any:
    """Apply a validated Hand.py operation plan to a Hand-like object."""

    errors = validate_hand_operations(operations)
    for index, operation in enumerate(operations, start=1):
        method_name = operation.get("method")
        if not method_name:
            continue
        method = getattr(hand, method_name, None)
        if not callable(method):
            errors.append(f"operation {index}: hand object has no callable {method_name}")

    if errors:
        raise CaptureNotImportableError("; ".join(errors))

    for operation in operations:
        method = getattr(hand, operation["method"])
        method(*operation.get("args", []), **operation.get("kwargs", {}))

    return hand


def build_fpdb_hand(
    hand_data: dict[str, Any],
    config: Any | None = None,
    hhc: Any | None = None,
    hand_text: str = "",
) -> Any:
    """Construct a real Hand.py hand from an importable HTTP capture envelope."""

    build_input = build_hand_input(hand_data)
    hand_class = _resolve_hand_class(build_input["hand_class"])
    config = config or HttpCaptureHandConfig()
    hhc = hhc or HttpCaptureHHC()
    gametype = _normalized_gametype(build_input["gametype"])
    hand = hand_class(
        config,
        hhc,
        build_input["site"],
        gametype,
        hand_text,
        builtFrom="HTTP_CAPTURE",
        handid=build_input["hand_id"],
    )
    hand.handid = build_input["hand_id"]
    hand.tablename = str(build_input["table_id"] or "")
    hand.maxseats = gametype.get("maxSeats")
    hand.startTime = _parse_capture_start_time(hand_data.get("timestamp"))
    if hand_data.get("buttonpos") is not None:
        hand.buttonpos = hand_data["buttonpos"]
    execute_hand_operations(hand, build_input["operations"])
    return hand


def render_fpdb_hand(hand: Any) -> str:
    """Return the Hand.py text rendering for replayer/parity checks."""

    output = StringIO()
    hand.totalPot()
    hand.writeHand(output)
    return output.getvalue()


def summarize_fpdb_hand(hand: Any) -> dict[str, Any]:
    """Return a small stable summary useful for HTTP capture import tests."""

    return {
        "hand_id": hand.handid,
        "site": hand.sitename,
        "table": hand.tablename,
        "gametype": dict(hand.gametype),
        "players": list(hand.players),
        "actions": {street: list(actions) for street, actions in hand.actions.items()},
        "board": {street: list(cards) for street, cards in hand.board.items() if cards},
        "holecards": dict(hand.holecards),
        "collected": list(hand.collected),
        "totalcollected": str(hand.totalcollected),
    }


def import_fpdb_hand(
    hand: Any,
    db: Any,
    file_id: int = 0,
    doinsert: bool = True,
    printtest: bool = False,
    starting_hand_id: int | None = None,
) -> Any:
    """Store a built HTTP capture hand through the legacy Hand.py DB pipeline."""

    hand.prepInsert(db, printtest=printtest)
    hand.totalPot()
    hand.assembleHand()
    next_id = starting_hand_id if starting_hand_id is not None else db.nextHandId()
    hand.getHandId(db, next_id)
    hand.updateSessionsCache(db, None, doinsert)
    hand.insertHands(db, file_id, doinsert, printtest)
    hand.updateCardsCache(db, None, doinsert)
    hand.updatePositionsCache(db, None, doinsert)
    hand.updateHudCache(db, doinsert)
    hand.updateTourneyResults(db)
    hand.insertHandsPlayers(db, doinsert, printtest)
    hand.insertHandsActions(db, doinsert, printtest)
    hand.insertHandsStove(db, doinsert)
    hand.insertHandsShowdown(db, doinsert)
    hand.insertHandsCashout(db, doinsert)
    return hand


def _resolve_hand_class(hand_class_name: str) -> Any:
    if hand_class_name not in HAND_CLASS_IMPORTS:
        raise CaptureNotImportableError(f"unsupported Hand.py class '{hand_class_name}'")
    from fpdb_3_legacy.Hand import DrawHand, HoldemOmahaHand, StudHand

    return {
        "HoldemOmahaHand": HoldemOmahaHand,
        "DrawHand": DrawHand,
        "StudHand": StudHand,
    }[hand_class_name]


def _normalized_gametype(gametype: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(gametype)
    normalized.setdefault("type", "ring")
    normalized.setdefault("limitType", "nl")
    normalized.setdefault("currency", "USD")
    normalized["sb"] = Decimal(str(normalized.get("sb", "0")))
    normalized["bb"] = Decimal(str(normalized.get("bb", "0")))
    normalized["ante"] = Decimal(str(normalized.get("ante", "0")))
    normalized.setdefault("mix", "none")
    normalized.setdefault("maxSeats", None)
    return normalized


def _parse_capture_start_time(timestamp: Any) -> datetime.datetime:
    if isinstance(timestamp, datetime.datetime):
        return timestamp.replace(tzinfo=None)
    if isinstance(timestamp, str) and timestamp:
        try:
            return datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.datetime(1970, 1, 1)
