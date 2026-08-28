"""The last uncovered corners of the Fast-Fold support modules.

Small paths, all of them reached only when something is unusual: an
executable that cannot be resolved, a registry asked about a table it does not
hold, a pool re-recording the game it already knows. They are the ones a
Windows or Linux port is most likely to walk into first, because "unusual" on
macOS is often ordinary elsewhere.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import hud_diagnostics
from fpdb_3_legacy.hud_window_registry import HudWindowRegistry
from fpdb_3_legacy.ui_instrumentation import (
    SLOW_TAB_OPEN_MS,
    UI_STALL_BUDGET_MS,
    TabOpenProfiler,
    UiStallMonitor,
)
from fpdb_3_legacy.winamax_pool_games import WinamaxPoolGames

# ---------------------------------------------------------------------------
# Launch identity
# ---------------------------------------------------------------------------


def test_an_executable_path_that_cannot_be_resolved_is_reported_as_given(monkeypatch) -> None:
    """A deleted or unreadable interpreter must not stop the banner.

    Resolving walks symlinks, which touches the filesystem: a translocated
    mount going away underneath a running app is exactly when this fails, and
    that is the case the banner exists to report.
    """
    monkeypatch.setattr(
        hud_diagnostics.Path,
        "resolve",
        lambda self, *a, **k: (_ for _ in ()).throw(OSError("stale NFS handle")),
    )

    assert hud_diagnostics.executable_path() == str(sys.executable)


def test_a_build_without_package_metadata_reports_an_unknown_version(monkeypatch) -> None:
    """The banner is worth writing even when the version cannot be read."""
    monkeypatch.setitem(sys.modules, "fpdb_3_legacy", None)

    assert hud_diagnostics.app_version() == "unknown"


# ---------------------------------------------------------------------------
# The window registry
# ---------------------------------------------------------------------------


def test_the_generation_counter_is_readable_without_advancing_it() -> None:
    """Diagnostics read it; reading must not hand out a number."""
    registry = HudWindowRegistry()
    assert registry.generation == 0

    registry.claim(61825, "Bucarest 3 #61825")

    assert registry.generation == 1
    assert registry.generation == 1


def test_a_window_nobody_holds_has_no_key() -> None:
    registry = HudWindowRegistry()

    assert registry.lookup(61825) is None
    assert registry.key_for(61825) is None


def test_a_window_id_of_none_is_never_held() -> None:
    """An untracked table must not collide with another untracked one."""
    registry = HudWindowRegistry()
    registry.claim(None, "Some Cash Table")

    assert registry.lookup(None) is None
    assert registry.key_for(None) is None


def test_releasing_a_key_the_registry_never_held_is_harmless() -> None:
    """Teardown runs for tables that were refused a renderer."""
    registry = HudWindowRegistry()
    registry.claim(61825, "Bucarest 3 #61825")

    assert registry.release("Never Existed") is None
    assert registry.key_for(61825) == "Bucarest 3 #61825"


def test_a_key_the_registry_never_held_is_not_current() -> None:
    assert HudWindowRegistry().is_current("Never Existed", 1) is False


# ---------------------------------------------------------------------------
# UI instrumentation
# ---------------------------------------------------------------------------


def test_a_tab_timing_is_reported_as_one_line(caplog) -> None:
    """A slow tab is reported by users whose logs are not running at DEBUG."""
    log = logging.getLogger("test_ui_instrumentation_report")
    profiler = TabOpenProfiler("Session Stats")
    with profiler.phase("construct"):
        pass
    # Only a slow open is a WARNING now, and this test asserts one. Backdating
    # the start is what makes it slow: sleeping for a second to prove a log
    # line's format would be a second added to every run of the suite.
    profiler._started -= SLOW_TAB_OPEN_MS / 1000 + 0.1

    with caplog.at_level(logging.WARNING, logger=log.name):
        timing = profiler.report(log)

    message = " ".join(record.getMessage() for record in caplog.records)
    assert "tab open:" in message
    assert "tab='Session Stats'" in message
    assert "construct=" in message
    assert timing.name == "Session Stats"


def test_a_stall_report_names_what_was_being_done(caplog) -> None:
    """A stall figure with no context cannot be acted on."""
    log = logging.getLogger("test_ui_instrumentation_stalls")
    monitor = UiStallMonitor()
    monitor._stalls.extend([10.0, UI_STALL_BUDGET_MS + 50])
    monitor.ticks = 2

    with caplog.at_level(logging.WARNING, logger=log.name):
        worst = monitor.report(log, "opening three tabs")

    message = " ".join(record.getMessage() for record in caplog.records)
    assert "opening three tabs" in message
    assert "max_stall=150ms" in message
    assert worst == UI_STALL_BUDGET_MS + 50


def test_stalls_are_reported_in_the_order_they_happened() -> None:
    """Which phase was slow is only recoverable from the order."""
    monitor = UiStallMonitor()
    monitor._stalls.extend([1.0, 200.0, 2.0])

    assert monitor.stalls == (1.0, 200.0, 2.0)
    assert monitor.max_stall_ms == 200.0


def test_a_monitor_that_never_ran_reports_no_stall() -> None:
    """An empty measurement must read as zero, not raise."""
    monitor = UiStallMonitor()

    assert monitor.max_stall_ms == 0.0
    assert monitor.stalls == ()
    assert monitor.stalls_over() == ()


def test_the_first_tick_is_never_counted_as_a_stall() -> None:
    """Nothing to measure against before the first tick sets a baseline."""
    monitor = UiStallMonitor()
    monitor._expected = None

    monitor._on_tick()

    assert monitor.ticks == 1
    assert monitor.stalls == ()
    assert monitor._expected is not None


def test_a_tick_that_arrives_early_is_not_a_negative_stall() -> None:
    """Timer jitter runs both ways; a negative would flatter the worst case."""
    import time

    monitor = UiStallMonitor()
    monitor._expected = time.perf_counter() + 10

    monitor._on_tick()

    assert monitor.stalls == (0.0,)


# ---------------------------------------------------------------------------
# Remembered pool games
# ---------------------------------------------------------------------------


@pytest.fixture
def pool_games(tmp_path):
    """A store on its own file, never the user's."""
    return WinamaxPoolGames(tmp_path / "pool_games.json")


def test_re_recording_the_same_game_writes_nothing(pool_games) -> None:
    """A pool is proved on every imported hand; rewriting each time is churn."""
    pool_games.remember("Bucarest 3", "omahahi")
    save = MagicMock()
    pool_games._save = save

    pool_games.remember("Bucarest 3", "omahahi")

    save.assert_not_called()
    assert pool_games.get("Bucarest 3") == "omahahi"


def test_a_pool_that_changes_game_is_re_recorded(pool_games) -> None:
    pool_games.remember("Bucarest 3", "omahahi")

    pool_games.remember("Bucarest 3", "holdem")

    assert pool_games.get("Bucarest 3") == "holdem"


@pytest.mark.parametrize(("table", "game"), [("", "omahahi"), ("Bucarest 3", ""), ("", "")])
def test_half_an_answer_is_not_recorded(pool_games, table, game) -> None:
    """A pool remembered without its game would build the wrong HUD profile."""
    pool_games.remember(table, game)

    assert pool_games.get(table or "Bucarest 3") is None
