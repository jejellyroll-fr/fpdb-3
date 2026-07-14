from __future__ import annotations

from fpdb_3_legacy.ring_stats import controller


def test_debug_log_uses_configured_logger(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(controller.log, "debug", messages.append)

    controller.debug_log("positions refreshed")

    assert messages == ["positions refreshed"]
