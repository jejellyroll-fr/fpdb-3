"""Import completion invalidates Hand Viewer tabs and refreshes on activation."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace
from unittest.mock import MagicMock

SOURCE = Path(__file__).resolve().parents[1] / "fpdb_3_legacy" / "fpdb.pyw"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _method(name: str) -> FunctionType:
    fpdb_class = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "fpdb")
    node = next(node for node in fpdb_class.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    code = compile(module, str(SOURCE), "exec")
    function_code = next(item for item in code.co_consts if isinstance(item, CodeType) and item.co_name == name)
    function = FunctionType(function_code, {"log": logging.getLogger("test-import-refresh")}, name)
    function.__kwdefaults__ = {
        arg.arg: ast.literal_eval(default)
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True)
        if default is not None
    }
    return function


def test_completed_import_marks_all_hand_viewers_stale_and_refreshes_visible_one() -> None:
    visible = SimpleNamespace(filters=None, mark_stale=MagicMock(), refresh_if_stale=MagicMock())
    hidden = SimpleNamespace(filters=None, mark_stale=MagicMock(), refresh_if_stale=MagicMock())
    window = SimpleNamespace(threads=[visible, hidden], nb=SimpleNamespace(currentWidget=lambda: visible))

    _method("refresh_after_import")(window)

    visible.mark_stale.assert_called_once_with()
    visible.refresh_if_stale.assert_called_once_with()
    hidden.mark_stale.assert_called_once_with()
    hidden.refresh_if_stale.assert_not_called()


def test_import_without_stored_hands_does_not_invalidate_hand_viewers() -> None:
    viewer = SimpleNamespace(filters=None, mark_stale=MagicMock(), refresh_if_stale=MagicMock())
    window = SimpleNamespace(threads=[viewer], nb=SimpleNamespace(currentWidget=lambda: viewer))

    _method("refresh_after_import")(window, data_changed=False)

    viewer.mark_stale.assert_not_called()
    viewer.refresh_if_stale.assert_not_called()


def test_activating_a_tab_retries_its_stale_refresh() -> None:
    viewer = SimpleNamespace(refresh_if_stale=MagicMock())
    window = SimpleNamespace(nb=SimpleNamespace(widget=lambda _index: viewer))

    _method("_tab_activated")(window, 2)

    viewer.refresh_if_stale.assert_called_once_with()
