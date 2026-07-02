"""Rule primitives for legacy automatic player notes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FORCED_ACTIONS = {
    "ante",
    "small blind",
    "big blind",
    "secondsb",
    "both",
    "button blind",
    "bringin",
    "straddle",
}
RAISE_ACTIONS = {"raises", "completes"}
CALL_ACTIONS = {"calls"}
FOLD_ACTIONS = {"folds"}
LATE_STEAL_POSITIONS = {1, 0, "S"}


@dataclass(frozen=True)
class LegacyAction:
    player: str
    action: str
    amount: Any = None
    raw: tuple[Any, ...] | list[Any] | None = None
    index: int = 0

    @property
    def is_raise(self) -> bool:
        return self.action in RAISE_ACTIONS

    @property
    def is_call(self) -> bool:
        return self.action in CALL_ACTIONS

    @property
    def is_fold(self) -> bool:
        return self.action in FOLD_ACTIONS

    @property
    def is_allin(self) -> bool:
        if self.action == "allin":
            return True
        return bool(self.raw and isinstance(self.raw[-1], bool) and self.raw[-1])


@dataclass(frozen=True)
class PreflopContext:
    actions: list[LegacyAction]
    raises: list[LegacyAction]
    player_actions: dict[str, list[LegacyAction]]
    handsplayers: dict[str, dict[str, Any]]
    positions: dict[str, Any]
    hole_cards: dict[str, list[str]]

    @classmethod
    def from_hand(cls, hand) -> PreflopContext:
        preflop_street = hand.actionStreets[1] if len(getattr(hand, "actionStreets", [])) > 1 else "PREFLOP"
        raw_actions = list(getattr(hand, "actions", {}).get(preflop_street, []))
        actions: list[LegacyAction] = []
        player_actions: dict[str, list[LegacyAction]] = {}

        for index, raw in enumerate(raw_actions):
            if len(raw) < 2:
                continue
            action = LegacyAction(
                player=raw[0],
                action=raw[1],
                amount=raw[2] if len(raw) > 2 else None,
                raw=raw,
                index=index,
            )
            actions.append(action)
            if action.action not in FORCED_ACTIONS:
                player_actions.setdefault(action.player, []).append(action)

        raises = [action for action in actions if action.is_raise]
        handsplayers = getattr(hand, "handsplayers", {}) or {}
        players = getattr(hand, "players", []) or []

        return cls(
            actions=actions,
            raises=raises,
            player_actions=player_actions,
            handsplayers=handsplayers,
            positions={player: stats.get("position") for player, stats in handsplayers.items()},
            hole_cards={player[1]: _player_hole_cards(hand, player[1]) for player in players if len(player) > 1},
        )

    @property
    def first_raise(self) -> LegacyAction | None:
        return self.raises[0] if len(self.raises) >= 1 else None

    @property
    def second_raise(self) -> LegacyAction | None:
        return self.raises[1] if len(self.raises) >= 2 else None

    @property
    def third_raise(self) -> LegacyAction | None:
        return self.raises[2] if len(self.raises) >= 3 else None

    def player_made_raise_number(self, player: str, raise_number: int) -> bool:
        return len(self.raises) >= raise_number and self.raises[raise_number - 1].player == player

    def player_vpip(self, player: str) -> bool:
        stats = _player_stats(self, player)
        if stats and stats.get("vpip"):
            return True
        return any(action.is_call or action.is_raise for action in self.player_actions.get(player, []))

    def player_called_first_raise(self, player: str) -> bool:
        first_raise = self.first_raise
        if not first_raise:
            return False
        return any(
            action.index > first_raise.index and action.is_call for action in self.player_actions.get(player, [])
        )

    def player_open_raised_then_folded_to_3bet(self, player: str) -> bool:
        if not self.player_made_raise_number(player, 1) or not self.second_raise:
            return False
        return any(
            action.index > self.second_raise.index and action.is_fold
            for action in self.player_actions.get(player, [])
        )

    def first_raise_is_late_steal(self) -> bool:
        first_raise = self.first_raise
        return bool(first_raise and self.positions.get(first_raise.player) in LATE_STEAL_POSITIONS)

    def has_position_on(self, player: str, other_player: str) -> bool:
        return _position_rank(self.positions.get(player)) < _position_rank(self.positions.get(other_player))


def _player_hole_cards(hand, player_name: str) -> list[str]:
    try:
        return [card for card in hand.join_holecards(player_name, asList=True) if card and card != "0x"]
    except Exception:
        return []


def _position_rank(position: Any) -> int:
    if position == 0:
        return 0
    if position == "S":
        return 1
    if position == "B":
        return 2
    if isinstance(position, int):
        return 10 + position
    return 99


def _player_stats(context: PreflopContext, player: str) -> dict[str, Any] | None:
    return context.handsplayers.get(player)
