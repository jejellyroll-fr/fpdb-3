"""Tests for the live-path latency profile (#680).

The profile exists to report the tail (p50/p95/p99/max), not averages, so these
tests pin the percentile math, the counters, the JSON report and the fact that
everything is inert when the flag is off.
"""

from __future__ import annotations

import json

import pytest

from fpdb_3_legacy import latency_profile
from fpdb_3_legacy.latency_profile import LatencyProfile


def test_percentiles_use_linear_interpolation() -> None:
    profile = LatencyProfile()
    for seconds in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0):
        profile.record("m", seconds)
    stats = profile.metric_stats("m")
    assert stats["count"] == 10
    assert stats["p50"] == 5.5
    assert stats["p95"] == pytest.approx(9.55)
    assert stats["p99"] == pytest.approx(9.91)
    assert stats["max"] == 10.0
    assert stats["mean"] == 5.5


def test_single_sample_is_every_percentile() -> None:
    profile = LatencyProfile()
    profile.record("m", 0.25)
    stats = profile.metric_stats("m")
    assert stats["p50"] == stats["p95"] == stats["p99"] == stats["max"] == 0.25


def test_counters_are_separate_from_duration_samples() -> None:
    profile = LatencyProfile()
    profile.count("hud_session_rows", 40)
    profile.count("hud_session_rows", 2)
    profile.record("hud_batch_total", 0.5)
    rows = profile.metric_stats("hud_session_rows")
    assert rows["count"] == 0
    assert rows["counter"] == 42
    batch = profile.metric_stats("hud_batch_total")
    assert batch["count"] == 1
    assert batch["counter"] == 0


def test_scope_records_wall_time() -> None:
    profile = LatencyProfile()
    with profile.scope("block"):
        sum(range(100_000))
    stats = profile.metric_stats("block")
    assert stats["count"] == 1
    assert stats["max"] > 0


def test_snapshot_is_json_serialisable_and_covers_all_metrics() -> None:
    profile = LatencyProfile()
    profile.record("a", 0.1)
    profile.count("b", 3)
    payload = profile.snapshot()
    json.dumps(payload)
    assert set(payload["metrics"]) == {"a", "b"}


def test_report_names_metrics_and_counters() -> None:
    profile = LatencyProfile()
    profile.record("hud_batch_total", 0.01)
    profile.count("hudcache_insert", 7)
    text = profile.report()
    assert "hud_batch_total" in text
    assert "hudcache_insert=7" in text
    assert "p99" in text


def test_empty_report_says_nothing_was_recorded() -> None:
    assert LatencyProfile().report() == "Latency profile: nothing recorded."


def test_reservoir_sampling_keeps_the_cap(monkeypatch) -> None:
    monkeypatch.setattr(latency_profile, "MAX_EXACT_SAMPLES", 10)
    profile = LatencyProfile()
    for i in range(1000):
        profile.record("m", float(i))
    stats = profile.metric_stats("m")
    assert stats["count"] == 10
    # The kept samples are all real observations.
    assert 0.0 <= stats["min"] if "min" in stats else True
    assert stats["max"] < 1000.0


def test_module_level_helpers_are_noops_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(latency_profile, "_ENABLED", False)
    latency_profile.record("m", 1.0)
    latency_profile.count("c", 5)
    with latency_profile.scope("s"):
        pass
    assert latency_profile.get_profile().snapshot()["metrics"] == {}


def test_module_level_helpers_record_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(latency_profile, "_ENABLED", True)
    profile = latency_profile.get_profile()
    profile.reset()
    latency_profile.record("m", 0.5)
    latency_profile.count("c", 2)
    metrics = profile.snapshot()["metrics"]
    assert metrics["m"]["count"] == 1
    assert metrics["c"]["counter"] == 2
    profile.reset()


def test_write_report_uses_env_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(latency_profile, "_ENABLED", True)
    target = tmp_path / "latency.json"
    monkeypatch.setenv(latency_profile.REPORT_PATH_ENV, str(target))
    profile = latency_profile.get_profile()
    profile.reset()
    profile.record("hud_queue_wait", 0.75)
    written = latency_profile.write_report()
    assert written == str(target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["metrics"]["hud_queue_wait"]["max"] == 0.75
    profile.reset()
