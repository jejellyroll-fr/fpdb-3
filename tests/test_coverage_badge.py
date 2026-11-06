"""tools/coverage_badge.py: the shields.io endpoint behind the README badge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.coverage_badge import badge, colour_for, main, total_percent


@pytest.mark.parametrize(
    ("percent", "colour"),
    [
        (100.0, "brightgreen"),
        (90.0, "brightgreen"),
        (89.99, "green"),
        (80.0, "green"),
        (75.0, "yellowgreen"),
        (60.0, "yellow"),
        (55.0, "orange"),
        (49.9, "red"),
        (0.0, "red"),
    ],
)
def test_the_colour_follows_shields_own_scale(percent: float, colour: str) -> None:
    assert colour_for(percent) == colour


def test_the_badge_rounds_down_so_it_never_claims_a_threshold_it_missed() -> None:
    assert badge(89.96) == {"schemaVersion": 1, "label": "coverage", "message": "89%", "color": "green"}


@pytest.mark.parametrize("percent", [-0.1, 100.1])
def test_a_percentage_out_of_range_is_refused(percent: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        badge(percent)


def test_the_total_is_read_from_a_coverage_report() -> None:
    assert total_percent({"totals": {"percent_covered": 71.234}}) == pytest.approx(71.234)


@pytest.mark.parametrize("report", [{}, {"totals": {}}, {"totals": {"percent_covered": "n/a"}}, []])
def test_something_that_is_not_a_coverage_report_is_refused(report: object) -> None:
    with pytest.raises(ValueError, match="not a coverage.py JSON report"):
        total_percent(report)  # type: ignore[arg-type]


def test_main_writes_the_endpoint_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": 64.5}}), encoding="utf-8")
    output = tmp_path / "badge.json"

    assert main([str(report), str(output)]) == 0

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": "64%",
        "color": "yellow",
    }
    assert "64% (yellow)" in capsys.readouterr().out


def test_main_fails_without_writing_when_the_report_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "badge.json"

    assert main([str(tmp_path / "missing.json"), str(output)]) == 1

    assert not output.exists()
    assert "coverage_badge:" in capsys.readouterr().err


def test_ci_publishes_the_badge_from_development_pushes_only() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text()
    start = workflow.index("\n  coverage:\n")
    coverage = workflow[start : workflow.index("\n  database-integration:\n", start)]
    step_start = coverage.index("- name: Publish the coverage badge")
    step = coverage[step_start : coverage.index("- name:", step_start + 1)]

    assert "      contents: write\n" in coverage
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/development'" in step
    assert 'python tools/coverage_badge.py coverage.json "$badge_dir/coverage.json"' in step
    assert "git push -q --force" in step
    assert step.rstrip().endswith("badges")
