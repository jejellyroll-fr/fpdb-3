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


def test_async_is_the_default_outside_a_test_run(monkeypatch) -> None:
    """The DbWorker threads must actually be used in production.

    ``async_mode`` was decided by ``"unittest" not in sys.modules``, and
    ``fpdb_3_legacy.interlocks`` -- imported by fpdb.pyw at startup -- imported
    ``doctest``, which imports ``unittest``. Every real session therefore looked
    like a test run and ran all four Ring Player Stats queries, plus every model
    it builds from them, on the GUI thread.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setitem(controller.sys.modules, "unittest", controller.sys)
    monkeypatch.delitem(controller.sys.modules, "pytest", raising=False)

    assert controller.running_under_test() is False


def test_pytest_still_forces_the_synchronous_path(monkeypatch) -> None:
    monkeypatch.setitem(controller.sys.modules, "pytest", controller.sys)

    assert controller.running_under_test() is True


def test_the_current_test_env_var_is_enough_on_its_own(monkeypatch) -> None:
    monkeypatch.delitem(controller.sys.modules, "pytest", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_x (call)")

    assert controller.running_under_test() is True


def test_importing_interlocks_does_not_look_like_a_test_run() -> None:
    """The specific import chain that produced the bug, pinned at the source.

    Asserting on sys.modules cannot work here -- pytest has already imported
    unittest by the time this runs -- so the check is that the module the GUI
    imports at startup no longer drags doctest in at import time.
    """
    import ast
    import pathlib

    source = pathlib.Path(controller.__file__).parent.parent / "interlocks.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    module_level = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    imported = {alias.name.split(".")[0] for node in module_level if isinstance(node, ast.Import) for alias in node.names}

    assert "doctest" not in imported
    assert "unittest" not in imported


class StaleSender:
    """Stands in for the DbWorker whose result is being delivered."""

    def __init__(self, generation: int) -> None:
        self.generation = generation


class GuardHost:
    """The real guard, on a host reduced to the two things it reads.

    Borrowing the function rather than instantiating a RingStatsController
    keeps the test off QObject construction while still exercising the
    shipped implementation.
    """

    is_current_result = controller.RingStatsController.is_current_result

    def __init__(self, current: int, sender_generation: int | None) -> None:
        self._generation = current
        self._sender = None if sender_generation is None else StaleSender(sender_generation)

    def sender(self) -> StaleSender | None:
        return self._sender


def test_a_result_from_the_current_refresh_is_kept() -> None:
    assert GuardHost(current=4, sender_generation=4).is_current_result() is True


def test_a_result_from_a_superseded_refresh_is_discarded() -> None:
    """The race disconnecting signals cannot close.

    ``shutdown_workers`` only reaches workers that are still running, so a query
    that finished before the user changed the filters still has its callback
    queued for the GUI thread -- and it is delivered after the new refresh has
    begun.
    """
    assert GuardHost(current=5, sender_generation=4).is_current_result() is False


def test_a_direct_call_with_no_sender_is_treated_as_current() -> None:
    """Tests call the callbacks themselves; that must not read as stale."""
    assert GuardHost(current=5, sender_generation=None).is_current_result() is True


def test_every_result_callback_asks_before_it_acts() -> None:
    """A guard on three of the four callbacks is a guard on none of them."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(controller.RingStatsController))
    callbacks = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_on_") and node.name.endswith("_finished")
    }

    assert set(callbacks) == {
        "_on_summary_query_finished",
        "_on_profit_query_finished",
        "_on_hands_query_finished",
        "_on_positions_query_finished",
    }
    for name, node in callbacks.items():
        guards = [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "is_current_result"
        ]
        assert guards, f"{name} does not check whether its result is still wanted"
