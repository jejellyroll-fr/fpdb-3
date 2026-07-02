#!/usr/bin/env python3
"""Summarize raw HTTP/WebSocket capture archives for room integration."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fpdb_3_legacy.http_capture_registry import get_http_capture_adapter


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def analyze_raw_archive(raw_path: str | Path) -> dict[str, Any]:
    """Return high-level diagnostics for a raw capture JSONL archive."""

    records = _read_jsonl(Path(raw_path))
    sites = Counter()
    message_types = Counter()
    transports = Counter()
    directions = Counter()
    hands_by_site: dict[str, set] = defaultdict(set)
    tables_by_site: dict[str, set] = defaultdict(set)
    games_by_site: dict[str, Counter] = defaultdict(Counter)
    unrecognized = 0

    for record in records:
        site = record.get("site") or "unknown"
        sites[site] += 1
        message_types[record.get("message_type") or "unknown"] += 1
        transports[record.get("transport") or "unknown"] += 1
        directions[record.get("direction") or "unknown"] += 1
        if record.get("hand_id") is not None:
            hands_by_site[site].add(record.get("hand_id"))
        if record.get("table_id") is not None:
            tables_by_site[site].add(record.get("table_id"))

        payload = record.get("payload")
        if record.get("message_type") != "GameState":
            continue
        try:
            adapter = get_http_capture_adapter(site)
            game = adapter.extract_game_definition(payload)
            if game:
                games_by_site[site][f"{game.base}/{game.category}/{game.limit_type}"] += 1
            else:
                unrecognized += 1
        except ValueError:
            unrecognized += 1

    return {
        "records": len(records),
        "sites": dict(sites),
        "message_types": dict(message_types),
        "transports": dict(transports),
        "directions": dict(directions),
        "hands_by_site": {site: len(values) for site, values in hands_by_site.items()},
        "tables_by_site": {site: len(values) for site, values in tables_by_site.items()},
        "games_by_site": {site: dict(counter) for site, counter in games_by_site.items()},
        "unrecognized_records": unrecognized,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a raw HTTP/WebSocket capture JSONL archive.")
    parser.add_argument("raw_path", help="Path to raw_messages.jsonl")
    args = parser.parse_args()

    print(json.dumps(analyze_raw_archive(args.raw_path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
