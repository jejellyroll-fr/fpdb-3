#!/usr/bin/env python3
"""Enforce the tracked coverage floors of the project.

The ratchet reads a ``coverage.json`` report and compares it against the floors
recorded in ``coverage-baseline.json``. Coverage may rise freely; it may not
fall. Floors are re-seeded with ``--update`` once a change genuinely raises
them, exactly like the Ruff and technical-debt ratchets: an entry leaves the
baseline upwards, never downwards.

Percentages are the branch-aware figures coverage.py itself reports, so the
numbers printed here match ``pytest --cov-report=term``.

One case legitimately lowers a floor: extracting a well-covered domain out of a
guarded module leaves a less-covered remainder, so its percentage falls even
though nothing became untested. Before re-seeding such a change, check that the
covered units of the source and the new module together are no fewer than the
source had on its own -- the percentage moved, the coverage did not.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = ROOT / "coverage-baseline.json"
DEFAULT_REPORT = ROOT / "coverage.json"

# Nondeterminism allowance, in percentage points. Splitting the suite into two
# passes already moves the total by a few lines, and a run is not bit-stable
# across Python patch releases. Kept small on purpose: it absorbs noise, it is
# not a licence to erode.
TOLERANCE = 0.5

# Coverage that genuinely depends on the operating system gets a wider
# allowance, because the ratchet is enforced on Linux while the floors are
# seeded by a developer on macOS or Windows. The values below are not guesses:
# they come from comparing a Linux CI artefact against the floors seeded on
# macOS for the same commit, which showed
#
#   live-capture -1.0   Hand.py -1.1   hud -0.5   other -0.5   poker-domain -0.3
#
# and everything else inside the ordinary tolerance. `platform-pkg` keeps the
# widest allowance: its factory selects one implementation per OS outright.
#
# Re-measure with:  gh run download <run> -n coverage-report
#                   python tools/coverage_ratchet.py --check <that>/coverage.json
EXTRA_TOLERANCE: dict[str, float] = {
    "platform-pkg": 3.0,
    "live-capture": 1.5,
    "fpdb_3_legacy/Hand.py": 1.5,
    "hud": 1.0,
    "other": 1.0,
    "poker-domain": 1.0,
}

# Domains, in match order: the first pattern that matches a file owns it. The
# split follows the risk boundaries of the codebase rather than the directory
# layout, so that the large, visibly-broken-when-wrong GUI cannot dilute the
# floors of the code that silently computes wrong numbers.
DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "poker-domain",
        (
            "fpdb_3_legacy/Hand.py",
            "fpdb_3_legacy/DerivedStats.py",
            "fpdb_3_legacy/Card.py",
            "fpdb_3_legacy/Deck.py",
            "fpdb_3_legacy/Stats.py",
            "fpdb_3_legacy/stats_*.py",
            "fpdb_3_legacy/equity.py",
            "fpdb_3_legacy/aof_equity.py",
            "fpdb_3_legacy/aof_ranges.py",
        ),
    ),
    (
        "database",
        (
            "fpdb_3_legacy/Database.py",
            "fpdb_3_legacy/database_*.py",
            "fpdb_3_legacy/SQL.py",
            "fpdb_3_legacy/sql_*.py",
            "fpdb_3_legacy/db_*.py",
            "fpdb_3_legacy/dialects.py",
        ),
    ),
    (
        "import",
        (
            "fpdb_3_legacy/Importer.py",
            "fpdb_3_legacy/IdentifySite.py",
            "fpdb_3_legacy/ImprovedErrorHandler.py",
            "fpdb_3_legacy/detect_site.py",
        ),
    ),
    ("parsers", ("fpdb_3_legacy/*ToFpdb.py", "fpdb_3_legacy/iPoker/*.py")),
    ("tourney-summaries", ("fpdb_3_legacy/*Summary.py", "fpdb_3_legacy/TourneySummary.py")),
    (
        "hud",
        (
            "fpdb_3_legacy/Aux_*.py",
            "fpdb_3_legacy/HUD*.py",
            "fpdb_3_legacy/Hud*.py",
            "fpdb_3_legacy/pt4hud.py",
            "fpdb_3_legacy/pt4_adapter/*.py",
            "fpdb_3_legacy/Mucked.py",
            "fpdb_3_legacy/*Tables.py",
            "fpdb_3_legacy/TableWindow.py",
        ),
    ),
    (
        "live-capture",
        (
            "fpdb_3_legacy/*capture*.py",
            "fpdb_3_legacy/coinpoker_*.py",
            "fpdb_3_legacy/swc_*.py",
        ),
    ),
    (
        "gui",
        (
            "fpdb_3_legacy/Gui*.py",
            "fpdb_3_legacy/Modern*.py",
            "fpdb_3_legacy/fpdb.pyw",
            "fpdb_3_legacy/Filters.py",
            "fpdb_3_legacy/Theme*.py",
            "fpdb_3_legacy/*Popup*.py",
            "fpdb_3_legacy/ring_stats/*.py",
            "fpdb_3_legacy/ring_stats/**/*.py",
            "fpdb_3_legacy/ConfigReloadWidget.py",
        ),
    ),
    (
        "maintenance-scripts",
        (
            "fpdb_3_legacy/backfill_*.py",
            "fpdb_3_legacy/fix_*.py",
        ),
    ),
    ("platform-pkg", ("fpdb/*.py", "fpdb/**/*.py")),
    ("other", ("*",)),
)

# Modules guarded on their own, on top of their domain floor. These are the
# places where a wrong number reaches the user without raising an exception:
# the cache writers feeding the HUD, hand reconstruction, the import entry
# point and the configuration reader/writer.
GUARDED_MODULES: tuple[str, ...] = (
    "fpdb_3_legacy/Database.py",
    "fpdb_3_legacy/database_*.py",
    "fpdb_3_legacy/Hand.py",
    "fpdb_3_legacy/DerivedStats.py",
    "fpdb_3_legacy/aof_equity.py",
    "fpdb_3_legacy/aof_ranges.py",
    "fpdb_3_legacy/equity.py",
    "fpdb_3_legacy/equity_async.py",
    "fpdb_3_legacy/stats_*.py",
    "fpdb_3_legacy/Importer.py",
    "fpdb_3_legacy/Configuration.py",
)


@dataclass(frozen=True)
class Measure:
    """Coverage of one file or one group of files."""

    covered: int
    total: int

    def __add__(self, other: Measure) -> Measure:
        return Measure(self.covered + other.covered, self.total + other.total)

    @property
    def percent(self) -> float:
        """Branch-aware coverage, matching what coverage.py reports."""
        if self.total == 0:
            return 100.0
        return 100.0 * self.covered / self.total


EMPTY = Measure(0, 0)


def _measure(summary: dict[str, int]) -> Measure:
    """Read one file summary as covered/total units, branches included."""
    covered = summary["covered_lines"] + summary["covered_branches"]
    total = summary["num_statements"] + summary["num_branches"]
    return Measure(covered, total)


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def domain_of(path: str) -> str:
    """Return the domain owning *path*; the first matching domain wins."""
    for name, patterns in DOMAINS:
        if _matches(path, patterns):
            return name
    return "other"


def read_report(report_path: Path) -> dict[str, Measure]:
    """Read a coverage.json report as one measure per file."""
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    return {path: _measure(entry["summary"]) for path, entry in payload["files"].items()}


def collect(files: dict[str, Measure]) -> tuple[Measure, dict[str, Measure], dict[str, Measure]]:
    """Aggregate a report into (total, per-domain, per-guarded-module) measures."""
    total = EMPTY
    domains: dict[str, Measure] = {name: EMPTY for name, _ in DOMAINS}
    modules: dict[str, Measure] = {}
    for path, measure in files.items():
        total += measure
        domains[domain_of(path)] += measure
        if _matches(path, GUARDED_MODULES):
            modules[path] = measure
    return total, domains, modules


def _floor(percent: float) -> float:
    """Round a measured percentage down to a tenth of a point."""
    return int(percent * 10) / 10


def render_baseline(files: dict[str, Measure]) -> str:
    """Render the baseline document for the current report."""
    total, domains, modules = collect(files)
    payload = {
        "_comment": (
            "Coverage floors enforced by tools/coverage_ratchet.py. Branch-aware "
            "percentages, as reported by coverage.py. Regenerate with "
            "python tools/coverage_ratchet.py --update coverage.json after a change "
            "that genuinely raises coverage."
        ),
        "total": _floor(total.percent),
        "domains": {name: _floor(domains[name].percent) for name, _ in DOMAINS},
        "modules": {path: _floor(modules[path].percent) for path in sorted(modules)},
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def tolerance_for(label: str) -> float:
    """Return the allowance granted to *label*, wider for OS-dependent domains."""
    return TOLERANCE + EXTRA_TOLERANCE.get(label, 0.0)


def _report_lines(label: str, actual: Measure, floor: float) -> str:
    slack = actual.percent - floor
    return f"  {label:<44} {actual.percent:6.1f}%  floor {floor:5.1f}%  {slack:+5.1f}"


def check(files: dict[str, Measure], baseline: dict) -> tuple[list[str], list[str], list[str]]:
    """Compare a report against the baseline.

    Returns (failures, warnings, report_lines).
    """
    total, domains, modules = collect(files)
    failures: list[str] = []
    warnings: list[str] = []
    lines: list[str] = []

    def verify(label: str, actual: Measure, floor: float) -> None:
        lines.append(_report_lines(label, actual, floor))
        allowance = tolerance_for(label)
        if actual.percent < floor - allowance:
            failures.append(
                f"{label}: {actual.percent:.1f}% is below the {floor:.1f}% floor (tolerance {allowance:.1f} point)",
            )

    lines.append("Domains")
    for name, _ in DOMAINS:
        verify(name, domains[name], baseline["domains"].get(name, 0.0))

    lines.append("Guarded modules")
    baselined = baseline.get("modules", {})
    for path in sorted(modules):
        if path not in baselined:
            warnings.append(f"{path} is newly guarded; re-seed with --update to record its floor")
            continue
        verify(path, modules[path], baselined[path])
    for path in sorted(baselined):
        if path not in modules:
            failures.append(
                f"{path} is in the baseline but absent from the report: renamed, deleted "
                f"or no longer imported. Re-seed with --update once the move is intended.",
            )

    lines.append("Total")
    verify("TOTAL", total, baseline["total"])
    return failures, warnings, lines


def main(argv: list[str] | None = None) -> int:
    """Verify the tracked coverage floors, or re-seed them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report",
        nargs="?",
        type=Path,
        default=DEFAULT_REPORT,
        help="coverage.json report to read (default: ./coverage.json)",
    )
    parser.add_argument("--check", action="store_true", help="fail when coverage fell below a floor")
    parser.add_argument("--update", action="store_true", help="re-seed the floors from the report")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="baseline document to read or write",
    )
    args = parser.parse_args(argv)

    if args.update == args.check:
        print("Choose exactly one of --check or --update", file=sys.stderr)
        return 2
    if not args.report.exists():
        print(
            f"{args.report} not found; produce it with python -m coverage json -o {args.report}",
            file=sys.stderr,
        )
        return 2

    files = read_report(args.report)

    if args.update:
        args.baseline.write_text(render_baseline(files), encoding="utf-8")
        print(f"Wrote {args.baseline.relative_to(ROOT) if args.baseline.is_relative_to(ROOT) else args.baseline}")
        return 0

    if not args.baseline.exists():
        print(f"{args.baseline} not found; seed it with --update", file=sys.stderr)
        return 2

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    failures, warnings, lines = check(files, baseline)
    print("\n".join(lines))
    for warning in warnings:
        print(f"warning: {warning}")
    if failures:
        print("\nCoverage ratchet failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nAdd tests for the code you changed. Re-seed with "
            "python tools/coverage_ratchet.py --update coverage.json only when coverage rose.",
            file=sys.stderr,
        )
        return 1
    print("\nCoverage ratchet holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
