"""Adapter protocol for HTTP/WebSocket poker room capture."""

from __future__ import annotations

from typing import Any, Protocol

from fpdb_3_legacy.http_capture_models import CapturedGameDefinition


class HttpRoomAdapter(Protocol):
    """Contract implemented by room-specific HTTP capture adapters."""

    site: str

    def identify_message(self, payload: Any) -> bool:
        """Return True when payload is a hand/table message this adapter understands."""
        ...

    def extract_hand_id(self, payload: Any) -> str | int | None:
        """Return the stable room hand id if present."""
        ...

    def extract_game_definition(self, payload: Any) -> CapturedGameDefinition | None:
        """Return the FPDB-aligned game definition if the payload identifies a game."""
        ...

    def process_socketio_frame(self, payload: str, *, captured_at: str | None = None, raw_ref: str | None = None) -> Any:
        """Normalize one transport frame into the adapter's process result."""
        ...
