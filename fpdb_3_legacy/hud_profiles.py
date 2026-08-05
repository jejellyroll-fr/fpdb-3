"""Generic HUD profile selection and position scoping.

This module deliberately contains no Qt, room, or game-mode special cases.  A
room integration only has to describe the current table through ``HudContext``;
the same resolver then works for cash, tournaments, AoF, spins, or future
formats.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


def _text(value: Any, default: str = "all") -> str:
    value = str(value or default).strip()
    return value.casefold() if value else default


def _number(value: Any) -> int | None:
    if value in (None, "", "all", "ANY"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class HudContext:
    site: str
    game: str
    game_type: str
    limit_type: str = "all"
    max_seats: int = 0
    players: int = 0
    speed: str = "normal"

    def normalized(self) -> HudContext:
        return HudContext(
            site=_text(self.site),
            game=_text(self.game),
            game_type=_text(self.game_type),
            limit_type=_text(self.limit_type),
            max_seats=int(self.max_seats or 0),
            players=int(self.players or 0),
            speed=_text(self.speed, "normal"),
        )


@dataclass(frozen=True)
class HudProfileRule:
    profile: str
    rule_id: str = ""
    site: str = "all"
    game: str = "all"
    game_type: str = "all"
    limit_type: str = "all"
    seats: int | None = None
    players: int | None = None
    speed: str = "all"
    priority: int = 0
    order: int = field(default=0, compare=False)

    @classmethod
    def from_mapping(cls, values: dict[str, Any], order: int = 0) -> HudProfileRule:
        return cls(
            profile=str(values.get("profile", "")).strip(),
            rule_id=str(values.get("id", values.get("rule_id", ""))).strip(),
            site=_text(values.get("site")),
            game=_text(values.get("game")),
            game_type=_text(values.get("game_type", values.get("type"))),
            limit_type=_text(values.get("limit_type", values.get("limit"))),
            seats=_number(values.get("seats")),
            players=_number(values.get("players")),
            speed=_text(values.get("speed")),
            priority=int(values.get("priority", 0) or 0),
            order=order,
        )

    def matches(self, context: HudContext) -> bool:
        ctx = context.normalized()
        return (
            self._match(self.site, ctx.site)
            and self._match(self.game, ctx.game)
            and self._match(self.game_type, ctx.game_type)
            and self._match(self.limit_type, ctx.limit_type)
            and (self.seats is None or self.seats == ctx.max_seats)
            and (self.players is None or self.players == ctx.players)
            and self._match(self.speed, ctx.speed)
        )

    @staticmethod
    def _match(expected: str, actual: str) -> bool:
        return expected == "all" or expected == actual

    @property
    def specificity(self) -> int:
        textual = (self.site, self.game, self.game_type, self.limit_type, self.speed)
        return sum(value != "all" for value in textual) + int(self.seats is not None) + int(self.players is not None)

    def selector(self) -> tuple[Any, ...]:
        return (self.site, self.game, self.game_type, self.limit_type, self.seats, self.players, self.speed)

    def as_xml_attributes(self) -> dict[str, str]:
        return {
            "id": self.rule_id,
            "site": self.site,
            "game": self.game,
            "game_type": self.game_type,
            "limit": self.limit_type,
            "seats": "all" if self.seats is None else str(self.seats),
            "players": "all" if self.players is None else str(self.players),
            "speed": self.speed,
            "profile": self.profile,
            "priority": str(self.priority),
        }


class HudProfileResolver:
    def __init__(self, rules: Iterable[HudProfileRule] = ()) -> None:
        self.rules = list(rules)

    def matching_rule(self, context: HudContext) -> HudProfileRule | None:
        """The rule that wins for ``context``, or None when none applies.

        Exposed separately from :meth:`resolve` so the preferences preview can
        show *which* rule decided, using the same precedence the HUD uses
        rather than a second implementation of it.
        """
        matches = [rule for rule in self.rules if rule.profile and rule.matches(context)]
        if not matches:
            return None
        # XML order is the final, deterministic tie-breaker.  Earlier rules win,
        # making hand-edited configs stable and easy to reason about.
        return max(matches, key=lambda rule: (rule.specificity, rule.priority, -rule.order))

    def resolve(self, context: HudContext, fallback: str | None = None) -> str | None:
        winner = self.matching_rule(context)
        return fallback if winner is None else winner.profile

    def duplicate_selectors(self) -> list[tuple[Any, ...]]:
        seen: set[tuple[Any, ...]] = set()
        duplicates: list[tuple[Any, ...]] = []
        for rule in self.rules:
            selector = rule.selector()
            if selector in seen and selector not in duplicates:
                duplicates.append(selector)
            seen.add(selector)
        return duplicates


@dataclass(frozen=True)
class HudPositionScope:
    site: str
    game: str
    game_type: str
    max_seats: int
    profile: str
    layout: str

    @classmethod
    def from_hud(cls, hud: Any, profile: str | None = None, layout: str | None = None) -> HudPositionScope:
        params = getattr(hud, "supported_games_parameters", {}) or {}
        stat_set = params.get("game_stat_set") if isinstance(params, dict) else None
        return cls(
            site=str(getattr(hud, "site", "")),
            game=str(getattr(hud, "poker_game", "")),
            game_type=str(getattr(hud, "game_type", getattr(hud, "type", ""))),
            max_seats=_number(getattr(hud, "max", 0)) or 0,
            profile=profile or str(getattr(stat_set, "name", "default")),
            layout=layout or str(getattr(getattr(hud, "layout_set", None), "name", "default")),
        )

    def normalized_tuple(self) -> tuple[Any, ...]:
        return (
            _text(self.site, ""),
            _text(self.game, ""),
            _text(self.game_type, ""),
            int(self.max_seats),
            _text(self.profile, ""),
            _text(self.layout, ""),
        )

    def key(self, seat: str | int, block_id: str | int) -> str:
        # JSON avoids delimiter collisions in room/profile names.
        return json.dumps((*self.normalized_tuple(), str(seat), str(block_id)), separators=(",", ":"))
