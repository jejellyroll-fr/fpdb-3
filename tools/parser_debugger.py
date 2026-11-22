"""Parser Debugger on the command line (#903).

Shows everything a converter did with a hand-history file: the site and
converter the importer would pick and why, each hand's step trace, the generic
parser contract checked step by step, the whole-hand checks, the log records,
the line coverage and the diagnostics. Nothing is written to a database or to
the configuration.

    python tools/parser_debugger.py path/to/history.txt
    python tools/parser_debugger.py history.txt --site PokerStars --hand 3 --lines
    python tools/parser_debugger.py history.txt --json > report.json
    python tools/parser_debugger.py history.txt --compare report.json
    python tools/parser_debugger.py history.txt --bug-report

The exit status is 0 when every hand parses and no error was found, 1
otherwise, so the command can gate a script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fpdb_3_legacy import Configuration
from fpdb_3_legacy.parser_debug import bug_report, debug_parse_file, diff_reports, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show everything a converter did with a hand-history file.")
    parser.add_argument("path", type=Path, help="the hand-history file")
    parser.add_argument("--site", help="force this site's converter instead of the detection")
    parser.add_argument("--config", type=Path, help="HUD_config.xml to read (default: the user's, read only)")
    parser.add_argument("--hand", type=int, help="show only this hand (0-based index)")
    parser.add_argument("--lines", action="store_true", help="show the line coverage of each hand")
    parser.add_argument("--no-trace", action="store_true", help="skip the line coverage (one parse instead of two)")
    parser.add_argument("--derived", action="store_true", help="add what fpdb would store for each hand")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="print the whole report as JSON")
    output.add_argument("--bug-report", action="store_true", help="print a Markdown report with names replaced")
    output.add_argument("--compare", type=Path, help="print what changed since a report saved with --json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.path.is_file():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 2
    config = Configuration.Config(file=str(args.config)) if args.config else Configuration.Config()
    report = debug_parse_file(args.path, config, args.site, trace_lines=not args.no_trace, derived=args.derived)

    if args.json:
        print(report.to_json())
    elif args.bug_report:
        print(bug_report(report, args.hand))
    elif args.compare:
        previous = json.loads(args.compare.read_text(encoding="utf-8"))
        changes = diff_reports(previous, report.to_dict())
        print("\n".join(changes) if changes else "No change.")
    else:
        print(render_text(report, hand=args.hand, lines=args.lines))
    return 0 if report.verdict == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
