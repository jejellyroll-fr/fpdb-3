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
