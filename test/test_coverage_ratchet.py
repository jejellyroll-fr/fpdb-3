from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import coverage_ratchet  # noqa: E402


def summary(covered_lines, num_statements, covered_branches=0, num_branches=0):
    """Build the subset of a coverage.json file summary the ratchet reads."""
    return {
        "covered_lines": covered_lines,
        "num_statements": num_statements,
        "covered_branches": covered_branches,
        "num_branches": num_branches,
    }


def write_report(path: Path, files: dict[str, dict[str, int]]) -> Path:
    path.write_text(
        json.dumps({"files": {name: {"summary": data} for name, data in files.items()}}),
        encoding="utf-8",
    )
    return path


BASE_FILES = {
    "fpdb_3_legacy/Hand.py": summary(50, 100, 10, 40),
    "fpdb_3_legacy/database_caches.py": summary(20, 100, 5, 50),
    "fpdb_3_legacy/PokerStarsToFpdb.py": summary(90, 100),
    "fpdb_3_legacy/GuiLogView.py": summary(0, 100),
}


@pytest.fixture
def seeded(tmp_path):
    """A report and the baseline seeded from it."""
    report = write_report(tmp_path / "coverage.json", BASE_FILES)
    baseline = tmp_path / "coverage-baseline.json"
    assert coverage_ratchet.main(["--update", str(report), "--baseline", str(baseline)]) == 0
    return report, baseline


def test_domains_claim_files_in_declaration_order():
    # Hand.py matches poker-domain before any later, broader pattern.
    assert coverage_ratchet.domain_of("fpdb_3_legacy/Hand.py") == "poker-domain"
    assert coverage_ratchet.domain_of("fpdb_3_legacy/database_caches.py") == "database"
    assert coverage_ratchet.domain_of("fpdb_3_legacy/PokerStarsToFpdb.py") == "parsers"
    assert coverage_ratchet.domain_of("fpdb_3_legacy/PokerStarsSummary.py") == "tourney-summaries"
    assert coverage_ratchet.domain_of("fpdb_3_legacy/ring_stats/views/table_view.py") == "gui"
    assert coverage_ratchet.domain_of("fpdb/infrastructure/platform/linux.py") == "platform-pkg"
    assert coverage_ratchet.domain_of("fpdb_3_legacy/loggingFpdb.py") == "other"


def test_percentage_counts_branches_like_coverage_does():
    # 50 of 100 statements and 10 of 40 branches is 60 of 140 units, not 50%.
    measure = coverage_ratchet._measure(summary(50, 100, 10, 40))

    assert measure.percent == pytest.approx(100 * 60 / 140)


def test_seeded_baseline_accepts_the_report_it_came_from(seeded, capsys):
    report, baseline = seeded

    assert coverage_ratchet.main(["--check", str(report), "--baseline", str(baseline)]) == 0
    assert "Coverage ratchet holds" in capsys.readouterr().out


def test_rising_coverage_is_accepted(seeded, tmp_path):
    _, baseline = seeded
    improved = dict(BASE_FILES)
    improved["fpdb_3_legacy/database_caches.py"] = summary(95, 100, 45, 50)
    report = write_report(tmp_path / "improved.json", improved)

    assert coverage_ratchet.main(["--check", str(report), "--baseline", str(baseline)]) == 0


def test_falling_module_coverage_fails_the_check(seeded, tmp_path, capsys):
    _, baseline = seeded
    regressed = dict(BASE_FILES)
    regressed["fpdb_3_legacy/Hand.py"] = summary(20, 100, 5, 40)
    report = write_report(tmp_path / "regressed.json", regressed)

    assert coverage_ratchet.main(["--check", str(report), "--baseline", str(baseline)]) == 1

    errors = capsys.readouterr().err
    assert "fpdb_3_legacy/Hand.py" in errors
    assert "poker-domain" in errors


