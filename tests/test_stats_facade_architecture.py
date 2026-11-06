"""Architectural guardrails for the legacy Stats compatibility facade."""

from __future__ import annotations

import inspect

from fpdb_3_legacy import Stats


def test_stats_facade_defines_only_orchestration_functions() -> None:
    """Business stat implementations must stay in their domain modules."""
    locally_defined = {
        name
        for name, value in vars(Stats).items()
        if inspect.isfunction(value) and value.__module__ == Stats.__name__
    }
    assert locally_defined == {"_descriptor_stat", "do_stat", "get_valid_stats", "main"}


def test_registered_stats_come_from_domain_modules() -> None:
    """Every legacy registered stat must be re-exported by the facade."""
    compatibility_sentinels = set()
    for name in Stats.STATLIST:
        stat = getattr(Stats, name)
        if callable(stat):
            assert stat.__module__ != Stats.__name__, name
        else:
            compatibility_sentinels.add(name)
    assert compatibility_sentinels == {"STATS_DATA_ERRORS", "STAT_FUNCTIONS", "annotations"}
