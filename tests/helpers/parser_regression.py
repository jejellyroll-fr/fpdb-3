"""Stable fingerprints for file-by-file hand-history parser regression tests."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal


def _stable(value):
    """Convert parser values to deterministic, JSON-serializable data."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _stable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, set):
        return sorted(_stable(item) for item in value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def hand_fingerprint(hand) -> dict:
    """Select parser outputs whose drift changes the meaning of an imported hand."""
    gametype_keys = ("type", "base", "category", "limitType", "currency", "sb", "bb", "ante", "mix")
    gametype = {key: hand.gametype.get(key) for key in gametype_keys}
    return _stable(
        {
            "handid": hand.handid,
            "tour_no": getattr(hand, "tourNo", None),
            "table": getattr(hand, "tablename", None),
            "button": getattr(hand, "buttonpos", None),
            "gametype": gametype,
            "players": hand.players,
            "board": hand.board,
            "actions": hand.actions,
            "collectees": hand.collectees,
            "totalpot": hand.totalpot,
            "rake": hand.rake,
        }
    )


def file_snapshot(hands) -> list[dict]:
    """Return the ordered semantic snapshot for every hand parsed from one file."""
    return [hand_fingerprint(hand) for hand in hands]


def snapshot_digest(snapshot: list[dict]) -> str:
    """Hash a canonical snapshot for compact manifests and reviewable failures."""
    payload = json.dumps(snapshot, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
