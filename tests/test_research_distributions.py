"""Semantics of the chart-ready Research distribution models (#362)."""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.research_distributions import build_distribution


def result(metric: str, rows: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        compiled=SimpleNamespace(metric=metric),
        rows=[SimpleNamespace(**row) for row in rows],
    )


def row(group: dict, opportunities: int, *, actions: int = 0, frequency_bp: int | None = None) -> dict:
    return {
        "group": group,
        "opportunities": opportunities,
        "actions": actions,
        "value": actions,
        "unit": "bp" if frequency_bp is not None else "count",
        "frequency_bp": frequency_bp,
        "as_dict": lambda: {
            **group,
            "opportunities": opportunities,
            "actions": actions,
            "value": actions,
            "unit": "bp" if frequency_bp is not None else "count",
            "frequency_bp": frequency_bp,
        },
    }


def test_sizing_keeps_configured_empty_buckets_and_calculates_shares() -> None:
    data = result(
        "opportunities",
        [
            row({"sizing_bucket": "0-25"}, 2),
            row({"sizing_bucket": "50-66"}, 1),
        ],
    )

    series = build_distribution(data, "sizing_bucket")

    assert len(series.bins) == 11  # ten configured buckets + unknown
    assert series.total_opportunities == 3
    assert series.bins[0].label == "0-25"
    assert series.bins[0].opportunities == 2
    assert series.bins[0].share_bp == 6666
    assert series.bins[1].label == "25-33"
    assert series.bins[1].is_empty
    assert series.bins[1].percentage == 0
    assert series.bins[4].opportunities == 1
    assert series.bins[0].filter_name == "sizing_bucket"


def test_response_order_is_poker_order_and_share_is_not_a_rate() -> None:
    data = result(
        "opportunities",
        [
            row({"response": "raise"}, 1),
            row({"response": "fold"}, 3),
            row({"response": "call"}, 2),
        ],
    )

    series = build_distribution(data, "response")

    assert [item.label for item in series.bins] == ["fold", "call", "raise"]
    assert [item.percentage for item in series.bins] == [50.0, 33.33, 16.66]
    assert series.chart_unit == "share of decisions"


def test_frequency_distribution_plots_response_rate_and_keeps_denominator() -> None:
    data = result(
        "fold_frequency",
        [row({"facing_sizing_bucket": "50-66"}, 20, actions=7, frequency_bp=3500)],
    )

    series = build_distribution(data, "facing_sizing_bucket")

    bucket = next(item for item in series.bins if item.label == "50-66")
    assert bucket.opportunities == 20
    assert bucket.frequency_bp == 3500
    assert bucket.percentage == 35.0
    assert series.chart_unit == "response rate"


def test_low_sample_warning_is_explicit_and_empty_results_are_safe() -> None:
    low = build_distribution(
        result("opportunities", [row({"response": "fold"}, 4)]),
        "response",
        min_sample=10,
    )
    empty = build_distribution(result("opportunities", []), "sizing_bucket", min_sample=10)

    assert low.low_sample_warning == "Low sample: 4 decisions (recommended minimum 10)"
    assert not low.sample_sufficient
    assert empty.total_opportunities == 0
    assert len(empty.bins) == 11
    assert all(item.opportunities == 0 for item in empty.bins)
