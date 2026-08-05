"""Build and inspect Hand.py hands from normalized HTTP capture JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fpdb_3_legacy.http_capture_hand_builder import build_fpdb_hand, render_fpdb_hand, summarize_fpdb_hand
from fpdb_3_legacy.http_capture_models import json_default


def build_capture_file(path: str | Path) -> Any:
    """Build a real Hand.py instance from a normalized capture JSON file."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return build_fpdb_hand(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Hand.py hand from normalized HTTP capture JSON")
    parser.add_argument("path", help="Path to a normalized capture JSON file")
    parser.add_argument("--render", action="store_true", help="Print Hand.py writeHand output instead of JSON summary")
    args = parser.parse_args(argv)

    hand = build_capture_file(args.path)
    if args.render:
        print(render_fpdb_hand(hand), end="")
    else:
        print(json.dumps(summarize_fpdb_hand(hand), default=json_default, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
