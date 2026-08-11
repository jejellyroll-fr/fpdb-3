"""Default-path discovery must be tied to an active import workflow.

``Configuration.get_default_paths()`` can recover stale room paths by probing
platform-specific fallback locations. That is useful once an import workflow is
requested, but calling it from ``fpdb.load_profile()`` also did those probes at
application startup and on routine profile refreshes.

The tests inspect/exercise just the relevant methods from ``fpdb.pyw`` so they
do not construct the heavy Qt main window.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _fpdb_method(name: str) -> ast.FunctionDef:
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    return next(node for node in fpdb_class.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls_get_default_paths(method: ast.FunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get_default_paths"
        for node in ast.walk(method)
    )


def _load_method(name: str, namespace: dict[str, Any]) -> Any:
    module = ast.Module(body=[_fpdb_method(name)], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE), "exec"), namespace)  # noqa: S102  # nosec B102 - executes repository source under test
    return namespace[name]


def test_profile_loading_never_resolves_import_default_paths() -> None:
    """Startup/profile refresh stays passive even when saved paths are stale."""
    assert not _calls_get_default_paths(_fpdb_method("load_profile"))


def test_bulk_import_resolves_default_paths_only_when_opened() -> None:
    """Opening Bulk Import retains its detected/custom initial directory."""
    widget = object()
    constructor = MagicMock(return_value=widget)
    tab_bulk_import = _load_method(
        "tab_bulk_import",
        {"GuiBulkImport": SimpleNamespace(GuiBulkImport=constructor)},
    )

    settings = {"global_lock": object(), "db-host": "localhost"}
    config = MagicMock()
    config.get_default_paths.return_value = {
        "bulkImport-defaultPath": "/Users/player/Documents/Poker/Hands",
        "hud-defaultPath": "/Users/player/Documents/Poker/Hands",
    }
    window = SimpleNamespace(
        settings=settings,
        config=config,
        sql=object(),
        threads=[],
        add_and_display_tab=MagicMock(),
    )

    tab_bulk_import(window, None)

    config.get_default_paths.assert_called_once_with()
    assert settings["bulkImport-defaultPath"] == "/Users/player/Documents/Poker/Hands"
    constructor.assert_called_once_with(settings, config, window.sql, window)
    assert window.threads == [widget]
    window.add_and_display_tab.assert_called_once_with(widget, "Bulk Import")


def test_opening_auto_import_does_not_trigger_global_default_detection() -> None:
    """Auto Import performs enabled-site resolution later, after Start."""
    widget = SimpleNamespace(startButton=object())
    constructor = MagicMock(return_value=widget)
    tab_auto_import = _load_method(
        "tab_auto_import",
        {
            "GuiAutoImport": SimpleNamespace(GuiAutoImport=constructor),
            "options": SimpleNamespace(autoimport=False),
        },
    )

    settings = {"global_lock": object(), "db-host": "localhost"}
    config = MagicMock()
    config.get_default_paths.side_effect = AssertionError("opening the tab must remain passive")
    window = SimpleNamespace(
        settings=settings,
        config=config,
        sql=object(),
        threads=[],
        add_and_display_tab=MagicMock(),
    )

    tab_auto_import(window, None)

    config.get_default_paths.assert_not_called()
    constructor.assert_called_once_with(settings, config, window.sql, window)
    assert window.threads == [widget]
