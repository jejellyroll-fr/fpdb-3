"""PLO hand texture helpers for legacy automatic notes."""

from __future__ import annotations

from collections import Counter


def normalize_cards(cards) -> list[str]:
    """Return non-empty two-character-ish card strings."""
    normalized = []
    for card in cards or []:
        value = str(card).strip()
        if value and value != "0x":
            normalized.append(value)
    return normalized


def is_plo4(hand) -> bool:
    gametype = getattr(hand, "gametype", {}) or {}
    return gametype.get("base") == "hold" and gametype.get("category") in {"omahahi", "omahahilo"}


def player_hole_cards(hand, player_name: str) -> list[str]:
    try:
        return normalize_cards(hand.join_holecards(player_name, asList=True))
    except Exception:
        return []


def rank_counts(cards) -> Counter[str]:
    return Counter(card[0].upper() for card in normalize_cards(cards) if len(card) >= 2)


def is_aaxx(cards) -> bool:
    return len(normalize_cards(cards)) == 4 and rank_counts(cards).get("A", 0) >= 2


def is_single_paired(cards) -> bool:
    counts = sorted(rank_counts(cards).values())
    return len(normalize_cards(cards)) == 4 and counts == [1, 1, 2]


def is_single_paired_non_aaxx(cards) -> bool:
    return is_single_paired(cards) and not is_aaxx(cards)


def is_rainbow(cards) -> bool:
    normalized = normalize_cards(cards)
    suits = [card[-1].lower() for card in normalized if len(card) >= 2]
    return len(normalized) == 4 and len(set(suits)) == 4


def is_non_aaxx(cards) -> bool:
    return len(normalize_cards(cards)) == 4 and not is_aaxx(cards)
