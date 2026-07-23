#!/usr/bin/env python3
"""Replay raw HTTP/WebSocket capture archives into normalized hand JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fpdb_3_legacy.http_capture_archive import JsonHandArchive
from fpdb_3_legacy.http_capture_registry import get_http_capture_adapter, registered_http_capture_sites


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                records.append(json.loads(line))
    return records


def replay_raw_archive(
    raw_path: str | Path,
    output_dir: str | Path,
    *,
    site: str | None = None,
    include_active: bool = False,
) -> list[Path]:
    """Replay a raw JSONL archive and write normalized hand files."""

    raw_path = Path(raw_path).expanduser()
    hand_archive = JsonHandArchive(output_dir)
    adapters = {}
    written: list[Path] = []
    written_keys = set()

    for record in _read_jsonl(raw_path):
        record_site = site or record.get("site")
        if not record_site:
            continue
        if record.get("message_type") != "GameState":
            continue
        if record_site not in adapters:
            adapters[record_site] = get_http_capture_adapter(record_site)
        adapter = adapters[record_site]
        payload = record.get("payload")
        if not isinstance(payload, str):
            continue
        sequence = record.get("sequence")
        raw_ref = f"{raw_path.name}:{sequence}" if sequence is not None else raw_path.name
        result = adapter.process_socketio_frame(
            payload,
            captured_at=record.get("captured_at"),
            raw_ref=raw_ref,
        )
        for hand_data in result.finalized_hands:
            key = (hand_data.get("site"), hand_data.get("hand_id"))
            if key not in written_keys:
                written.append(hand_archive.write_hand(hand_data))
                written_keys.add(key)

    if include_active:
        for adapter in adapters.values():
            for hand_data in getattr(adapter, "active_hands", {}).values():
                key = (hand_data.get("site"), hand_data.get("hand_id"))
                if key not in written_keys:
                    written.append(hand_archive.write_hand(hand_data))
                    written_keys.add(key)

    return written


def replay_swc_raw_archive(
    raw_path: str | Path,
    output_dir: str | Path,
    *,
    include_active: bool = False,
) -> list[Path]:
    """Replay a SwC raw JSONL archive and write normalized hand files."""

    return replay_raw_archive(raw_path, output_dir, site="SealsWithClubs", include_active=include_active)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay raw HTTP/WebSocket capture JSONL into normalized hand JSON.")
    parser.add_argument("raw_path", help="Path to raw_messages.jsonl")
    parser.add_argument("--output-dir", required=True, help="Directory for normalized hand JSON")
    parser.add_argument(
        "--site",
        help=f"Force adapter site instead of using each JSONL record. Registered: {', '.join(registered_http_capture_sites())}",
    )
    parser.add_argument("--include-active", action="store_true", help="Write active/incomplete hands too")
    args = parser.parse_args()

    written = replay_raw_archive(args.raw_path, args.output_dir, site=args.site, include_active=args.include_active)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
