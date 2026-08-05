"""Filesystem archive helpers for HTTP/WebSocket poker capture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fpdb_3_legacy.http_capture_models import RawCaptureMessage, json_default


class JsonlRawCaptureArchive:
    """Append-only JSONL archive for raw capture messages."""

    def __init__(self, output_dir: str | Path, filename: str = "raw_messages.jsonl") -> None:
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.output_dir / filename
        self._sequence = 0

    def append(self, message: RawCaptureMessage) -> str:
        self._sequence += 1
        message.sequence = self._sequence
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message.to_dict(), ensure_ascii=False, default=json_default))
            handle.write("\n")
        return f"{self.path.name}:{self._sequence}"


class JsonHandArchive:
    """Writes normalized capture envelopes as one JSON file per hand."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_hand(self, hand_data: dict[str, Any]) -> Path:
        hand_id = hand_data["hand_id"]
        filepath = self.output_dir / f"hand_{hand_id}.json"
        save_data = {k: v for k, v in hand_data.items() if not k.startswith("_")}
        with filepath.open("w", encoding="utf-8") as handle:
            json.dump(save_data, handle, indent=2, ensure_ascii=False, default=json_default)
        return filepath
