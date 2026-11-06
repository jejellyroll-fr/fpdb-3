#!/usr/bin/env python3
"""Turn a coverage.py JSON report into a shields.io endpoint badge.

The CI coverage job runs this on each push to ``development`` and commits the
result to the orphan ``badges`` branch, where the README badge reads it through
``https://img.shields.io/endpoint?url=<raw coverage.json>``. No coverage service
or extra secret is involved.

The percentage is the branch-aware total coverage.py reports, the same figure
``coverage report`` prints and ``tools/coverage_ratchet.py`` enforces floors on.

Usage: ``python tools/coverage_badge.py coverage.json badge.json``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# shields.io's own scale, from the lowest percentage each colour starts at.
COLOURS = (
    (90.0, "brightgreen"),
    (80.0, "green"),
    (70.0, "yellowgreen"),
    (60.0, "yellow"),
    (50.0, "orange"),
)


def colour_for(percent: float) -> str:
    """Return the shields.io colour name for a coverage percentage."""
    for floor, colour in COLOURS:
        if percent >= floor:
            return colour
    return "red"


def total_percent(report: dict) -> float:
    """Read the total percentage out of a coverage.py JSON report."""
    try:
        return float(report["totals"]["percent_covered"])
    except (KeyError, TypeError, ValueError) as exc:
        msg = "not a coverage.py JSON report: no totals.percent_covered"
        raise ValueError(msg) from exc


def badge(percent: float) -> dict[str, object]:
    """Build the shields.io endpoint document for a coverage percentage."""
    if not 0.0 <= percent <= 100.0:
        msg = f"coverage must be between 0 and 100, got {percent}"
        raise ValueError(msg)
    return {
        "schemaVersion": 1,
        "label": "coverage",
        # Rounded down: 89.96 % must not be shown as a 90 % it did not reach.
        "message": f"{int(percent)}%",
        "color": colour_for(percent),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", type=Path, help="coverage.py JSON report (coverage json)")
    parser.add_argument("output", type=Path, help="where to write the shields.io endpoint JSON")
    args = parser.parse_args(argv)

    try:
        percent = total_percent(json.loads(args.report.read_text(encoding="utf-8")))
        document = badge(percent)
    except (OSError, ValueError) as exc:
        print(f"coverage_badge: {exc}", file=sys.stderr)
        return 1

    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"coverage badge: {document['message']} ({document['color']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
