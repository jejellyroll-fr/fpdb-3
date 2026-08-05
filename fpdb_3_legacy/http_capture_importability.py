"""Importability gate for normalized HTTP capture envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportabilityDecision:
    """Decision explaining whether a normalized capture can become a Hand.py hand."""

    importable: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "importable" if self.importable else "capture_only"

    def to_dict(self) -> dict[str, Any]:
        return {"importable": self.importable, "status": self.status, "reasons": list(self.reasons)}


def evaluate_capture_importability(hand_data: dict[str, Any]) -> ImportabilityDecision:
    """Apply the first importability gate before attempting Hand.py construction."""

    reasons = []
    game = hand_data.get("game", {})
    metadata = hand_data.get("metadata", {})

    if game.get("base") == "ofc":
        if not hand_data.get("ofc_rounds"):
            reasons.append("OFC placement rounds are missing")
        validation = hand_data.get("ofc_validation") or {}
        if validation.get("errors"):
            reasons.append("OFC layout validation failed")
        reasons.append("OFC requires a dedicated importer/replayer")
        return ImportabilityDecision(importable=False, reasons=tuple(reasons))

    if not game.get("fpdb_supported"):
        reasons.append("game is not supported by FPDB Hand.py yet")

    if metadata.get("state_model") == "snapshot":
        reconstruction = metadata.get("action_reconstruction", {})
        if reconstruction.get("status") != "complete":
            reasons.append("snapshot action reconstruction is incomplete")
        if not hand_data.get("actions"):
            reasons.append("snapshot actions have not been reconstructed")

    if not hand_data.get("players"):
        reasons.append("players are missing")

    if not hand_data.get("steps") and not hand_data.get("actions"):
        reasons.append("no normalized steps or actions are available")

    has_collection_action = any(action.get("type") == "collects" for action in hand_data.get("actions", []))
    showdown = hand_data.get("showdown") or {}
    if not hand_data.get("collections") and not showdown.get("collections") and not has_collection_action:
        reasons.append("pot collections are missing")

    return ImportabilityDecision(importable=not reasons, reasons=tuple(reasons))