def test_noise_within_tolerance_does_not_fail(seeded, tmp_path):
    _, baseline = seeded
    # One statement of 140 units is 0.7 point on this module but stays inside
    # the tolerance once the whole domain is considered.
    jittered = dict(BASE_FILES)
    jittered["fpdb_3_legacy/PokerStarsToFpdb.py"] = summary(90, 100, 0, 0)
    jittered["fpdb_3_legacy/GuiLogView.py"] = summary(0, 100)
    report = write_report(tmp_path / "jittered.json", jittered)

    assert coverage_ratchet.main(["--check", str(report), "--baseline", str(baseline)]) == 0


def test_os_dependent_domain_gets_a_wider_allowance():
    # The CI runner is Linux while a developer may re-seed from macOS, and the
    # platform factory does not exercise the same implementation on both.
    assert coverage_ratchet.tolerance_for("platform-pkg") > coverage_ratchet.tolerance_for("poker-domain")
    assert coverage_ratchet.tolerance_for("poker-domain") == coverage_ratchet.TOLERANCE


def test_platform_drift_is_tolerated_while_the_same_drop_elsewhere_fails(tmp_path):
    # Proportions matter: platform-pkg is a small share of the corpus, so its
    # drift moves the total by too little to trip the global floor.
    files = {
        "fpdb/infrastructure/platform/factory.py": summary(60, 100),
        "fpdb_3_legacy/PokerStarsToFpdb.py": summary(6000, 10000),
    }
    report = write_report(tmp_path / "coverage.json", files)
    baseline = tmp_path / "baseline.json"
    assert coverage_ratchet.main(["--update", str(report), "--baseline", str(baseline)]) == 0

    # A two-point drop on the platform package: inside its wider allowance.
    drifted = {**files, "fpdb/infrastructure/platform/factory.py": summary(58, 100)}
    assert (
        coverage_ratchet.main(
            ["--check", str(write_report(tmp_path / "drifted.json", drifted)), "--baseline", str(baseline)],
        )
        == 0
    )

    # The same two-point drop on a parser is a real regression.
    regressed = {**files, "fpdb_3_legacy/PokerStarsToFpdb.py": summary(5800, 10000)}
    assert (
        coverage_ratchet.main(
            ["--check", str(write_report(tmp_path / "regressed.json", regressed)), "--baseline", str(baseline)],
        )
        == 1
    )


def test_a_vanished_guarded_module_fails_rather_than_passing_silently(seeded, tmp_path, capsys):
    _, baseline = seeded
    # Splitting Database.py must not drop a floor without anybody noticing.
    moved = {name: data for name, data in BASE_FILES.items() if name != "fpdb_3_legacy/database_caches.py"}
    report = write_report(tmp_path / "moved.json", moved)

    assert coverage_ratchet.main(["--check", str(report), "--baseline", str(baseline)]) == 1
    assert "database_caches.py" in capsys.readouterr().err


def test_a_newly_guarded_module_warns_without_failing(seeded, tmp_path, capsys):
    _, baseline = seeded
    # Well covered, so the warning is what is under test rather than a floor breach.
    added = dict(BASE_FILES)
    added["fpdb_3_legacy/database_ddl.py"] = summary(95, 100)
    report = write_report(tmp_path / "added.json", added)

    assert coverage_ratchet.main(["--check", str(report), "--baseline", str(baseline)]) == 0
    assert "database_ddl.py is newly guarded" in capsys.readouterr().out


def test_the_tracked_baseline_matches_the_declared_domains():
    baseline = json.loads((ROOT / "coverage-baseline.json").read_text(encoding="utf-8"))

    assert set(baseline["domains"]) == {name for name, _ in coverage_ratchet.DOMAINS}
    assert all(
        coverage_ratchet._matches(path, coverage_ratchet.GUARDED_MODULES) for path in baseline["modules"]
    )


def test_check_and_update_are_mutually_exclusive(tmp_path):
    report = write_report(tmp_path / "coverage.json", BASE_FILES)

    assert coverage_ratchet.main([str(report)]) == 2
    assert coverage_ratchet.main(["--check", "--update", str(report)]) == 2


def test_a_missing_report_is_reported_rather_than_crashing(tmp_path, capsys):
    assert coverage_ratchet.main(["--check", str(tmp_path / "absent.json")]) == 2
    assert "not found" in capsys.readouterr().err
