"""The spot of each hero decision in a whole-hand review, and decisions grouped by spot (#448).

A study tool solves a spot, not a hand: "my big blind against the button's
open, single-raised pot, on the turn, at an SPR of 2 to 4, on a two-tone
board". This module names the spot of each of the hero's decisions in a
version 2 review (:func:`fpdb_3_legacy.hand_review_payload.build_full_review`)
from the review itself, so a parsed hand and a stored one name it the same,
and groups the decisions of many hands by it.

A spot is:

- ``game`` and ``table_size``: a solver solves one game at one table size, so
  NL and PLO, or six- and nine-handed, are never the same spot;
- ``street``;
- ``pot_type``: from the raises before the decision preflop, and from the whole
  preflop on later streets, in the situation model's words (``unopened``,
  ``limped``, ``single_raised``, ``three_bet``, ``four_bet_plus``);
- ``hero``, ``aggressor``: the hero's seat and the last preflop raiser's (none
  in a limped pot), as the document names seats;
- ``players``: how many were still in as the street began;
- ``spr``: the stack-to-pot band as the street began, the hero's stack capped
  by the deepest opponent's over the pot (postflop only);
- ``board_rank``, ``board_suits``, ``board_pairing``: the board so far, in the
  board-feature words the research studies use (postflop only).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from fpdb_3_legacy.board_features import pairing, rank_bucket, suit_structure
from fpdb_3_legacy.spr_buckets import SPR_SCALE, spr_bucket_of

__all__ = ["SPOT_FIELDS", "decision_spots", "spot_groups"]

SPOT_FIELDS = (
    "game",
    "table_size",
    "street",
    "pot_type",
    "hero",
    "aggressor",
    "players",
    "spr",
    "board_rank",
    "board_suits",
    "board_pairing",
)

_POT_TYPES = ("limped", "single_raised", "three_bet", "four_bet_plus")


def _pot_type(preflop: Sequence[Any], before: int | None = None) -> str:
    """The pot's shape from the preflop actions (all of them, or those before *before*)."""
    actions = preflop if before is None else preflop[:before]
    raises = sum(1 for action in actions if action.kind == "raises")
    if raises:
        return _POT_TYPES[min(raises, len(_POT_TYPES) - 1)]
    return "limped" if any(action.kind == "calls" for action in actions) else "unopened"


def _aggressor(preflop: Sequence[Any], before: int | None = None) -> str | None:
    actions = preflop if before is None else preflop[:before]
    raisers = [action.position for action in actions if action.kind == "raises"]
    return raisers[-1] if raisers else None


def _spr(street: Any, hero: str) -> str:
    stacks = dict(street.stacks_start)
    if hero not in stacks or street.pot_start <= 0:
        return spr_bucket_of(None)
    others = [stack for position, stack in stacks.items() if position != hero]
    effective = min(stacks[hero], max(others, default=stacks[hero]))
    return spr_bucket_of(int(effective * SPR_SCALE / street.pot_start))


def decision_spots(review: Any) -> list[dict[str, Any]]:
    """Each hero decision of a version 2 *review*: ``{"street", "index", "spot"}``, in order."""
    if not review.streets:
        return []
    preflop = review.streets[0].actions
    found = []
    for street in review.streets:
        for action in street.actions:
            if not action.is_hero:
                continue
            first_street = street.name == "PREFLOP"
            before = action.index if first_street else None
            spot: dict[str, Any] = {
                # Codex (#639): a mixed batch must not merge NL and PLO, or six- and nine-handed, spots.
                "game": review.game,
                "table_size": review.table_size,
                "street": street.name,
                "pot_type": _pot_type(preflop, before),
                "hero": review.hero_position,
                "aggressor": _aggressor(preflop, before),
                "players": len(street.stacks_start),
                "spr": None if first_street else _spr(street, review.hero_position),
                "board_rank": None if first_street else rank_bucket(street.board),
                "board_suits": None if first_street else suit_structure(street.board),
                "board_pairing": None if first_street else pairing(street.board),
            }
            found.append({"street": street.name, "index": action.index, "spot": spot})
    return found


def spot_groups(reviews: Iterable[Any]) -> list[dict[str, Any]]:
    """The hero decisions of *reviews* grouped by spot, the most frequent spot first.

    Each group is ``{"spot", "count", "decisions"}``; a decision is
    ``{"hand_id", "street", "index"}``, ``hand_id`` as the document's hands give it.
    """
    groups: dict[tuple, dict[str, Any]] = {}
    for review in reviews:
        hand_id = (
            str(review.fpdb_hand_id) if review.fpdb_hand_id is not None else f"{review.site}#{review.site_hand_no}"
        )
        for decision in decision_spots(review):
            key = tuple(decision["spot"][field] for field in SPOT_FIELDS)
            group = groups.setdefault(key, {"spot": decision["spot"], "count": 0, "decisions": []})
            group["count"] += 1
            group["decisions"].append({"hand_id": hand_id, "street": decision["street"], "index": decision["index"]})
    return sorted(
        groups.values(), key=lambda group: (-group["count"], [str(value) for value in group["spot"].values()])
    )
