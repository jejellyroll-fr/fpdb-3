from __future__ import annotations

from fpdb_3_legacy.ring_stats import controller


def test_debug_log_uses_configured_logger(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(controller.log, "debug", messages.append)

    controller.debug_log("positions refreshed")

    assert messages == ["positions refreshed"]


def test_dashboard_kpis_preserve_single_result_currency() -> None:
    result = [
        (10, 125.0, 20.0, 15.0, 5.0, 2.0, "USD"),
        (30, -25.0, 40.0, 25.0, 10.0, 4.0, "USD"),
    ]
    colnames = ["n", "net", "vpip", "pfr", "pf3", "aggfac", "currency"]

    stats = controller.RingStatsController._calculate_dashboard_kpis(object(), result, colnames)

    assert stats["hands"] == 40
    assert stats["net"] == 100.0
    assert stats["currency"] == "USD"
