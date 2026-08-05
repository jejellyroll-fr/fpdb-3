"""Refresh normalized HTTP capture hands with the current reconstruction logic."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from fpdb_3_legacy.http_capture_actions import infer_snapshot_street, reconstruct_snapshot_actions
from fpdb_3_legacy.http_capture_diff import diff_snapshot_steps
from fpdb_3_legacy.http_capture_importability import evaluate_capture_importability
from fpdb_3_legacy.http_capture_models import json_default, swc_game_definition


def refresh_normalized_hand(hand_data: dict[str, Any]) -> dict[str, Any]:
    """Recompute derived snapshot fields on a normalized capture hand."""

    _refresh_game_definition(hand_data)

    steps = hand_data.get("steps", [])
    previous_step = None
    for step in steps:
        step["street"] = infer_snapshot_street(hand_data, step)
        step["diff"] = diff_snapshot_steps(previous_step, step)
        previous_step = step

    hand_data.pop("collections", None)
    reconstruct_snapshot_actions(hand_data)
    hand_data.setdefault("metadata", {})["importability"] = evaluate_capture_importability(hand_data).to_dict()
    return hand_data


def _refresh_game_definition(hand_data: dict[str, Any]) -> None:
    game_type = str(hand_data.get("game_type", ""))
    match = re.search(r"Type\s+(\d+)", game_type)
    if not match:
        return

    definition = swc_game_definition(int(match.group(1)))
    if definition.base == "unknown":
        return

    previous_gametype = hand_data.get("gametype", {})
    hand_data["game"] = definition.to_capture_dict()
    hand_data["streets"] = definition.street_profile.to_dict()
    hand_data["gametype"] = definition.gametype(
        game_type=previous_gametype.get("type", "ring"),
        currency=previous_gametype.get("currency", "mBTC"),
        small_blind=previous_gametype.get("sb", 0),
        big_blind=previous_gametype.get("bb", 0),
        ante=previous_gametype.get("ante", 0),
        max_seats=previous_gametype.get("maxSeats"),
    )


def refresh_file(path: str | Path, output_dir: str | Path | None = None) -> Path:
    """Refresh one normalized hand JSON file and write the result."""

    source = Path(path)
    hand_data = json.loads(source.read_text(encoding="utf-8"))
    refreshed = refresh_normalized_hand(hand_data)
    target = Path(output_dir) / source.name if output_dir else source
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(refreshed, default=json_default, indent=2, sort_keys=True), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh normalized HTTP capture hand JSON files")
    parser.add_argument("paths", nargs="+", help="Normalized hand JSON files or directories containing hand_*.json")
    parser.add_argument("--output-dir", help="Write refreshed files to this directory instead of overwriting")
    args = parser.parse_args(argv)

    files: list[Path] = []
    for raw_path in args.paths:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(path.glob("hand_*.json")))
        else:
            files.append(path)

    for file_path in files:
        print(refresh_file(file_path, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
